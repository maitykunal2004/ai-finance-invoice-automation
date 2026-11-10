"""
Document intake layer: turns messy invoice text into the structured CSV that
pipeline.py consumes.

Input is raw text as you would get from an OCR pass over a PDF or a scanned
invoice, which in practice means: currency symbols in inconsistent places,
Indian and international date formats, thousands separators, GST rates written
on the same line as the tax amount, missing purchase orders, and the occasional
document that OCR simply destroyed.

Two extraction modes:
  default  deterministic parser (regex + normalisation). No network, no keys,
           fully reproducible, and its accuracy is measured by tests.
  --llm    optional adapter that sends the text to an OpenAI-compatible
           endpoint when OPENAI_API_KEY is set, and falls back to the
           deterministic parser for any document the model fails to return
           valid JSON for. Silence is never treated as success.

Usage:
    python3 intake.py --inbox samples/inbox --out invoices_intake.csv
    python3 intake.py --inbox samples/inbox --out x.csv --llm

Output columns match invoices_raw.csv exactly, so pipeline.py runs unchanged.
"""

import argparse
import csv
import json
import os
import re
import urllib.request
from decimal import Decimal, InvalidOperation

OUT_FIELDS = [
    "invoice_id",
    "vendor_name",
    "invoice_date",
    "po_number",
    "invoice_total",
    "tax_amount",
    "status",
]

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# A number that can be read as money: optional currency marker, thousands
# separators, up to two decimals. The rate rules in amounts_on_line() stop us
# reading a tax *rate* as a tax *amount*.
AMOUNT_RE = re.compile(
    r"(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

DOC_ID_RE = re.compile(r"\b([A-Z]{2,}[A-Z0-9]*(?:[-/][A-Z0-9]+){1,4})\b")
PO_RE = re.compile(r"\b(PO[-/]?[A-Z]{0,3}\d{3,})\b", re.IGNORECASE)


def to_amount(raw):
    """'Rs. 15,000.00' -> Decimal('15000.00'). Returns None on failure."""
    if raw is None:
        return None
    cleaned = re.sub(r"(?i)(rs\.?|inr|₹)", "", str(raw))
    cleaned = cleaned.replace(",", "").replace("%", "").strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def amounts_on_line(line):
    """Every money-looking number on a line, in order, with rate tokens dropped.

    A token is a rate, not an amount, when it is followed by '%' or preceded by
    '@'. That is what keeps 'GST @5%   625.00' reading as 625.00, not 5.
    """
    found = []
    for match in AMOUNT_RE.finditer(line):
        before = line[: match.start(1)].rstrip()
        after = line[match.end(1):].lstrip()
        if after.startswith("%"):
            continue
        if before.endswith("@"):
            continue
        amount = to_amount(match.group(1))
        if amount is not None:
            found.append(amount)
    return found


def label_line(text, patterns):
    """Return the first line matching any label pattern, or an empty string."""
    for pattern in patterns:
        for line in text.splitlines():
            if re.search(pattern, line, re.IGNORECASE):
                return line
    return ""


def normalise_date(raw):
    """Accept 01-11-2026, 01/11/2026, 2026-11-01, 1 Nov 2026, Nov 1 2026."""
    if not raw:
        return ""
    text = raw.strip()

    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if len(year) == 2:
            year = "20" + year
        return f"{year}-{month:02d}-{day:02d}"

    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$", text)
    if m:
        month = MONTHS.get(m.group(2)[:3].lower())
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"

    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", text)
    if m:
        month = MONTHS.get(m.group(1)[:3].lower())
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"

    return ""


def date_from_text(text):
    """Find a date anywhere on a labelled line, not only at the start."""
    line = label_line(text, [r"invoice\s*date", r"date\s*of\s*invoice", r"\bdated?\b"])
    if not line:
        return ""
    tokens = re.findall(
        r"\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}"
        r"|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
        r"|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}",
        line,
    )
    for token in tokens:
        parsed = normalise_date(token)
        if parsed:
            return parsed
    return ""


def extract_deterministic(text):
    """Field-by-field extraction: permissive about OCR noise, strict about output."""
    vendor = ""
    line = label_line(text, [r"vendor(?:\s*name)?\s*[:\-]", r"billed?\s*(?:by|from)\s*[:\-]", r"supplier\s*[:\-]"])
    if line:
        vendor = re.split(r"[:\-]", line, maxsplit=1)[-1].strip()
    if not vendor:
        for candidate in text.splitlines():
            stripped = candidate.strip()
            if stripped and not re.search(r"invoice|tax|gst", stripped, re.IGNORECASE):
                vendor = stripped
                break

    invoice_id = ""
    line = label_line(
        text,
        [r"invoice\s*(?:no\.?|number|#)", r"\binv\s*(?:no\.?|#)", r"tax\s*invoice\s*(?:no\.?|number)"],
    )
    if line:
        match = DOC_ID_RE.search(line)
        if match:
            invoice_id = match.group(1)
    if not invoice_id:
        match = DOC_ID_RE.search(text)
        if match:
            invoice_id = match.group(1)

    po_number = ""
    line = label_line(text, [r"\bp\.?\s*o\.?\s*(?:no\.?|number|#|box)", r"purchase\s*order"])
    if line:
        match = PO_RE.search(line)
        if match:
            po_number = match.group(1).upper()
    if not po_number:
        match = PO_RE.search(text)
        if match:
            po_number = match.group(1).upper()

    invoice_date = date_from_text(text)

    total = None
    line = label_line(
        text,
        [r"invoice\s*total", r"total\s*amount\s*(?:due)?", r"grand\s*total", r"amount\s*due", r"^total\b"],
    )
    if line:
        candidates = amounts_on_line(line)
        if candidates:
            total = candidates[-1]

    tax = None
    line = label_line(text, [r"\bgst\b", r"\btax\b", r"\bvat\b"])
    if line:
        candidates = amounts_on_line(line)
        if candidates:
            tax = candidates[-1]

    if total is None:
        # last resort: the largest number in the document is the invoice total
        all_amounts = [amount for ln in text.splitlines() for amount in amounts_on_line(ln)]
        if all_amounts:
            total = max(all_amounts)

    if tax is not None and total is not None and tax > total:
        tax = None

    return {
        "invoice_id": invoice_id,
        "vendor_name": vendor.strip(),
        "invoice_date": invoice_date,
        "po_number": po_number,
        "invoice_total": f"{total:.2f}" if total is not None else "",
        "tax_amount": f"{tax:.2f}" if tax is not None else "",
        "status": "PENDING",
    }


def extract_with_llm(text, model="gpt-4o-mini"):
    """Optional adapter. Returns None when unavailable or invalid, so the caller
    falls back to the deterministic parser instead of trusting a bad answer."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    prompt = (
        "Extract invoice fields as JSON with keys invoice_id, vendor_name, "
        "invoice_date (YYYY-MM-DD), po_number, invoice_total, tax_amount. "
        "Use empty strings for anything absent. Return JSON only.\n\n" + text
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read())
        parsed = json.loads(body["choices"][0]["message"]["content"].strip())
    except Exception:
        return None

    if not {"invoice_id", "vendor_name", "invoice_date", "invoice_total"}.issubset(parsed):
        return None
    total = to_amount(parsed.get("invoice_total")) or Decimal("0")
    tax = to_amount(parsed.get("tax_amount")) or Decimal("0")
    return {
        "invoice_id": str(parsed.get("invoice_id", "")).strip(),
        "vendor_name": str(parsed.get("vendor_name", "")).strip(),
        "invoice_date": normalise_date(str(parsed.get("invoice_date", ""))),
        "po_number": str(parsed.get("po_number", "")).strip(),
        "invoice_total": f"{total:.2f}",
        "tax_amount": f"{tax:.2f}",
        "status": "PENDING",
    }


def is_usable(record):
    """A record enters the pipeline only if the fields the controls depend on exist."""
    return bool(record["invoice_id"]) and bool(record["vendor_name"]) and bool(record["invoice_total"])


def main():
    parser = argparse.ArgumentParser(description="Invoice document intake")
    parser.add_argument("--inbox", default="samples/inbox", help="folder of raw invoice text files")
    parser.add_argument("--out", default="invoices_intake.csv", help="structured output CSV")
    parser.add_argument("--llm", action="store_true", help="try the LLM adapter first, fall back per document")
    args = parser.parse_args()

    paths = sorted(
        os.path.join(args.inbox, name)
        for name in os.listdir(args.inbox)
        if name.lower().endswith((".txt", ".md"))
    )

    records, rejected, llm_used, fallback_used = [], [], 0, 0

    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()

        record = extract_with_llm(text) if args.llm else None
        if record is not None:
            llm_used += 1
        else:
            if args.llm:
                fallback_used += 1
            record = extract_deterministic(text)

        if is_usable(record):
            records.append(record)
        else:
            rejected.append(os.path.basename(path))

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    print(f"Documents read: {len(paths)}")
    print(f"Structured records: {len(records)}")
    print(f"Routed to manual review (unparseable): {len(rejected)}")
    if rejected:
        print("  " + ", ".join(rejected))
    if args.llm:
        print(f"LLM extracted: {llm_used}, fell back to deterministic: {fallback_used}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

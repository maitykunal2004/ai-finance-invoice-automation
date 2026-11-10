"""
AP Invoice Exception & Reconciliation Pipeline
------------------------------------------------
Validates a raw AP invoice batch against financial controls and routes
exceptions to a structured review queue.

Controls implemented:
  C1  Tax rate mismatch      : tax_amount must equal invoice_total * TAX_RATE (+/- tolerance)
  C2  Duplicate invoice      : same vendor + same amount + same PO appears more than once
  C3  Missing PO reference   : non-PO invoices flagged for manual PO attachment
  C4  Negative / zero value  : invoice_total must be > 0

Dependencies: Python 3.8+ standard library only. No installs required.

Usage:
    python3 pipeline.py
    python3 pipeline.py --input invoices_raw.csv --outdir .

Outputs:
    invoices_processed.csv   - every input row with a reconciliation status
    exceptions_flagged.csv   - one row per exception, with reason and action
    run_summary.txt          - control-level counts for audit trail
"""

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

TAX_RATE = Decimal("0.05")      # standard 5% GST assumption for this dataset
TAX_TOLERANCE = Decimal("1.00")  # rupees of acceptable rounding difference


def to_decimal(value):
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        return None


def validate_batch(rows):
    """Apply controls C1-C4 and return (processed_rows, exceptions, control_counts)."""
    exceptions = []
    control_counts = defaultdict(int)

    # Pre-compute duplicate keys across the whole batch (C2)
    key_counts = defaultdict(int)
    for row in rows:
        key = (
            row["vendor_name"].strip().lower(),
            row["invoice_total"].strip(),
            row["po_number"].strip().upper(),
        )
        key_counts[key] += 1

    seen_keys = defaultdict(int)

    for index, row in enumerate(rows, start=1):
        total = to_decimal(row["invoice_total"])
        tax = to_decimal(row["tax_amount"])
        key = (
            row["vendor_name"].strip().lower(),
            row["invoice_total"].strip(),
            row["po_number"].strip().upper(),
        )
        seen_keys[key] += 1

        reasons = []

        # C4 - invalid or non-positive amount
        if total is None or total <= 0:
            reasons.append(("INVALID_AMOUNT", "0.00", "Correct invoice amount before posting"))

        # C3 - missing PO reference
        if not row["po_number"].strip():
            reasons.append(("MISSING_PO_REFERENCE", "0.00", "Attach approved PO or log as non-PO exception"))

        # C2 - duplicate invoice (second and later occurrences)
        if key_counts[key] > 1 and seen_keys[key] > 1:
            reasons.append(("DUPLICATE_INVOICE", "0.00", "Confirm no prior payment in ERP ledger"))

        # C1 - tax rate mismatch
        if total is not None and total > 0 and tax is not None:
            expected_tax = (total * TAX_RATE).quantize(Decimal("0.01"))
            variance = (tax - expected_tax).quantize(Decimal("0.01"))
            if abs(variance) > TAX_TOLERANCE:
                reasons.append(
                    (
                        "TAX_MISMATCH",
                        f"{variance:+.2f}",
                        f"Expected tax {expected_tax}, received {tax}; verify rate with vendor",
                    )
                )

        if reasons:
            for seq, (discrepancy, variance, action) in enumerate(reasons, start=1):
                exceptions.append(
                    {
                        "exception_id": f"EXC-{index:04d}-{seq}",
                        "invoice_id": row["invoice_id"],
                        "vendor_name": row["vendor_name"],
                        "discrepancy_type": discrepancy,
                        "detected_variance": variance,
                        "action_required": action,
                        "detected_on": datetime.now().strftime("%Y-%m-%d"),
                    }
                )
                control_counts[discrepancy] += 1
            # Status shows the highest-priority control that fired.
            row["status"] = "EXCEPTION_" + reasons[0][0]
        else:
            control_counts["MATCHED"] += 1
            row["status"] = "MATCHED"

    return rows, exceptions, control_counts


def main():
    parser = argparse.ArgumentParser(description="AP invoice exception and reconciliation pipeline")
    parser.add_argument("--input", default="invoices_raw.csv", help="raw invoice batch CSV")
    parser.add_argument("--outdir", default=".", help="output directory")
    args = parser.parse_args()

    with open(args.input, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(r) for r in reader]
        fieldnames = reader.fieldnames

    print(f"Loaded {len(rows)} invoice records from {args.input}")

    processed, exceptions, counts = validate_batch(rows)

    os.makedirs(args.outdir, exist_ok=True)
    processed_path = os.path.join(args.outdir, "invoices_processed.csv")
    with open(processed_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed)

    exception_fields = [
        "exception_id",
        "invoice_id",
        "vendor_name",
        "discrepancy_type",
        "detected_variance",
        "action_required",
        "detected_on",
    ]
    exceptions_path = os.path.join(args.outdir, "exceptions_flagged.csv")
    with open(exceptions_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=exception_fields)
        writer.writeheader()
        writer.writerows(exceptions)

    summary_path = os.path.join(args.outdir, "run_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("AP Invoice Pipeline - Run Summary\n")
        handle.write(f"Rows processed: {len(processed)}\n")
        handle.write(f"Exceptions raised: {len(exceptions)}\n")
        for control in sorted(counts):
            handle.write(f"  {control}: {counts[control]}\n")

    print(f"Exceptions raised: {len(exceptions)}")
    for control in sorted(counts):
        print(f"  {control}: {counts[control]}")
    print(f"Wrote {processed_path}, {exceptions_path}, {summary_path}")


if __name__ == "__main__":
    main()

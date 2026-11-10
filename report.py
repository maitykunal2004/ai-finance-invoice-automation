"""
Exception reporting: builds a self-contained HTML dashboard from the pipeline
output, so the numbers a finance reviewer cares about are visible without a
BI licence.

Shows: batch size and value, exception rate, exceptions by control, value at
risk, and the vendors generating the most exceptions.

Usage:
    python3 report.py --processed invoices_processed.csv \
                      --exceptions exceptions_flagged.csv \
                      --out docs/dashboard.html
"""

import argparse
import csv
import html
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build(processed, exceptions, title="AP Invoice Control Dashboard"):
    invoices = len(processed)
    batch_value = sum((money(r.get("invoice_total")) for r in processed), Decimal("0"))
    exception_invoices = {e["invoice_id"] for e in exceptions}
    rate = (len(exception_invoices) / invoices * 100) if invoices else 0.0

    by_control = Counter(e["discrepancy_type"] for e in exceptions)
    exposure = defaultdict(Decimal)
    vendors = Counter()
    for exception in exceptions:
        exposure[exception["discrepancy_type"]] += abs(money(exception.get("detected_variance")))
        vendors[exception["vendor_name"]] += 1

    total_exposure = sum(exposure.values(), Decimal("0"))
    max_control = max(by_control.values()) if by_control else 1
    max_vendor = max(vendors.values()) if vendors else 1

    control_rows = "".join(
        f"<tr><td>{html.escape(name.replace('_', ' ').title())}</td>"
        f"<td class='num'>{count:,}</td>"
        f"<td><div class='bar'><span style='width:{count / max_control * 100:.1f}%'></span></div></td>"
        f"<td class='num'>{exposure[name]:,.2f}</td></tr>"
        for name, count in by_control.most_common()
    )

    vendor_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td class='num'>{count:,}</td>"
        f"<td><div class='bar alt'><span style='width:{count / max_vendor * 100:.1f}%'></span></div></td></tr>"
        for name, count in vendors.most_common(6)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{ --ink:#111827; --muted:#6b7280; --line:#e5e7eb; --accent:#1d4ed8; --warn:#b45309; --bg:#ffffff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; }}
  h1 {{ font-size:20px; margin:0 0 4px; letter-spacing:-0.01em; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:24px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
  .kpi {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .kpi .label {{ font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted); }}
  .kpi .value {{ font-size:26px; font-weight:650; margin-top:6px; letter-spacing:-0.02em; }}
  .kpi .value.warn {{ color:var(--warn); }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:0.06em; color:var(--muted);
        margin:26px 0 10px; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; font-weight:600; color:var(--muted); font-size:11px;
        text-transform:uppercase; letter-spacing:0.05em; padding:6px 8px; border-bottom:1px solid var(--line); }}
  td {{ padding:9px 8px; border-bottom:1px solid var(--line); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; width:110px; }}
  .bar {{ background:#f3f4f6; border-radius:4px; height:8px; overflow:hidden; min-width:80px; }}
  .bar span {{ display:block; height:100%; background:var(--accent); }}
  .bar.alt span {{ background:#9ca3af; }}
  footer {{ margin-top:26px; color:var(--muted); font-size:11px; border-top:1px solid var(--line); padding-top:12px; }}
</style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="sub">Synthetic AP batch, generated and processed by this repository. Reproduce with
    <code>generate_batch.py</code> then <code>pipeline.py</code>.</div>

  <div class="kpis">
    <div class="kpi"><div class="label">Invoices in batch</div><div class="value">{invoices:,}</div></div>
    <div class="kpi"><div class="label">Batch value</div><div class="value">&#8377;{batch_value:,.0f}</div></div>
    <div class="kpi"><div class="label">Exceptions raised</div><div class="value">{len(exceptions):,}</div></div>
    <div class="kpi"><div class="label">Invoice exception rate</div>
      <div class="value warn">{rate:.1f}%</div></div>
  </div>

  <div class="kpis" style="grid-template-columns:repeat(2,1fr)">
    <div class="kpi"><div class="label">Value under exception (abs variance)</div>
      <div class="value">&#8377;{total_exposure:,.2f}</div></div>
    <div class="kpi"><div class="label">Clean invoices straight through</div>
      <div class="value">{invoices - len(exception_invoices):,}</div></div>
  </div>

  <h2>Exceptions by control</h2>
  <table>
    <thead><tr><th>Control</th><th class="num">Count</th><th>Distribution</th><th class="num">Abs variance</th></tr></thead>
    <tbody>{control_rows}</tbody>
  </table>

  <h2>Vendors generating the most exceptions</h2>
  <table>
    <thead><tr><th>Vendor</th><th class="num">Exceptions</th><th>Share</th></tr></thead>
    <tbody>{vendor_rows}</tbody>
  </table>

  <footer>Generated by report.py. Amounts in INR. No employer or client data is used.</footer>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Build the exception dashboard")
    parser.add_argument("--processed", default="invoices_processed.csv")
    parser.add_argument("--exceptions", default="exceptions_flagged.csv")
    parser.add_argument("--out", default="docs/dashboard.html")
    args = parser.parse_args()

    page = build(read_csv(args.processed), read_csv(args.exceptions))
    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(page)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

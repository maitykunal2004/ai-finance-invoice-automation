"""
Seeded synthetic AP batch generator, for scale testing.

Produces a batch where the defect rate is known in advance (default 6%), so the
pipeline's recall can be checked against ground truth instead of eyeballed.

Usage:
    python3 generate_batch.py --rows 50000 --out invoices_50k.csv
    python3 generate_batch.py --rows 50000 --out /tmp/big.csv --defect-rate 0.06 --seed 7
"""

import argparse
import csv
import random
from datetime import date, timedelta
from decimal import Decimal

VENDORS = [
    "Acme Supplies Corp", "Global Logistics Ltd", "Apex Office Tech",
    "Vertex Solutions", "Swift Freight", "NCR Atleos Facilities",
    "Metro Landlord Services", "Pinnacle IT Hardware", "Bluepeak Consulting",
    "Orion Stationery Mart", "Northgate Facility Care", "Sterling Print Works",
    "Cobalt Security Systems", "Everline Couriers", "Summit Electricals",
]

FIELDS = [
    "invoice_id", "vendor_name", "invoice_date", "po_number",
    "invoice_total", "tax_amount", "status", "expected_defect",
]


def generate(rows, defect_rate, seed, tax_rate=Decimal("0.05")):
    random.seed(seed)
    start = date(2026, 1, 1)
    out = []

    for index in range(1, rows + 1):
        vendor = random.choice(VENDORS)
        # Floor of 500 keeps the 18%-vs-5% tax gap well outside the INR 1
        # rounding tolerance, so the batch exercises the control rather than
        # the tolerance.
        base = Decimal(random.randrange(50000, 2500000)) / Decimal("100")
        expected_tax = (base * tax_rate).quantize(Decimal("0.01"))
        po_number = f"PO-{random.randrange(100000, 999999)}"
        invoice_date = (start + timedelta(days=random.randrange(0, 320))).isoformat()

        roll = random.random()
        defect = "NONE"

        if roll < defect_rate:
            kind = random.choice(["TAX_MISMATCH", "DUPLICATE_INVOICE", "MISSING_PO_REFERENCE", "INVALID_AMOUNT"])

            if kind == "TAX_MISMATCH":
                # 18% GST applied instead of 5%: a real, common mis-key
                tax = (base * Decimal("0.18")).quantize(Decimal("0.01"))
                defect = "TAX_MISMATCH"
            elif kind == "DUPLICATE_INVOICE":
                tax = expected_tax
                defect = "DUPLICATE_INVOICE"
            elif kind == "MISSING_PO_REFERENCE":
                tax = expected_tax
                po_number = ""
                defect = "MISSING_PO_REFERENCE"
            else:
                tax = Decimal("0.00")
                base = Decimal("0.00")
                defect = "INVALID_AMOUNT"
        else:
            tax = expected_tax

        out.append(
            {
                "invoice_id": f"INV-2026-{index:06d}",
                "vendor_name": vendor,
                "invoice_date": invoice_date,
                "po_number": po_number,
                "invoice_total": f"{base:.2f}",
                "tax_amount": f"{tax:.2f}",
                "status": "PENDING",
                "expected_defect": defect,
            }
        )

        # A duplicate is a copy of an earlier row under a new id, which is how
        # a re-submission actually arrives. Ground truth marks only the
        # re-submission: the first occurrence is legitimately payable, so
        # flagging it would be a false positive, not a catch.
        if defect == "DUPLICATE_INVOICE" and len(out) > 1:
            source = out[-1]
            source["expected_defect"] = "NONE"
            clone = dict(source)
            clone["invoice_id"] = f"INV-2026-{index:06d}D"
            clone["expected_defect"] = "DUPLICATE_INVOICE"
            out.append(clone)

    return out


def main():
    parser = argparse.ArgumentParser(description="Generate a seeded synthetic AP batch")
    parser.add_argument("--rows", type=int, default=50000)
    parser.add_argument("--out", default="invoices_50k.csv")
    parser.add_argument("--defect-rate", type=float, default=0.06)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = generate(args.rows, args.defect_rate, args.seed)
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    planted = sum(1 for r in rows if r["expected_defect"] != "NONE")
    print(f"Rows written: {len(rows)}")
    print(f"Planted defects (ground truth): {planted}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

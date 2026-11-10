"""
Intake tests. Each sample invoice is asserted field by field, so the parser's
accuracy is a measured number rather than an impression.
"""

import os
import unittest

from intake import extract_deterministic, is_usable

INBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "inbox")

EXPECTED = {
    "01_acme.txt": {
        "invoice_id": "INV-2026-2001",
        "vendor_name": "ACME SUPPLIES CORP",
        "invoice_date": "2026-11-03",
        "po_number": "PO-88491",
        "invoice_total": "13125.00",
        "tax_amount": "625.00",
    },
    "02_global_logistics.txt": {
        "invoice_id": "GL-2026-4471",
        "vendor_name": "Global Logistics Ltd",
        "invoice_date": "2026-11-04",
        "po_number": "PO-88492",
        "invoice_total": "8820.53",
        "tax_amount": "420.03",
    },
    "03_apex_taxslip.txt": {
        "invoice_id": "APX/2026/0771",
        "vendor_name": "APEX OFFICE TECH",
        "invoice_date": "2026-11-05",
        "po_number": "PO-88493",
        "invoice_total": "15900.00",
        "tax_amount": "900.00",
    },
    "04_ncr_nonpo.txt": {
        "invoice_id": "NA-778812",
        "vendor_name": "NCR Atleos Facilities",
        "invoice_date": "2026-11-06",
        "po_number": "",
        "invoice_total": "9885.00",
        "tax_amount": "490.00",
    },
    "05_vertex.txt": {
        "invoice_id": "VS-2026-0198",
        "vendor_name": "Vertex Solutions",
        "invoice_date": "2026-11-07",
        "po_number": "PO-88494",
        "invoice_total": "3360.00",
        "tax_amount": "160.00",
    },
    "06_swift_dupe.txt": {
        "invoice_id": "INV-2026-1005",
        "vendor_name": "SWIFT FREIGHT",
        "invoice_date": "2026-11-08",
        "po_number": "PO-88495",
        "invoice_total": "7875.00",
        "tax_amount": "375.00",
    },
    "07_metro_landlord.txt": {
        "invoice_id": "MLS-2026-881",
        "vendor_name": "METRO LANDLORD SERVICES",
        "invoice_date": "2026-11-09",
        "po_number": "PO-88501",
        "invoice_total": "0.00",
        "tax_amount": "0.00",
    },
}


def read(name):
    with open(os.path.join(INBOX, name), encoding="utf-8") as handle:
        return handle.read()


class TestIntakeAccuracy(unittest.TestCase):
    def test_every_parseable_document_matches_expected_fields(self):
        for name, expected in EXPECTED.items():
            with self.subTest(document=name):
                record = extract_deterministic(read(name))
                for field, value in expected.items():
                    self.assertEqual(record[field], value, f"{name} field {field}")

    def test_destroyed_scan_is_rejected_not_guessed(self):
        record = extract_deterministic(read("08_scanned_unreadable.txt"))
        self.assertFalse(is_usable(record))

    def test_parsed_document_count(self):
        parsed = 0
        for name in sorted(os.listdir(INBOX)):
            if name.endswith(".txt"):
                if is_usable(extract_deterministic(read(name))):
                    parsed += 1
        self.assertEqual(parsed, 7)

    def test_gst_rate_is_not_read_as_tax_amount(self):
        # 'GST @5%   625.00' must yield 625.00, never 5.00
        record = extract_deterministic(read("01_acme.txt"))
        self.assertEqual(record["tax_amount"], "625.00")

    def test_missing_po_is_left_blank_rather_than_invented(self):
        record = extract_deterministic(read("04_ncr_nonpo.txt"))
        self.assertEqual(record["po_number"], "")


if __name__ == "__main__":
    unittest.main()

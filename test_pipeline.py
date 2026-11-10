"""
Unit tests for the AP invoice exception pipeline.
Run with: python3 -m unittest discover -s . -p "test_*.py" -v
"""

import unittest

from pipeline import validate_batch


def row(**kwargs):
    base = {
        "invoice_id": "INV-1",
        "vendor_name": "Vendor A",
        "invoice_date": "2026-11-01",
        "po_number": "PO-1",
        "invoice_total": "1000.00",
        "tax_amount": "50.00",
        "status": "PENDING",
    }
    base.update(kwargs)
    return base


class TestControls(unittest.TestCase):
    def test_clean_invoice_matches(self):
        rows, exceptions, counts = validate_batch([row()])
        self.assertEqual(exceptions, [])
        self.assertEqual(rows[0]["status"], "MATCHED")

    def test_tax_mismatch_flagged_with_variance(self):
        rows, exceptions, _ = validate_batch([row(tax_amount="90.00")])
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["discrepancy_type"], "TAX_MISMATCH")
        self.assertEqual(exceptions[0]["detected_variance"], "+40.00")
        self.assertEqual(rows[0]["status"], "EXCEPTION_TAX_MISMATCH")

    def test_tax_within_tolerance_is_not_an_exception(self):
        rows, exceptions, _ = validate_batch([row(tax_amount="50.50")])
        self.assertEqual(exceptions, [])

    def test_duplicate_flags_second_occurrence_only(self):
        rows, exceptions, _ = validate_batch([row(), row(invoice_id="INV-2")])
        self.assertEqual(len(exceptions), 1)
        self.assertEqual(exceptions[0]["invoice_id"], "INV-2")
        self.assertEqual(exceptions[0]["discrepancy_type"], "DUPLICATE_INVOICE")
        self.assertEqual(rows[0]["status"], "MATCHED")

    def test_same_vendor_different_amount_is_not_duplicate(self):
        _, exceptions, _ = validate_batch(
            [row(), row(invoice_id="INV-2", invoice_total="2000.00", tax_amount="100.00")]
        )
        self.assertEqual(exceptions, [])

    def test_missing_po_reference_flagged(self):
        _, exceptions, _ = validate_batch([row(po_number="")])
        self.assertEqual(exceptions[0]["discrepancy_type"], "MISSING_PO_REFERENCE")

    def test_zero_value_invoice_flagged(self):
        _, exceptions, _ = validate_batch([row(invoice_total="0.00", tax_amount="0.00")])
        self.assertEqual(exceptions[0]["discrepancy_type"], "INVALID_AMOUNT")

    def test_counting_matched_and_exceptions(self):
        rows, exceptions, counts = validate_batch(
            [row(), row(invoice_id="INV-2", tax_amount="90.00")]
        )
        self.assertEqual(counts["MATCHED"], 1)
        self.assertEqual(counts["TAX_MISMATCH"], 1)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()

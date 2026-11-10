-- PostgreSQL schema and reconciliation queries for the AP invoice exception pipeline.
-- Mirrors the controls implemented in pipeline.py so the same logic can run in-database.

CREATE TABLE vendors (
    vendor_id      SERIAL PRIMARY KEY,
    vendor_name    VARCHAR(255) NOT NULL UNIQUE,
    payment_terms  VARCHAR(50)
);

CREATE TABLE purchase_orders (
    po_number      VARCHAR(50) PRIMARY KEY,
    vendor_id      INT REFERENCES vendors(vendor_id),
    po_total       NUMERIC(12, 2) NOT NULL CHECK (po_total > 0),
    approved_date  TIMESTAMP
);

CREATE TABLE invoices (
    invoice_id     VARCHAR(50) PRIMARY KEY,
    vendor_name    VARCHAR(255) NOT NULL,
    invoice_date   DATE NOT NULL,
    po_number      VARCHAR(50) REFERENCES purchase_orders(po_number),
    invoice_total  NUMERIC(12, 2) NOT NULL,
    tax_amount     NUMERIC(12, 2) NOT NULL,
    status         VARCHAR(50) NOT NULL DEFAULT 'PENDING'
);

CREATE TABLE exception_queue (
    exception_id       VARCHAR(50) PRIMARY KEY,
    invoice_id         VARCHAR(50) NOT NULL REFERENCES invoices(invoice_id),
    vendor_name        VARCHAR(255) NOT NULL,
    discrepancy_type   VARCHAR(50) NOT NULL,
    detected_variance  NUMERIC(12, 2) NOT NULL DEFAULT 0,
    action_required    TEXT NOT NULL,
    detected_on        DATE NOT NULL DEFAULT CURRENT_DATE,
    resolved           BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by        VARCHAR(255),
    resolved_on        TIMESTAMP
);

CREATE INDEX idx_exception_open ON exception_queue (discrepancy_type) WHERE NOT resolved;

-- ---------------------------------------------------------------------------
-- Control validation: one row per control failure, so an invoice with several
-- defects appears several times rather than being flattened to a first match.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_invoice_control_failures AS
WITH duplicate_keys AS (
    SELECT vendor_name, invoice_total, po_number, COUNT(*) AS occurrences
    FROM invoices
    GROUP BY vendor_name, invoice_total, po_number
)
SELECT
    i.invoice_id,
    i.vendor_name,
    'TAX_MISMATCH' AS discrepancy_type,
    ROUND(i.tax_amount - ROUND(i.invoice_total * 0.05, 2), 2) AS detected_variance
FROM invoices i
WHERE i.invoice_total > 0
  AND ABS(i.tax_amount - ROUND(i.invoice_total * 0.05, 2)) > 1.00

UNION ALL

SELECT
    i.invoice_id,
    i.vendor_name,
    'MISSING_PO_REFERENCE',
    0.00
FROM invoices i
WHERE i.po_number IS NULL OR BTRIM(i.po_number) = ''

UNION ALL

SELECT
    i.invoice_id,
    i.vendor_name,
    'DUPLICATE_INVOICE',
    0.00
FROM invoices i
JOIN duplicate_keys d
  ON i.vendor_name = d.vendor_name
 AND i.invoice_total = d.invoice_total
 AND i.po_number IS NOT DISTINCT FROM d.po_number
WHERE d.occurrences > 1
  AND i.invoice_id <> (
      SELECT MIN(i2.invoice_id) FROM invoices i2
      WHERE i2.vendor_name = d.vendor_name
        AND i2.invoice_total = d.invoice_total
        AND i2.po_number IS NOT DISTINCT FROM d.po_number
  )

UNION ALL

SELECT
    i.invoice_id,
    i.vendor_name,
    'INVALID_AMOUNT',
    0.00
FROM invoices i
WHERE i.invoice_total IS NULL OR i.invoice_total <= 0;

-- ---------------------------------------------------------------------------
-- Three-way match: invoice against purchase order, with a payment-derived
-- settled flag. Unmatched or partially matched rows are the review workload.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_three_way_match AS
SELECT
    i.invoice_id,
    i.vendor_name,
    i.invoice_total,
    i.tax_amount,
    po.po_total,
    COALESCE(po.po_total - i.invoice_total, 0) AS po_variance,
    CASE
        WHEN i.po_number IS NULL           THEN 'NO_PO'
        WHEN po.po_number IS NULL          THEN 'PO_NOT_FOUND'
        WHEN i.invoice_total = po.po_total THEN 'MATCHED'
        WHEN i.invoice_total < po.po_total THEN 'PARTIAL'
        ELSE 'OVER_INVOICED'
    END AS match_status
FROM invoices i
LEFT JOIN purchase_orders po ON i.po_number = po.po_number;

-- Exception rate by control, for the finance dashboard.
CREATE OR REPLACE VIEW v_exception_summary AS
SELECT
    discrepancy_type,
    COUNT(*)                                   AS exceptions,
    COUNT(*) FILTER (WHERE NOT resolved)       AS open_exceptions,
    ROUND(AVG(ABS(detected_variance)), 2)      AS avg_abs_variance
FROM exception_queue
GROUP BY discrepancy_type
ORDER BY exceptions DESC;

-- PostgreSQL Schema & 3-Way Matching Reconciliation Queries for AP Automation

CREATE TABLE vendors (
    vendor_id SERIAL PRIMARY KEY,
    vendor_name VARCHAR(255) NOT NULL,
    payment_terms VARCHAR(50)
);

CREATE TABLE purchase_orders (
    po_number VARCHAR(50) PRIMARY KEY,
    vendor_id INT REFERENCES vendors(vendor_id),
    po_total DECIMAL(12, 2) NOT NULL,
    approved_date TIMESTAMP
);

CREATE TABLE invoices (
    invoice_id VARCHAR(50) PRIMARY KEY,
    vendor_name VARCHAR(255) NOT NULL,
    invoice_date DATE NOT NULL,
    po_number VARCHAR(50),
    invoice_total DECIMAL(12, 2) NOT NULL,
    tax_amount DECIMAL(12, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING'
);

CREATE TABLE exception_queue (
    exception_id VARCHAR(50) PRIMARY KEY,
    invoice_id VARCHAR(50) REFERENCES invoices(invoice_id),
    vendor_name VARCHAR(255) NOT NULL,
    discrepancy_type VARCHAR(100),
    detected_variance DECIMAL(12, 2),
    action_required TEXT,
    resolved BOOLEAN DEFAULT FALSE
);

-- 3-Way Matching & Exception Query
SELECT 
    i.invoice_id,
    i.vendor_name,
    i.invoice_total,
    i.tax_amount,
    po.po_total,
    CASE 
        WHEN i.invoice_total = po.po_total AND i.tax_amount = (i.invoice_total * 0.05) THEN 'MATCHED'
        WHEN i.tax_amount != (i.invoice_total * 0.05) THEN 'EXCEPTION_TAX_MISMATCH'
        ELSE 'EXCEPTION_VARIANCE'
    END AS reconciliation_status
FROM invoices i
LEFT JOIN purchase_orders po ON i.po_number = po.po_number;

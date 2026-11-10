# AP Invoice Exception & Reconciliation Pipeline

A deterministic financial-controls pipeline for Accounts Payable batches. It ingests a raw
invoice batch, applies four validation controls, and routes exceptions to a structured review
queue with an audit trail.

Built to replace the manual exception-spotting step in a high-volume AP operation: the kind of
work where a 5% tax-rate slip or a re-submitted vendor invoice is caught only because someone
happens to notice it.

**Runs with zero dependencies.** Python 3.8+ standard library only, no `pip install`.

## Quick start

```bash
git clone https://github.com/maitykunal2004/ai-finance-invoice-automation.git
cd ai-finance-invoice-automation
python3 pipeline.py
```

Console output:

```
Loaded 12 invoice records from invoices_raw.csv
Exceptions raised: 5
  DUPLICATE_INVOICE: 1
  INVALID_AMOUNT: 1
  MATCHED: 7
  MISSING_PO_REFERENCE: 1
  TAX_MISMATCH: 2
```

Run the tests:

```bash
python3 -m unittest discover -s . -p "test_*.py" -v
```

## Controls implemented

| ID | Control | Rule | Route |
|----|---------|------|-------|
| C1 | Tax mismatch | `tax_amount` must equal `invoice_total x 5%` within a ₹1 rounding tolerance | `EXCEPTION_TAX_MISMATCH` |
| C2 | Duplicate invoice | Same vendor + same amount + same PO appearing more than once; the first occurrence passes, later ones are flagged | `EXCEPTION_DUPLICATE_INVOICE` |
| C3 | Missing PO reference | Non-PO invoices are held for PO attachment instead of being silently posted | `EXCEPTION_MISSING_PO_REFERENCE` |
| C4 | Invalid amount | `invoice_total` must be greater than zero and parseable | `EXCEPTION_INVALID_AMOUNT` |

When several controls fire on one invoice, every reason is written to the exception log and the
status column shows the highest-priority one, so a single row can never hide a second problem.

## Files

| File | Purpose |
|------|---------|
| `pipeline.py` | The pipeline: controls C1-C4, exception routing, audit summary |
| `test_pipeline.py` | 8 unit tests covering each control and the multi-reason case |
| `invoices_raw.csv` | 12-row synthetic AP batch used as demo input |
| `invoices_processed.csv` | Generated: every input row with a reconciliation status |
| `exceptions_flagged.csv` | Generated: one row per exception, with variance and required action |
| `run_summary.txt` | Generated: row counts and exceptions by control, for audit |
| `schema.sql` | PostgreSQL schema (`vendors`, `purchase_orders`, `invoices`, `exception_queue`) plus the 3-way matching query |

The two `*.csv` outputs and `run_summary.txt` in this repo are the actual committed output of
`python3 pipeline.py` against the 12-row input, not hand-written samples. Re-running reproduces
them.

## Sample exception output

```csv
exception_id,invoice_id,vendor_name,discrepancy_type,detected_variance,action_required
EXC-0003-1,INV-2026-1003,Apex Office Tech,TAX_MISMATCH,+150.00,"Expected tax 750.00, received 900.00; verify rate with vendor"
EXC-0006-1,INV-2026-1006,Acme Supplies Corp,DUPLICATE_INVOICE,0.00,Confirm no prior payment in ERP ledger
EXC-0007-1,INV-2026-1007,NCR Atleos Facilities,MISSING_PO_REFERENCE,0.00,Attach approved PO or log as non-PO exception
```

## Design notes

- **Money uses `Decimal`, not `float`.** Rounding errors in tax comparison are the difference
  between a clean batch and a false exception queue.
- **Duplicates are detected batch-wide, not row-by-row.** A duplicate only exists relative to
  the whole batch, so the key is counted up front and then matched off occurrence by occurrence.
- **Tolerance is explicit.** ₹1 of rounding difference is not a control failure; a ₹150 variance is.
- **The exception log is additive.** One invoice can produce several exception rows rather than
  being flattened to a single first-match reason.

## Scope and what this is not

This repository is deliberately narrow. To be explicit about the boundary between built and planned:

**Built and tested here**
- Deterministic controls C1-C4 over a CSV batch
- Exception queue with variance and required action per row
- Audit summary by control
- PostgreSQL schema and 3-way matching query for loading the same logic into a database

**Not in this repository yet**
- OCR / LLM document extraction from PDF and image invoices. Input is a structured CSV.
  Document intake is the natural next layer, and the pipeline is shaped to sit behind it.
- Live database execution. `schema.sql` is schema and query only; no migration runner or ORM.
- Power BI report. The dataset is report-ready, but no `.pbix` is published here.
- n8n or Make orchestration. The pipeline runs as a CLI; scheduling is not wired up.

Anything not listed under "Built and tested here" should be read as roadmap, not as a shipped feature.

## Data

`invoices_raw.csv` is synthetic. Vendor names, amounts and PO numbers are fabricated for
demonstration; no client or employer data is used.

## Next steps

1. Add a document-intake layer (OCR plus schema-constrained LLM extraction) that emits the same
   CSV, so unstructured invoices feed the controls unchanged.
2. Persist results to PostgreSQL and expose a read-only exception queue view for reviewers.
3. Publish a Power BI report over `invoices_processed.csv` and `exceptions_flagged.csv`: cycle
   time, exception rate by control, and vendor-level variance trends.

## License

MIT. See `LICENSE`.

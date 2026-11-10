# AI-Powered Financial Operations & Invoice Exception Automation Toolkit

An end-to-end Accounts Payable (AP) analytics and automation pipeline designed to process incoming PDF/image invoices, extract structured financial data using LLMs, validate against PO and vendor records, flag tax/pricing mismatches, and route exceptions to structured queues.

## 🛠️ Tech Stack & Architecture
- **Data Ingestion & Processing:** Python (Pandas, Pydantic), OCR / LLM Schema Extraction
- **Financial Validation & Controls:** 3-Way Matching (Invoice vs. PO vs. Payment Ledger), Automated Exception Routing
- **Analytics & BI Reporting:** SQL / PostgreSQL, Power BI Dashboards & Dynamic Excel Models
- **Workflow Orchestration:** n8n / Make.com Automated Pipelines

## 📊 Core Workflow
1. **Invoice Intake:** Unstructured PDF invoices ingested via automated email/folder triggers.
2. **AI Extraction:** LLM parser extracts structured fields (Vendor Name, Invoice #, Date, Line Items, Tax, Total) into strict JSON schemas.
3. **Financial Gate & Validation:** Deterministic rules check for duplicate invoices, PO pricing variances, and tax mismatches.
4. **Exception Queue:** Clean records proceed to Ledger / ERP, while exceptions are flagged with detailed audit reasons for human review.

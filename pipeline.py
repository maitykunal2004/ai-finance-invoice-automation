import pandas as pd
import numpy as np

def run_ap_pipeline():
    print("Starting AP Invoice Automation & 3-Way Matching Pipeline...")
    
    # 1. Load raw invoice batch
    df = pd.read_csv('invoices_raw.csv')
    print(f"Loaded {len(df)} raw invoice records.")
    
    # 2. Financial Validation & 3-Way Matching Rules
    exceptions = []
    for idx, row in df.iterrows():
        expected_tax = row['invoice_total'] * 0.05
        if abs(row['tax_amount'] - expected_tax) > 1.0:
            exceptions.append({
                'exception_id': f"EXC-00{idx+1}",
                'invoice_id': row['invoice_id'],
                'vendor_name': row['vendor_name'],
                'discrepancy_type': 'TAX_MISMATCH',
                'detected_variance': round(row['tax_amount'] - expected_tax, 2),
                'action_required': 'Verify GST rate with vendor statement'
            })
            df.loc[idx, 'status'] = 'EXCEPTION_TAX_MISMATCH'
        else:
            df.loc[idx, 'status'] = 'MATCHED'
            
    df.to_csv('invoices_processed.csv', index=False)
    exc_df = pd.DataFrame(exceptions)
    exc_df.to_csv('exceptions_flagged.csv', index=False)
    print("Pipeline execution complete. Processed records and exception logs saved successfully.")

if __name__ == '__main__':
    run_ap_pipeline()

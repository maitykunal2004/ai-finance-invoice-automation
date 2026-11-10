"""
Scale and accuracy benchmark.

Generates a batch of a known size with a known defect rate, runs the control
engine over it, measures wall time, and compares what the controls caught
against the planted ground truth. The point is to replace "it should scale"
with a number and a recall figure that can be re-checked.

Usage:
    python3 benchmark.py --rows 50000
    python3 benchmark.py --rows 50000 --write-report docs/scale_test.txt
"""

import argparse
import os
import time
from collections import defaultdict

from generate_batch import generate
from pipeline import validate_batch

CONTROLS = {"TAX_MISMATCH", "DUPLICATE_INVOICE", "MISSING_PO_REFERENCE", "INVALID_AMOUNT"}


def run(rows, seed=42, defect_rate=0.06):
    records = generate(rows, defect_rate, seed)

    started = time.perf_counter()
    processed, exceptions, counts = validate_batch(records)
    elapsed = time.perf_counter() - started

    planted = defaultdict(set)
    for record in records:
        if record["expected_defect"] != "NONE":
            planted[record["expected_defect"]].add(record["invoice_id"])

    caught = defaultdict(set)
    for exception in exceptions:
        caught[exception["discrepancy_type"]].add(exception["invoice_id"])

    lines = []
    lines.append("AP invoice pipeline - scale and accuracy test")
    lines.append(f"Rows in batch: {len(records):,}")
    lines.append(f"Runtime: {elapsed:.2f} s  ({len(records) / elapsed:,.0f} rows/s)")
    lines.append("")

    total_planted = sum(len(v) for v in planted.values())
    total_caught = 0
    lines.append(f"{'Control':<24}{'Planted':>9}{'Caught':>9}{'Recall':>9}")
    for control in sorted(CONTROLS):
        expected = planted.get(control, set())
        actual = caught.get(control, set())
        total_caught += len(expected & actual)
        recall = (len(expected & actual) / len(expected) * 100) if expected else 0.0
        lines.append(f"{control:<24}{len(expected):>9,}{len(expected & actual):>9,}{recall:>8.1f}%")

    overall_recall = (total_caught / total_planted * 100) if total_planted else 0.0
    exceptions_raised = len(exceptions)
    precision = (total_caught / exceptions_raised * 100) if exceptions_raised else 0.0

    lines.append("")
    lines.append(f"Planted defects: {total_planted:,}")
    lines.append(f"Exceptions raised: {exceptions_raised:,}")
    lines.append(f"Recall on planted defects: {overall_recall:.1f}%")
    lines.append(f"Precision (raised exceptions that were planted): {precision:.1f}%")
    lines.append(f"Clean invoices passed through: {counts.get('MATCHED', 0):,}")
    lines.append("")
    lines.append("Reproduce with: python3 benchmark.py --rows 50000")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Scale benchmark for the AP pipeline")
    parser.add_argument("--rows", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--defect-rate", type=float, default=0.06)
    parser.add_argument("--write-report", default=None)
    args = parser.parse_args()

    report = run(args.rows, args.seed, args.defect_rate)
    print(report)

    if args.write_report:
        os.makedirs(os.path.dirname(args.write_report) or ".", exist_ok=True)
        with open(args.write_report, "w", encoding="utf-8") as handle:
            handle.write(report + "\n")
        print(f"\nWrote {args.write_report}")


if __name__ == "__main__":
    main()

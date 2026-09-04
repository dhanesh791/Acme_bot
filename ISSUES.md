# Problems encountered

This file is a running record of problems found while building the project. Keep entries here after they are fixed so the project retains its debugging history.

## 2026-09-04 — Filtered Excel query rejected by the reranker

- **Problem:** Filtering to `sales_q1.xlsx` and asking “What is South revenue?” returned no answer even though the indexed chunk contained the fact.
- **Cause:** The cross-encoder emits unbounded relevance logits. The relevant chunk scored `-2.41`, while the initial `MIN_RERANK_SCORE=0.0` configuration rejected all negative scores.
- **Resolution:** Calibrated the threshold to `-6.0` and added `test_default_stack_filtered_excel_query_returns_evidence`.

## How to add an entry

For every problem found, add its date, observed behavior, cause (when known), and resolution or current status.

# Evaluation evidence

The automated regression suite verifies the following acceptance cases against `sample_data/`:

| Case | Expected evidence | Verification |
| --- | --- | --- |
| Multi-format parsing | CSV: 3 rows; Excel: 3 data rows; PPTX: 2 slides; DOCX: 5 records (1 title paragraph, 1 section, 3 table rows) | `test_sample_formats_parse_with_traceable_metadata` |
| Cross-document Q1 question | `sales_q1.xlsx -> Regional Sales -> row 2-4`, `q1_business_review.pptx -> Slide 1/2`, and `q1_summary_memo.docx -> Regional Highlights - Table 1 -> row 3` | `test_end_to_end_multi_document_and_no_answer_acceptance` |
| No-answer behavior | Vacation-policy question is refused for insufficient evidence | Same acceptance test |
| Citation fidelity | Citations are generated solely from persisted source metadata | parser, retrieval, and filtered-retrieval tests |
| Grounded local answer | Returned extractive answer includes facts from returned evidence | `test_extractive_answer_is_grounded_in_returned_evidence` |
| Word structure-awareness | Heading-delimited sections and tables are extracted as separate, correctly cited records | `test_word_document_extracts_sections_and_tables_with_citations`, `test_word_table_rows_batch_into_row_range_chunks` |
| Word section filtering | Retrieval can be scoped to one Word section via metadata filter | `test_metadata_filters_limit_retrieval_to_selected_word_section` |

## Manual review record

Reviewed against the generated Acme source files:

- `sales_q1.xlsx`, **Regional Sales**, row 3: South revenue is `4,200,000`, target is `4,000,000`, attainment is `105%`.
- `q1_business_review.pptx`, **Slide 2: Regional Performance**: South delivered `$4.2M` against a `$4.0M` target.
- `customer_sales.csv`, row 2: South Enterprise retention is `94%`.
- `q1_summary_memo.docx`, **Regional Highlights - Table 1**, row 3: South revenue is `4200000`, target is `4000000`, attainment is `105%` — a fourth, independently-formatted source corroborating the same South Q1 figures.

These locations match the citation format rendered by the application. Hosted-LLM faithfulness must be re-evaluated after changing prompts or models; the local fallback remains extractive by design.

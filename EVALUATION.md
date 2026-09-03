# Evaluation evidence

The automated regression suite verifies the following acceptance cases against `sample_data/`:

| Case | Expected evidence | Verification |
| --- | --- | --- |
| Multi-format parsing | CSV: 3 rows; Excel: 3 data rows; PPTX: 2 slides | `test_sample_formats_parse_with_traceable_metadata` |
| Cross-document Q1 question | `sales_q1.xlsx -> Regional Sales -> row 2-4` and `q1_business_review.pptx -> Slide 1/2` | `test_end_to_end_multi_document_and_no_answer_acceptance` |
| No-answer behavior | Vacation-policy question is refused for insufficient evidence | Same acceptance test |
| Citation fidelity | Citations are generated solely from persisted source metadata | parser, retrieval, and filtered-retrieval tests |
| Grounded local answer | Returned extractive answer includes facts from returned evidence | `test_extractive_answer_is_grounded_in_returned_evidence` |

## Manual review record

Reviewed against the generated Acme source files:

- `sales_q1.xlsx`, **Regional Sales**, row 3: South revenue is `4,200,000`, target is `4,000,000`, attainment is `105%`.
- `q1_business_review.pptx`, **Slide 2: Regional Performance**: South delivered `$4.2M` against a `$4.0M` target.
- `customer_sales.csv`, row 2: South Enterprise retention is `94%`.

These locations match the citation format rendered by the application. Hosted-LLM faithfulness must be re-evaluated after changing prompts or models; the local fallback remains extractive by design.

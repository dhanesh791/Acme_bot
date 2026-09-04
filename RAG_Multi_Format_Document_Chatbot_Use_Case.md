Interview Use Case: Multi-Format RAG Document Chatbot

Build, demonstrate, and explain an end-to-end Retrieval-Augmented Generation (RAG) pipeline

1. Problem Statement

Organizations store business knowledge across Excel workbooks, CSV files, PowerPoint presentations, and other documents. Users often need to ask questions across these sources without manually opening and searching each file. The candidate must build a working RAG-based chatbot that ingests Excel, CSV, and PPT/PPTX files, indexes their content, retrieves relevant information, and generates grounded answers.

2. Objective

Build a small but production-oriented prototype that can:

- Accept multiple Excel (.xlsx/.xls), CSV, and PowerPoint (.ppt/.pptx) files.

- Extract text and structured/tabular content from each file type.

- Normalize the extracted content into a common document/chunk representation.

- Generate embeddings and store them in a vector database.

- Retrieve the most relevant chunks for a user question.

- Use an LLM to generate an answer grounded in the retrieved content.

- Show source/file references and, where practical, slide/sheet/row metadata.

- Provide a simple chatbot UI for upload, indexing, and question answering.

3. Suggested Business Scenario

Use a fictional company named Acme Retail. The knowledge base contains quarterly business reviews, sales targets, regional performance data, product information, and operating metrics. The chatbot should answer questions that require information from one or multiple files.
now. 
4. Input Data

| Format | Example | Expected extraction | Metadata |
| --- | --- | --- | --- |
| Excel | sales_q1.xlsx | Sheet names, headers, rows, formulas/results where available | file, sheet, row range |
| CSV | customer_sales.csv | Headers and records | file, row range |
| PowerPoint | q1_business_review.pptx | Slide title, text, tables, notes where accessible | file, slide number, title |

5. Functional Requirements

| ID | Capability | Requirement |
| --- | --- | --- |
| FR-01 | File Upload | User can upload one or more Excel, CSV, and PowerPoint files. |
| FR-02 | Parsing | System extracts useful content from each supported format. |
| FR-03 | Chunking | Extracted content is split into retrieval-friendly chunks while preserving metadata. |
| FR-04 | Embedding | Each chunk is converted into an embedding. |
| FR-05 | Vector Store | Embeddings and metadata are persisted in a vector database. |
| FR-06 | Retrieval | System retrieves top relevant chunks for a user question. |
| FR-07 | Generation | LLM generates an answer using retrieved context. |
| FR-08 | Grounding | Answer identifies supporting files and locations where possible. |
| FR-09 | Multi-document QA | Questions can require information from more than one source. |
| FR-10 | No-answer behavior | If evidence is insufficient, chatbot should clearly say it cannot answer from the indexed content rather than inventing facts. |

6. Non-Functional Expectations

- Modular design: ingestion, parsing, chunking, embedding, retrieval, generation, and UI should be separable.

- Traceability: every retrieved chunk should retain source metadata.

- Error handling: unsupported/corrupt files should produce useful errors.

- Security awareness: do not expose uploaded file contents to unrelated users.

- Performance awareness: avoid re-embedding unchanged documents where possible.

- Observability: log ingestion failures, retrieval latency, and model/API errors.

- Maintainability: provide a clear README and setup instructions.

7. End-to-End RAG Pipeline

| Stage | Expected behavior |
| --- | --- |
| 1. Upload | User uploads Excel, CSV, and PPT/PPTX files. |
| 2. Identify format | System routes each file to the appropriate parser. |
| 3. Extract | Parser converts file contents into normalized records. |
| 4. Enrich metadata | Attach file name, file type, sheet/slide number, title, row range, and other useful metadata. |
| 5. Chunk | Split content into semantically useful chunks; avoid blindly splitting structured tables. |
| 6. Embed | Generate vector embeddings for each chunk. |
| 7. Index | Store vectors, chunk text, and metadata in the vector store. |
| 8. Query | Convert the user's question into an embedding. |
| 9. Retrieve | Perform similarity search and optionally metadata filtering/reranking. |
| 10. Generate | Pass the retrieved context plus the question to the LLM. |
| 11. Cite | Return the answer with supporting source references. |

8. Expected Chatbot Behavior

For each response, the chatbot should provide a concise answer followed by supporting sources. For example:

Answer: The South region achieved 105% of its Q1 target, with $4.2M revenue against a $4.0M target.

Sources: sales_q1.xlsx → Regional Sales → row 12; q1_business_review.pptx → Slide 8.

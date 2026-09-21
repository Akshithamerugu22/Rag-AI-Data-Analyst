# Universal RAG AI Data Analyst — Final Year Project

## Resume-ready title
**Universal RAG-Based AI Data Analyst with Natural Language Query Planning**

## What it does
A schema-independent analytics platform accepting CSV, Excel, TSV, JSON, Parquet and PDF. It profiles unfamiliar datasets, converts natural-language questions into safe analytical SQL, executes them with DuckDB, retrieves context with RAG, and generates grounded answers, charts and reports.

## Architecture
Upload → ingestion → schema inference → profiling → natural-language query planner → SQL validation → DuckDB execution → RAG retrieval → Gemini explanation → table/chart/report.

## Why this architecture?
The LLM plans and explains. DuckDB performs the calculation. This is more reliable than asking the LLM to calculate directly.

## SQL safety
Only SELECT/WITH analytical queries are accepted. Modification commands are rejected.

## Supported formats
CSV, TSV, XLSX/XLS, JSON, Parquet, PDF.

## Included benchmark
`large_sales_dataset_250k.csv` contains **250,000 rows**, multiple years, 20 products, 9 regions, 4 channels, 3 customer segments and multiple numeric measures.

## Installation
```bash
python -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
```
Create `.env` with `GEMINI_API_KEY=your_key` and run:
```bash
streamlit run app.py
```

## Example questions
- What is the total sales?
- Which product has the highest sales?
- Compare sales by region.
- Show monthly sales trend.
- Which channel has the highest average profit?
- Find outliers.
- Which columns have missing values?
- Summarize the dataset.
- Upload an HR dataset and ask for salary analysis.
- Upload a marketing dataset and ask for campaign ROI.
- Upload a student dataset and ask about marks/attendance.

## Resume description
**Universal RAG-Based AI Data Analyst | Python, DuckDB, Pandas, Streamlit, RAG, ChromaDB, Gemini** — Developed a schema-independent AI analytics platform that accepts CSV, Excel, JSON, Parquet and PDF inputs and answers natural-language business questions. Implemented automatic schema profiling, RAG-based contextual retrieval, LLM-driven SQL query planning, validated DuckDB execution, automated visualization and PDF/Excel reporting. Designed a hybrid architecture where deterministic SQL performs calculations while Gemini generates grounded explanations.

## Resume bullets
- Built a schema-independent AI Data Analyst supporting multiple structured and document formats.
- Implemented RAG with Sentence Transformers and ChromaDB for contextual retrieval.
- Developed natural-language-to-DuckDB SQL query planning with read-only validation.
- Added automated data profiling, aggregation, comparison, time-series analysis, outlier detection and visualization.
- Created a 250K-row benchmark dataset and downloadable Excel/PDF reports.

## Viva
**Why RAG?** It retrieves information from uploaded files and grounds the response.

**Why DuckDB?** It executes analytical SQL efficiently without sending the whole dataset to the LLM.

**Why not let Gemini calculate?** LLMs can make arithmetic mistakes; the database performs calculations.

**What happens for a new schema?** The application profiles the columns and sends the discovered schema to the query planner.

**What makes it different from a chatbot?** It has a deterministic execution layer between the user's question and the answer.

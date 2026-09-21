#RAG AI Data Analyst

Ask questions about any dataset in plain English. The app profiles whatever you upload, turns your question into validated DuckDB SQL, runs the calculation on the data itself, and uses Gemini only to plan the query and explain the result — never to do the arithmetic.

```
Upload → ingestion → schema inference → profiling → NL query planner
       → SQL validation → DuckDB execution → RAG retrieval
       → Gemini explanation → table / chart / report
```

---

## Why it's built this way

Asking an LLM to compute totals from raw rows is unreliable and doesn't scale past a few thousand records. Here the responsibilities are split:

| Layer | Responsibility |
|---|---|
| Gemini | Understands the question, writes SQL, explains the result |
| Validator | Rejects anything that isn't a read-only single-statement query |
| DuckDB | Performs every calculation, in-process, over the full dataset |
| FAISS + MiniLM | Retrieves schema profiles, sample rows and PDF text as grounding context |

The dataset is never sent to the model — only the schema, the generated SQL and the computed result are.

---

## Features

- **Schema-independent.** No hardcoded column names. Numeric measures, categorical dimensions, dates and high-cardinality IDs are detected automatically.
- **Multi-format ingestion.** CSV, TSV, XLSX/XLS (all sheets merged), JSON, Parquet and PDF.
- **Automatic profiling.** Row/column counts, dtypes, inferred roles, missing cells, duplicates, unique counts and example values.
- **Read-only SQL enforcement.** Only `SELECT` / `WITH`; `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `COPY`, `ATTACH`, `PRAGMA`, `LOAD` and friends are blocked, along with multi-statement input and queries that don't reference an uploaded table.
- **Works without an API key.** A rule-based fallback planner builds sensible aggregate SQL when no Gemini key is configured.
- **Retry handling.** 429 / 503 responses from Gemini are retried with exponential backoff.
- **Auto-charting.** Time-series results render as line charts, categorical results as bar charts (small result sets only).
- **Report export.** One-click Excel and PDF reports containing the question, answer, SQL and result table.
- **Benchmark dataset included.** 250,000 sales rows across multiple years, products, regions, channels and segments.

---

## Tech stack

Python · Streamlit · Pandas · DuckDB · FAISS · Sentence Transformers (`all-MiniLM-L6-v2`) · Google Gemini (`google-genai`) · Plotly · openpyxl · pypdf · ReportLab

---

## Quick start

```bash
git clone <your-repo-url>
cd universal-rag-ai-data-analyst

python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file (see `.env.example`):

```env
GEMINI_API_KEY=your_gemini_api_key_here
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Run it:

```bash
streamlit run app.py
```

Then upload a file in the sidebar and press **Process files**. The Gemini key is optional — you can also paste it into the sidebar at runtime — but the fallback planner produces much simpler queries without it.

---

## Project structure

```
app.py                        Streamlit UI, session state, chat loop, report buttons
universal_data.py             File ingestion, column cleaning, type inference,
                              profiling, RAG document construction
duckdb_engine.py              Registers DataFrames as DuckDB tables, schema text, execution
query_planner.py              Gemini prompting, SQL validation, fallback planner,
                              charting, grounded explanation, end-to-end answer()
rag_engine.py                 FAISS index, embedding, similarity search
report_generator.py           Excel and PDF report builders
large_sales_dataset_250k.csv  250K-row benchmark dataset
requirements.txt
.env.example
```

---

## How a question is answered

1. `DataEngine` registers each uploaded DataFrame as a DuckDB table with a safe alias (`t_<name>`).
2. The schema text is embedded into a planning prompt and sent to Gemini, which returns JSON containing `sql` and an `explanation`.
3. `validate()` strips code fences and rejects multi-statement, non-`SELECT`, over-long, unsafe, or off-schema queries.
4. DuckDB executes the query and returns a DataFrame.
5. FAISS retrieves the top 6 relevant chunks (schema profiles, sample rows, PDF pages).
6. Gemini writes the final answer using **only** the numbers present in the computed result.
7. A Plotly chart is generated if the shape of the result suits one.

---

## Benchmark dataset

`large_sales_dataset_250k.csv` — 250,000 rows:

`order_id, order_date, product, category, region, channel, customer_segment, payment_method, quantity, unit_price, discount_pct, sales, cost, profit`

## Example questions

- What is the total sales?
- Which product has the highest profit?
- Compare sales by region.
- Show the monthly sales trend.
- Which channel has the highest average profit?
- Which columns have missing values?
- Summarize the dataset.

The same questions work on an HR file, a marketing file or a student-records file — nothing about the schema is assumed.

---

## Limitations

- Datasets are held in memory; very large files are bounded by available RAM.
- The FAISS index is rebuilt per session and is not persisted to disk.
- Reports are written to `/tmp` and overwritten on each export.
- Single-table reasoning is strongest; multi-file joins depend entirely on the planner inferring the relationship.

## Roadmap

Forecasting · statistical tests · anomaly detection · persistent vector storage · semantic data catalog · authentication · cloud deployment · Power BI integration

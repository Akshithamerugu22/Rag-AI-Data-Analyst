# Universal RAG AI Data Analyst — Technical Documentation

A schema-independent analytics application. You upload a dataset it has never
seen before, ask a question in plain English, and it profiles the schema,
generates analytical SQL, executes that SQL on a real database engine, and
explains the computed result.

The guiding design rule: **the language model plans and explains, the database
calculates.** No number shown to the user is produced by the LLM.

---

## 1. Why this architecture

The obvious way to build a "chat with your data" tool is to paste rows into an
LLM prompt and ask for the answer. That approach has two failures:

1. **Arithmetic is unreliable.** Language models predict tokens; they do not
   compute. Sums over thousands of rows drift.
2. **It does not scale.** A 250,000-row dataset does not fit in a context
   window, so you end up sampling and the answer describes the sample rather
   than the data.

This project separates the two concerns:

| Responsibility | Handled by |
| --- | --- |
| Understanding the question | Gemini |
| Deciding which columns/aggregations answer it | Gemini |
| Performing the calculation | DuckDB |
| Grounding the wording in the dataset's context | FAISS retrieval |
| Phrasing the final answer | Gemini, constrained to the computed values |

The LLM never sees the full dataset — only the schema. It returns SQL. DuckDB
runs that SQL over the full table. The numbers are therefore deterministic and
reproducible: re-running the same SQL gives the same answer every time, and the
generated SQL is shown in the UI so it can be checked by hand.

---

## 2. End-to-end flow

```
Upload (CSV / Excel / TSV / JSON / Parquet / PDF)
        │
        ▼
  Ingestion          normalize column names, infer dtypes
        │
        ▼
  Profiling          rows, dupes, missing cells, per-column role
        │
        ├──────────────► Document chunks ──► Embeddings ──► FAISS index
        │
        ▼
  User question
        │
        ▼
  Query planning     schema + question ──► Gemini ──► {sql, explanation}
        │
        ▼
  SQL validation     SELECT/WITH only, single statement, known tables
        │
        ▼
  DuckDB execution   runs against the registered DataFrame
        │
        ▼
  RAG retrieval      top-k profile / sample-row chunks for this question
        │
        ▼
  Explanation        Gemini, given the SQL + computed result + context
        │
        ▼
  Answer + table + Plotly chart + downloadable Excel / PDF report
```

---

## 3. Module reference

### `app.py` — Streamlit interface

Owns session state (`workspace`, `rag`, `planner`, `messages`,
`last_result`), the sidebar upload/report controls, and the chat loop.
Rendering is split so that chat history replays tables, charts and the
generated SQL on every rerun, not just when the answer first arrives.
The Gemini key is optional: without it the planner falls back to
rule-based SQL.

### `universal_data.py` — ingestion, type inference, profiling

The "works on any dataset" layer.

- `clean_columns` — lowercases, strips punctuation to underscores, and
  de-duplicates collisions (`total`, `total_2`) so column names are safe as SQL
  identifiers.
- `infer_types` — for each object column, attempts datetime parsing and keeps it
  if ≥90% of values parse; otherwise attempts numeric parsing (stripping
  thousands separators) and keeps it if ≥95% parse. Thresholds rather than
  all-or-nothing, so a few dirty values don't block a column from being typed.
- `infer_role` — classifies each column as `date/time`, `numeric measure`,
  `high-cardinality / possible ID` (unique ratio > 0.90), or
  `categorical dimension`. This is what makes the planner prompt useful on an
  unfamiliar schema.
- `profile_dataset` — row/column counts, duplicate rows, missing cells, and a
  per-column line with dtype, role, null count, cardinality and three example
  values.
- `make_documents` — builds the RAG corpus: one profile chunk per dataset, plus
  sampled rows (max 1000, in blocks of 50) serialized as CSV.
- `ingest_files` — routes by extension; PDFs are split per page (12,000 char
  cap) into text-only documents with no table.

Excel workbooks are handled sheet-by-sheet and concatenated, with a
`_source_sheet` column added so the origin of each row survives the merge.

### `duckdb_engine.py` — execution layer

Opens an in-memory DuckDB connection and registers each uploaded DataFrame
under a safe alias (`t_` prefix, non-alphanumerics collapsed). Registration is
zero-copy — DuckDB reads the pandas buffers directly, so there is no duplication
of a large dataset in memory.

`schema_text()` renders the schema in the exact form the planner prompt
consumes, including the mapping back to the original filename:

```
TABLE "t_sales" [source=large_sales_dataset_250k.csv] COLUMNS: "region" (object), ...
```

### `rag_engine.py` — retrieval

Sentence-Transformers (`all-MiniLM-L6-v2` by default, overridable via the
`EMBEDDING_MODEL` environment variable) encodes each chunk; vectors are
L2-normalized and stored in a FAISS `IndexFlatL2` for exact search. Parallel
lists hold the document text and its source so results can be attributed.

API: `add_documents`, `search`, `search_with_sources`, `clear`/`reset`,
`count`.

> Note: the project brief mentions ChromaDB; the implementation uses FAISS.
> FAISS was chosen because the index is rebuilt on every upload and never needs
> to persist, so a server-backed store adds deployment cost with no benefit.

### `query_planner.py` — planning, validation, charting, explanation

The core of the system.

**Planning.** Sends the rendered schema and the question to Gemini with an
18-rule prompt (SELECT-only, never invent columns or tables, aggregate large
datasets, `DATE_TRUNC` for trends, `NULLIF` for percentage denominators, cap
detail results at 100 rows) and requires a JSON response of `{sql, explanation}`.
Responses are stripped of markdown fences and, if JSON parsing still fails, the
first `{...}` block is extracted as a fallback.

**Retry.** `generate_with_retry` retries 503/UNAVAILABLE/429/RESOURCE_EXHAUSTED
with exponential backoff (1s, 2s, 4s). Other errors raise immediately — retrying
a bad model name or a malformed request would only waste time.

**Validation.** Prompt rules are a request, not a guarantee, so every generated
query is independently checked before execution:

1. non-empty after fence stripping
2. no second statement (rejects `;` anywhere but trailing)
3. no forbidden keyword (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, COPY,
   ATTACH, DETACH, INSTALL, LOAD, CALL, EXPORT, IMPORT, PRAGMA, SET, RESET,
   TRUNCATE, VACUUM)
4. must begin with `SELECT` or `WITH`
5. length ≤ 12,000 characters
6. must reference at least one registered table alias — blocks queries against
   something that isn't the user's data

**Fallback.** With no API key, a keyword-matching planner inspects the profiled
numeric and date columns and emits reasonable SQL, so the app remains
demonstrable offline.

**Charting.** Purely rule-based, from the shape of the result: ≤50 rows and a
numeric second column, then a line chart if the first column is a datetime and a
bar chart if it is categorical. Anything else renders as a table only — no chart
is invented for data that doesn't support one.

**Explanation.** Gemini receives the question, the SQL, the first 100 rows of the
computed result and the retrieved context, and is instructed to answer directly,
use only the numbers present, and never alter a computed value.

### `report_generator.py` — export

`create_excel_report` writes question, answer, SQL and the result table via
openpyxl. `create_pdf_report` builds an A4 document with ReportLab, including a
styled table of the first 25 rows.

---

## 4. Worked example

**Dataset:** `customer_shopping_behavior.csv` — 3,900 rows, 18 columns, 5 numeric
measures, 37 missing cells.

**Question:** *"What are the top 5 items by total purchase amount, and what
percentage of total purchases do they represent?"*

**Generated SQL** (shape):

```sql
SELECT item_purchased,
       SUM(purchase_amount_usd) AS total_purchase_amount,
       ROUND(SUM(purchase_amount_usd) * 100.0
             / NULLIF((SELECT SUM(purchase_amount_usd) FROM t_customer_shopping_behavior), 0), 2)
           AS percentage_of_total
FROM t_customer_shopping_behavior
GROUP BY item_purchased
ORDER BY total_purchase_amount DESC
LIMIT 5
```

**Result:** Blouse 10,410 (4.47%), Shirt 10,332 (4.43%), Dress 10,320 (4.43%),
Pants 10,090 (4.33%), Jewelry 10,010 (4.29%).

The window function is avoided in favour of a scalar subquery for the
denominator, `NULLIF` guards division by zero, and the bar chart is emitted
automatically because the result is 5 rows with a categorical first column and a
numeric second column.

---

## 5. Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Create a `.env` file:

```
GEMINI_API_KEY=your_key_here
EMBEDDING_MODEL=all-MiniLM-L6-v2   # optional
```

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. The key can also be pasted into the
sidebar at runtime instead of using `.env`.

First run downloads the embedding model (~90 MB) from Hugging Face.

---

## 6. Design decisions, stated plainly

**Why validate SQL when the prompt already forbids these commands?**
Because prompt rules are probabilistic and validation is not. The validator is
the actual security boundary; the prompt rules only reduce how often it has to
fire.

**Why rebuild the DuckDB engine per question?**
Registration is zero-copy and near-instant, and a fresh connection guarantees no
state leaks between questions. Persisting the connection would be a
micro-optimization with a correctness cost.

**Why cap chart rendering at 50 rows?**
A 200-bar chart is less readable than the table it came from. Above the
threshold the table is the better presentation.

**Why send only the schema to the LLM, never the rows?**
Cost, latency, privacy, and correctness. The model needs column names, types and
roles to write SQL — it does not need the data, and giving it the data is what
causes it to answer from a sample instead of from the full dataset.

---

## 7. Known limitations

Stated honestly; these are the boundaries of the current implementation.

- **The system profiles data quality rather than cleaning it.** Column names are
  normalized and types inferred, but duplicates and missing values are reported
  to the user, not removed or imputed. This is intentional — silently altering
  someone's data changes their answers without their knowledge — but it does
  mean "cleaning" is the user's decision, informed by the profile.
- **Single-table questions.** Joins across two uploaded files are possible in
  principle (all tables are registered together) but are not specifically prompted
  for or tested.
- **Trend questions require a detected date column.** If type inference finds no
  datetime column, `DATE_TRUNC` questions will fail or return something odd.
  Datasets without dates support aggregation and comparison questions only.
- **Keyword validation is textual.** A legitimate query with a string literal
  such as `WHERE channel = 'Call Center'` can be rejected by the `CALL` rule.
  Safe direction to fail in, but a real false-positive.
- **Retrieved context is rebuilt per upload and held in memory.** Restarting the
  app clears the index.
- **PDF inputs are retrieval-only.** They contribute to explanations but cannot
  be queried with SQL, since they produce no table.

---

## 8. Future work

Forecasting on detected time series, statistical significance tests for group
comparisons, dedicated anomaly detection, persistent vector storage, a semantic
data catalog that remembers previously seen schemas, multi-table join planning,
authentication and cloud deployment.

---

## 9. File map

| File | Responsibility |
| --- | --- |
| `app.py` | Streamlit UI, session state, chat loop |
| `universal_data.py` | Ingestion, cleaning, type inference, profiling, chunking |
| `duckdb_engine.py` | Table registration, schema rendering, SQL execution |
| `rag_engine.py` | Embeddings, FAISS index, similarity search |
| `query_planner.py` | Prompting, validation, execution orchestration, charts, explanation |
| `report_generator.py` | Excel and PDF export |
| `requirements.txt` | Dependencies |
| `large_sales_dataset_250k.csv` | 250K-row benchmark dataset |

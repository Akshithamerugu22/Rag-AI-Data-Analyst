import re
import json
import time

import pandas as pd
import plotly.express as px

from google import genai

from duckdb_engine import DataEngine


# ================================================================
# BLOCKED SQL COMMANDS
# ================================================================

FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|COPY|ATTACH|DETACH|"
    r"INSTALL|LOAD|CALL|EXPORT|IMPORT|PRAGMA|SET|RESET|"
    r"TRUNCATE|VACUUM"
    r")\b",
    re.I
)


class QueryPlanner:

    # ============================================================
    # INITIALIZATION
    # ============================================================

    def __init__(self, api_key=""):

        self.client = (
            genai.Client(api_key=api_key)
            if api_key
            else None
        )

        # Gemini model requested by your current API
        self.model = "gemini-3.6-flash"

    # ============================================================
    # GEMINI CALL WITH RETRY
    # ============================================================

    def generate_with_retry(
        self,
        contents,
        max_retries=3
    ):
        """
        Calls Gemini and automatically retries temporary
        availability/rate-limit errors.
        """

        if not self.client:
            return None

        last_error = None

        for attempt in range(max_retries):

            try:

                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents
                )

                return response

            except Exception as error:

                last_error = error

                error_text = str(error).upper()

                # ------------------------------------------------
                # Temporary Gemini errors
                # ------------------------------------------------

                temporary_error = (
                    "503" in error_text
                    or "UNAVAILABLE" in error_text
                    or "429" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                )

                if temporary_error:

                    if attempt < max_retries - 1:

                        wait_time = 2 ** attempt

                        time.sleep(wait_time)

                        continue

                # ------------------------------------------------
                # Permanent error
                # ------------------------------------------------

                raise error

        raise last_error

    # ============================================================
    # SQL PROMPT
    # ============================================================

    def prompt(
        self,
        question,
        engine
    ):

        return f"""
You are a senior Data Analyst and SQL planner.

Your job is to convert the user's natural-language
question into ONE DuckDB analytical SQL query.

DATABASE SCHEMA:
{engine.schema_text()}

USER QUESTION:
{question}

Return JSON ONLY.

Required format:

{{
    "sql": "SELECT ...",
    "explanation": "Brief explanation of what the query calculates."
}}

RULES:

1. Only generate SELECT or WITH queries.

2. NEVER generate:

INSERT
UPDATE
DELETE
DROP
ALTER
CREATE
COPY
ATTACH
DETACH
INSTALL
LOAD
CALL
EXPORT
IMPORT
PRAGMA
SET
RESET
TRUNCATE
VACUUM

3. Use ONLY columns that exist in the provided schema.

4. Use ONLY tables that exist in the provided schema.

5. Use valid DuckDB SQL syntax.

6. Use SUM, AVG, COUNT, MIN, and MAX when appropriate.

7. For time-based analysis use DATE_TRUNC.

8. For percentage calculations use NULLIF
   to prevent division by zero.

9. For large datasets, aggregate the data.

10. Detailed result sets must contain at most 100 rows.

11. Never invent columns.

12. Never invent tables.

13. Never assume a column exists.

14. If the user asks for top, highest, or largest,
    sort appropriately.

15. If the user asks for trends,
    group by the appropriate date/time period.

16. If the user asks for comparisons,
    calculate the relevant metric for each group.

17. Use aliases for calculated columns.

18. Return JSON only.
"""

    # ============================================================
    # SQL VALIDATION
    # ============================================================

    def validate(
        self,
        sql,
        engine
    ):

        if not sql:

            raise ValueError(
                "Gemini returned an empty SQL query."
            )

        sql = (
            sql
            .strip()
            .replace("```json", "")
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )

        # --------------------------------------------------------
        # Multiple statements
        # --------------------------------------------------------

        if ";" in sql.rstrip(";"):

            raise ValueError(
                "Multiple SQL statements are not allowed."
            )

        # --------------------------------------------------------
        # Dangerous SQL
        # --------------------------------------------------------

        if FORBIDDEN.search(sql):

            raise ValueError(
                "Unsafe SQL command detected."
            )

        # --------------------------------------------------------
        # SELECT / WITH only
        # --------------------------------------------------------

        if not re.match(
            r"^(SELECT|WITH)\b",
            sql,
            re.I
        ):

            raise ValueError(
                "Only SELECT or WITH queries are allowed."
            )

        # --------------------------------------------------------
        # SQL length
        # --------------------------------------------------------

        if len(sql) > 12000:

            raise ValueError(
                "Generated SQL is too long."
            )

        # --------------------------------------------------------
        # Dataset reference
        # --------------------------------------------------------

        aliases = list(
            engine.aliases.values()
        )

        if aliases:

            references_dataset = any(
                re.search(
                    rf"\b{re.escape(table)}\b",
                    sql,
                    re.I
                )
                for table in aliases
            )

            if not references_dataset:

                raise ValueError(
                    "Query does not reference "
                    "an uploaded dataset."
                )

        return sql.rstrip(";").strip()

    # ============================================================
    # FALLBACK SQL
    # ============================================================

    def fallback(
        self,
        question,
        engine
    ):

        q = question.lower()

        original, df = next(
            iter(engine.tables.items())
        )

        table = engine.aliases[original]

        # --------------------------------------------------------
        # Numeric columns
        # --------------------------------------------------------

        numeric_columns = list(
            df.select_dtypes(
                include="number"
            ).columns
        )

        # --------------------------------------------------------
        # Date columns
        # --------------------------------------------------------

        date_columns = [
            column

            for column in df.columns

            if pd.api.types.is_datetime64_any_dtype(
                df[column]
            )
        ]

        # --------------------------------------------------------
        # Categorical columns
        # --------------------------------------------------------

        categorical_columns = [

            column

            for column in df.columns

            if (
                column not in numeric_columns
                and column not in date_columns
                and 2 <= df[column].nunique(
                    dropna=True
                ) <= 200
            )
        ]

        # --------------------------------------------------------
        # Find useful numeric column
        # --------------------------------------------------------

        number_column = next(

            (
                column

                for column in numeric_columns

                if any(
                    word in column.lower()

                    for word in [
                        "sales",
                        "revenue",
                        "amount",
                        "profit",
                        "price",
                        "value",
                        "cost",
                        "purchase"
                    ]
                )
            ),

            numeric_columns[0]
            if numeric_columns
            else None
        )

        # --------------------------------------------------------
        # Find dimension
        # --------------------------------------------------------

        dimension = next(

            (
                column

                for column in categorical_columns

                if column.lower() in q
            ),

            categorical_columns[0]
            if categorical_columns
            else None
        )

        # --------------------------------------------------------
        # Find date
        # --------------------------------------------------------

        date_column = (
            date_columns[0]
            if date_columns
            else None
        )

        # ========================================================
        # TOTAL
        # ========================================================

        if (
            number_column
            and "total" in q
        ):

            return (
                f'SELECT '
                f'SUM("{number_column}") '
                f'AS total_{number_column} '
                f'FROM "{table}"'
            )

        # ========================================================
        # AVERAGE
        # ========================================================

        if (
            number_column
            and any(
                word in q

                for word in [
                    "average",
                    "avg",
                    "mean"
                ]
            )
        ):

            return (
                f'SELECT '
                f'AVG("{number_column}") '
                f'AS average_{number_column} '
                f'FROM "{table}"'
            )

        # ========================================================
        # TOP / HIGHEST
        # ========================================================

        if (
            number_column
            and dimension
            and any(
                word in q

                for word in [
                    "top",
                    "highest",
                    "largest"
                ]
            )
        ):

            return (
                f'SELECT '
                f'"{dimension}", '
                f'SUM("{number_column}") '
                f'AS total_{number_column} '
                f'FROM "{table}" '
                f'GROUP BY 1 '
                f'ORDER BY 2 DESC '
                f'LIMIT 10'
            )

        # ========================================================
        # MONTHLY TREND
        # ========================================================

        if (
            number_column
            and date_column
            and any(
                word in q

                for word in [
                    "trend",
                    "monthly",
                    "over time"
                ]
            )
        ):

            return (
                f"""
SELECT
    DATE_TRUNC(
        'month',
        "{date_column}"
    ) AS month,

    SUM(
        "{number_column}"
    ) AS total_{number_column}

FROM "{table}"

GROUP BY 1

ORDER BY 1
"""
            )

        # ========================================================
        # SAFE DEFAULT
        # ========================================================

        return (
            f'SELECT * '
            f'FROM "{table}" '
            f'LIMIT 20'
        )

    # ============================================================
    # CHART GENERATION
    # ============================================================

    def chart(
        self,
        result
    ):

        if (
            result is None
            or result.empty
            or len(result.columns) < 2
        ):

            return None

        x = result.columns[0]

        y = result.columns[1]

        # --------------------------------------------------------
        # Only chart small result sets
        # --------------------------------------------------------

        if (
            len(result) <= 50
            and pd.api.types.is_numeric_dtype(
                result[y]
            )
        ):

            # ----------------------------------------------------
            # Time series
            # ----------------------------------------------------

            if pd.api.types.is_datetime64_any_dtype(
                result[x]
            ):

                return px.line(
                    result,
                    x=x,
                    y=y,
                    markers=True
                )

            # ----------------------------------------------------
            # Category
            # ----------------------------------------------------

            if not pd.api.types.is_numeric_dtype(
                result[x]
            ):

                return px.bar(
                    result,
                    x=x,
                    y=y
                )

        return None

    # ============================================================
    # GEMINI EXPLANATION
    # ============================================================

    def explain(
        self,
        question,
        sql,
        result,
        retrieved
    ):

        # --------------------------------------------------------
        # Gemini unavailable
        # --------------------------------------------------------

        if not self.client:

            return (
                "The validated analytical query "
                "returned the result shown below."
            )

        # --------------------------------------------------------
        # Build RAG context
        # --------------------------------------------------------

        context_parts = []

        for item in retrieved:

            if isinstance(item, dict):

                source = item.get(
                    "source",
                    "unknown"
                )

                text = item.get(
                    "text",
                    ""
                )

            else:

                source = "unknown"

                text = str(item)

            context_parts.append(
                f"SOURCE {source}:\n"
                f"{text[:3500]}"
            )

        context = "\n\n".join(
            context_parts
        )

        # --------------------------------------------------------
        # Result
        # --------------------------------------------------------

        result_text = (
            result
            .head(100)
            .to_string(index=False)
        )

        # --------------------------------------------------------
        # Explanation prompt
        # --------------------------------------------------------

        prompt = f"""
You are an AI Data Analyst.

USER QUESTION:
{question}

SQL QUERY:
{sql}

CALCULATED RESULT:
{result_text}

RETRIEVED CONTEXT:
{context}

Instructions:

1. Give the direct answer first.

2. Briefly explain how the result was calculated.

3. Use ONLY numbers present in the calculated result.

4. Never invent numbers.

5. Never change calculated values.

6. Clearly describe comparisons.

7. Keep the explanation concise and professional.

8. If the result is empty, say that no matching
   records were found.

"""

        # --------------------------------------------------------
        # Gemini with retry
        # --------------------------------------------------------

        response = self.generate_with_retry(
            prompt
        )

        if response is None:

            return (
                "The analytical query completed "
                "successfully. See the result below."
            )

        return response.text

    # ============================================================
    # MAIN ANSWER
    # ============================================================

    def answer(
        self,
        question,
        workspace,
        rag
    ):

        # --------------------------------------------------------
        # Create DuckDB engine
        # --------------------------------------------------------

        engine = DataEngine(
            workspace["tables"]
        )

        # ========================================================
        # STEP 1 — SQL GENERATION
        # ========================================================

        if self.client:

            response = self.generate_with_retry(

                self.prompt(
                    question,
                    engine
                )
            )

            raw = response.text.strip()

            # ----------------------------------------------------
            # Remove Markdown
            # ----------------------------------------------------

            raw = (
                raw
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            # ----------------------------------------------------
            # Parse JSON
            # ----------------------------------------------------

            try:

                parsed = json.loads(
                    raw
                )

            except json.JSONDecodeError:

                # Try extracting JSON
                # if Gemini returned extra text.

                match = re.search(
                    r"\{.*\}",
                    raw,
                    re.S
                )

                if not match:

                    raise ValueError(
                        "Gemini did not return "
                        "valid JSON."
                    )

                parsed = json.loads(
                    match.group(0)
                )

            # ----------------------------------------------------
            # Validate generated SQL
            # ----------------------------------------------------

            if "sql" not in parsed:

                raise ValueError(
                    "Gemini response did not "
                    "contain SQL."
                )

            sql = self.validate(
                parsed["sql"],
                engine
            )

        else:

            # ----------------------------------------------------
            # No Gemini API key
            # ----------------------------------------------------

            sql = self.validate(

                self.fallback(
                    question,
                    engine
                ),

                engine
            )

        # ========================================================
        # STEP 2 — EXECUTE SQL
        # ========================================================

        result = engine.execute(
            sql
        )

        # ========================================================
        # STEP 3 — RAG SEARCH
        # ========================================================

        retrieved = rag.search(
            question,
            6
        )

        # ========================================================
        # STEP 4 — EXPLANATION
        # ========================================================

        answer = self.explain(
            question,
            sql,
            result,
            retrieved
        )

        # ========================================================
        # STEP 5 — CHART
        # ========================================================

        chart = self.chart(
            result
        )

        # ========================================================
        # RETURN RESULT
        # ========================================================

        return {
            "answer": answer,
            "sql": sql,
            "table": result,
            "chart": chart,
            "question": question,
            "retrieved": retrieved
        }
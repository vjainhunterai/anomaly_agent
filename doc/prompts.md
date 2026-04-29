# Prompt Catalogue

Every prompt is a plain `.txt` file under `prompts/`, loaded once on first
use by `backend/llm_service.py::load_prompt` (memoised in
`_prompt_cache`). All status entries below are **IMPLEMENTED**.

Placeholders are filled with `str.format(...)`. To put a literal `{` or
`}` in the prompt body, double them up (`{{` / `}}`). Today only
`date_extract_prompt.txt` uses this -- the example JSON skeleton uses
`{{...}}` so `format()` does not consume the braces.

## File index

| File | Caller | Output expected |
|------|--------|-----------------|
| `date_extract_prompt.txt`   | `normalize_date_range`     | JSON object `{ "start_date": "...", "end_date": "..." }` |
| `understanding_prompt.txt`  | `understand_dataset`       | Free-form markdown, <= 180 words |
| `anomaly_prompt.txt`        | `detect_anomalies`         | JSON array of anomaly objects |
| `anomaly_format_prompt.txt` | `format_report`            | Markdown report with fixed section headings |
| `anomaly_chat_prompt.txt`   | `chat_about_anomalies`     | 2-6 sentence markdown answer |
| `status_prompt.txt`         | `status_qa`                | 1-4 sentence markdown answer |
| `sql_prompt.txt`            | `generate_sql`             | Single MySQL `SELECT` wrapped in ```sql fences |
| `reconciliation_prompt.txt` | `reconciliation_report`    | Markdown report with 5 fixed section headings |

## Per-file detail

### `date_extract_prompt.txt`
Placeholder: `{input}` -- the user's free-text message.

Returns JSON. The wrapper strips ```json fences before parsing. If the
LLM is unavailable or produces invalid JSON, `_normalize_with_regex`
takes over and pulls `YYYY-MM-DD` (or `YYYY/MM/DD`) substrings.

### `understanding_prompt.txt`
Placeholders: `{column_info}`, `{data}`.

`column_info` is the formatted output of
`database.format_column_metadata(...)`. `data` is `json.dumps` of the
first 200 rows of `anomaly.duplicate_ap_invoice` (the slice happens in
`llm_service.understand_dataset`).

### `anomaly_prompt.txt`
Placeholders: `{column_info}`, `{understanding}`, `{memory}`, `{data}`.

Called once per chunk of 200 rows. Each chunk's response is parsed as a
JSON array; objects are deduped by `invoice_id`.

`memory` is currently the literal string `"[]"` (see
`llm_service.detect_anomalies`). Persistent memory is PLANNED -- the
original `anomaly_analyst.py` reads/writes a `memory.json` file but the
FastAPI wrapper does not yet.

### `anomaly_format_prompt.txt`
Placeholder: `{anomalies}`.

Required headings the prompt instructs the LLM to emit:
1. `### Executive Summary`
2. `### Findings by Severity`
3. `### Detailed Anomaly Table`
4. `### Recommended Next Steps`

Fallback (when LLM returns nothing): `format_report` builds a plain
markdown table from the keys of the anomaly dicts.

### `anomaly_chat_prompt.txt`
Placeholders: `{column_info}`, `{understanding}`, `{anomalies}`, `{question}`.

Used by both the analysis panel's follow-up Q&A and -- via
`llm_service.chat_about_anomalies` -- as the natural-language layer of
`/api/analysis/ask`.

### `status_prompt.txt`
Placeholders: `{summary}`, `{rows}`, `{question}`.

Drives `/api/status/ask`. `summary` is the dict returned by
`database.fetch_anomaly_summary`; `rows` is the first 50 rows of
`fetch_anomaly_rows(50)`.

### `sql_prompt.txt`
Placeholders: `{column_info}`, `{table}`, `{question}`.

Drives the *opportunistic* SQL leg of `/api/analysis/ask`. The wrapper:
1. Calls the LLM.
2. Extracts the first ` ```sql ... ``` ` block via regex (or uses the
   raw response if no fences).
3. Strips trailing `;`.
4. Hands the result to `database.run_select_safely`, which throws on any
   non-SELECT statement.

The prompt explicitly tells the model to add `LIMIT 200` and to never use
INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE. The runtime guard re-checks
both, so a malicious / hallucinated SQL response cannot mutate data.

### `reconciliation_prompt.txt`
Placeholders: `{start_date}`, `{end_date}`, `{summary}`, `{anomalies}`.

Drives `/api/reports/reconciliation`. Required headings:
1. `### Reconciliation Summary`
2. `### Coverage`
3. `### Flagged vs. Accepted`
4. `### Risk Highlights`
5. `### Open Questions`

Fallback: a brief deterministic summary built from the supplied counts.

## Editing prompts safely

1. Run the backend and edit a prompt. Uvicorn's `--reload` watches
   `prompts/` (configured in `run_backend.py`) so the next request picks
   up the change.
2. The file is cached in process memory until the next reload. If you
   edit a prompt while reload is off, restart the backend.
3. When you change a placeholder, update the matching `format(...)` call
   in `llm_service.py` in the same commit -- otherwise you'll get a
   `KeyError` at runtime.

## Planned prompt work

- **Memory-backed prompts.** Wire `memory.json` (or a DB table) into
  `anomaly_prompt.txt` so prior runs influence detection. PLANNED.
- **Per-domain prompt sets.** Today every prompt is hard-coded for the
  duplicate-AP-invoice dataset. Multi-domain support requires either a
  prompt directory per domain or templated table descriptions. PLANNED.
- **Streaming responses.** The wrapper is blocking; switching to LangChain
  streaming would let the UI render tokens as they arrive. PLANNED.
- **Prompt evaluations / unit tests.** No automated checks today.
  PLANNED.

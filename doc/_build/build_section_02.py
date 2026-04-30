"""Generate doc/lld_section_02.docx — Section 2: Agent Identity, Persona & Voice."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _docx_utils import LLDBuilder  # noqa: E402

OUT = HERE.parent / "lld_section_02.docx"


def build() -> None:
    b = LLDBuilder("Anomaly Agent — LLD Section 2: Agent Identity, Persona & Voice")

    # ------------------------------------------------------------------ §2
    b.h1("2. Agent Identity, Persona & Voice")
    b.p(
        "Section 2 defines who the agent is, how it talks, and how that voice "
        "is enforced in code. Every behavioural claim ties back to a prompt "
        "file under prompts/ or a fixed string in backend/main.py."
    )

    # 2.1 -------------------------------------------------------------- Persona
    b.h2("2.1 Persona Definition")

    b.kv_table([
        ("Name (user-facing)",      "\"Anomaly Detection Agent\""),
        ("Internal product name",   "Anomaly Agent (sister product to AdminFee Agent)"),
        ("Role",                    "Specialist assistant for duplicate-AP-invoice anomaly review"),
        ("Expertise level",         "Finance audit + MySQL data review; not a general-purpose chatbot"),
        ("Tone",                    "Direct, professional, audit-grade"),
        ("Register",                "Business-formal; uses markdown formatting (lists, tables, code spans)"),
        ("Speaking voice",          "First-person singular when greeting; otherwise impersonal report style"),
        ("Anchor strings",          "GREETING constant in backend/main.py defines the opening turn verbatim"),
    ])

    b.p("The greeting that establishes the persona on every new session:")
    b.code(
        "Hello — welcome to the **Anomaly Detection Agent**. "
        "Please provide a date range (e.g. `2024-12-25 to 2025-12-25`) "
        "or type `exit` to quit."
    )

    b.status_table([
        (
            "Fixed greeting + name on every new session",
            "IMPLEMENTED",
            "backend/main.py constant GREETING; surfaced via /api/agent/start.",
        ),
        (
            "Persona reinforced through every prompt (\"You are ...\")",
            "IMPLEMENTED",
            "prompts/*.txt — each opens with a role line (e.g. \"You are the Anomaly Agent's analyst chatbot.\")",
        ),
        (
            "Single, consistent persona across panels (chat / status / analyst)",
            "IMPLEMENTED",
            "All three panels render through the same prompt set; no per-panel persona drift.",
        ),
        (
            "Configurable persona / multi-persona support (e.g. \"strict auditor\" vs. \"explainer\")",
            "PLANNED",
            "Persona is hard-coded in prompt files. roadmap Phase 4 (multi-domain) and §5.1.",
        ),
        (
            "Localized persona (non-English variants)",
            "PLANNED",
            "All prompts and fixed strings are English-only.",
        ),
    ])

    # 2.2 -------------------------------------------------------------- Voice & Style
    b.h2("2.2 Voice & Style Guide")

    b.h3("Defaults enforced by prompts")
    b.kv_table([
        ("Sentence length",
         "Short. anomaly_chat_prompt → \"Direct, 2–6 sentences.\" "
         "status_prompt → \"1–4 sentences.\" "
         "reconciliation_prompt → \"under ~250 words.\""),
        ("Formality",
         "Business-formal. No slang, no humor, no exclamatory tone."),
        ("Humor / personality",
         "None. Prompts give zero room for jokes; tone is auditor-grade."),
        ("Markdown",
         "Required. anomaly_format_prompt → \"Use markdown only — no HTML.\" "
         "Tables for evidence; inline code for field names."),
        ("Citations",
         "Always cite `invoice_id` when referring to a specific record "
         "(anomaly_chat_prompt). Field names in inline code spans."),
        ("Section headings",
         "Fixed required headings in two prompts: anomaly_format_prompt "
         "(Executive Summary / Findings by Severity / Detailed Anomaly Table / "
         "Recommended Next Steps) and reconciliation_prompt "
         "(Reconciliation Summary / Coverage / Flagged vs. Accepted / "
         "Risk Highlights / Open Questions)."),
        ("Emoji policy — fixed strings",
         "Mixed. backend/main.py uses ✅, ⚠️, ❌ glyphs in three fixed "
         "strings (pipeline triggered, soft failure, hard failure). "
         "These are status accents, not decoration."),
        ("Emoji policy — LLM output",
         "Discouraged but not explicitly forbidden in prompts; LLM rarely "
         "emits emoji given the audit-grade tone. PLANNED: add explicit "
         "\"no emoji in LLM output\" rule to every prompt."),
    ])

    b.h3("Frontend rendering rules")
    b.bullets([
        "Markdown is parsed by a hand-rolled component "
        "(frontend/src/components/MarkdownRenderer.jsx). "
        "Supported: H1–H4 (rendered as H2–H5 to avoid clashing with panel "
        "headings), bold, italic, inline code, fenced code blocks, ordered "
        "and unordered lists, GitHub-style tables, links.",
        "All inline content is HTML-escaped before tag injection — there is "
        "no path for an LLM response to inject script tags.",
        "Code blocks render with a `lang-<name>` class; the SQL view in the "
        "analyst panel exploits this for the `lang-sql` style.",
        "Long status answers and reconciliation reports are scrolled inside "
        "the panel, not the page — see .analysis-output overflow rule in "
        "frontend/src/index.css.",
    ])

    b.status_table([
        (
            "Sentence-length, markdown, and citation rules in prompts",
            "IMPLEMENTED",
            "prompts/anomaly_chat_prompt.txt, prompts/status_prompt.txt, prompts/reconciliation_prompt.txt.",
        ),
        (
            "Required-headings contract for report prompts",
            "IMPLEMENTED",
            "prompts/anomaly_format_prompt.txt (4 sections), prompts/reconciliation_prompt.txt (5 sections).",
        ),
        (
            "Markdown renderer with HTML escape + table support",
            "IMPLEMENTED",
            "frontend/src/components/MarkdownRenderer.jsx escapeHtml + parseTable.",
        ),
        (
            "Style-rule consistency between prompts and fixed agent strings (emoji)",
            "PARTIAL",
            "main.py uses ✅/⚠️/❌ emojis in three messages; prompts neither encourage nor forbid emoji explicitly.",
        ),
        (
            "Lint-style validation that LLM output meets the required heading set",
            "PLANNED",
            "No automated post-check on LLM output today.",
        ),
        (
            "Style guide file in repo for prompt authors",
            "PLANNED",
            "Voice rules live inside individual prompts; no central STYLE.md.",
        ),
    ])

    # 2.3 -------------------------------------------------------------- Principles
    b.h2("2.3 Communication Principles")

    b.h3("Principles the prompts enforce")
    b.bullets([
        "Honesty over fluency. anomaly_chat_prompt: \"If the answer is not "
        "supported by the context, say so plainly and suggest what "
        "information would be needed.\" The chat agent never invents columns "
        "or invoice IDs.",
        "Epistemic humility. status_prompt: \"If the question is outside "
        "this scope, say so.\" The agent doesn't pretend to know the state "
        "of unrelated systems.",
        "Pushback on invalid input. The chat FSM responds to a malformed "
        "date with \"I couldn't read that date range\" plus an example, "
        "instead of guessing (backend/main.py::_handle_await_dates → "
        "validate_date_range).",
        "Confirmation before side effects. The agent never writes to "
        "anomaly_metadata or triggers Airflow on first turn — it parses, "
        "echoes the parsed range, and waits for `confirm` "
        "(backend/main.py::_handle_confirm).",
    ])

    b.h3("Failure-mode behavior")
    b.kv_table([
        ("LLM unreachable / quota exhausted",
         "Each public function in backend/llm_service.py has a "
         "deterministic fallback. normalize_date_range falls back to a "
         "regex; format_report builds a plain markdown table; "
         "reconciliation_report emits a static summary with the real "
         "counts. The user sees something useful, not an error toast."),
        ("LLM returns malformed JSON",
         "Strip ```json fences, try json.loads, log a warning, drop the "
         "chunk. The remainder of the run continues."),
        ("Airflow SSH fails",
         "metadata table is already written; assistant says \"Metadata was "
         "written but the Airflow trigger failed\" with stderr in a fenced "
         "block, and instructs the user to reply `retry`. No silent failure."),
        ("DB unreachable",
         "/api/health flips to db: \"down\". Status panel surfaces an "
         "amber backend badge in the header (App.jsx HealthBadge)."),
    ])

    b.status_table([
        (
            "Pushback on invalid date input (no guessing)",
            "IMPLEMENTED",
            "backend/llm_service.py::validate_date_range + _handle_await_dates retry loop.",
        ),
        (
            "Confirmation gate before any side effect",
            "IMPLEMENTED",
            "FSM state STEP_CONFIRM in backend/session_manager.py, gated by _handle_confirm.",
        ),
        (
            "Honest \"I don't know\" instructions in chat prompts",
            "IMPLEMENTED",
            "prompts/anomaly_chat_prompt.txt + prompts/status_prompt.txt.",
        ),
        (
            "Soft-fail on Airflow SSH error (assistant explains, offers retry)",
            "IMPLEMENTED",
            "backend/main.py::_trigger_pipeline STEP_ERROR branch.",
        ),
        (
            "Confidence scoring on anomalies (e.g. \"high / medium / low confidence\")",
            "PARTIAL",
            "Anomalies carry severity (low/medium/high), but no separate confidence dimension. roadmap §5 + §17.",
        ),
        (
            "Refusal templates for out-of-scope questions",
            "PLANNED",
            "The chat prompt instructs the model to say so, but there is no canonical refusal template.",
        ),
    ])

    # 2.4 -------------------------------------------------------------- Brand Alignment
    b.h2("2.4 Brand Alignment")

    b.h3("Visual & UX parity with AdminFee Agent")
    b.bullets([
        "Same 3-panel layout: chat (left) / status monitor (center) / "
        "analyst (right). frontend/src/App.jsx mirrors AdminFee's "
        "App.jsx structure verbatim.",
        "Same header treatment: brand dot + product name + tagline + "
        "health badge + New Session button "
        "(frontend/src/index.css .app-header).",
        "Same monospace status chips for FSM steps "
        "(.step-chip with per-state color variants).",
        "Same dark theme via CSS variables in :root "
        "(--bg, --accent, --ok, --warn, --err) so a switch to the AdminFee "
        "theme is one variable change.",
        "Same step-based FSM in the backend; AdminFee Agent uses the same "
        "session_manager pattern (UUID dict, threading.Lock).",
    ])

    b.h3("Brand voice continuity")
    b.bullets([
        "Both agents introduce themselves with the product name in bold "
        "and ask for a single concrete input before doing anything.",
        "Both products use markdown reports with required section "
        "headings to make outputs scannable for auditors.",
        "Both products surface their backend health in the header so the "
        "operator can tell at a glance whether the LLM/DB are reachable.",
    ])

    b.status_table([
        (
            "Layout / theme parity with AdminFee Agent",
            "IMPLEMENTED",
            "frontend/src/App.jsx + frontend/src/index.css.",
        ),
        (
            "Shared component library / design tokens package",
            "PARTIAL",
            "Patterns are duplicated between repos; no shared package yet. CSS variables make the swap trivial.",
        ),
        (
            "Brand kit (logo, color palette, typography spec) in repo",
            "PLANNED",
            "No assets folder; brand-dot is a CSS pseudo-element, no actual logo.",
        ),
        (
            "Light theme + theme switcher",
            "PLANNED",
            "Variables are dark-only today; the var() structure already supports a sibling [data-theme=\"light\"] block.",
        ),
        (
            "Internationalisation (i18n) of UI strings",
            "PLANNED",
            "All UI copy is inline English strings; no i18n framework.",
        ),
    ])

    # 2.5 -------------------------------------------------------------- Example Interactions
    b.h2("2.5 Example Interactions")
    b.p(
        "Each example below is a literal transcript of what the FSM produces "
        "given the input. Assistant turns are constructed by "
        "backend/main.py + prompts; user turns are exactly what the analyst "
        "types in the chat panel."
    )

    b.h3("Example 1 — Happy path: greeting → confirm → trigger")
    b.code(
        "AGENT: Hello — welcome to the **Anomaly Detection Agent**. "
        "Please provide a date range (e.g. `2024-12-25 to 2025-12-25`) "
        "or type `exit` to quit.\n"
        "\n"
        "USER: 2024-01-01 to 2024-12-31\n"
        "\n"
        "AGENT: I parsed:\n"
        "\n"
        "- **Start date:** `2024-01-01`\n"
        "- **End date:** `2024-12-31`\n"
        "\n"
        "Reply `confirm` to run the anomaly pipeline or send a new range.\n"
        "\n"
        "USER: confirm\n"
        "\n"
        "AGENT: ✅ Anomaly pipeline triggered.\n"
        "\n"
        "- **Run ID:** `anomaly_20260101_143012`\n"
        "- **Range:** `2024-01-01` → `2024-12-31`\n"
        "\n"
        "Watch the **Status Monitor** panel for progress."
    )

    b.h3("Example 2 — Pushback on invalid input")
    b.code(
        "USER: last quarter sometime\n"
        "\n"
        "AGENT: I couldn't read that date range (Missing start or end date). "
        "Please try again, e.g. `2024-01-01 to 2024-12-31`."
    )
    b.p(
        "The fallback path: when the LLM cannot extract dates, the regex "
        "fallback in backend/llm_service.py::_normalize_with_regex returns "
        "(None, None); validate_date_range flags it; the agent does not "
        "guess."
    )

    b.h3("Example 3 — Soft failure of the Airflow trigger")
    b.code(
        "USER: confirm\n"
        "\n"
        "AGENT: ⚠️ Metadata was written but the Airflow trigger failed:\n"
        "\n"
        "```\n"
        "ssh: connect to host 172.31.25.132 port 22: Connection timed out\n"
        "```\n"
        "\n"
        "Fix the SSH / DAG configuration and reply `retry`."
    )

    b.h3("Example 4 — Analyst follow-up Q&A")
    b.code(
        "USER (analyst panel): Which vendor has the most duplicates?\n"
        "\n"
        "AGENT: Vendor `ACME Logistics` accounts for 6 of the 17 detected "
        "duplicates, all in the `2024-Q3` window. Two of those (`INV-1042`, "
        "`INV-1071`) are exact-amount near-duplicates separated by 2 days; "
        "the other four are split-payment patterns under the `vendor_alias` "
        "value `ACME LOG.`\n"
        "\n"
        "[expandable: Generated SQL]\n"
        "SELECT vendor_name, COUNT(*) AS duplicate_count\n"
        "FROM anomaly.duplicate_ap_invoice\n"
        "GROUP BY vendor_name\n"
        "ORDER BY duplicate_count DESC\n"
        "LIMIT 200"
    )
    b.p(
        "The natural-language answer is produced by chat_about_anomalies "
        "(prompts/anomaly_chat_prompt.txt). The SQL leg is opportunistic — "
        "generate_sql + run_select_safely; if generate_sql returns empty or "
        "the SQL is rejected, the answer still renders without the "
        "expandable block."
    )

    b.h3("Example 5 — Status Q&A from the centre panel")
    b.code(
        "USER: How many high-severity anomalies are there?\n"
        "\n"
        "AGENT: There are 4 high-severity anomalies in the current run "
        "(out of 17 total). The latest update was at 14:31 UTC."
    )

    b.status_table([
        (
            "Greeting / confirm / trigger transcripts",
            "IMPLEMENTED",
            "backend/main.py constants and _trigger_pipeline output strings.",
        ),
        (
            "Pushback transcript (regex fallback path)",
            "IMPLEMENTED",
            "backend/llm_service.py::_normalize_with_regex + validate_date_range.",
        ),
        (
            "Airflow soft-failure transcript",
            "IMPLEMENTED",
            "backend/main.py::_trigger_pipeline result.ok=False branch.",
        ),
        (
            "Analyst Q&A with optional SQL",
            "IMPLEMENTED",
            "POST /api/analysis/ask in backend/main.py + frontend AnalysisPanel.jsx <details> block.",
        ),
        (
            "Persistent transcripts across sessions / replay",
            "PLANNED",
            "Session.history is in-process only; lost on backend restart. roadmap Phase 1.",
        ),
        (
            "\"Gold standard\" reference dialogues used as eval fixtures",
            "PLANNED",
            "These examples are documentation only; no automated eval harness yet (§20.2).",
        ),
    ])

    b.save(OUT)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()

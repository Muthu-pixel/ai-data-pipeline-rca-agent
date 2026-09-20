# OpsFix — Pipeline Incident/RCA Agent on Claude Agent SDK

## Context

`doc/OpsFix_Agent_Design_Brief.docx` (in the `claude-agent-sdk-demo` scratch repo) specs an agent that investigates a failed Python/ETL pipeline run, classifies the root cause (schema drift, DQ issue, code bug, infra/timeout, credential/config error, resource exhaustion), and produces an evidence-backed RCA report with a suggested fix — gated by mandatory human (SRE) approval before anything is finalized. The brief assumed **LangGraph** + **Pydantic AI**. The user wants it built on the **Claude Agent SDK** instead (`claude_agent_sdk`, the Claude Code harness as a library — not the raw Messages API, not Tool Runner).

**Working mode**: the user wants to build this **step by step, one piece at a time, to understand each part** — not a single large code drop. Each implementation turn should: build one concrete step, explain what it does and why, run/show it working, and pause before moving to the next step. The user also actively steers architecture as we go (see "Decisions made along the way" below) — treat this plan as a living document, not a fixed spec.

## Status as of 2026-09-19

**Done:** schema (now 2 live categories, see decision #1), evidence-extraction tools (including a live DB schema-introspection tool, see decision #8), a real fixture pipeline now covering 3 scenarios, a shared log intake folder, a unit test suite for the tools, and **a real working end-to-end agent** (step 4): `agent/pipeline.py` runs an actual `query()` session with `read_log_file` and `get_table_schema` as SDK tools, `output_format=RCAReport`, and `main.py` calls it for real on every `FAILED` log in `RCA_LOGS`.

Verified against **both** live categories: `schema_drift` → confidence 0.97-0.98, correct category. `data_quality` → tested *before* `DATA_QUALITY` was uncommented (forced into the only available enum value, `schema_drift`) and the agent correctly self-corrected via calibration — confidence dropped to 0.15, `needs_more_context: true`, summary explicitly said "doesn't fit schema_drift" — good evidence the calibration design works. After uncommenting `DATA_QUALITY`, re-ran the same log: confidence 0.9, correct category, correct remediation (`.get()` with a default instead of a bare key lookup, quarantine bad rows instead of failing the whole batch). Both runs' evidence citations traced to real tool calls, nothing invented.

**Not started:** `eval/` (step 5 — the natural next step now that there's a real agent to score, and now 2 categories to score it against), `agent/tracer.py`, `agent/output_handling.py` (the 3-branch logic currently lives inline in `pipeline.py`, not split out yet), `agent/approval.py`.

**Not yet touched:** the `synthetic/generate_fixtures.py` idea (superseded for now — see decision #3).

**Known dead code to clean up:** `config/settings.py` (`openai_api_key`/`model_name`) is now unused by anything — flagged to the user, not yet removed pending confirmation. The `openai` dependency was already dropped from `pyproject.toml`.

## Decisions made along the way (deviations from the original design)

These are real steering decisions from the user during implementation — later sessions should treat these as settled, not revisit them without reason:

1. **`FailureCategory` is scoped down and uncommented one category at a time**, not all 6 at once. `schema_drift` first; `data_quality` uncommented in this session once a real fixture + working classification existed for it (see decision #11). The remaining 4 (`code_bug`, `infra_timeout`, `credential_config`, `resource_exhaustion`) stay commented out in `agent/schemas.py` until each gets the same treatment. Do not add more categories preemptively.
   - **Useful side-effect observed**: testing an out-of-scope category (running the agent on the `data_quality` log *before* uncommenting it) is actually a good calibration test — the agent was structurally forced to output the only available enum value, but used `confidence`/`needs_more_context`/`summary` to honestly flag "this doesn't really fit." Worth doing deliberately for each new category before uncommenting it, not just as an accident.
2. **No fabricated ground truth anywhere in the evidence chain.** An early version of the schema-diff tool read an `expected_schema` from a JSON file the agent repo itself authored — the user correctly called this out as answer-leaking, not evidence-gathering. It was deleted. Same reasoning later removed `validate.py`'s proactive "Missing expected columns" warning in the sample pipeline itself (also answer-leaking) and the corresponding `extract_validation_warning` tool. The only root-cause evidence now available to the (future) agent is what a real pipeline failure actually produces: the traceback, the exception, and what columns actually came back — it has to reason from that, the way an SRE would.
3. **Real runnable pipeline instead of synthetic fixture files.** Rather than building `synthetic/generate_fixtures.py` (parametrized fault-injection templates producing static `run.log` + `ground_truth.json` files), the user asked for something more real: an actual runnable ETL pipeline, backed by a real SQL Server database, that produces genuine Python tracebacks by actually failing. This lives in a **sibling project**, not inside this repo:
   `C:\Users\91978\Documents\2026-AI-projects\sample-pipeline\`
   - `extract.py` / `validate.py` / `transform.py` / `main.py` — a small multi-module orders ETL, run as `python main.py <scenario>`
   - `db_config.py` / `setup_db.py` — connects to `localhost\JUST_INTO_DS` (SQL Server, Windows Integrated auth, ODBC Driver 17, confirmed working), dedicated database `rca_orders_demo` with tables: `dbo.orders_healthy` (`customer_id`), `dbo.orders_drift` (`cust_id`, a real DB-level schema mismatch), `dbo.orders_dq` (has a `metadata` JSON column; 1 of 20 rows is missing the `promo_code` key it's supposed to have — a real per-record data gap, decision #11)
   - `enrich.py` (new, `data_quality` scenario only) — `enrich_orders()` loops rows, does `json.loads(row["metadata"])["promo_code"]`; crashes for real on the one bad row
   - Originally built as two separate repos (`sample-pipeline-healthy` / `sample-pipeline-schema-drift`); consolidated into one repo with a `scenario` CLI arg once the user flagged the duplication
   - Has its own `.venv` (installed `pyodbc`), separate from this repo's `.venv`
   - The `synthetic/generate_fixtures.py` step in the original build order is **superseded by this** for now. Revisit only if/when we need many fixture variants at once (this approach doesn't scale to a full 6-category × several-variant corpus as easily as a generator would) — that's a step-8-ish concern, not now.
4. **Logs land in a shared, external folder**, not `data/logs/` inside this repo:
   `C:\Users\91978\Documents\2026-AI-projects\RCA_LOGS\`
   - Every pipeline run writes its own file, named `<repo_name>_<timestamp>.log` (e.g. `sample-pipeline_20260919_180757.log`) — no overwriting, no cross-run log accumulation
   - The scenario name was originally in the filename too; removed on request since it's redundant with the `Scenario: <name>` line already logged inside the file — filenames should identify the *repo*, log content should identify everything else (including a `Source file: <path>` line so a log is self-describing even if separated from its folder)
   - This repo's `main.py` currently scans **all** `*.log` files in `RCA_LOGS` (no time-based filter yet — explicitly deferred by the user until "one flow is completed")
5. **`main.py` evolved from a manual evidence walker into the real entrypoint.** It originally called `extract_error_sections` → `parse_traceback` → `extract_source_file`/`extract_columns_found` itself and printed a dict (built to prove the tools worked before an agent existed). As of step 4 it's simpler: it only uses the tools to classify each log as `SUCCESS`/`FAILED` (cheap, no LLM cost), then calls `agent.pipeline.investigate_log()` — the real agent — on every `FAILED` log and prints the resulting `RCAReport` JSON. `SUCCESS` logs are skipped entirely (nothing to investigate, and no reason to spend a real API call on them).
6. **Original baseline commit**: the OpenAI single-shot spike (`get_rca_analysis`, forced tool-choice) plus a couple of real bugfixes in `tools.py` (explicit file encoding, an infinite-loop guard in `extract_error_sections` when a traceback never hits an `Error`/`Exception` line) were committed as-is first, before any rebuild — commit `8e84279` on `feature/dataset-exploration`. `agent/pipeline.py` has since been fully replaced (step 4, this session) — the OpenAI spike is gone, along with the `openai` dependency; `config/settings.py` (`openai_api_key`/`model_name`) is now dead code, not yet deleted.
7. Confirmed via research: **the Claude Agent SDK has no Gemini-ADK-style built-in web dev UI** (no `adk web` equivalent). The documented dev/test workflow is console-stream based — run a script using `query()`/`ClaudeSDKClient`, stream `AssistantMessage`/`ResultMessage` to stdout — plus `claude plugin eval` for automated test cases, hooks for interception, and session resume for debugging multi-turn runs. Testing `agent/pipeline.py` will follow this pattern (run it against a real `RCA_LOGS` file, read the streamed console output), not a browser UI.
8. **`extract_columns_found` (regex on log text) was replaced with a live DB tool.** The user pointed out that regex-parsing a "Columns found: [...]" line the pipeline happened to log is the same hardcoding problem as decision #2, just in a new spot — since we have real SQL Server access, there's no reason to trust a log string over asking the database directly. Replaced with `extract_queried_table(log_text)` (tiny, honest use of regex — just identifies *which table* a run touched, from `Querying dbo.<table> from SQL Server`) + `get_table_schema(table_name)` (queries `INFORMATION_SCHEMA.COLUMNS` live). This repo now has its own `config/db_config.py` and its own `pyodbc` dependency, independent of `sample-pipeline`'s.
9. **Not every helper function needs to be an agent-facing SDK tool.** Worked through with the user: a tool is only necessary when the LLM cannot get that information itself — i.e. it reaches outside the LLM's context (real file I/O, a real DB query). Text-parsing helpers (`extract_error_sections`, `extract_source_file`, `extract_queried_table`, `parse_traceback`) operate on text the LLM already has after calling `read_log_file`, so the LLM can reason over that raw text directly. **Decision: only `read_log_file` and `get_table_schema` are exposed as SDK tools in `agent/pipeline.py`.** The parsing helpers stay as internal Python functions, used only by `main.py`'s cheap pre-classification step (SUCCESS/FAILED) and by `tests/test_tools.py` — not handed to the agent. This is deliberate: it tests whether the agent can actually do the detective work over raw text, not whether it can call a tool we pre-chewed the answer into.
10. **`tests/test_tools.py` was written before step 4** (unit tests, no LLM/agent involved) — covers all the pure-Python tool functions plus two live queries against the real `orders_healthy`/`orders_drift` tables. Distinguish this from `eval/` (step 5, not started): unit tests check the tools are correct; evals will check whether the *agent* reasons correctly using them. Writing evals before step 4 existed would have had nothing to measure.
11. **`sample-pipeline` is a general real-failure generator, not a database-only tool.** The user was explicit: don't couple the repo's identity to SQL Server just because the first 3 scenarios happened to be DB-driven — its actual job is "produce whichever REAL error is natural for a given failure category," and every future category (`code_bug`, `infra_timeout`, `credential_config`, `resource_exhaustion`) should use whatever real mechanism fits best (a real bad network call for `infra_timeout`, a real bad credential for `credential_config`, a real memory/resource limit for `resource_exhaustion`, etc.) rather than forcing another SQL table into existence. The one fixed contract that doesn't change: still a *real* failure (real traceback from real execution, never hand-typed), and it still writes a real log to `RCA_LOGS/` the same way every scenario so far has. `data_quality` (decision above) is the first proof this pattern extends past schema/DB issues while staying real.
    - Along the way, found and fixed a real bug this surfaced: log filenames only had second-precision timestamps, so two scenarios run back-to-back could land in the same file and get silently merged (`FileHandler` appends by default) — a `FAILED` and a `SUCCESS` run ended up in one log. Fixed with microsecond precision (`%Y%m%d_%H%M%S_%f`). Worth remembering if log naming ever changes again: whatever scheme is used needs to survive rapid sequential runs, not just manual one-at-a-time testing.
12. **`FailureCategory` gained a permanent `OTHER = "other"` catch-all**, on top of the "uncomment one at a time" rollout from decision #1 — the two ideas are complementary, not in tension. `OTHER` is not part of that rollout and is never commented out: it's how the agent should honestly answer when a real failure doesn't fit any currently-live category, instead of being structurally forced into the closest wrong one (exactly what happened testing `data_quality` before it was uncommented, decision #1's side-note). The user's framing: route unclassifiable failures into a common bucket now, review that bucket periodically, and let recurring patterns in it justify adding the *next* real category (with its own `sample-pipeline` fixture) — the discovery mechanism for what to build next, driven by real data rather than by guessing from the original 6-category brief. Reinforced structurally, not just via prompt wording: `RCAReport` has a `model_validator` that raises if `category == OTHER` and `needs_more_context` isn't `True` — verified both the accept and reject paths with a plain Pydantic round-trip (no LLM call needed for this one). `agent/prompts.py` updated to explain when to use `other` and to require the summary explain what the real category might actually be.
13. **`agent/results.py` (new) persists every `RCAReport` as a CSV row** to `RCA_LOGS/results/rca_reports.csv` (one shared file, appended to — not one file per report). Two id columns by design: `run_id` (the log file's own name — identifies *which pipeline run* this report is about) vs `run_id_unique_id` (a fresh UUID per call — identifies *this particular analysis* of that run, since the same log can legitimately be investigated more than once, e.g. re-running the agent or a later eval loop, and each attempt should get its own row rather than overwrite the last). Nested/variable-length fields (`evidence`, `remediation.steps`) are JSON-encoded into single cells since CSV has no native nesting; `impact`'s 3 fields and `remediation.summary`/`risk_notes` are flattened to their own columns since they're plain strings and more useful readable directly in a spreadsheet. `append_report()` takes an optional `csv_path` override specifically so `tests/test_results.py` never writes to the real results file. Wired into `main.py`: every real `investigate_log()` result gets appended here in addition to being printed. This is effectively the seed of `eval/report.py` from the original build order — a running history to eventually score against, not just a one-off print.

### Verified Claude Agent SDK mechanics (confirmed against live docs, not assumed)

- **Tool tiers / ReAct loop** → the SDK's built-in agent loop + in-process custom tools: `@tool(name, description, input_schema)` decorator + `create_sdk_mcp_server(name, tools=[...])`, passed via `ClaudeAgentOptions(mcp_servers=..., allowed_tools=["mcp__opsfix__<tool>", ...])`. No Bash/Write/Edit in the allowlist → auto-remediation is structurally impossible (matches the brief's explicit out-of-scope item), not just discouraged. **Important architectural point** (came up explaining this to the user): tool results are fed back to the model incrementally, one turn at a time — Claude calls a tool, sees that result, decides the next action — not batched and delivered only once the loop ends. The loop "finishing" refers to Claude choosing to stop calling tools and emit its final answer, not to when it receives results.
- **Structured RCA report** → `ClaudeAgentOptions(output_format={"type":"json_schema","schema": RCAReport.model_json_schema()})`, set once alongside the tools. This is a documented pattern: the agent tool-calls freely during the loop, and the SDK validates + internally retries the final turn against the schema. Result lands in `ResultMessage.structured_output`, not the text stream. **Must branch on `subtype == "success" and structured_output is not None`** — a `"success"` subtype with `structured_output=None` is a documented failure mode, as is `subtype == "error_max_structured_output_retries"`. Keep `RCAReport` shallow-ish (deeply-nested required fields are a documented driver of retry failures); make the calibration signal ("not confident, need more context") a first-class field, not an afterthought.
- **Human approval gate** → no SDK hook sits between "structured output produced" and "caller receives it," so this is correctly an **application-level** gate: present the parsed `RCAReport` via CLI after the session ends, before persisting/finalizing. The narrow `allowed_tools` list is the structural guarantee against auto-remediation; a `PreToolUse` deny-by-default hook is defense-in-depth.
- **Session pause/resume** → `ClaudeAgentOptions(resume=session_id)`, session_id captured from the init message.
- **Multi-agent "crew"** → explicitly *not* built for v1 (brief: single agent + 4-5 tools is right-sized). `AgentDefinition`/`options.agents` is the documented extension point if the project later grows into multi-pipeline cascading RCA — noted, not built.
- **CORRECTION (learned the hard way in step 4): `pip install claude-agent-sdk` does NOT bundle the native `claude.exe` binary on this machine.** The wheel installs fine and imports fine, but calling `query()`/`ClaudeSDKClient` raises `CLINotFoundError` until the SDK can find a real `claude.exe`. Fix used here: the VS Code Claude Code extension already ships one, so `agent/pipeline.py` has a `_find_cli_path()` helper that globs `~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe` (sorted, takes the newest) and passes it as `ClaudeAgentOptions(cli_path=...)`. The officially "correct" fix per the SDK's own error message is `irm https://claude.ai/install.ps1 | iex` to install the standalone native CLI — not done here since the VS Code extension's copy already works; revisit if that extension is ever uninstalled or its path pattern changes.
- **GOTCHA: returning early from inside `async for message in query(...)`** (the natural thing to do once you see the `ResultMessage` you want) **can raise a benign `RuntimeError: aclose(): asynchronous generator is already running`** during cleanup, from the SDK's subprocess transport. Result value is unaffected, but it's noisy. Fix used in `investigate_log_async`: hold the `query()` generator in a variable, `break` out of the loop instead of returning from inside it, then explicitly `await messages.aclose()` in a `finally` block wrapped in `try/except RuntimeError: pass`.
- No built-in web dev UI (see decision #7 above) — test via console streaming, not a browser.

## Architecture / File Structure (current real state, not the original guess)

```
ai-data-pipeline-rca-agent/                 # this repo
  .venv/                          # DONE — pydantic, pyodbc, pytest, claude-agent-sdk all installed
  agent/
    tools.py                      # DONE (evolved twice from the original plan):
                                   #   read_log_file, extract_error_sections (bugfixed),
                                   #   extract_source_file, extract_queried_table, parse_traceback,
                                   #   get_table_schema (live SQL Server query, decision #8)
                                   #   -- no get_expected_schema/diff_schema/extract_validation_warning/
                                   #      extract_columns_found, all removed as answer-leaking or
                                   #      hardcoded (decisions #2, #8)
    schemas.py                    # DONE: RCAReport, FailureCategory (schema_drift only, rest
                                   #   commented), EvidenceCitation, ImpactAnalysis,
                                   #   RemediationSuggestion
    prompts.py                    # DONE: SYSTEM_PROMPT -- role, the 2 available tools, the
                                   #   no-Bash/no-fix-it-yourself constraint, single-category
                                   #   scope note, evidence-citation requirement
    tracer.py                     # NOT STARTED: PreToolUse/PostToolUse hooks -> JSONL transcript
    output_handling.py            # NOT STARTED as a separate file -- the 3-branch
                                   #   ResultMessage logic currently lives inline in pipeline.py's
                                   #   investigate_log_async; split out if/when it gets reused
    approval.py                   # NOT STARTED -- deliberately late
    pipeline.py                   # DONE (step 4, this session): real ClaudeSDKClient-style session
                                   #   via query(). Only read_log_file + get_table_schema are
                                   #   exposed as SDK tools (decision #9); output_format=RCAReport;
                                   #   cli_path resolved via _find_cli_path() (see CORRECTION above);
                                   #   investigate_log(path) is the sync entrypoint main.py calls.
                                   #   Verified end-to-end against the real schema_drift fixture.
  config/
    settings.py                   # DEAD CODE -- nothing imports it anymore (see Status above),
                                   #   flagged to user, not yet deleted
    db_config.py                  # DONE (new, decision #8): SQL Server connection string,
                                   #   same instance/DB as sample-pipeline but owned independently
  main.py                         # DONE: cheap SUCCESS/FAILED pre-check via the tools, then calls
                                   #   agent.pipeline.investigate_log() -- the real agent -- on every
                                   #   FAILED log; SUCCESS logs skipped (no LLM cost)
  pyproject.toml                  # DONE: python-dotenv, pydantic, pyodbc, claude-agent-sdk;
                                   #   openai dependency dropped (spike is gone)
  tests/test_tools.py             # DONE: unit tests for every tools.py function, including 2
                                   #   live queries against the real orders_healthy/orders_drift
                                   #   tables. No LLM involved (decision #10).
  data/logs/sample_run.log        # superseded by RCA_LOGS/ (decision #4) -- left in place,
                                   #   unused by the current flow

RCA_LOGS/                         # NEW, sibling folder -- shared log intake (decision #4)
  <repo_name>_<timestamp>.log     # e.g. sample-pipeline_20260919_180757.log

sample-pipeline/                  # NEW, sibling project -- general real-failure generator
                                   #   (decisions #3 and #11 -- not DB-only by design)
  .venv/                          # separate venv, pyodbc installed
  main.py                         # `python main.py healthy|schema_drift|data_quality`; sets up
                                   #   logging to RCA_LOGS (microsecond-precision filenames, see
                                   #   decision #11's bugfix note), orchestrates
                                   #   extract -> validate -> transform -> (enrich, data_quality only)
  extract.py                      # queries dbo.orders_healthy / orders_drift / orders_dq
  validate.py                     # generic sanity check only (no schema-specific check, see
                                   #   decision #2) -- raises if zero rows extracted
  transform.py                    # groups by customer_id -- KeyErrors on the drift table
  enrich.py                       # data_quality only: reads metadata JSON's promo_code key --
                                   #   KeyErrors on the 1-of-20 rows missing it (real per-record
                                   #   data gap, not a schema issue)
  db_config.py                    # connection string: localhost\JUST_INTO_DS, Trusted_Connection
  setup_db.py                     # one-time: creates rca_orders_demo DB + all 3 tables, seeds rows
                                   #   (future non-DB scenarios per decision #11 won't need this file)
  requirements.txt, README.md     # DONE (README not yet updated for data_quality -- TODO)
```

## Build order (eval-loop-first, step by step)

Each numbered step below is one implementation session/turn with the user — build it, explain it, demo it, pause.

1. ~~**`agent/schemas.py`**~~ **DONE** — `RCAReport` + `FailureCategory` (scoped to `schema_drift` only, see decision #1). This is also the `output_format` schema source. Round-trip verified.
2. ~~**Evidence tools**~~ **DONE, but evolved** — instead of a job-run-metadata tool + schema-diff-against-fabricated-expected-schema tool, built `extract_source_file`, `extract_columns_found`, and `parse_traceback` (structured exception/frame parsing) in `agent/tools.py`, all deriving evidence purely from real log content (decision #2). Verified against real pipeline logs, both scenarios.
3. ~~**Fixture generator + 2 fixtures**~~ **DONE, but via a different mechanism** — no `synthetic/generate_fixtures.py`; instead a real, runnable, DB-backed pipeline (`sample-pipeline/`, decision #3) covering `healthy` and `schema_drift` scenarios, writing real logs to `RCA_LOGS/` (decision #4). Revisit the generator idea only when scaling to many fixtures at once (step 8 territory).
4. ~~**`agent/pipeline.py` (minimal rewrite)**~~ **DONE (this session).** Swapped the OpenAI single-shot call for a `query()`-based Claude Agent SDK session (see decision #9 for why `query()` over `ClaudeSDKClient`: one instruction in, one structured result out, no multi-turn conversation needed). `read_log_file` + `get_table_schema` wrapped as SDK tools; `agent/prompts.py` written; `output_format=RCAReport.model_json_schema()`; starting instruction points at a log **path**, never a pre-extracted error string. Verified end-to-end against the real `schema_drift` log: correct category, confidence 0.97-0.98, evidence citations that trace to real tool calls, correct remediation naming the exact file/line. Two real gotchas hit and fixed — see the "CORRECTION" and "GOTCHA" bullets above (`cli_path` discovery, async generator cleanup).
5. **`eval/run_eval.py` + `eval/metrics.py` (minimal: classification accuracy + FP rate) — NEXT STEP, NOT STARTED.** Milestone: a scored loop exists. Everything after this is measured, not eyeballed. Trivially runnable now against the `sample-pipeline` healthy/schema_drift pair by calling `agent.pipeline.investigate_log()` (already proven working) instead of static fixture files. With only one category and 2 scenarios, expect this to start as a very small scorecard (2 runs), not a real statistical eval — that's fine, it's about proving the scoring mechanism works before the corpus grows (step 8).
6. **`agent/tracer.py`** — instrument the now-working loop; add tool-call-efficiency + latency to `metrics.py`.
7. Remaining tool tiers (logs search, dependency lineage, runbook RAG, pipeline source read) — one at a time, each paired with a new `FailureCategory` being uncommented and a new `sample-pipeline` scenario/table that actually exercises it (decision #1 + #3 combined: category and real fixture arrive together). RAG (`rag/index.py`, BM25/TF-IDF — no embeddings API needed for a small runbook corpus) arrives with the runbook tool.
8. Full corpus across all categories + healthy control set — likely where the `synthetic/generate_fixtures.py` idea gets revisited, since hand-building a `sample-pipeline` scenario per variant won't scale as well as a generator would.
9. **`agent/approval.py`** — deliberately late: pure application glue, no eval dependency.
10. **`eval/fix_validity.py`** and **`eval/llm_judge.py`** last — depend on remediation suggestions already being non-garbage.

## Key implementation notes to not relearn later

- `PreToolUse` supports `permissionDecision: "defer"` to pause a whole session for later resume — the right primitive for a future *mid-investigation* human checkpoint (not the finalize gate). Extension point, not built now.
- If unattended runs with async approval (Slack/webhook) are ever needed instead of a blocking CLI prompt, model finalization as a 9th MCP tool (`submit_rca_report`) gated by a `PreToolUse` hook returning `"ask"`/`"defer"`. v1.1 idea, not v1.
- Claude Agent SDK's implicit branching (LLM picks the next tool based on evidence so far) is the direct substitute for LangGraph's explicit conditional graph edges — a deliberate architecture substitution, not a capability gap.
- Every time a new "evidence" mechanism is added anywhere in this project (a tool, a validation check, a log line), ask: does this reveal the answer, or does it reveal a fact the agent has to interpret? Decision #2 exists because this line got crossed twice already (once in the agent repo, once in the sample pipeline itself).

## Verification

- `tests/test_schemas.py` — Pydantic round-trips for `RCAReport`. (Ad hoc round-trip already verified manually; not yet a committed test file.)
- `tests/test_output_handling.py` — all 3 `ResultMessage` branches (success+data, success+None, max-retries-error) without a live SDK call.
- `tests/test_tools.py` — each tool against real `sample-pipeline` log output, no SDK session needed. (Verified ad hoc so far; not yet a committed test file.)
- End-to-end smoke test after step 4: run the pipeline against a real `schema_drift` log in `RCA_LOGS/`, confirm `RCAReport` parses and the category is correct.
- `python -m eval.run_eval` after step 5, and again as the corpus grows; track the `eval/report.py` summary (F1, localization accuracy, FP rate, tool-call efficiency, later fix-validity/LLM-judge) across iterations.
- After step 7 (guardrails in place): attempt a tool name outside the allowlist, confirm `PreToolUse` denies it.
- Confirm resume: interrupt a run, restart with the persisted `session_id`, confirm it continues rather than restarting.

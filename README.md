# ai-data-pipeline-rca-agent
AI agent for detecting and analyzing data pipeline failures.

It reads a pipeline's real log output, investigates the failure itself using
the Claude Agent SDK (reads the log, queries the live database schema when
relevant), and produces a structured, evidence-backed root-cause report --
never a hardcoded guess. It only investigates and reports; it has no access
to Bash, file editing, or the database beyond a read-only schema lookup, so
it cannot modify the pipeline or "fix" anything itself.

# run below commands to activate virtual env
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
source .venv/Scripts/activate 
pip install -e .
# to start process
python main.py

## Prerequisites

- **A local SQL Server with the `rca_orders_demo` database, reachable and
  matching [produce-error-pipeline](../produce-error-pipeline)'s schema.**
  This base version is not portable to "any log file" -- `get_table_schema`
  is a real tool the agent calls during investigation (see the
  `get_table_schema(orders_drift)` evidence citations in existing reports),
  and it queries this exact live database. Without it reachable, schema- and
  data-quality investigations lose their strongest evidence source.
  - Reachable at `localhost\JUST_INTO_DS` (edit `config/db_config.py` if
    yours is named differently), Windows Integrated auth, ODBC Driver 17
  - Created and seeded by running `produce-error-pipeline`'s `setup_db.py`
    once (see that repo's README) -- this repo only reads from it, never
    writes
- A logged-in Claude Code session on this machine (the agent authenticates
  via that login, not a separate `ANTHROPIC_API_KEY` -- see
  `.claude/plans/opsfix-plan.md` for why)
- At least one log file in `sample_error_log/` to investigate -- these come
  from running the [produce-error-pipeline](../produce-error-pipeline)
  fixture project and copying its output over:
  ```powershell
  cd ..\produce-error-pipeline
  .venv\Scripts\python.exe main.py schema_drift   # or: healthy, data_quality, timeout
  # then copy the new file from ../RCA_LOGS/ into this repo's sample_error_log/
  ```

## What `python main.py` does

Scans every `*.log` file in `sample_error_log/`. `SUCCESS` runs are skipped
(no LLM cost). For each `FAILED` run, it runs a real agent investigation,
prints the resulting report, and appends one JSON line to a fresh
`result/rca_reports_<timestamp>.jsonl` (one file per `main.py` run, so
concurrent/repeated runs never collide).

## Project structure

```
agent/
  schemas.py      # RCAReport + FailureCategory (the categories currently supported)
  tools.py        # evidence-gathering functions: read a log, query the live DB schema, parse a traceback
  prompts.py      # the agent's system prompt
  pipeline.py     # the actual Claude Agent SDK session
  results.py      # appends each report as one JSON line to a .jsonl file
config/
  db_config.py    # SQL Server connection string
sample_error_log/ # log files to investigate (copied over from produce-error-pipeline)
result/           # rca_reports_<timestamp>.jsonl + eval_summary_<timestamp>.csv output
eval/
  run_eval.py     # scores existing rca_reports*.jsonl against ground truth (no new LLM calls)
  ground_truth.py # {scenario_name: expected_category} map, read from each log's own Scenario: line
  metrics.py      # accuracy / confidently-wrong scoring
tests/            # unit tests for the tools and results writer (no LLM calls)
```

## Tests

```powershell
python -m pytest
```

## Running the eval

Scores the investigation history already sitting in `result/rca_reports*.jsonl`
against ground truth -- it doesn't call the LLM again, so it's free to re-run
any time after `python main.py` has produced at least one report:

```powershell
python eval/run_eval.py
```

Prints overall accuracy, the confidently-wrong rate, and a per-category
breakdown, then appends one row to a fresh `result/eval_summary_<timestamp>.csv`.

## Failure Analysis

This was built step by step, and several early approaches were tried, broke,
or turned out to be the wrong design -- and were replaced. The full raw log
is `.claude/plans/opsfix-plan.md`; the entries below are the ones that
actually changed the architecture.

**Baseline spike replaced outright.** The very first working version was a
single-shot OpenAI call with forced tool-choice (`get_rca_analysis`),
committed as a baseline. It was fully replaced by a real Claude Agent SDK
agentic session (`agent/pipeline.py`) -- the `openai` dependency was dropped
entirely, not just deprioritized.

**Evidence-leaking tools were deleted twice, for the same reason.** An early
schema-diff tool read an `expected_schema` from a JSON file this repo itself
authored -- the tool was handing the agent the answer, not evidence to
reason over. It was deleted. The exact same mistake then reappeared in
`produce-error-pipeline` itself: `validate.py` had a proactive "missing
expected columns" warning, which is the identical leak in a different file.
Also deleted. Two occurrences of the same failure mode turned into a
standing design rule: *does this reveal the answer, or a fact the agent has
to interpret?*

**A regex-based evidence tool was replaced with a live DB query for the same
reason.** `extract_columns_found` parsed a `"Columns found: [...]"` line the
pipeline happened to log -- convenient, but it's trusting a string that
already looks like the answer instead of checking the real schema. Replaced
with `get_table_schema`, which queries `INFORMATION_SCHEMA.COLUMNS` on the
live database directly.

**A synthetic fixture generator was abandoned for a real, runnable
pipeline.** The original plan called for `synthetic/generate_fixtures.py` --
parametrized fault-injection templates producing static log files plus a
ground-truth file. That was scrapped in favor of `produce-error-pipeline`: a
real ETL that fails for real and produces a genuine Python traceback. More
realistic, at the acknowledged cost that it won't scale to a full
multi-category corpus as easily as a generator would -- a tradeoff accepted
deliberately, not overlooked.

**A planned metric didn't actually apply to this architecture.** The
original eval plan called for "accuracy + false-positive rate," where FP
meant "the agent said FAILED on a healthy run." That can't happen here --
`SUCCESS`/`FAILED` is decided by deterministic Python before the agent is
ever invoked, so there's no agent-level false positive to measure. Replaced
with `confidently_wrong` (wrong category *and* `needs_more_context == False`)
-- the failure mode that's actually dangerous for this system: a wrong
answer presented as trustworthy.

**Two environment failures, not logic bugs.** `pip install claude-agent-sdk`
doesn't bundle the native `claude.exe` binary on this machine, so
`query()` raised `CLINotFoundError` until `pipeline.py` was given a
`_find_cli_path()` fallback that locates the binary the VS Code Claude Code
extension already ships. Separately, returning early from inside
`async for message in query(...)` raised a benign but noisy
`RuntimeError` during subprocess cleanup -- fixed by holding the generator,
`break`-ing instead of returning, and explicitly `await`-ing `aclose()` in a
guarded `finally`.

**A stray empty file silently shadowed a real package.** A leftover empty
`eval.py` at the project root predated the `eval/` package and was shadowing
it -- `from eval.metrics import ...` was silently resolving to the empty
file instead of the real module. Found while wiring up the eval loop;
deleted.

**A real concurrency bug surfaced only under rapid repeated runs.** Log
filenames originally had second-precision timestamps, so two scenarios run
back-to-back could land in the same file and get silently merged (log
handlers append by default) -- a `FAILED` and a `SUCCESS` run ended up in
one log file. Fixed with microsecond-precision filenames. It only showed up
once runs were fired in quick succession, not during one-at-a-time manual
testing.

**More recently: the results format itself was wrong twice.** Reports were
first written as CSV rows, with `evidence` JSON-encoded into a single cell
and `remediation.steps` joined into one string. That broke as soon as
someone actually opened the file -- multi-line joined text inside a quoted
CSV cell rendered as extra rows in some viewers, and the nested structure
was lost either way. Replaced with JSON Lines (`.jsonl`): one full JSON
object per report, so `evidence` and `remediation.steps` keep their real
list structure instead of being flattened into text. Separately, the
results and log-intake paths originally lived in a shared folder one level
above every project (`../RCA_LOGS/`); a fixed shared filename there also
caused a real `PermissionError` the first time it was left open in Excel
during a run. Both problems were solved together by moving to
timestamped, per-run files (`rca_reports_<timestamp>.jsonl`,
`eval_summary_<timestamp>.csv`) inside this repo's own `sample_error_log/`
and `result/` folders -- no shared external path, no fixed filename to
collide on or lock.

**A third category was wired up, and it exposed a real gap in its own
fixture.** `INFRA_TIMEOUT` sat commented out until `produce-error-pipeline`
grew a real `timeout` scenario for it (a join missing its effective-date
predicate, run against a short pyodbc query timeout). The first live run
against it surfaced something the design didn't anticipate: the query took
~84 seconds to fail, not the ~3 seconds the timeout was configured for, and
the final error was a generic `pyodbc.Error: ('HY000', 'The driver did not
supply an error!')`, not a clean "query timeout expired." The agent handled
this correctly on its own -- it classified `infra_timeout` (right answer),
but lowered confidence to 0.6 and set `needs_more_context: true`, explicitly
noting the error message didn't confirm a real timeout vs. a dropped
connection or memory exhaustion. That's the calibration design (decision
#12 in the plan doc) working on a case it was never specifically tuned for,
not a coincidence.

**Repeated real runs of the same scenario aren't diverse test coverage --
this got checked directly, not assumed.** By the time 3 categories existed,
`schema_drift` had 3 real log files and `data_quality` had 2, all scoring
100%. Checked what they actually contained: every `schema_drift` log had
the identical `KeyError: 'customer_id'` on the identical rename, and both
`data_quality` logs had the identical `KeyError: 'promo_code'` on the
identical hardcoded row (`setup_db.py` always marks `order_id == 7`) --
real, distinct executions, but the same underlying bug triggered
repeatedly, not genuinely different failure instances. Fixed by adding a
second `data_quality` fixture with a different real defect
(`data_quality_malformed`: invalid JSON, not a missing key -- a real
`JSONDecodeError` instead of `KeyError`) and a fourth category, `code_bug`
(a real `ZeroDivisionError` from a wrong assumption, on data that's
otherwise identical to the `healthy` scenario -- deliberately chosen so the
agent has to conclude "schema and data are both fine" before it can
correctly blame the code). Both were classified correctly on the first
real run, and the `data_quality_malformed` report explicitly noted it did
*not* rely on the log's own `Scenario:` label as evidence -- direct
confirmation the category generalizes past the one specific exception it
had seen twice before, rather than pattern-matching on it.

## Full history and design decisions

`.claude/plans/opsfix-plan.md` tracks the running design log -- every
architecture decision made along the way and why, kept up to date as the
project evolves.

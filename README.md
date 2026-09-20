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

- SQL Server reachable at `localhost\JUST_INTO_DS` (edit `config/db_config.py`
  if yours is named differently), Windows Integrated auth, ODBC Driver 17
- A logged-in Claude Code session on this machine (the agent authenticates
  via that login, not a separate `ANTHROPIC_API_KEY` -- see
  `.claude/plans/opsfix-plan.md` for why)
- At least one log file in `../RCA_LOGS/` to investigate -- these come from
  running the [sample-pipeline](../sample-pipeline) fixture project:
  ```powershell
  cd ..\sample-pipeline
  .venv\Scripts\python.exe main.py schema_drift   # or: healthy, data_quality
  ```

## What `python main.py` does

Scans every `*.log` file in `../RCA_LOGS/`. `SUCCESS` runs are skipped (no
LLM cost). For each `FAILED` run, it runs a real agent investigation, prints
the resulting report, and appends a row to
`../RCA_LOGS/results/rca_reports.csv`.

## Project structure

```
agent/
  schemas.py      # RCAReport + FailureCategory (the categories currently supported)
  tools.py        # evidence-gathering functions: read a log, query the live DB schema, parse a traceback
  prompts.py      # the agent's system prompt
  pipeline.py     # the actual Claude Agent SDK session
  results.py      # appends each report as a CSV row
config/
  db_config.py    # SQL Server connection string
tests/            # unit tests for the tools and results writer (no LLM calls)
```

## Tests

```powershell
python -m pytest
```

## Full history and design decisions

`.claude/plans/opsfix-plan.md` tracks the running design log -- every
architecture decision made along the way and why, kept up to date as the
project evolves.

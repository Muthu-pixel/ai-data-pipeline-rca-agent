import json
import uuid
from datetime import datetime
from pathlib import Path

from agent.schemas import RCAReport

RESULTS_DIR = Path(__file__).resolve().parent.parent / "result"
RESULTS_JSONL = RESULTS_DIR / "rca_reports.jsonl"


def new_results_path() -> Path:
    """A fresh, timestamped results file for one run of main.py (rca_reports_<timestamp>.jsonl).
    Call this once per run, not once per report, so every report from that run lands in the
    same file. Microsecond precision avoids collisions with a previous run's file, including
    one still open (and locked) elsewhere, e.g. in Excel."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return RESULTS_DIR / f"rca_reports_{timestamp}.jsonl"


def append_report(report: RCAReport, log_path: Path, results_path: Path = RESULTS_JSONL) -> None:
    """Appends one RCAReport as a single JSON line to a JSON Lines (.jsonl) file --
    one JSON object per line, so appending means adding a line (no rewriting a JSON
    array's closing bracket), and evidence/remediation.steps keep their real list
    structure instead of being flattened or stringified into CSV cells.

    run_id identifies which pipeline run this report is about (the log file's
    own name, already unique to the run -- see the microsecond-timestamp
    decision in the plan). run_id_unique_id identifies this particular
    *analysis* of that run -- a fresh id each call, since the same log can be
    investigated more than once (e.g. re-running the agent, or later an eval
    loop) and each attempt gets its own line rather than overwriting the last.

    results_path defaults to the real results file; tests pass a tmp_path instead.
    """
    results_path.parent.mkdir(parents=True, exist_ok=True)

    remediation = report.remediation.model_dump()
    remediation["steps"] = [
        f"Step {i}: {step}" for i, step in enumerate(report.remediation.steps, start=1)
    ]

    row = {
        "create_date": datetime.now().isoformat(timespec="seconds"),
        "run_id": log_path.stem,
        "run_id_unique_id": str(uuid.uuid4()),
        "log_file": log_path.name,
        "category": report.category.value,
        "confidence": report.confidence,
        "needs_more_context": report.needs_more_context,
        "summary": report.summary,
        "evidence": [e.model_dump() for e in report.evidence],
        "impact": report.impact.model_dump(),
        "remediation": remediation,
    }

    with open(results_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

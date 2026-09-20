import csv
import json
import uuid
from datetime import datetime
from pathlib import Path

from agent.schemas import RCAReport

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "RCA_LOGS" / "results"
RESULTS_CSV = RESULTS_DIR / "rca_reports.csv"

FIELDNAMES = [
    "create_date",
    "run_id",
    "run_id_unique_id",
    "log_file",
    "category",
    "confidence",
    "needs_more_context",
    "summary",
    "evidence",
    "impact_affected_component",
    "impact_severity",
    "impact_downstream_effects",
    "remediation_summary",
    "remediation_steps",
    "remediation_risk_notes",
]


def append_report(report: RCAReport, log_path: Path, csv_path: Path = RESULTS_CSV) -> None:
    """Appends one RCAReport as a row to RCA_LOGS/results/rca_reports.csv.

    run_id identifies which pipeline run this report is about (the log file's
    own name, already unique to the run -- see the microsecond-timestamp
    decision in the plan). run_id_unique_id identifies this particular
    *analysis* of that run -- a fresh id each call, since the same log can be
    investigated more than once (e.g. re-running the agent, or later an eval
    loop) and each attempt gets its own row rather than overwriting the last.

    csv_path defaults to the real results file; tests pass a tmp_path instead.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not csv_path.exists() or csv_path.stat().st_size == 0

    row = {
        "create_date": datetime.now().isoformat(timespec="seconds"),
        "run_id": log_path.stem,
        "run_id_unique_id": str(uuid.uuid4()),
        "log_file": log_path.name,
        "category": report.category.value,
        "confidence": report.confidence,
        "needs_more_context": report.needs_more_context,
        "summary": report.summary,
        "evidence": json.dumps([e.model_dump() for e in report.evidence]),
        "impact_affected_component": report.impact.affected_component,
        "impact_severity": report.impact.severity,
        "impact_downstream_effects": report.impact.downstream_effects,
        "remediation_summary": report.remediation.summary,
        "remediation_steps": json.dumps(report.remediation.steps),
        "remediation_risk_notes": report.remediation.risk_notes,
    }

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)

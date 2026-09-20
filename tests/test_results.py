import csv
from pathlib import Path

from agent.results import append_report
from agent.schemas import RCAReport, FailureCategory, EvidenceCitation, ImpactAnalysis, RemediationSuggestion

REPORT = RCAReport(
    category=FailureCategory.SCHEMA_DRIFT,
    confidence=0.97,
    needs_more_context=False,
    summary="Upstream renamed customer_id to cust_id.",
    evidence=[EvidenceCitation(source="read_log_file", quote="KeyError: 'customer_id'", relevance="shows the crash")],
    impact=ImpactAnalysis(affected_component="transform", severity="run blocked", downstream_effects="no output"),
    remediation=RemediationSuggestion(summary="use cust_id", steps=["update transform.py"], risk_notes="verify first"),
)


def test_append_report_writes_header_and_row(tmp_path):
    csv_path = tmp_path / "rca_reports.csv"
    log_path = Path("sample-pipeline_20260919_214340_426707.log")

    append_report(REPORT, log_path, csv_path=csv_path)

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    row = rows[0]
    assert row["run_id"] == "sample-pipeline_20260919_214340_426707"
    assert row["log_file"] == "sample-pipeline_20260919_214340_426707.log"
    assert row["category"] == "schema_drift"
    assert row["confidence"] == "0.97"
    assert row["needs_more_context"] == "False"
    assert row["remediation_summary"] == "use cust_id"
    assert row["run_id_unique_id"]  # a uuid was generated


def test_append_report_appends_without_duplicating_header(tmp_path):
    csv_path = tmp_path / "rca_reports.csv"
    log_path = Path("sample-pipeline_20260919_214340_426707.log")

    append_report(REPORT, log_path, csv_path=csv_path)
    append_report(REPORT, log_path, csv_path=csv_path)

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("create_date,run_id,run_id_unique_id")
    assert len(lines) == 3  # 1 header + 2 rows
    # the two rows get different run_id_unique_id even for the same log
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["run_id_unique_id"] != rows[1]["run_id_unique_id"]

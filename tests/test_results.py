import json
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


def test_append_report_writes_one_json_line(tmp_path):
    results_path = tmp_path / "rca_reports.jsonl"
    log_path = Path("sample-pipeline_20260919_214340_426707.log")

    append_report(REPORT, log_path, results_path=results_path)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])

    assert row["run_id"] == "sample-pipeline_20260919_214340_426707"
    assert row["log_file"] == "sample-pipeline_20260919_214340_426707.log"
    assert row["category"] == "schema_drift"
    assert row["confidence"] == 0.97
    assert row["needs_more_context"] is False
    assert row["remediation"]["summary"] == "use cust_id"
    assert row["remediation"]["steps"] == ["Step 1: update transform.py"]
    assert row["run_id_unique_id"]  # a uuid was generated


def test_append_report_appends_one_line_per_call(tmp_path):
    results_path = tmp_path / "rca_reports.jsonl"
    log_path = Path("sample-pipeline_20260919_214340_426707.log")

    append_report(REPORT, log_path, results_path=results_path)
    append_report(REPORT, log_path, results_path=results_path)

    lines = results_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    # each call gets its own run_id_unique_id even for the same log
    assert rows[0]["run_id_unique_id"] != rows[1]["run_id_unique_id"]

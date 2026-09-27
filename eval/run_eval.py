import csv
import json
from datetime import datetime
from pathlib import Path

from ground_truth import GROUND_TRUTH
from metrics import EvalRecord, summarize

from agent.results import RESULTS_DIR
from agent.tools import read_log_file, extract_scenario

RCA_LOGS_DIR = Path(__file__).resolve().parent.parent / "sample_error_log"


def new_eval_summary_path() -> Path:
    """A fresh, timestamped summary file for one run of run_eval.py
    (eval_summary_<timestamp>.csv), so repeated runs never collide or overwrite."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return RESULTS_DIR / f"eval_summary_{timestamp}.csv"


def build_records() -> list[EvalRecord]:
    """Scores the existing investigation history in every rca_reports*.jsonl (one per
    main.py run, since it started timestamping them) against ground truth -- no new
    agent calls, just re-scoring what main.py already produced."""
    jsonl_paths = sorted(RESULTS_DIR.glob("rca_reports*.jsonl"))
    if not jsonl_paths:
        print(f"No results yet in {RESULTS_DIR} -- run main.py first.")
        return []

    records = []
    for jsonl_path in jsonl_paths:
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)

                log_path = RCA_LOGS_DIR / row["log_file"]
                if not log_path.exists():
                    print(f"  skip {row['log_file']}: log file no longer exists")
                    continue

                scenario = extract_scenario(read_log_file(str(log_path)))
                expected_category = GROUND_TRUTH.get(scenario) if scenario else None
                if expected_category is None:
                    print(f"  skip {row['log_file']}: scenario '{scenario}' has no ground truth entry")
                    continue

                records.append(EvalRecord(
                    run_id=row["run_id"],
                    expected_category=expected_category,
                    actual_category=row["category"],
                    confidence=float(row["confidence"]),
                    needs_more_context=row["needs_more_context"],
                ))
    return records


def print_summary(summary: dict) -> None:
    print(f"\nTotal scored: {summary['total']}")
    if summary["total"] == 0:
        return
    print(f"Correct: {summary['correct']} ({summary['accuracy']:.0%})")
    print(f"Confidently wrong: {summary['confidently_wrong']} ({summary['confidently_wrong_rate']:.0%})")
    print("\nBy category:")
    for category, stats in summary["by_category"].items():
        print(f"  {category}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.0%})")


def append_summary_row(summary: dict, summary_path: Path) -> None:
    if summary["total"] == 0:
        return
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not summary_path.exists() or summary_path.stat().st_size == 0

    row = {
        "eval_date": datetime.now().isoformat(timespec="seconds"),
        "total": summary["total"],
        "correct": summary["correct"],
        "accuracy": summary["accuracy"],
        "confidently_wrong": summary["confidently_wrong"],
        "confidently_wrong_rate": summary["confidently_wrong_rate"],
        "by_category": json.dumps(summary["by_category"]),
    }
    with open(summary_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)


def main() -> None:
    records = build_records()
    summary = summarize(records)
    print_summary(summary)
    append_summary_row(summary, new_eval_summary_path())


if __name__ == "__main__":
    main()

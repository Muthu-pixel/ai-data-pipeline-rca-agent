from pathlib import Path

from agent.pipeline import investigate_log
from agent.results import append_report
from agent.tools import read_log_file, extract_error_sections

RCA_LOGS_DIR = Path(__file__).resolve().parent.parent / "RCA_LOGS"


def main() -> None:
    log_files = sorted(RCA_LOGS_DIR.glob("*.log"))
    if not log_files:
        print(f"No log files found in {RCA_LOGS_DIR}")
        return

    for log_path in log_files:
        log_text = read_log_file(str(log_path))
        status = "FAILED" if extract_error_sections(log_text) else "SUCCESS"

        print(f"\n=== {log_path.name} ({status}) ===")
        if status == "SUCCESS":
            continue

        report = investigate_log(str(log_path))
        if report is not None:
            print(report.model_dump_json(indent=2))
            append_report(report, log_path)


if __name__ == "__main__":
    main()

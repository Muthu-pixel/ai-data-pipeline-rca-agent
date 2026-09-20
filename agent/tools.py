import re

import pyodbc

from config.db_config import CONNECTION_STRING


def read_log_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_error_sections(log_text: str) -> list[str]:
    lines = log_text.splitlines()
    sections = []
    i = 0
    while i < len(lines):
        if "Traceback" in lines[i]:
            
            end = None
            for j in range(i, len(lines)):
                if lines[j] and not lines[j].startswith(" ") and ("Error" in lines[j] or "Exception" in lines[j]):
                    end = j
                    break
            if end is not None:
                sections.append("\n".join(lines[i:end + 1]))
                i = end + 1
            else:
                # traceback ran off the end of the log without a clear error line
                sections.append("\n".join(lines[i:]))
                break
        else:
            i += 1
    return sections


def extract_source_file(log_text: str) -> str | None:
    """Parses the 'Source file: <path>' line the pipeline logs at startup, identifying which
    pipeline produced this log regardless of where the log file itself ended up."""
    match = re.search(r"Source file: (.+)", log_text)
    return match.group(1).strip() if match else None


def extract_queried_table(log_text: str) -> str | None:
    """Parses the 'Querying dbo.<table> from SQL Server' line, identifying which table a run
    actually read from -- just enough to know what to ask get_table_schema about."""
    match = re.search(r"Querying dbo\.(\w+) from SQL Server", log_text)
    return match.group(1) if match else None


def get_table_schema(table_name: str) -> list[dict]:
    """Queries SQL Server directly for a table's real, current column names and types --
    live ground truth from the database itself, not a guess or a hardcoded expectation."""
    conn = pyodbc.connect(CONNECTION_STRING, timeout=5)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = ? "
        "ORDER BY ORDINAL_POSITION",
        table_name,
    )
    columns = [
        {"column_name": row.COLUMN_NAME, "data_type": row.DATA_TYPE, "is_nullable": row.IS_NULLABLE}
        for row in cursor.fetchall()
    ]
    conn.close()
    return columns


def parse_traceback(section: str) -> dict:
    """Parses one traceback block (as returned by extract_error_sections) into its key facts:
    the exception type/message, and the innermost frame that actually raised it."""
    lines = [line for line in section.splitlines() if line.strip()]

    exc_type, _, exc_message = lines[-1].partition(":")
    exc_type = exc_type.strip()
    exc_message = exc_message.strip()

    frame_pattern = re.compile(r'File "(.+?)", line (\d+), in (.+)')
    failing_file = failing_line_number = failing_function = failing_code = None
    for i, line in enumerate(lines):
        match = frame_pattern.search(line)
        if match:
            failing_file, failing_function = match.group(1), match.group(3)
            failing_line_number = int(match.group(2))
            for candidate in lines[i + 1:]:
                stripped = candidate.strip()
                if stripped and not set(stripped) <= set("~^"):
                    failing_code = stripped
                    break

    return {
        "exception_type": exc_type,
        "exception_message": exc_message,
        "failing_file": failing_file,
        "failing_line_number": failing_line_number,
        "failing_function": failing_function,
        "failing_code": failing_code,
    }
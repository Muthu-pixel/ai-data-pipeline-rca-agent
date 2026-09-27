from agent.tools import (
    read_log_file,
    extract_error_sections,
    extract_source_file,
    extract_queried_table,
    get_table_schema,
    parse_traceback,
)

DRIFT_LOG = """\
2026-09-19 18:02:35 INFO [run] Starting pipeline: orders_etl
2026-09-19 18:02:35 INFO [run] Source file: C:\\Users\\91978\\Documents\\2026-AI-projects\\sample-pipeline\\main.py
2026-09-19 18:02:35 INFO [run] Scenario: schema_drift
2026-09-19 18:02:35 INFO [extract] Extract stage started
2026-09-19 18:02:35 INFO [extract] Querying dbo.orders_drift from SQL Server
2026-09-19 18:02:36 INFO [extract] Extracted 20 rows total
2026-09-19 18:02:36 INFO [extract] Extract stage completed
2026-09-19 18:02:36 INFO [validate] Validation stage started
2026-09-19 18:02:36 INFO [validate] Validation stage completed
2026-09-19 18:02:36 INFO [transform] Transform stage started
2026-09-19 18:02:36 ERROR [run] Transform stage failed
Traceback (most recent call last):
  File "C:\\Users\\91978\\Documents\\2026-AI-projects\\sample-pipeline\\main.py", line 34, in run
    transform(orders)
    ~~~~~~~~~^^^^^^^^
  File "C:\\Users\\91978\\Documents\\2026-AI-projects\\sample-pipeline\\transform.py", line 11, in transform
    revenue_by_customer = compute_customer_revenue(orders)
  File "C:\\Users\\91978\\Documents\\2026-AI-projects\\sample-pipeline\\transform.py", line 21, in compute_customer_revenue
    customer = order["customer_id"]
               ~~~~~^^^^^^^^^^^^^^^
KeyError: 'customer_id'
2026-09-19 18:02:36 ERROR [run] Pipeline run ended with status: FAILED
"""

HEALTHY_LOG = """\
2026-09-19 18:06:44 INFO [run] Starting pipeline: orders_etl
2026-09-19 18:06:44 INFO [run] Source file: C:\\Users\\91978\\Documents\\2026-AI-projects\\sample-pipeline\\main.py
2026-09-19 18:06:44 INFO [run] Scenario: healthy
2026-09-19 18:06:44 INFO [extract] Extract stage started
2026-09-19 18:06:44 INFO [extract] Querying dbo.orders_healthy from SQL Server
2026-09-19 18:06:44 INFO [extract] Extracted 20 rows total
2026-09-19 18:06:44 INFO [extract] Extract stage completed
2026-09-19 18:06:44 INFO [validate] Validation stage started
2026-09-19 18:06:44 INFO [validate] Validation stage completed
2026-09-19 18:06:44 INFO [transform] Transform stage started
2026-09-19 18:06:44 INFO [transform] Transform stage completed
2026-09-19 18:06:44 INFO [run] Pipeline run ended with status: SUCCESS
"""


def test_read_log_file(tmp_path):
    log_path = tmp_path / "run.log"
    log_path.write_text(DRIFT_LOG, encoding="utf-8")

    assert read_log_file(str(log_path)) == DRIFT_LOG


def test_extract_error_sections_finds_the_traceback():
    sections = extract_error_sections(DRIFT_LOG)

    assert len(sections) == 1
    assert "KeyError: 'customer_id'" in sections[0]


def test_extract_error_sections_empty_for_a_healthy_run():
    assert extract_error_sections(HEALTHY_LOG) == []


def test_extract_source_file():
    expected = r"C:\Users\91978\Documents\2026-AI-projects\sample-pipeline\main.py"

    assert extract_source_file(DRIFT_LOG) == expected
    assert extract_source_file("no such line here") is None


def test_extract_queried_table():
    assert extract_queried_table(DRIFT_LOG) == "orders_drift"
    assert extract_queried_table(HEALTHY_LOG) == "orders_healthy"
    assert extract_queried_table("no such line here") is None


def test_parse_traceback():
    section = extract_error_sections(DRIFT_LOG)[0]
    failure = parse_traceback(section)

    assert failure["exception_type"] == "KeyError"
    assert failure["exception_message"] == "'customer_id'"
    assert failure["failing_function"] == "compute_customer_revenue"
    assert failure["failing_line_number"] == 21
    assert failure["failing_code"] == 'customer = order["customer_id"]'
    assert failure["failing_file"].endswith("transform.py")


def test_get_table_schema_healthy_has_customer_id():
    columns = {c["column_name"] for c in get_table_schema("orders_healthy")}

    assert "customer_id" in columns
    assert "cust_id" not in columns


def test_get_table_schema_drift_has_cust_id_not_customer_id():
    columns = {c["column_name"] for c in get_table_schema("orders_drift")}

    assert "cust_id" in columns
    assert "customer_id" not in columns

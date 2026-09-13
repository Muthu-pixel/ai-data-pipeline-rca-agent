from agent.tools import read_log_file, extract_error_sections
from agent.pipeline import get_root_cause

log = read_log_file("data/logs/sample_run.log")
errors = extract_error_sections(log)
print(get_root_cause(errors[0]))
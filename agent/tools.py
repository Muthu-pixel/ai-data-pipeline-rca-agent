def read_log_file(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def extract_error_sections(log_text: str) -> list[str]:
    """Returns every traceback found in the log, one entry per failure."""
    lines = log_text.splitlines()
    sections = []
    i = 0
    while i < len(lines):
        if "Traceback" in lines[i]:
            for j in range(i, len(lines)):
                if lines[j] and not lines[j].startswith(" ") and ("Error" in lines[j] or "Exception" in lines[j]):
                    sections.append("\n".join(lines[i:j + 1]))
                    i = j
                    break
        i += 1
    if not sections:
        sections.append(log_text[-500:])  # no traceback found, fall back to the tail
    return sections
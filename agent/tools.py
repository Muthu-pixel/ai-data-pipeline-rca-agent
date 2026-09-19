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
    if not sections:
        sections.append(log_text[-500:])
    return sections
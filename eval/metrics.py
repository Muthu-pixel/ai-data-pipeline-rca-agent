from dataclasses import dataclass


@dataclass
class EvalRecord:
    run_id: str
    expected_category: str
    actual_category: str
    confidence: float
    needs_more_context: bool

    @property
    def correct(self) -> bool:
        return self.actual_category == self.expected_category

    @property
    def confidently_wrong(self) -> bool:
        """The dangerous failure mode: wrong category, but presented as trustworthy
        (needs_more_context=False) -- exactly what the calibration signal exists to
        prevent. A wrong answer flagged with needs_more_context=True is a lesser
        problem: the report already told you not to trust it."""
        return not self.correct and not self.needs_more_context


def summarize(records: list[EvalRecord]) -> dict:
    total = len(records)
    correct = sum(r.correct for r in records)
    confidently_wrong = sum(r.confidently_wrong for r in records)

    by_category: dict[str, dict] = {}
    for r in records:
        bucket = by_category.setdefault(r.expected_category, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(r.correct)

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else None,
        "confidently_wrong": confidently_wrong,
        "confidently_wrong_rate": confidently_wrong / total if total else None,
        "by_category": {
            category: {**stats, "accuracy": stats["correct"] / stats["total"]}
            for category, stats in by_category.items()
        },
    }

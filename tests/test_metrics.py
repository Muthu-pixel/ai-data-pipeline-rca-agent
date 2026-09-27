from eval.metrics import EvalRecord, summarize


def test_correct_record():
    r = EvalRecord("run1", "schema_drift", "schema_drift", 0.95, False)
    assert r.correct
    assert not r.confidently_wrong


def test_wrong_but_flagged_is_not_confidently_wrong():
    r = EvalRecord("run1", "schema_drift", "data_quality", 0.3, True)
    assert not r.correct
    assert not r.confidently_wrong


def test_wrong_and_unflagged_is_confidently_wrong():
    r = EvalRecord("run1", "schema_drift", "data_quality", 0.9, False)
    assert not r.correct
    assert r.confidently_wrong


def test_summarize_empty():
    summary = summarize([])
    assert summary["total"] == 0
    assert summary["accuracy"] is None


def test_summarize_mixed():
    records = [
        EvalRecord("run1", "schema_drift", "schema_drift", 0.95, False),  # correct
        EvalRecord("run2", "schema_drift", "data_quality", 0.9, False),   # confidently wrong
        EvalRecord("run3", "data_quality", "data_quality", 0.8, False),   # correct
    ]
    summary = summarize(records)

    assert summary["total"] == 3
    assert summary["correct"] == 2
    assert summary["accuracy"] == 2 / 3
    assert summary["confidently_wrong"] == 1
    assert summary["by_category"]["schema_drift"] == {"total": 2, "correct": 1, "accuracy": 0.5}
    assert summary["by_category"]["data_quality"] == {"total": 1, "correct": 1, "accuracy": 1.0}

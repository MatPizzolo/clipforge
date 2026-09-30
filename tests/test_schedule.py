from clipforge.schedule import normalize_hashtags, normalize_slots, schedule_problem


def test_normalize() -> None:
    assert normalize_slots(["8:00", "13:30"]) == ["08:00", "13:30"]
    assert normalize_hashtags(["#mindset", "money"]) == ["mindset", "money"]


def test_problems() -> None:
    assert schedule_problem("America/New_York", ["08:00"], ["ok_tag"]) is None
    assert schedule_problem("Mars/Base", ["08:00"], [])[0] == "timezone"  # type: ignore[index]
    assert schedule_problem("UTC", [], [])[0] == "slots"  # type: ignore[index]
    assert schedule_problem("UTC", ["9:5"], [])[0] == "slots"  # type: ignore[index]
    assert schedule_problem("UTC", ["10:00", "09:00"], [])[0] == "slots"  # type: ignore[index]
    assert schedule_problem("UTC", ["09:00"], ["no-dash"])[0] == "hashtags"  # type: ignore[index]

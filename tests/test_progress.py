from datetime import datetime

import progress
from progress import Score

NOW = datetime(2026, 10, 9, 18, 22, 0)


def test_missing_file_is_fresh(tmp_path):
    assert progress.load(tmp_path / "p.json") == ({"chapters": {}}, None)


def test_round_trip(tmp_path):
    path = tmp_path / "nested" / "p.json"
    saved = progress.record(progress.fresh(), "1", Score(3, 5), Score(4, 5), 48213, NOW)
    assert progress.save(saved, path) is None
    loaded, warning = progress.load(path)
    assert warning is None
    assert loaded["chapters"]["1"] == {"at": "2026-10-09T18:22:00", "seed": 48213, "self": [3, 5], "claude": [4, 5]}


def test_corrupt_file_warns_and_keeps_a_backup(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{not json", encoding="utf-8")
    loaded, warning = progress.load(path)
    assert loaded == {"chapters": {}}
    assert "starting fresh" in warning and "p.json.bad" in warning
    assert (tmp_path / "p.json.bad").exists()


def test_wrong_shape_warns(tmp_path):
    path = tmp_path / "p.json"
    path.write_text('{"chapters": []}', encoding="utf-8")
    assert progress.load(path)[1] is not None


def test_unwritable_location_returns_warning(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    warning = progress.save(progress.fresh(), blocker / "p.json")
    assert warning is not None and "Couldn't save progress" in warning


def test_latest_prefers_claude_then_self():
    saved = progress.record(progress.fresh(), "1", Score(3, 5), Score(4, 5), 1, NOW)
    progress.record(saved, "2", Score(2, 6), None, 1, NOW)
    assert progress.latest_score(saved, "1") == Score(4, 5)
    assert progress.latest_score(saved, "2") == Score(2, 6)
    assert progress.latest_score(saved, "3") is None


def test_malformed_entry_is_ignored():
    saved = {"chapters": {"1": {"self": ["x", 5]}, "2": "junk"}}
    assert progress.latest_score(saved, "1") is None
    assert progress.latest_score(saved, "2") is None


def test_weakest_skips_perfect_scores():
    saved = progress.fresh()
    progress.record(saved, "1", Score(5, 5), None, 1, NOW)
    progress.record(saved, "2", Score(2, 6), None, 1, NOW)
    progress.record(saved, "3", Score(3, 6), None, 1, NOW)
    progress.record(saved, "4", Score(4, 5), None, 1, NOW)
    assert progress.weakest(saved) == ["2", "3"]


def test_weakest_never_marks_every_scored_chapter():
    # Two scored chapters both showed "weakest", even at 5/6 (Sean, 2026-10-14). The label has to tell
    # chapters apart: always fewer marks than scored chapters.
    saved = progress.fresh()
    progress.record(saved, "1", Score(1, 5), None, 1, NOW)
    assert progress.weakest(saved) == []
    progress.record(saved, "2", Score(5, 6), None, 1, NOW)
    assert progress.weakest(saved) == ["1"]
    progress.record(saved, "3", Score(3, 6), None, 1, NOW)
    assert progress.weakest(saved) == ["1", "3"]


def test_weakest_never_breaks_a_tie_by_chapter_number():
    # Codex review on #38: two chapters at 4/5 marked chapter 1 alone. A mark must mean "lower than the rest".
    saved = progress.fresh()
    progress.record(saved, "1", Score(4, 5), None, 1, NOW)
    progress.record(saved, "2", Score(4, 5), None, 1, NOW)
    assert progress.weakest(saved) == []
    progress.record(saved, "3", Score(1, 5), None, 1, NOW)
    assert progress.weakest(saved) == ["3"]  # the 4/5s tie for second, so neither is marked
    progress.record(saved, "4", Score(5, 5), None, 1, NOW)
    assert progress.weakest(saved) == ["3"]  # two marks would split the 4/5 tie, so only the clear lowest


def test_weakest_counts_perfect_scores_as_scored():
    # A perfect chapter is never marked, but it is something the others can be compared against.
    saved = progress.fresh()
    progress.record(saved, "1", Score(5, 5), None, 1, NOW)
    progress.record(saved, "2", Score(2, 6), None, 1, NOW)
    assert progress.weakest(saved) == ["2"]


def test_score_text_and_pct():
    assert str(Score(3, 5)) == "3/5"
    assert Score(3, 5).pct == 0.6


def test_reset(tmp_path):
    path = tmp_path / "p.json"
    progress.save(progress.fresh(), path)
    progress.reset(path)
    assert not path.exists()
    progress.reset(path)  # already gone: no error


def test_unreadable_folder_warns_instead_of_crashing(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "p.json").write_text('{"chapters": {}}', encoding="utf-8")
    locked.chmod(0o000)
    try:
        loaded, warning = progress.load(locked / "p.json")
    finally:
        locked.chmod(0o755)
    assert loaded == {"chapters": {}}
    assert warning is not None and "starting fresh" in warning


def test_reset_in_read_only_folder_returns_warning(tmp_path):
    path = tmp_path / "p.json"
    progress.save(progress.fresh(), path)
    tmp_path.chmod(0o555)
    try:
        warning = progress.reset(path)
    finally:
        tmp_path.chmod(0o755)
    assert warning is not None and "Couldn't delete" in warning
    assert path.exists()


def test_second_corruption_keeps_the_first_backup(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{first", encoding="utf-8")
    progress.load(path)
    path.write_text("{second", encoding="utf-8")
    _, warning = progress.load(path)
    assert (tmp_path / "p.json.bad").read_text(encoding="utf-8") == "{first"
    assert (tmp_path / "p.json.bad2").read_text(encoding="utf-8") == "{second"
    assert "p.json.bad2" in warning


def test_unreadable_file_is_moved_aside_so_a_save_cannot_overwrite_it(tmp_path):
    path = tmp_path / "p.json"
    original = '{"chapters": {"1": {"self": [4, 5]}}}'
    path.write_text(original, encoding="utf-8")
    path.chmod(0o000)
    try:
        _, warning = progress.load(path)
    finally:
        (tmp_path / "p.json.bad").chmod(0o644)
    assert "p.json.bad" in warning
    progress.save(progress.fresh(), path)
    assert (tmp_path / "p.json.bad").read_text(encoding="utf-8") == original

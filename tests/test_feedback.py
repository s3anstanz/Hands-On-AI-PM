import json
import platform
import webbrowser
from urllib.parse import parse_qs, urlsplit

import feedback

ENV = feedback.Env(commit="abc1234", python="3.14.0", os="macOS-26.6", width="80", mode="offline")
WHERE = "Chapter 1 (How an LLM generates text), step 7 of 19, seed 4242"


def note(text="The bars confused me.\nMore detail here.", kind="Confusing", summary=""):
    return feedback.Note(kind=kind, text=text, where=WHERE, env=ENV, summary=summary)


def query(url):
    parts = urlsplit(url)
    return parts, {key: values[0] for key, values in parse_qs(parts.query).items()}


def test_issue_url_fills_in_the_feedback_form():
    url, trimmed = feedback.issue_url(note())
    parts, q = query(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == f"https://github.com/{feedback.REPO}/issues/new"
    assert q["template"] == "feedback.yml"
    assert q["title"] == "Confusing: The bars confused me."
    assert q["feedback"] == "The bars confused me.\nMore detail here."
    assert q["where"] == WHERE
    assert q["environment"] == "Commit abc1234 · Python 3.14.0 · macOS-26.6 · 80 columns · offline mode"
    assert trimmed is False


def test_issue_url_never_sets_labels():
    # Testers have the Read role, and GitHub 404s a new-issue link that sets labels
    # without triage access. The form's own `labels:` adds the feedback label.
    _, q = query(feedback.issue_url(note())[0])
    assert "labels" not in q


def test_title_uses_the_first_non_empty_line_and_is_shortened():
    assert feedback.title(note(text="\n\n  Second try  \nmore")) == "Confusing: Second try"
    long = feedback.title(note(text="x" * 200))
    assert len(long) == feedback.TITLE_LENGTH and long.endswith("…")


def test_title_prefers_the_summary_over_the_first_line():
    assert feedback.title(note(summary="Bars are unclear")) == "Confusing: Bars are unclear"
    assert feedback.title(note(summary="   ")) == "Confusing: The bars confused me."
    long = feedback.title(note(summary="y" * 200))
    assert len(long) == feedback.TITLE_LENGTH and long.endswith("…")


def test_issue_url_uses_the_summary_as_the_title():
    _, q = query(feedback.issue_url(note(summary="Bars are unclear"))[0])
    assert q["title"] == "Confusing: Bars are unclear"
    assert q["feedback"] == "The bars confused me.\nMore detail here."


def test_long_note_is_trimmed_to_fit_a_github_link():
    url, trimmed = feedback.issue_url(note(text="naïve café 🙂 " * 2000))
    assert trimmed is True
    assert len(url) <= feedback.MAX_URL_LENGTH
    _, q = query(url)
    assert q["feedback"].startswith("naïve café 🙂")
    assert q["feedback"].endswith(feedback.TRIMMED)


def test_environment_reports_this_machine():
    env = feedback.environment(width=120, live_on=True)
    assert env.python == platform.python_version()
    assert env.width == "120" and env.mode == "live"
    assert feedback.environment(width=80, live_on=False).mode == "offline"


def test_git_commit_from_a_loose_ref(tmp_path):
    (tmp_path / ".git" / "refs" / "heads").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp_path / ".git" / "refs" / "heads" / "main").write_text("0123456789abcdef\n", encoding="utf-8")
    assert feedback.git_commit(tmp_path) == "0123456"


def test_git_commit_from_packed_refs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (tmp_path / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\nfedcba9876543210 refs/heads/main\n", encoding="utf-8"
    )
    assert feedback.git_commit(tmp_path) == "fedcba9"


def test_git_commit_detached_head(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("aaaabbbbccccdddd\n", encoding="utf-8")
    assert feedback.git_commit(tmp_path) == "aaaabbb"


def test_git_commit_without_a_checkout(tmp_path):
    assert feedback.git_commit(tmp_path) == "unknown"


def test_pending_round_trip():
    path = feedback.save_pending(note())
    assert path is not None and path.parent == feedback.FEEDBACK_DIR
    assert feedback.load_pending() == ([(path, note())], [])
    assert feedback.discard(path) is None
    assert feedback.load_pending() == ([], [])


def test_pending_round_trip_keeps_the_summary():
    path = feedback.save_pending(note(summary="Bars are unclear"))
    assert feedback.load_pending() == ([(path, note(summary="Bars are unclear"))], [])


def test_a_note_saved_before_summaries_existed_still_loads():
    feedback.FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    old = feedback.FEEDBACK_DIR / "old.json"
    raw = {"kind": "Idea", "text": "x", "where": WHERE, "env": {f: getattr(ENV, f) for f in ENV.__dataclass_fields__}}
    old.write_text(json.dumps(raw), encoding="utf-8")
    assert feedback.load_pending() == ([(old, feedback.Note("Idea", "x", WHERE, ENV))], [])


def test_a_note_with_a_non_text_summary_is_reported_not_fatal():
    feedback.FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    bad = feedback.FEEDBACK_DIR / "bad-summary.json"
    raw = {
        "kind": "Idea",
        "text": "x",
        "where": WHERE,
        "summary": 5,
        "env": {f: getattr(ENV, f) for f in ENV.__dataclass_fields__},
    }
    bad.write_text(json.dumps(raw), encoding="utf-8")
    assert feedback.load_pending() == ([], [bad])


def test_two_notes_in_the_same_second_are_both_kept():
    first, second = feedback.save_pending(note()), feedback.save_pending(note(kind="Idea"))
    assert first != second
    notes, _ = feedback.load_pending()
    assert len(notes) == 2


def test_a_broken_pending_note_is_reported_not_fatal():
    good = feedback.save_pending(note())
    broken = feedback.FEEDBACK_DIR / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    wrong_shape = feedback.FEEDBACK_DIR / "wrong.json"
    wrong_shape.write_text(json.dumps({"kind": 1, "text": "x"}), encoding="utf-8")
    notes, bad = feedback.load_pending()
    assert notes == [(good, note())]
    assert sorted(bad) == sorted([broken, wrong_shape])


def test_save_pending_returns_none_when_it_cannot_write(monkeypatch, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(feedback, "FEEDBACK_DIR", blocker / "feedback")
    assert feedback.save_pending(note()) is None


def test_open_browser_reports_success_and_failure(browser, monkeypatch):
    assert feedback.open_browser("https://example.com") is True
    assert browser.opened == ["https://example.com"]
    browser.works = False
    assert feedback.open_browser("https://example.com") is False

    def broken(url):
        raise webbrowser.Error("no browser")

    monkeypatch.setattr(webbrowser, "open", broken)
    assert feedback.open_browser("https://example.com") is False


def test_discard_reports_a_file_it_cannot_remove(tmp_path):
    folder = tmp_path / "not-a-file"
    folder.mkdir()
    (folder / "inside").write_text("", encoding="utf-8")
    problem = feedback.discard(folder)  # unlinking a non-empty directory fails
    assert problem is not None and "Delete it so it isn't offered again" in problem

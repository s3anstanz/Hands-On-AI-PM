import json
import shutil

import pytest
from helpers import ScriptedIO

import data
import tutorial
from lessons import CHAPTERS


def run(io, *args, tmp_path, **kwargs):
    return tutorial.run(["--offline", *args], io=io, progress_path=tmp_path / "progress.json", **kwargs)


def test_menu_then_quit(tmp_path):
    io = ScriptedIO(menu=["q"])
    assert run(io, "--seed", "48213", tmp_path=tmp_path) == 0
    out = io.output
    assert "HANDS-ON AI PM" in out and "seed 48213" in out and "prices checked 2026-10-09" in out
    assert "How an LLM generates text" in out and "not started" in out
    assert "Live mode: OFF (--offline)" in out


def test_invalid_menu_choice(tmp_path):
    io = ScriptedIO(menu=["9", "q"])
    assert run(io, tmp_path=tmp_path) == 0
    assert "Not a chapter" in io.output


def test_eof_exits_cleanly(tmp_path):
    io = ScriptedIO(menu=[])  # first menu prompt raises EOFError
    assert run(io, tmp_path=tmp_path) == 0
    assert "Bye" in io.output


def test_ctrl_c_exits_cleanly(tmp_path):
    io = ScriptedIO(menu=["q"])

    def interrupt(prompt, kind):
        raise KeyboardInterrupt

    io.ask = interrupt
    assert run(io, "--lesson", "1", tmp_path=tmp_path) == 0
    assert "Bye" in io.output


def test_lesson_saves_progress_then_shows_menu(tmp_path):
    io = ScriptedIO(menu=["q"])
    assert run(io, "--lesson", "1", "--seed", "4242", tmp_path=tmp_path) == 0
    saved = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    assert saved["chapters"]["1"]["seed"] == 4242
    assert saved["chapters"]["1"]["self"] == [5, 5]
    assert "last: 5/5" in io.output


def test_learn_mode_saves_nothing_and_exits(tmp_path):
    io = ScriptedIO(menu=[])
    assert run(io, "--learn", "1", tmp_path=tmp_path) == 0
    assert not (tmp_path / "progress.json").exists()
    assert "Recap" in io.output
    assert "HANDS-ON AI PM" not in io.output  # learn mode exits without showing the menu


def test_same_seed_same_run(tmp_path):
    first, second = ScriptedIO(menu=["q"]), ScriptedIO(menu=["q"])
    run(first, "--lesson", "1", "--seed", "777", tmp_path=tmp_path / "a")
    run(second, "--lesson", "1", "--seed", "777", tmp_path=tmp_path / "b")
    assert first.output == second.output


def test_reset_progress(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text('{"chapters": {}}', encoding="utf-8")
    io = ScriptedIO()
    assert run(io, "--reset-progress", tmp_path=tmp_path) == 0
    assert not path.exists() and "Progress cleared" in io.output


def test_corrupt_progress_warns_and_continues(tmp_path):
    (tmp_path / "progress.json").write_text("{oops", encoding="utf-8")
    io = ScriptedIO(menu=["q"])
    assert run(io, tmp_path=tmp_path) == 0
    assert "starting fresh" in io.output


def test_unwritable_progress_warns_and_continues(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    io = ScriptedIO(menu=["q"])
    code = tutorial.run(["--offline", "--lesson", "1"], io=io, progress_path=blocker / "progress.json")
    assert code == 0 and "Couldn't save progress" in io.output


def test_broken_data_file_names_the_entry(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for toml in data.DATA_DIR.glob("*.toml"):
        shutil.copy(toml, data_dir)
    (data_dir / "prompts.toml").write_text('[[prompt]]\ntext = "x"\ntokens = { "a" = 1 }\n', encoding="utf-8")
    io = ScriptedIO()
    assert run(io, tmp_path=tmp_path, data_dir=data_dir) == 1
    assert "prompts.toml: prompt #1 (x) needs at least 3 candidates" in io.output
    assert "Traceback" not in io.output


def test_live_status_line_when_key_present(tmp_path):
    io = ScriptedIO(menu=["q"])
    code = tutorial.run([], io=io, progress_path=tmp_path / "p.json", env={"ANTHROPIC_API_KEY": "test"})
    assert code == 0 and "Live mode: ON (ANTHROPIC_API_KEY)" in io.output


def test_new_seed_is_five_digits():
    assert all(10_000 <= tutorial.new_seed() <= 99_999 for _ in range(50))


def terminal_io(monkeypatch, menu):
    """A ScriptedIO whose console behaves like a real terminal, so clear() really clears."""
    import io as _io

    from rich.console import Console

    monkeypatch.setenv("TERM", "xterm-256color")
    scripted = ScriptedIO(menu=menu)
    scripted.console = Console(file=_io.StringIO(), width=100, force_terminal=True, color_system=None)
    return scripted


def after_last_clear(scripted) -> str:
    return scripted.output.rsplit("\x1b[2J", 1)[-1]


def test_progress_warning_survives_the_menu_clear(tmp_path, monkeypatch):
    (tmp_path / "progress.json").write_text("{oops", encoding="utf-8")
    scripted = terminal_io(monkeypatch, ["q"])
    assert run(scripted, tmp_path=tmp_path) == 0
    assert "starting fresh" in after_last_clear(scripted)


def test_bad_menu_choice_hint_survives_the_clear(tmp_path, monkeypatch):
    scripted = terminal_io(monkeypatch, ["9", "q"])
    assert run(scripted, tmp_path=tmp_path) == 0
    assert "Not a chapter number" in after_last_clear(scripted)


def test_progress_warning_pauses_before_a_lesson(tmp_path):
    (tmp_path / "progress.json").write_text("{oops", encoding="utf-8")
    io = ScriptedIO(menu=["q"])
    assert run(io, "--lesson", "1", tmp_path=tmp_path) == 0
    kinds = [kind for kind, _ in io.prompts]
    assert kinds[0] == "pause"


def test_reset_progress_in_read_only_folder_warns(tmp_path):
    folder = tmp_path / "ro"
    folder.mkdir()
    (folder / "progress.json").write_text('{"chapters": {}}', encoding="utf-8")
    folder.chmod(0o555)
    try:
        io = ScriptedIO()
        code = tutorial.run(["--offline", "--reset-progress"], io=io, progress_path=folder / "progress.json")
    finally:
        folder.chmod(0o755)
    assert code == 0 and "Couldn't delete" in io.output and "Progress cleared" not in io.output


def test_repicking_a_chapter_gets_a_fresh_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(tutorial, "new_seed", lambda: 55555)
    io = ScriptedIO(menu=["1", "1", "q"])
    assert run(io, "--seed", "777", tmp_path=tmp_path) == 0
    navs = [prompt for kind, prompt in io.prompts if kind == "nav"]
    assert "seed 777" in navs[0] and "seed 55555" in navs[-1]
    assert io.output.rsplit("HANDS-ON AI PM", 1)[-1].lstrip().startswith("seed 55555")


def test_menu_rows_fit_a_40_column_terminal(tmp_path):
    io = ScriptedIO(menu=["q"], width=40)
    assert run(io, tmp_path=tmp_path) == 0
    rows = [line for line in io.output.splitlines() if " min " in line]
    chapter_rows, cheat_row = rows[:-1], rows[-1]
    assert len(chapter_rows) == len(CHAPTERS) and all("not started" in row for row in chapter_rows)
    assert "~3 min" in cheat_row and "not started" not in cheat_row
    assert "How an" in rows[0]


def feedback_note(text):
    import feedback

    env = feedback.Env(commit="abc1234", python="3.14.0", os="macOS", width="80", mode="offline")
    return feedback.Note("Idea", text, "Start menu", env)


def test_f_at_the_menu_sends_feedback(tmp_path, browser):
    from urllib.parse import parse_qs, urlsplit

    io = ScriptedIO(menu=["f", "q"], overrides={"multiline": ["Add a glossary chapter.", ""], "choice": ["3"]})
    assert run(io, tmp_path=tmp_path) == 0
    query = parse_qs(urlsplit(browser.opened[0]).query)
    assert query["where"] == ["Start menu"]
    assert query["title"] == ["Idea: Add a glossary chapter."]
    assert any("f for feedback" in prompt for kind, prompt in io.prompts if kind == "menu")


def test_unsent_feedback_is_offered_at_startup(tmp_path, browser):
    import feedback

    feedback.save_pending(feedback_note("Written offline."))
    io = ScriptedIO(menu=["q"], overrides={"yesno": ["y", "y"]})  # send now, it went through
    assert run(io, tmp_path=tmp_path) == 0
    assert "You have 1 unsent feedback note. Send now? [Y/n]" in io.output
    assert len(browser.opened) == 1
    assert feedback.load_pending() == ([], [])


def test_unsent_feedback_stays_saved_when_declined(tmp_path, browser):
    import feedback

    feedback.save_pending(feedback_note("One."))
    feedback.save_pending(feedback_note("Two."))
    io = ScriptedIO(menu=["q"], overrides={"yesno": ["n"]})
    assert run(io, tmp_path=tmp_path) == 0
    assert "You have 2 unsent feedback notes." in io.output
    assert browser.opened == []
    assert len(feedback.load_pending()[0]) == 2


def test_unreadable_feedback_note_gets_one_line_not_a_crash(tmp_path):
    import feedback

    feedback.FEEDBACK_DIR.mkdir(parents=True)
    (feedback.FEEDBACK_DIR / "bad.json").write_text("{", encoding="utf-8")
    io = ScriptedIO(menu=["q"])
    assert run(io, tmp_path=tmp_path) == 0
    assert "Skipped an unreadable feedback note:" in io.output and "bad.json" in io.output


def test_broken_hallucination_case_is_one_line(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for toml in data.DATA_DIR.glob("*.toml"):
        shutil.copy(toml, data_dir)
    cases = data_dir / "hallucination.toml"
    cases.write_text(cases.read_text(encoding="utf-8").replace('answer = "Canberra"', 'answer = "Sydney"', 1), "utf-8")
    io = ScriptedIO(width=200)
    assert run(io, tmp_path=tmp_path, data_dir=data_dir) == 1
    assert "hallucination.toml: case #1 (The capital of Australia is) without context, a wrong answer" in io.output
    assert "Traceback" not in io.output


def test_broken_scenarios_file_names_the_entry(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for toml in data.DATA_DIR.glob("*.toml"):
        shutil.copy(toml, data_dir)
    (data_dir / "scenarios.toml").write_text('[[scenario]]\nid = "x"\nname = "X"\n', encoding="utf-8")
    io = ScriptedIO()
    assert run(io, tmp_path=tmp_path, data_dir=data_dir) == 1
    assert "scenarios.toml: scenario #1 (x) users must be [low, high]" in io.output
    assert "Traceback" not in io.output


def test_rubric_figure_the_chapter_doesnt_provide_is_one_line(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for toml in data.DATA_DIR.glob("*.toml"):
        shutil.copy(toml, data_dir)
    rubrics = data_dir / "checklists.toml"
    text = rubrics.read_text(encoding="utf-8")
    rubrics.write_text(text.replace('hint = "', 'hint = "{output_time} ', 1), encoding="utf-8")
    io = ScriptedIO(width=200)
    assert run(io, tmp_path=tmp_path, data_dir=data_dir) == 1
    assert "checklists.toml: chapter 1 uses {output_time}, which Chapter 1 doesn't compute" in io.output
    assert "Traceback" not in io.output


def test_lesson_cheat_shows_the_sheet_then_the_menu(tmp_path):
    io = ScriptedIO(menu=["q"])
    assert run(io, "--lesson", "cheat", tmp_path=tmp_path) == 0
    out = io.output
    assert out.index("Key numbers") < out.index("Glossary (1 of") < out.index("HANDS-ON AI PM")
    assert not (tmp_path / "progress.json").exists()


@pytest.mark.parametrize("key", ["C", "c", " c "])
def test_c_on_the_menu_opens_the_cheat_sheet(tmp_path, key):
    io = ScriptedIO(menu=[key, "q"])
    assert run(io, tmp_path=tmp_path) == 0
    assert "Key numbers" in io.output and "Not a chapter" not in io.output
    assert not (tmp_path / "progress.json").exists()


def test_q_in_the_cheat_sheet_goes_back_to_the_menu(tmp_path):
    io = ScriptedIO(menu=["c", "q"], overrides={"nav": ["q"]})
    assert run(io, tmp_path=tmp_path) == 0
    assert "Key numbers" not in io.output  # left on the first page
    assert io.output.count("HANDS-ON AI PM") == 2


def test_menu_lists_the_cheat_sheet(tmp_path):
    io = ScriptedIO(menu=["q"])
    assert run(io, tmp_path=tmp_path) == 0
    row = next(line for line in io.output.splitlines() if "Cheat sheet + glossary" in line)
    assert row.split()[0] == "C" and "~3 min" in row
    assert any("C for the cheat sheet" in prompt for kind, prompt in io.prompts if kind == "menu")


def test_learn_mode_is_chapters_only():
    with pytest.raises(SystemExit):
        tutorial.parse_args(["--learn", "cheat"])

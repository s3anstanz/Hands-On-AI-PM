"""Golden-file tests: what the user sees, at three terminal widths.

A failure means the rendered output changed. If the change is intended (new copy,
new layout), regenerate and review the diff in the PR:

    UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py
"""

import dataclasses
import difflib
import os
from pathlib import Path

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import data
import engine
import tutorial
from lessons import CHAPTERS

SNAPSHOTS = Path(__file__).parent / "snapshots"
WIDTHS = (40, 80, 120)


def check_snapshot(name: str, actual: str, width: int) -> None:
    too_wide = [line for line in actual.splitlines() if cell_len(line) > width]
    assert not too_wide, f"{len(too_wide)} line(s) wider than {width} columns, e.g. {too_wide[0]!r}"
    path = SNAPSHOTS / name
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.exists(), f"missing snapshot {name}; run: UPDATE_SNAPSHOTS=1 uv run pytest tests/test_snapshots.py"
    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True), actual.splitlines(keepends=True), "snapshot", "now", n=1
            )
        )
        pytest.fail(f"{name} changed. If intended, run UPDATE_SNAPSHOTS=1 and review:\n{diff[:4000]}")


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_1_full_run(width):
    io = ScriptedIO(width=width)
    ctx = engine.Ctx(io=io, seed=4242, chapter=CHAPTERS["1"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter1_seed4242_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_start_menu(width, tmp_path):
    io = ScriptedIO(menu=["q"], width=width)
    assert tutorial.run(["--offline", "--seed", "48213"], io=io, progress_path=tmp_path / "p.json") == 0
    check_snapshot(f"menu_seed48213_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_2_full_run(width):
    io = ScriptedIO(width=width)
    ctx = engine.Ctx(io=io, seed=2202, chapter=CHAPTERS["2"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter2_seed2202_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_3_full_run(width):
    # Whole-number guesses, and one temperature on the dial so its bars are in the snapshot.
    io = ScriptedIO(width=width, overrides={"number": ["7", "1"], "optional": ["0.3", ""]})
    ctx = engine.Ctx(io=io, seed=3303, chapter=CHAPTERS["3"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter3_seed3303_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_4_full_run(width):
    io = ScriptedIO(width=width, overrides={"number": ["15", "2"]})  # whole-number guesses, as a person types
    ctx = engine.Ctx(io=io, seed=4404, chapter=CHAPTERS["4"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter4_seed4404_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_5_full_run(width):
    io = ScriptedIO(width=width)
    ctx = engine.Ctx(io=io, seed=5505, chapter=CHAPTERS["5"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter5_seed5505_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_6_full_run(width):
    io = ScriptedIO(width=width, overrides={"number": ["5"]})  # a whole-number guess, as a person types
    ctx = engine.Ctx(io=io, seed=6606, chapter=CHAPTERS["6"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter6_seed6606_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_7_full_run(width):
    io = ScriptedIO(width=width, overrides={"number": ["4", "5"]})  # whole-number guesses, as a person types
    ctx = engine.Ctx(io=io, seed=7707, chapter=CHAPTERS["7"], data=data.load_all())
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter7_seed7707_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_chapter_8_full_run(width):
    # One scenario, so the snapshot doesn't depend on the order of scenarios.toml: the richest one
    # (needs facts, high stakes, runs in the background). Choices: Sonnet, medium effort, fetch, caching.
    bundle = data.load_all()
    bundle = dataclasses.replace(bundle, scenarios=[s for s in bundle.scenarios if s.id == "medical-note-summarizer"])
    io = ScriptedIO(width=width, overrides={"choice": ["2", "2", "3", "2"]})
    ctx = engine.Ctx(io=io, seed=8808, chapter=CHAPTERS["8"], data=bundle)
    assert engine.run_chapter(ctx) == "done"
    check_snapshot(f"chapter8_seed8808_w{width}.txt", io.output, width)


@pytest.mark.parametrize("width", WIDTHS)
def test_cheat_sheet(width):
    from lessons import cheat_sheet

    io = ScriptedIO(width=width)
    pages = cheat_sheet.pages(data.load_all().glossary, io.console)
    assert engine.run_pages(io, cheat_sheet.TITLE, pages) == "done"
    check_snapshot(f"cheat_sheet_w{width}.txt", io.output, width)

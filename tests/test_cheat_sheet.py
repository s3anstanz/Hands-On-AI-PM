import dataclasses
import inspect
import re

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import costs
import data
import engine
import pricing
from lessons import CHAPTERS, cheat_sheet

BUNDLE = data.load_all()


def run_sheet(width=120):
    io = ScriptedIO(width=width)
    assert engine.run_pages(io, cheat_sheet.TITLE, cheat_sheet.pages(BUNDLE.glossary, io.console)) == "done"
    return io.output


@pytest.mark.parametrize("width", (40, 120))
def test_every_glossary_term_is_in_the_cheat_sheet(width):
    flat = " ".join(run_sheet(width).split())  # undo line wrapping
    for term in BUNDLE.glossary:
        assert f"{term.term} (Ch {term.chapter}): {' '.join(term.definition.split())}" in flat, term.term


def test_glossary_is_alphabetical():
    out = run_sheet()
    # An entry starts its line; "token" would also match inside "output token (Ch ...".
    positions = [
        re.search(rf"^{re.escape(t.term)} \(Ch ", out, re.M).start()
        for t in sorted(BUNDLE.glossary, key=lambda t: t.term.lower())
    ]
    assert positions == sorted(positions)


@pytest.mark.parametrize("width", (40, 80, 120))
def test_glossary_pages_fit_the_page(width):
    io = ScriptedIO(width=width)
    for page in cheat_sheet.glossary_pages(BUNDLE.glossary, io.console):
        before = len(io.output.splitlines())
        page(io.console)
        assert len(io.output.splitlines()) - before <= cheat_sheet.PAGE_LINES + 2  # + heading and blank line
    assert all(cell_len(line) <= width for line in io.output.splitlines())


def test_every_chapter_has_a_line():
    assert list(cheat_sheet.chapter_lines()) == list(CHAPTERS)


def test_key_numbers_are_computed_from_pricing():
    out = " ".join(run_sheet().split())
    for expected in (
        "0.75 English words by OpenAI's rule of thumb",
        f"≈ {pricing.CLAUDE_WORDS_PER_TOKEN:g} on current Claude",
        "1,000 words ≈ 1,333 tokens by the rule, ≈ 1,802 on current Claude",
        "An output token costs 5× an input token",
        "Cache reads cost 0.05× to 0.1× the input price. Writes 1.25× (5 min) or 2× (1 hour)",
        "Batch: 50% off",
        "up to 1M tokens",
        f"prices checked {pricing.LAST_CHECKED}",
    ):
        assert expected in out, expected
    for key in cheat_sheet.CLAUDE_CURRENT:
        model = pricing.get(key)
        assert f"{model.display_name}: {costs.format_usd(model.input)} in / {costs.format_usd(model.output)} out" in out


def test_a_price_change_shows_up_on_the_sheet(monkeypatch):
    sonnet = pricing.get("sonnet-5-5")
    monkeypatch.setitem(pricing.MODELS, "sonnet-5-5", dataclasses.replace(sonnet, output=sonnet.input * 6))
    assert "An output token costs 5× to 6× an input token" in " ".join(run_sheet().split())


def test_no_price_is_typed_into_the_sheet():
    assert not re.search(r"\$\d", inspect.getsource(cheat_sheet))


def test_a_models_price_note_is_shown_with_its_price():
    out = " ".join(run_sheet().split())
    noted = [pricing.get(key) for key in cheat_sheet.CLAUDE_CURRENT if pricing.get(key).note]
    assert noted  # Haiku 5.5's long-prompt tier
    for model in noted:
        assert f"{model.display_name}: " in out and " ".join(model.note.split()) in out

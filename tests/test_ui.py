import io
import random
import re

import pytest
from rich.cells import cell_len
from rich.console import Console

import sampling
import ui


def render(renderable, width=80) -> str:
    buffer = io.StringIO()
    Console(file=buffer, width=width, color_system=None, force_terminal=False).print(renderable)
    return buffer.getvalue()


def test_md_bolds_terms_and_escapes_brackets():
    assert ui.md("a **token** [x]") == "a [bold]token[/bold] \\[x]"


def test_bar_chart_sorted_with_percentages():
    out = render(ui.bar_chart(sampling.normalize({"clear": 18, "blue": 62, "dark": 20}), width=80))
    lines = [line for line in out.splitlines() if line.strip()]
    assert "blue" in lines[0] and "62%" in lines[0]
    assert "clear" in lines[-1] and "18%" in lines[-1]


def test_bar_chart_counts_mode():
    out = render(ui.bar_chart({"blue": 0.75, "gray": 0.25}, width=80, counts={"blue": 15, "gray": 5}))
    assert "15×" in out and "5×" in out


def test_bar_chart_fits_narrow_terminal():
    probs = sampling.normalize({"extraordinarily": 5, "blue": 3, "x": 1})
    out = render(ui.bar_chart(probs, width=40), width=40)
    assert all(len(line) <= 40 for line in out.splitlines())


def test_learn_panel_shows_all_parts():
    out = render(
        ui.learn_panel(
            "Tokens",
            "A **token** is a piece.",
            "It's the unit of cost.",
            2,
            7,
            analogy="Lego bricks.",
            example="un + believ + able",
        )
    )
    for text in ("2 of 7 · Tokens", "token", "Think of it like:", "Lego bricks.", "Example:", "Why a PM cares:"):
        assert text in out


def test_learn_panel_narrow():
    out = render(ui.learn_panel("T", "word " * 40, "why", 1, 1), width=40)
    assert all(len(line) <= 40 for line in out.splitlines())


def test_footer():
    assert (
        ui.footer("3", 4, 11, 48213) == "Ch 3 · Step 4/11 · seed 48213   [Enter] next  [b] back  [q] menu  [f] feedback"
    )
    assert "live spent $0.0042" in ui.footer("3", 4, 11, 48213, spent=0.0042)


def test_bar_chart_rounds_halves_up_so_different_counts_differ():
    # Bar width 10 at 40 columns: 5 of 20 is 2.5 cells and 3 of 20 is 1.5; half-to-even drew both as 2.
    out = render(ui.bar_chart({"a": 0.6, "b": 0.25, "c": 0.15}, width=40), width=40)
    filled = {line.split()[0]: line.count("█") for line in out.splitlines()}
    assert filled == {"a": 6, "b": 3, "c": 2}


def test_bar_chart_percent_labels_add_up_to_100():
    rng = random.Random(0)
    for _ in range(500):
        words = [f"w{i}" for i in range(rng.randint(2, 6))]
        probs = sampling.normalize({word: rng.random() for word in words})
        out = render(ui.bar_chart(probs, width=80))
        labels = [int(m[1]) for m in re.finditer(r"(\d+)%$", out, re.MULTILINE)]
        assert len(labels) == len(words) and sum(labels) == 100, (probs, labels)


def test_bar_chart_keeps_bar_lengths_from_the_odds():
    out = render(ui.bar_chart({"a": 0.335, "b": 0.335, "c": 0.33}, width=40), width=40)
    assert [line.count("█") for line in out.splitlines()] == [3, 3, 3]  # labels 34/33/33, bars untouched


LONG_TITLE = "From probabilities to a pick"


def test_learn_panel_keeps_a_long_title_whole_on_a_narrow_terminal():
    out = render(ui.learn_panel(LONG_TITLE, "Body.", "Why.", 1, 7, width=40), width=40)
    border, *rest = out.splitlines()
    assert "1 of 7" in border and "From" not in border
    assert LONG_TITLE in " ".join(" ".join(rest).replace("│", " ").split())


def test_learn_panel_puts_a_title_that_fits_in_the_border():
    out = render(ui.learn_panel(LONG_TITLE, "Body.", "Why.", 1, 7, width=80), width=80)
    assert f"1 of 7 · {LONG_TITLE}" in out.splitlines()[0]
    assert out.count(LONG_TITLE) == 1


def test_shows_is_one_caption_style():
    assert render(ui.shows("odds [x] reshape")).strip() == "What this shows: odds [x] reshape"


def test_bar_chart_of_the_top_few_keeps_their_real_percents():
    # Chapter 1 charts only the top 4 candidates; their labels must not be rescaled to 100%.
    out = render(ui.bar_chart({"a": 0.35, "b": 0.25, "c": 0.20, "d": 0.12}, width=80))
    assert [int(m[1]) for m in re.finditer(r"(\d+)%$", out, re.MULTILINE)] == [35, 25, 20, 12]


def test_value_bars_scale_to_the_largest_value():
    out = render(ui.value_bars([("Big", 10.0, "$10"), ("Half", 5.0, "$5"), ("None", 0.0, "$0")], width=60))
    big, half, none = (line for line in out.splitlines() if line.strip())
    assert big.count("█") == 2 * half.count("█") and "█" not in none
    assert big.rstrip().endswith("$10")


def test_value_bars_fit_40_columns_with_long_labels_and_values():
    rows = [("Gemini 3.8 Flash*", 1_200_000_000.0, "$1,200,000,000.00"), ("Haiku 5.5", 1.0, "$1.00")]
    out = render(ui.value_bars(rows, width=40), width=40)
    assert all(len(line) <= 40 for line in out.splitlines())
    assert "$1,200,000,000.00" in out and "Gemini 3.8 Flash*" in out


def test_value_bars_all_zero():
    out = render(ui.value_bars([("A", 0.0, "too long")], width=40), width=40)
    assert "too long" in out and "█" not in out


def test_compact_table_fits_40_columns():
    table = ui.compact_table("Size", "Haiku 5.5", "Sonnet 5.5", "Opus 5.5")
    table.add_row("500K", "$0.0002", "$0.0040", "$0.0080")
    out = render(table, width=40)
    assert all(len(line) <= 40 for line in out.splitlines())
    assert "Size" in out and "Opus 5.5" in out and "$0.0080" in out


@pytest.mark.parametrize(
    "name, label",
    [("Claude Sonnet 5.5", "Sonnet 5.5"), ("Gemini 3.1 Pro (Preview)", "Gemini 3.1 Pro"), ("GPT-6 Luna", "GPT-6 Luna")],
)
def test_model_label(name, label):
    assert ui.model_label(name) == label


def test_a_long_chapter_title_moves_into_the_question_panel_body():
    title = "Context windows: what the model can see"
    narrow = render(ui.question_panel(title, "Design an AI feature for X.", "note", width=40), width=40)
    words = " ".join(narrow.replace("│", " ").split())
    assert title in words and "…" not in narrow  # whole (wrapped in the body), not cut at the border
    assert all(cell_len(line) <= 40 for line in narrow.splitlines())
    wide = render(ui.question_panel(title, "Design an AI feature for X.", "note", width=120), width=120)
    assert wide.splitlines()[0].count(title) == 1  # still in the border when it fits

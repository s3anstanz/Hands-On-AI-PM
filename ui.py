"""Shared rendering. Pure output: no prompts and no navigation."""

import math
import re

from rich import box
from rich.cells import cell_len
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import costs

ILLUSTRATIVE = "Illustrative odds, computed with the same math real models use."


def md(text: str) -> str:
    """Escape Rich markup in our copy, then render **term** as bold."""
    return re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/bold]", escape(text))


def percent_labels(probs: dict[str, float]) -> dict[str, int]:
    """Whole percents whose sum is the rounded total (largest remainder), so full odds never show 101%.

    Not rescaled: a chart of the top few candidates keeps their real percents.
    """
    exact = {word: 100 * p for word, p in probs.items()}
    whole = {word: math.floor(value) for word, value in exact.items()}
    short = round(sum(exact.values())) - sum(whole.values())
    for word in sorted(exact, key=lambda w: (whole[w] - exact[w], -exact[w]))[:short]:
        whole[word] += 1
    return whole


def shows(text: str) -> str:
    """The one-line caption under an experiment: what it shows, tied back to a Learn idea (spec §5 step 5)."""
    return f"[dim]What this shows: {escape(text)}[/dim]"


def bar_chart(
    probs: dict[str, float],
    width: int,
    highlight: str | None = None,
    dimmed: frozenset[str] = frozenset(),
    counts: dict[str, int] | None = None,
) -> Table:
    """One row per candidate, highest first. `dimmed` = filtered out (grayed, struck)."""
    bar_width = max(8, min(30, width - 30))
    percents = percent_labels(probs)
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", no_wrap=True, max_width=14, overflow="ellipsis")
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    for word, p in sorted(probs.items(), key=lambda item: item[1], reverse=True):
        if word in dimmed:
            style = "dim strike"
        elif word == highlight:
            style = "bold green"
        else:
            style = "cyan"
        filled = math.floor(p * bar_width + 0.5)  # halves round up, so 3 and 5 of 20 never draw the same bar
        label = f"{counts[word]}×" if counts is not None else f"{percents[word]}%"
        table.add_row(
            Text(word, style=style),
            Text("█" * filled + "·" * (bar_width - filled), style=style),
            Text(label, style=style),
        )
    return table


def value_bars(rows: list[tuple[str, float, str]], width: int) -> Table:
    """One row per (label, value, shown text), each bar scaled to the largest value.

    Labels and shown text never wrap; the bar shrinks to fit (down to 4 cells).
    """
    label_width = max((cell_len(label) for label, _, _ in rows), default=0)
    shown_width = max((cell_len(shown) for _, _, shown in rows), default=0)
    bar_width = max(4, min(30, width - label_width - shown_width - 2))
    top = max((value for _, value, _ in rows), default=0.0) or 1.0
    table = Table.grid(padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    for label, value, shown in rows:
        filled = round(value / top * bar_width)
        table.add_row(Text(label), "█" * filled + "·" * (bar_width - filled), Text(shown))
    return table


def compact_table(*headers: str) -> Table:
    """A table with no side borders, so a few short columns fit 40 columns. Columns after the first align right."""
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="bold")
    for i, header in enumerate(headers):
        table.add_column(header, justify="right" if i else "left", no_wrap=i > 0)
    return table


def model_label(display_name: str) -> str:
    """A short model name for narrow tables: "Claude Sonnet 5.5" -> "Sonnet 5.5"."""
    return display_name.removeprefix("Claude ").removesuffix(" (Preview)")


def learn_panel(
    title: str,
    body: str,
    why_pm: str,
    index: int,
    total: int,
    analogy: str = "",
    example: str = "",
    width: int | None = None,
) -> Panel:
    """A Learn screen. When "N of M · Title" won't fit the border at `width`, the title opens the body instead."""
    heading = f"{index} of {total} · {title}"
    fits = width is None or cell_len(heading) + 6 <= width  # "╭─ " + title + " ─╮"
    parts = [md(body)] if fits else [f"[bold]{escape(title)}[/bold]", md(body)]
    if analogy:
        parts.append(f"\n[italic]Think of it like:[/italic] {md(analogy)}")
    if example:
        parts.append(f"\n[italic]Example:[/italic] {md(example)}")
    parts.append(f"\n[bold magenta]Why a PM cares:[/bold magenta] {md(why_pm)}")
    border = escape(heading) if fits else f"{index} of {total}"
    return Panel("\n".join(parts), title=border, title_align="left", padding=(1, 2))


def question_panel(chapter_title: str, question: str, note: str, width: int | None = None) -> Panel:
    """The chapter's question. A title too long for the border at `width` opens the body instead."""
    fits = width is None or cell_len(chapter_title) + 6 <= width  # "╭─ " + title + " ─╮"
    heading = "" if fits else f"[bold]{escape(chapter_title)}[/bold]\n\n"
    return Panel(
        f'{heading}[bold]Question:[/bold] "{escape(question)}"\n\n[dim]{escape(note)}[/dim]',
        title=escape(chapter_title) if fits else None,
        title_align="left",
        padding=(1, 2),
    )


def answer_panel(answer: str) -> Panel:
    """The user's typed answer, shown read-only while they grade it."""
    return Panel(escape(answer), title="Your answer", title_align="left", border_style="dim", padding=(0, 1))


def strong_answer_panel(sample: str) -> Panel:
    return Panel(escape(sample), title="A strong answer", title_align="left", border_style="magenta", padding=(0, 1))


def recap_panel(items: tuple[str, ...], question: str) -> Panel:
    count = f"{len(items)} point. It's" if len(items) == 1 else f"{len(items)} points. They're"
    intro = f'This chapter in {count} also what a strong answer to "{escape(question)}" covers.'
    bullets = "\n".join(f"• {md(item)}" for item in items)
    return Panel(f"{intro}\n\n{bullets}", title="Recap", title_align="left", padding=(1, 2))


def footer(
    chapter_id: str, step: int, total: int, seed: int, spent: float | None = None, quit_label: str = "menu"
) -> str:
    parts = [f"Ch {chapter_id}", f"Step {step}/{total}", f"seed {seed}"]
    if spent is not None:
        parts.append(f"live spent {costs.format_usd(spent)}")
    return " · ".join(parts) + f"   [Enter] next  [b] back  [q] {quit_label}  [f] feedback"


def page_footer(title: str, page: int, total: int) -> str:
    return f"{title} · Page {page}/{total}   [Enter] next  [b] back  [q] menu  [f] feedback"

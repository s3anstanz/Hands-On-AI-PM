"""Cheat sheet + glossary (spec §6): `--lesson cheat` or C on the menu.

Read-only pages: no question, no grading, nothing saved. Every number is
computed from pricing.py, so the sheet never goes out of date by itself.
"""

from rich.console import Console
from rich.markup import escape
from rich.text import Text

import costs
import pricing
from data import GlossaryTerm
from engine import Page
from lessons import ch2_tokens

KEY = "C"
TITLE = "Cheat sheet + glossary"
MINUTES = 3
PAGE_LINES = 18  # glossary lines per page: fits a 24-row terminal with the heading and footer
CLAUDE_CURRENT = ("opus-5-5", "sonnet-5-5", "haiku-5-5")


def _ratio_range(values: list[float]) -> str:
    """One ratio when every model agrees, a range when they differ. Rounded: 0.01 / 0.1 isn't exactly 0.1."""
    low, high = round(min(values), 6), round(max(values), 6)
    return f"{low:g}×" if low == high else f"{low:g}× to {high:g}×"


def chapter_lines() -> dict[str, str]:
    """One quotable takeaway per chapter, with its number where it has one."""
    models = [pricing.get(key) for key in CLAUDE_CURRENT]
    opus, haiku = pricing.get("opus-5-5"), pricing.get("haiku-5-5")
    window = max(m.context_window for m in models)
    return {
        "1": "An LLM writes one token at a time, picking from probabilities. Its knowledge ends at the training cutoff.",
        "2": f"Price, speed and limits are counted in tokens. Hindi takes {ch2_tokens.HINDI_X:.1f}× the tokens of English.",
        "3": "Temperature changes the pick, not the facts. The newest Claude models fix it, so steer with prompts and checks.",
        "4": "Hallucinations are fluent and false. Give the model the facts; temperature 0 won't fix them.",
        "5": f"Opus costs {opus.input / haiku.input:g}× Haiku per token. Route easy work to small models and commit with conditions.",
        "6": f"An output token costs {_ratio_range([m.output / m.input for m in models])} an input token. "
        "Always end on cost per user per month.",
        "7": f"Every request re-sends the whole context window (up to {window / 1_000_000:g}M tokens). The model has no memory.",
        "8": "Cover user, requirements, model, settings, context, cost, risks and measurement. Then commit and name what would change your mind.",
    }


def key_numbers() -> list[str]:
    models = [pricing.get(key) for key in CLAUDE_CURRENT]
    rule, claude = pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN, pricing.CLAUDE_WORDS_PER_TOKEN
    context = max(m.context_window for m in models)
    return [
        f"One token ≈ {rule:g} English words by OpenAI's rule of thumb, ≈ {claude:g} on current Claude.",
        f"1,000 words ≈ {round(1000 / rule):,} tokens by the rule, ≈ {round(1000 / claude):,} on current Claude.",
        f"An output token costs {_ratio_range([m.output / m.input for m in models])} an input token.",
        f"Cache reads cost {_ratio_range([m.cache_read / m.input for m in models])} the input price. "
        f"Writes {_ratio_range([m.cache_write_5m / m.input for m in models if m.cache_write_5m])} (5 min) "
        f"or {_ratio_range([m.cache_write_1h / m.input for m in models if m.cache_write_1h])} (1 hour).",
        f"Batch: {max(m.batch_discount for m in models):.0%} off, for work nobody is waiting on.",
        f"Context window: up to {context / 1_000_000:g}M tokens on current Claude models.",
        *(
            f"{m.display_name}: {costs.format_usd(m.input)} in / {costs.format_usd(m.output)} out per 1M tokens."
            + (f" {m.note}" if m.note else "")
            for m in models
        ),
    ]


def _heading(console: Console, text: str) -> None:
    console.print(f"[bold]{escape(text)}[/bold]\n")


def chapters_page(console: Console) -> None:
    _heading(console, "Chapters in one line each")
    for chapter_id, line in chapter_lines().items():
        console.print(f"[bold]{chapter_id}[/bold]  {escape(line)}")


def numbers_page(console: Console) -> None:
    _heading(console, "Key numbers")
    for line in key_numbers():
        console.print(f"• {escape(line)}")
    console.print(f"\n[dim]prices checked {pricing.LAST_CHECKED}[/dim]")


def _entry(term: GlossaryTerm) -> Text:
    return Text.assemble((term.term, "bold"), f" (Ch {term.chapter}): {term.definition}")


def glossary_pages(glossary: list[GlossaryTerm], console: Console) -> list[Page]:
    """Alphabetical, split so each page's entries fit PAGE_LINES lines at this console's width."""
    groups: list[list[GlossaryTerm]] = [[]]
    used = 0
    for term in sorted(glossary, key=lambda t: t.term.lower()):
        lines = len(_entry(term).wrap(console, console.width))
        if groups[-1] and used + lines > PAGE_LINES:
            groups.append([])
            used = 0
        groups[-1].append(term)
        used += lines
    pages: list[Page] = []
    for number, group in enumerate(groups, 1):

        def page(console: Console, group: list[GlossaryTerm] = group, number: int = number) -> None:
            _heading(console, f"Glossary ({number} of {len(groups)})")
            for term in group:
                console.print(_entry(term))

        pages.append(page)
    return pages


def pages(glossary: list[GlossaryTerm], console: Console) -> list[Page]:
    return [chapters_page, numbers_page, *glossary_pages(glossary, console)]

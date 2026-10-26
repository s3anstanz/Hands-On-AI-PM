"""Runs one chapter: builds its step list, handles Enter / b / q, and gives
every step its own seeded random generator so going back shows the same numbers.

Step order (spec §5): question, Learn screens, Recap, Quick checks, hands-on,
Answer, Grade, Follow-up (or the chapter's own after-grade steps). Learn-only
mode stops after the Quick checks.
"""

import functools
import hashlib
import importlib
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.markup import escape
from rich.table import Table

import data
import feedback
import pricing
import progress
import ui
from data import ChapterRubric

if TYPE_CHECKING:
    from live import GradeResult

MIN_ANSWER_WORDS = 3  # spec §5: at least one sentence
OPENING_NOTE = (
    "You'll answer this in your own words at the end of the chapter. "
    "The Recap at the end of the Learn section lists what a strong answer covers."
)
HINT_WORD = "h"
THOUSANDS = re.compile(r"-?\d{1,3}(,\d{3})+(\.\d+)?")


def show_number(value: float) -> str:
    """1000000 -> "1,000,000" (":g" alone prints 1e+06); 0.5 -> "0.5"."""
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:g}"


def parse_number(reply: str, integer: bool = False) -> float | None:
    """The number typed, or None. "50,000" works, "0,5" doesn't (it's ambiguous); "-0" comes back as 0.

    Whole numbers are ASCII digits only (commas allowed), so "7.5", "-3" and "٣" are refused.
    """
    plain = reply.replace(",", "") if THOUSANDS.fullmatch(reply) else reply
    if integer:
        return float(plain) if plain.isascii() and plain.isdigit() else None
    try:
        return float(plain) + 0.0  # + 0.0 turns -0 into 0, so it never shows as "-0"
    except ValueError:
        return None


class LiveAPI(Protocol):
    """The parts of live.LiveSession that chapters use (tests pass a stand-in)."""

    spent: float
    last_error: str

    def grade(self, question: str, checklist: tuple[str, ...], answer: str) -> "GradeResult | None": ...

    def count_tokens(self, text: str, model_id: str) -> int | None: ...

    def temperature_run(self, prompt: str, temperature: float, n: int) -> list[str]: ...


class IO(Protocol):
    """Where prompts go. `kind` lets tests answer by prompt type; the terminal ignores it.

    Kinds: menu, nav, pause, choice, number, optional, yesno, offer, multiline.
    "optional" is free text where an empty line means "done".
    """

    console: Console

    def ask(self, prompt: str, kind: str) -> str: ...


class TerminalIO:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        _enable_line_editing()

    def ask(self, prompt: str, kind: str) -> str:
        # input() prints the prompt itself, so the line editor knows where the text starts and can move
        # back across a long answer that has wrapped onto the next line.
        return input(f"{prompt} ")


def _enable_line_editing() -> None:
    """Arrow keys, Home/End, and backspacing across a wrapped line (GNU readline or macOS libedit)."""
    try:
        importlib.import_module("readline")  # importing it is what switches input() to the line editor
    except ImportError:
        return  # Windows has no readline; plain input() still works, just without editing across a wrap


def ask_yes_no(io: IO, prompt: str, default: bool = False, kind: str = "yesno") -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        reply = io.ask(f"{prompt} [{hint}]", kind).strip().lower()
        if not reply:
            return default
        if reply in ("y", "yes"):
            return True
        if reply in ("n", "no"):
            return False
        io.console.print("Please type y or n.")


def read_lines(io: IO, prompt: str, previous: str = "") -> str:
    """Free text over several lines, finished by an empty line (which keeps `previous`)."""
    io.console.print(f"{escape(prompt)} [dim](finish with an empty line)[/dim]")
    if previous:
        io.console.print(f"[dim]Your previous answer (an empty line keeps it):[/dim]\n{escape(previous)}")
    lines: list[str] = []
    while True:
        line = io.ask(">", "multiline")
        if not line.strip():
            return "\n".join(lines) or previous
        lines.append(line.rstrip())


def give_feedback(io: IO, where: str, live_on: bool) -> None:
    """Write a note, preview it, then open it on GitHub for the user to submit."""
    console = io.console
    console.print(
        "\n[bold]Feedback[/bold] [dim]becomes a GitHub issue on this project. "
        "Nothing is sent until you click Submit on GitHub.[/dim]"
    )
    text = read_lines(io, "What would you change? Anything confusing, broken, or good?")
    if not text:
        console.print("Nothing typed, so nothing sent.")
        return
    for i, kind in enumerate(feedback.KINDS, 1):
        console.print(f"  {i}. {kind}")
    while True:
        reply = io.ask(f"What kind of feedback? [1-{len(feedback.KINDS)}]", "choice").strip()
        if reply.isdecimal() and 1 <= int(reply) <= len(feedback.KINDS):
            break
        console.print(f"Please type a number from 1 to {len(feedback.KINDS)}.")
    summary = " ".join(io.ask("Give it a short title (Enter to use the first line of your note)", "optional").split())
    kind = feedback.KINDS[int(reply) - 1]
    note = feedback.Note(kind, text, where, feedback.environment(console.width, live_on), summary)
    console.print(f"[bold]Title:[/bold] {escape(feedback.title(note))}")
    console.print(f"[bold]Where:[/bold] {escape(where)}")
    console.print(f"[dim]Also sent: {escape(feedback.describe(note.env))}[/dim]")
    if not ask_yes_no(io, "Open GitHub to submit it?", default=True):
        console.print("Not sent.")
        return
    send_feedback(io, note, feedback.save_pending(note))


def send_feedback(io: IO, note: feedback.Note, saved: Path | None) -> None:
    """Open the prefilled issue. `saved` is the local copy, removed once the user says it went through."""
    console = io.console
    url, trimmed = feedback.issue_url(note)
    if trimmed:
        console.print(
            "[yellow]Your note is long, so the GitHub link holds only the first part. "
            "Paste the rest into the issue before you submit.[/yellow]"
        )
    opened = feedback.open_browser(url)
    if opened:
        console.print("GitHub is open in your browser. [bold]Nothing is sent until you click Submit new issue.[/bold]")
    else:
        console.print("Couldn't open a browser. Open this link to submit:")
        console.print(escape(url), soft_wrap=True)
    if ask_yes_no(io, "Did you click Submit new issue?", default=opened):
        problem = feedback.discard(saved) if saved is not None else None
        if problem:
            console.print(f"[yellow]{escape(problem)}[/yellow]")
        console.print("Thanks! Your feedback is in.")
    elif saved is not None:
        console.print("Kept it. You'll be asked to send it next time you start the tutorial.")
    else:
        console.print("[yellow]Couldn't save it on this computer, so copy this link to send it later:[/yellow]")
        console.print(escape(url), soft_wrap=True)


def offer_unsent_feedback(io: IO) -> None:
    """At startup: offer to send notes that didn't go through last time."""
    notes, broken = feedback.load_pending()
    for path in broken:
        io.console.print(f"[yellow]Skipped an unreadable feedback note: {escape(str(path))}[/yellow]")
    if not notes:
        return
    count = f"{len(notes)} unsent feedback note" + ("s" if len(notes) > 1 else "")
    if not ask_yes_no(io, f"You have {count}. Send now?", default=True):
        io.console.print("They stay saved; you'll be asked again next time.")
        return
    for path, note in notes:
        send_feedback(io, note, path)


def make_rng(seed: int, chapter_id: str, step_index: int) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{chapter_id}:{step_index}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


@dataclass(frozen=True)
class LearnScreen:
    title: str
    body: str
    why_pm: str
    analogy: str = ""
    example: str = ""
    visual: Callable[["Ctx"], None] | None = None


@dataclass(frozen=True)
class QuickCheck:
    question: str
    options: tuple[str, ...]
    answer: int  # 0-based index into options
    explanation: str
    screen: int  # 1-based Learn screen to offer for rereading


Step = Callable[["Ctx"], None]


class LeaveStep(Exception):
    """Raised when b or q is typed at a prompt inside a step; run_chapter handles the move."""

    def __init__(self, move: str) -> None:
        super().__init__(move)
        self.move = move  # "back" | "quit"


@dataclass(frozen=True)
class Chapter:
    id: str
    title: str
    minutes: int
    learn: tuple[LearnScreen, ...]
    recap: tuple[str, ...]
    checks: tuple[QuickCheck, ...]
    hands_on: tuple[Step, ...]
    figures: Mapping[str, str] = field(default_factory=dict)  # fills {name} in this chapter's rubric
    # Steps after grading. Empty means the usual one follow-up from the rubric;
    # Chapter 8 uses its own (three scenario follow-ups, then the evals teaser).
    after_grade: tuple[Step, ...] = ()


@dataclass
class Ctx:
    io: IO
    seed: int
    chapter: Chapter
    data: data.Bundle
    live: LiveAPI | None = None  # live.LiveSession when a key is found
    on_scored: Callable[[progress.Score, progress.Score | None], None] | None = None
    state: dict = field(default_factory=dict)
    rng: random.Random = field(init=False)  # run_chapter reseeds it for every step
    step_index: int = 0
    step_count: int = 0

    def __post_init__(self) -> None:
        # Seeded even outside run_chapter, so a step called directly (as in tests) is repeatable.
        self.rng = make_rng(self.seed, self.chapter.id, 0)

    @property
    def console(self) -> Console:
        return self.io.console

    @property
    def rubric(self) -> ChapterRubric:
        return self.data.rubrics[self.chapter.id].filled(self.chapter.figures)

    def feedback(self, where: str | None = None) -> None:
        chapter = f"Chapter {self.chapter.id} ({self.chapter.title})"
        where = where or f"{chapter}, step {self.step_index + 1} of {self.step_count}, seed {self.seed}"
        give_feedback(self.io, where, self.live is not None)

    def _nav_word(self, reply: str) -> bool:
        """b and q leave the step. f sends feedback and returns True, so the caller asks again."""
        word = reply.strip().lower()
        if word == "b":
            raise LeaveStep("back")
        if word == "q":
            raise LeaveStep("quit")
        if word in feedback.FEEDBACK_WORDS:
            self.feedback()
            return True
        return False

    def ask_choice(self, prompt: str, n: int, key: str) -> int:
        previous = self.state.get(key)
        hint = f" (Enter keeps: {previous + 1})" if previous is not None else ""
        while True:
            reply = self.io.ask(f"{prompt} [1-{n}]{hint}", "choice").strip()
            if not reply and previous is not None:
                return previous
            if self._nav_word(reply):
                continue
            if reply.isdecimal() and 1 <= int(reply) <= n:
                self.state[key] = int(reply) - 1
                return self.state[key]
            self.console.print(f"Please type a number from 1 to {n}.")

    def ask_number(self, prompt: str, key: str, low: float, high: float, integer: bool = False) -> float:
        """A number in [low, high]. With integer=True only whole numbers are accepted (for count predictions)."""
        previous = self.state.get(key)
        hint = f" (Enter keeps: {show_number(previous)})" if previous is not None else ""
        span = f"{show_number(low)}-{show_number(high)}"
        while True:
            reply = self.io.ask(f"{prompt} [{span}]{hint}", "number").strip()
            if not reply and previous is not None:
                return previous
            if self._nav_word(reply):
                continue
            value = parse_number(reply, integer)
            if value is not None and low <= value <= high:
                self.state[key] = value
                return value
            self.console.print(
                f"Please type a {'whole number' if integer else 'number'} from {show_number(low)} to {show_number(high)}."
            )

    def ask_number_or_skip(self, prompt: str, key: str, low: float, high: float, integer: bool = False) -> float | None:
        """A number in [low, high], or None when the user presses Enter (ends a "try another" loop)."""
        span = f"{show_number(low)}-{show_number(high)}"
        while True:
            reply = self.io.ask(f"{prompt} [{span}, Enter to move on]", "optional").strip()
            if not reply:
                return None
            if self._nav_word(reply):
                continue
            value = parse_number(reply, integer)
            if value is not None and low <= value <= high:
                self.state[key] = value
                return value
            self.console.print(
                f"Please type a {'whole number' if integer else 'number'} from {show_number(low)} to {show_number(high)}, "
                "or press Enter to move on."
            )

    def ask_line(self, prompt: str) -> str:
        """One line of free text, as typed; "" when the user presses Enter. b, q and f work as elsewhere."""
        while True:
            reply = self.io.ask(prompt, "optional")
            if not self._nav_word(reply):
                return reply

    def ask_yes_no(self, prompt: str, default: bool = False) -> bool:
        return ask_yes_no(self.io, prompt, default)

    def pause(self, prompt: str) -> None:
        """Wait for Enter inside a step; b, q and f still work."""
        while self._nav_word(self.io.ask(prompt, "pause")):
            pass

    def ask_multiline(self, prompt: str, key: str) -> str:
        value = read_lines(self.io, prompt, self.state.get(key) or "")
        self.state[key] = value
        return value


def _question_step(ctx: Ctx) -> None:
    ctx.console.print(ui.question_panel(ctx.chapter.title, ctx.rubric.question, OPENING_NOTE, width=ctx.console.width))


def _show_learn(ctx: Ctx, number: int) -> None:
    screen = ctx.chapter.learn[number - 1]
    ctx.console.print(
        ui.learn_panel(
            screen.title,
            screen.body,
            screen.why_pm,
            number,
            len(ctx.chapter.learn),
            screen.analogy,
            screen.example,
            width=ctx.console.width,
        )
    )
    if screen.visual is not None:
        screen.visual(ctx)


def _learn_step(number: int) -> Step:
    def step(ctx: Ctx) -> None:
        _show_learn(ctx, number)

    return step


def _recap_step(ctx: Ctx) -> None:
    ctx.console.print(ui.recap_panel(ctx.chapter.recap, ctx.rubric.question))


def _check_step(check: QuickCheck, number: int) -> Step:
    def step(ctx: Ctx) -> None:
        ctx.console.print(f"[bold]Quick check {number}[/bold] [dim](not graded)[/dim]\n{escape(check.question)}")
        for i, option in enumerate(check.options, 1):
            ctx.console.print(f"  {i}. {escape(option)}")
        if ctx.ask_choice("Your pick", len(check.options), key=f"check{number}") == check.answer:
            ctx.console.print(f"[green]Right.[/green] {escape(check.explanation)}")
            return
        ctx.console.print(f"[yellow]Not quite: it's {check.answer + 1}.[/yellow] {escape(check.explanation)}")
        if ctx.ask_yes_no(f"Reread Learn screen {check.screen}?", default=True):
            _show_learn(ctx, check.screen)

    return step


def _answer_step(ctx: Ctx) -> None:
    ctx.console.print(ui.question_panel(ctx.chapter.title, ctx.rubric.question, "Your turn.", width=ctx.console.width))
    while True:
        previous = ctx.state.get("answer")
        answer = ctx.ask_multiline(
            "Answer out loud, then type your answer in your own words. Stuck? Type h for a hint.", "answer"
        )
        if answer.strip().lower() == HINT_WORD:
            ctx.state["answer"] = previous  # "h" asked for the hint; it isn't an answer
            ctx.console.print(f"[bold]Hint:[/bold] {escape(ctx.rubric.hint)}")
            continue
        if answer:
            if len(answer.split()) < MIN_ANSWER_WORDS:
                ctx.console.print(
                    "That's very short. Aim for at least one full sentence: say it out loud, then type it."
                )
                if ctx.ask_yes_no("Try again?", default=True):
                    continue
            ctx.state["skip_grading"] = False
            return
        if ctx.ask_yes_no("Nothing typed. Skip grading this time?", default=True):
            ctx.state["skip_grading"] = True
            return


def _grade_step(ctx: Ctx) -> None:
    if ctx.state.get("skip_grading"):
        ctx.console.print("Grading skipped. Nothing saved for this chapter.")
    else:
        _grade(ctx)
    ctx.console.print(ui.strong_answer_panel(ctx.rubric.sample_answer))
    ctx.console.print("Now say it out loud once more, in your own words.")


def _grade(ctx: Ctx) -> None:
    checklist = ctx.rubric.checklist
    ctx.console.print(ui.answer_panel(ctx.state.get("answer", "")))
    ctx.console.print("[bold]A strong answer covers these. Did yours?[/bold]")
    got = sum(ctx.ask_yes_no(f"{i}. {item}") for i, item in enumerate(checklist, 1))
    self_score = progress.Score(got, len(checklist))
    ctx.console.print(f"Self-score: [bold]{self_score}[/bold]")
    claude_score = None
    if ctx.live is not None and ctx.ask_yes_no(
        f"Have Claude grade it too? (~{pricing.GRADE_COST_HINT}, prices checked {pricing.LAST_CHECKED})"
    ):
        result = ctx.live.grade(ctx.rubric.question, checklist, ctx.state.get("answer", ""))
        if result is None:
            ctx.console.print(
                f"[yellow]Claude grading unavailable: {escape(ctx.live.last_error)}.[/yellow] Your self-score still counts."
            )
        else:
            table = Table(show_header=True, header_style="bold", expand=True)
            table.add_column("", width=2)
            table.add_column("Checklist item", ratio=1)
            table.add_column("Claude's reason", ratio=2)
            for item in result.items:
                table.add_row("✓" if item.met else "✗", escape(item.item), escape(item.why))
            ctx.console.print(table)
            ctx.console.print(f"[bold]Feedback:[/bold] {escape(result.feedback)}")
            claude_score = progress.Score(result.met_count, len(checklist))
            ctx.console.print(f"Claude's score: [bold]{claude_score}[/bold]")
    if ctx.on_scored is not None:
        ctx.on_scored(self_score, claude_score)


def _followup_step(ctx: Ctx) -> None:
    followup = ctx.rng.choice(ctx.rubric.followups)
    ctx.console.print(f"[bold]Follow-up:[/bold] {escape(followup.question)}")
    ctx.ask_multiline("Your reply", "followup")
    ctx.console.print(f"[bold magenta]A strong answer mentions:[/bold magenta] {escape(followup.strong)}")


def build_steps(chapter: Chapter, learn_only: bool) -> list[Step]:
    steps: list[Step] = [_question_step]
    steps += [_learn_step(n) for n in range(1, len(chapter.learn) + 1)]
    steps.append(_recap_step)
    steps += [_check_step(check, n) for n, check in enumerate(chapter.checks, 1)]
    if not learn_only:
        steps += [*chapter.hands_on, _answer_step, _grade_step, *(chapter.after_grade or (_followup_step,))]
    return steps


def _read_move(io: IO, prompt: str, quit_label: str, send_feedback: Callable[[], None], back_note: str) -> str:
    """Enter, b or q at a footer. f sends feedback, then asks again."""
    while True:
        reply = io.ask(prompt, "nav").strip().lower()
        if reply == "":
            return "next"
        if reply == "b":
            return "back"
        if reply == "q":
            return "quit"
        if reply in feedback.FEEDBACK_WORDS:
            send_feedback()
            io.console.print(back_note)
            continue
        io.console.print(f"Press Enter to continue, or type b (back), q ({quit_label}) or f (feedback).")


def _ask_nav(ctx: Ctx, step_number: int, total: int, quit_label: str) -> str:
    spent = ctx.live.spent if ctx.live is not None else None
    prompt = ui.footer(ctx.chapter.id, step_number, total, ctx.seed, spent, quit_label)
    return _read_move(ctx.io, prompt, quit_label, ctx.feedback, f"Back to step {step_number}.")


def run_chapter(ctx: Ctx, learn_only: bool = False) -> str:
    """Returns "done" after the last step, or "quit" if the user pressed q."""
    steps = build_steps(ctx.chapter, learn_only)
    ctx.step_count = len(steps)
    index = 0
    while index < len(steps):
        ctx.step_index = index
        ctx.rng = make_rng(ctx.seed, ctx.chapter.id, index)
        if ctx.console.is_terminal:
            ctx.console.clear()
        try:
            steps[index](ctx)
            move = _ask_nav(ctx, index + 1, len(steps), "quit" if learn_only else "menu")
        except LeaveStep as leave:
            move = leave.move
        if move == "quit":
            return "quit"
        if move == "back":
            index = max(0, index - 1)
            continue
        index += 1
    if not learn_only and ask_yes_no(ctx.io, "How was this chapter? Want to send feedback?", kind="offer"):
        ctx.feedback(f"End of Chapter {ctx.chapter.id} ({ctx.chapter.title}), seed {ctx.seed}")
    return "done"


Page = Callable[[Console], None]


def run_pages(io: IO, title: str, pages: Sequence[Page], live_on: bool = False) -> str:
    """Read-only screens (the cheat sheet): Enter, b, q and f, no grading, nothing saved.

    Returns "done" after the last page, or "quit" if the user pressed q.
    """
    index = 0
    while index < len(pages):
        if io.console.is_terminal:
            io.console.clear()
        pages[index](io.console)
        number = index + 1
        where = f"{title}, page {number} of {len(pages)}"
        move = _read_move(
            io,
            ui.page_footer(title, number, len(pages)),
            "menu",
            functools.partial(give_feedback, io, where, live_on),
            f"Back to page {number}.",
        )
        if move == "quit":
            return "quit"
        index = max(0, index - 1) if move == "back" else index + 1
    return "done"

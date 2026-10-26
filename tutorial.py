"""Hands-On AI PM: run `python tutorial.py`, press Enter to learn.

Works fully offline. With an Anthropic credential, a few optional extras turn
on (official token counts, a real temperature run, Claude grading your answers).
"""

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path

from rich.markup import escape
from rich.table import Table

import data
import engine
import feedback
import live
import pricing
import progress
from lessons import CHAPTERS, cheat_sheet


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="tutorial.py", description="Hands-on AI training for product managers.")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--lesson", choices=[*CHAPTERS, "cheat"], help="jump straight to a chapter, or the cheat sheet")
    where.add_argument("--learn", choices=[*CHAPTERS, "all"], help="refresher: Learn screens only, nothing saved")
    parser.add_argument("--seed", type=int, help="replay an exact run (shown on every screen)")
    parser.add_argument("--offline", action="store_true", help="never call the API, even with a key")
    parser.add_argument("--reset-progress", action="store_true", help="delete saved scores")
    return parser.parse_args(argv)


def new_seed() -> int:
    return random.SystemRandom().randint(10_000, 99_999)


def run(argv=None, io=None, progress_path: Path | None = None, env=None, data_dir: Path | None = None) -> int:
    args = parse_args(argv)
    io = io or engine.TerminalIO()
    try:
        return _run(args, io, progress_path or progress.PROGRESS_PATH, env, data_dir or data.DATA_DIR)
    except (KeyboardInterrupt, EOFError):
        io.console.print("\nBye. Scores are saved each time you finish grading a chapter.")
        return 0


def _run(args, io, progress_path: Path, env, data_dir: Path) -> int:
    console = io.console
    try:
        bundle = data.load_all(data_dir)
    except data.DataError as exc:
        console.print(f"[red]Data file problem:[/red] {escape(str(exc))}")
        console.print("Fix that entry (or undo your edit) and run again.")
        return 1
    missing = [cid for cid in CHAPTERS if cid not in bundle.rubrics]
    if missing:
        console.print(f"[red]Data file problem:[/red] checklists.toml has no entry for chapter {', '.join(missing)}")
        return 1
    for cid, chapter in CHAPTERS.items():
        unknown = sorted(bundle.rubrics[cid].figure_names() - set(chapter.figures))
        if unknown:
            console.print(
                f"[red]Data file problem:[/red] checklists.toml: chapter {cid} uses {{{escape(unknown[0])}}}, "
                f"which Chapter {cid} doesn't compute"
            )
            return 1

    if args.reset_progress:
        if engine.ask_yes_no(io, "Delete all saved scores?"):
            problem = progress.reset(progress_path)
            console.print(f"[yellow]{escape(problem)}[/yellow]" if problem else "Progress cleared.")
        return 0

    engine.offer_unsent_feedback(io)
    seed = args.seed if args.seed is not None else new_seed()
    status = live.detect(env=env, offline=args.offline)
    session = live.LiveSession(status) if status.available else None
    saved, warning = progress.load(progress_path)
    notice = f"[yellow]{escape(warning)}[/yellow]" if warning else ""
    if notice and (args.learn or args.lesson):
        # The chapter clears the screen on its first step, so give the warning a moment.
        console.print(notice)
        io.ask("Press Enter to continue", "pause")

    played: set[str] = set()

    def play(chapter_id: str, learn_only: bool) -> str:
        nonlocal seed
        if chapter_id in played:
            # A retry with the same seed would replay the same prompt and answers. The new
            # seed is shown in the footer and menu, so --seed still replays this attempt.
            seed = new_seed()
        played.add(chapter_id)

        def on_scored(self_score, claude_score) -> None:
            progress.record(saved, chapter_id, self_score, claude_score, seed, datetime.now())
            problem = progress.save(saved, progress_path)
            if problem:
                console.print(f"[yellow]{escape(problem)}[/yellow]")

        ctx = engine.Ctx(io=io, seed=seed, chapter=CHAPTERS[chapter_id], data=bundle, live=session, on_scored=on_scored)
        return engine.run_chapter(ctx, learn_only=learn_only)

    if args.learn:
        for chapter_id in CHAPTERS if args.learn == "all" else [args.learn]:
            if play(chapter_id, learn_only=True) == "quit":
                break
        return 0

    def cheat() -> None:
        engine.run_pages(io, cheat_sheet.TITLE, cheat_sheet.pages(bundle.glossary, console), status.available)

    if args.lesson == "cheat":
        cheat()
    elif args.lesson:
        play(args.lesson, learn_only=False)

    while True:
        _render_menu(console, saved, seed, status, notice)
        notice = ""
        prompt = f"Pick a chapter ({', '.join(CHAPTERS)}), {cheat_sheet.KEY} for the cheat sheet, f for feedback, or q to quit"
        choice = io.ask(prompt, "menu").strip().lower()
        if choice == "q":
            return 0
        if choice in feedback.FEEDBACK_WORDS:
            engine.give_feedback(io, "Start menu", status.available)
        elif choice in CHAPTERS:
            play(choice, learn_only=False)
        elif choice == cheat_sheet.KEY.lower():
            cheat()
        else:
            notice = "Not a chapter number."


def _render_menu(console, saved: dict, seed: int, status: live.LiveStatus, notice: str = "") -> None:
    if console.is_terminal:
        console.clear()
    console.print(f"[bold]HANDS-ON AI PM[/bold]   seed {seed} · prices checked {pricing.LAST_CHECKED}")
    weak = set(progress.weakest(saved))
    rows = []
    for chapter_id, chapter in CHAPTERS.items():
        score = progress.latest_score(saved, chapter_id)
        last = f"last: {score}" if score else "not started"
        if chapter_id in weak:
            last += "   ← weakest"
        rows.append((chapter_id, chapter.title, f"~{chapter.minutes} min", last))
    rows.append((cheat_sheet.KEY, cheat_sheet.TITLE, f"~{cheat_sheet.MINUTES} min", ""))
    # Only the title shrinks on a narrow terminal; number, time and score stay whole.
    fixed = sum(max(len(row[i]) for row in rows) for i in (0, 2, 3)) + 2 * 4  # + 1 space each side of 4 columns
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("#", no_wrap=True)
    table.add_column("Chapter", no_wrap=True, overflow="ellipsis", max_width=max(8, console.width - fixed))
    table.add_column("Time", no_wrap=True)
    table.add_column("Last", no_wrap=True)
    for chapter_id, title, minutes, last in rows:
        table.add_row(chapter_id, escape(title), minutes, last)
    console.print(table)
    if status.available:
        console.print(f"Live mode: ON ({escape(status.source)})")
    else:
        console.print(f"Live mode: OFF ({escape(status.source)}). Everything works offline.")
    if notice:  # printed after the clear, so it stays on screen
        console.print(notice)


if __name__ == "__main__":
    sys.exit(run())

"""Saved scores, so the start menu can point at your weakest chapters.

Lives outside the repo (~/.config/hands-on-ai-pm/) so it survives re-clones
and never gets committed. Unreadable or unwritable files produce a warning,
never a crash.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROGRESS_PATH = Path.home() / ".config" / "hands-on-ai-pm" / "progress.json"


@dataclass(frozen=True)
class Score:
    got: int
    out_of: int

    @property
    def pct(self) -> float:
        return self.got / self.out_of if self.out_of else 0.0

    def __str__(self) -> str:
        return f"{self.got}/{self.out_of}"


def fresh() -> dict:
    return {"chapters": {}}


def load(path: Path) -> tuple[dict, str | None]:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or not isinstance(saved.get("chapters"), dict):
            raise ValueError("unexpected file layout")
        return saved, None
    except FileNotFoundError:
        return fresh(), None
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        # Move the file aside even when it's only unreadable: otherwise the next save would overwrite it.
        try:
            backup = _free_backup_name(path)
            path.replace(backup)
            kept = f" The old file was kept as {backup.name}."
        except OSError:
            kept = ""
        return fresh(), f"Couldn't read saved progress ({exc}); starting fresh.{kept}"


def _free_backup_name(path: Path) -> Path:
    """progress.json.bad, then .bad2, .bad3... so an older backup is never overwritten."""
    backup = path.with_name(path.name + ".bad")
    n = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.bad{n}")
        n += 1
    return backup


def record(
    saved: dict, chapter: str, self_score: Score | None, claude_score: Score | None, seed: int, now: datetime
) -> dict:
    entry: dict = {"at": now.isoformat(timespec="seconds"), "seed": seed}
    if self_score is not None:
        entry["self"] = [self_score.got, self_score.out_of]
    if claude_score is not None:
        entry["claude"] = [claude_score.got, claude_score.out_of]
    saved["chapters"][chapter] = entry
    return saved


def save(saved: dict, path: Path) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return None
    except OSError as exc:
        return f"Couldn't save progress to {path} ({exc}). This session still works; scores just won't be remembered."


def _score(pair: object) -> Score | None:
    if (
        isinstance(pair, list)
        and len(pair) == 2
        and all(isinstance(x, int) and not isinstance(x, bool) for x in pair)
        and pair[1] > 0
    ):
        return Score(pair[0], pair[1])
    return None


def latest_score(saved: dict, chapter: str) -> Score | None:
    entry = saved["chapters"].get(chapter)
    if not isinstance(entry, dict):
        return None
    return _score(entry.get("claude")) or _score(entry.get("self"))


def weakest(saved: dict, n: int = 2) -> list[str]:
    """Lowest-scoring chapters by percentage, at most n and always fewer than the chapters scored, so the
    mark tells chapters apart (two scored chapters get one mark, one gets none). Perfect scores are never 'weak'."""
    scores = [
        (score.pct, chapter) for chapter in saved["chapters"] if (score := latest_score(saved, chapter)) is not None
    ]
    weak = sorted(entry for entry in scores if entry[0] < 1)
    marked = weak[: min(n, len(scores) - 1)]
    rest = [pct for pct, chapter in scores if (pct, chapter) not in marked]
    while marked and rest and marked[-1][0] >= min(rest):  # never split a tie: a mark means lower than the rest
        marked.pop()
    return [chapter for _, chapter in marked]


def reset(path: Path) -> str | None:
    try:
        path.unlink(missing_ok=True)
        return None
    except OSError as exc:
        return f"Couldn't delete saved progress at {path} ({exc})."

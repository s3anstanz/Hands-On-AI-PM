"""Feedback as GitHub issues: type f (or /feedback) at any prompt.

Nothing is sent from here. The tutorial opens GitHub's new-issue page in your
browser, filled in through the feedback form (.github/ISSUE_TEMPLATE/feedback.yml),
and you click Submit. Each note is saved under ~/.config/hands-on-ai-pm/feedback/
until you confirm it went through, so a note written offline is offered again
next time the tutorial starts. Your chapter answers are never included.
"""

import json
import platform
import uuid
import webbrowser
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode

REPO = "s3anstanz/Hands-On-AI-PM"
FORM = "feedback.yml"
FEEDBACK_DIR = Path.home() / ".config" / "hands-on-ai-pm" / "feedback"
KINDS = ("Bug", "Confusing", "Idea", "Liked it")
TITLE_LENGTH = 72
MAX_URL_LENGTH = 6000  # GitHub answers "414 URI Too Long" past roughly 8K characters
TRIMMED = "\n\n[trimmed to fit a GitHub link]"
FEEDBACK_WORDS = ("f", "/feedback")


@dataclass(frozen=True)
class Env:
    commit: str
    python: str
    os: str
    width: str
    mode: str


@dataclass(frozen=True)
class Note:
    kind: str
    text: str
    where: str
    env: Env
    summary: str = ""  # the tester's short title; empty means "use the first line of the note"


def environment(width: int, live_on: bool) -> Env:
    return Env(
        commit=git_commit(Path(__file__).parent),
        python=platform.python_version(),
        os=platform.platform(terse=True),
        width=str(width),
        mode="live" if live_on else "offline",
    )


def describe(env: Env) -> str:
    return f"Commit {env.commit} · Python {env.python} · {env.os} · {env.width} columns · {env.mode} mode"


def git_commit(root: Path) -> str:
    """Short commit of a git checkout, read from .git so no git binary is needed."""
    git = root / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head.removeprefix("ref: ")
        loose = git / ref
        if loose.exists():
            return loose.read_text(encoding="utf-8").strip()[:7]
        for line in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if line.endswith(f" {ref}"):
                return line[:7]
    except OSError:
        return "unknown"
    return "unknown"


def title(note: Note) -> str:
    first = note.summary.strip() or next((line.strip() for line in note.text.splitlines() if line.strip()), "")
    full = f"{note.kind}: {first}"
    return full if len(full) <= TITLE_LENGTH else full[: TITLE_LENGTH - 1] + "…"


def _url(note: Note, text: str) -> str:
    query = {
        "template": FORM,
        "title": title(note),
        "feedback": text,
        "where": note.where,
        "environment": describe(note.env),
    }
    return f"https://github.com/{REPO}/issues/new?{urlencode(query, quote_via=quote)}"


def issue_url(note: Note) -> tuple[str, bool]:
    """The prefilled new-issue link, and whether the note had to be trimmed to fit."""
    url = _url(note, note.text)
    if len(url) <= MAX_URL_LENGTH:
        return url, False
    # Accents and emoji take up to 12 URL characters each, so search for the longest start that fits.
    low, high = 0, len(note.text)
    while low < high:
        mid = (low + high + 1) // 2
        if len(_url(note, note.text[:mid].rstrip() + TRIMMED)) <= MAX_URL_LENGTH:
            low = mid
        else:
            high = mid - 1
    return _url(note, note.text[:low].rstrip() + TRIMMED), True


def open_browser(url: str) -> bool:
    try:
        return webbrowser.open(url)
    except webbrowser.Error:
        return False


def save_pending(note: Note) -> Path | None:
    try:
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        path = FEEDBACK_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(asdict(note), indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


def _parse(raw: object) -> Note:
    if not isinstance(raw, dict) or not isinstance(raw.get("env"), dict):
        raise ValueError("unexpected layout")
    env = raw["env"]
    values = [raw.get(name) for name in ("kind", "text", "where")] + [env.get(f.name) for f in fields(Env)]
    summary = raw.get("summary", "")  # notes saved before summaries existed have none
    if not all(isinstance(value, str) for value in [*values, summary]):
        raise ValueError("unexpected layout")
    return Note(raw["kind"], raw["text"], raw["where"], Env(**{f.name: env[f.name] for f in fields(Env)}), summary)


def load_pending() -> tuple[list[tuple[Path, Note]], list[Path]]:
    """Saved notes not yet confirmed as sent, oldest first, plus any files that couldn't be read."""
    notes: list[tuple[Path, Note]] = []
    broken: list[Path] = []
    for path in sorted(FEEDBACK_DIR.glob("*.json")):
        try:
            notes.append((path, _parse(json.loads(path.read_text(encoding="utf-8")))))
        except (OSError, ValueError):  # json.JSONDecodeError is a ValueError
            broken.append(path)
    return notes, broken


def discard(path: Path) -> str | None:
    try:
        path.unlink(missing_ok=True)
        return None
    except OSError as exc:
        return f"Couldn't remove the saved copy at {path} ({exc}). Delete it so it isn't offered again."

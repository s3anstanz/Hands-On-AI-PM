"""Bookkeeping for the /consume skill (.claude/skills/consume/SKILL.md).

/consume reads open `feedback` issues and PRs with `gh`, saves them as JSON,
and asks this module which issues may be read and which need a decision. The judgment calls (what an
issue is, whether to close it) stay with the agents; the rules that must not
drift live here, with tests. This module never calls `gh` or the network.

    python consume.py screen RAW.json --owner LOGIN [--testers FILE]  # drop strangers' issues and comments
    python consume.py queue ISSUES.json PRS.json --owner LOGIN  # issues that need a decision
    python consume.py batches ROUTED.json [--cap N] # routed issues grouped into PRs

Both print JSON. Exit 2 means an input file is missing or malformed (one line
on stderr).
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path

MARKER = "<!-- consume -->"  # starts every comment /consume writes on an issue
AGENT_LABELS = ("cori", "frank", "needs-sean", "in-progress")
LANES = ("cori", "frank")
MAX_PRS_PER_RUN = 3
# The repo is public, so anyone can open an issue that the Feedback form labels `feedback`.
# Only the owner's and these testers' issues and comments ever reach an agent. Changing the list takes a PR.
TESTERS_PATH = str(Path(__file__).parent / ".claude" / "skills" / "consume" / "trusted-authors.txt")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")

_WHERE = re.compile(r"^### Where in the tutorial[ \t]*\n(.*?)(?=^### |\Z)", re.DOTALL | re.MULTILINE)
_CHAPTER = re.compile(r"\bChapter (\w+) \(")
_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class QueueItem:
    number: int
    chapter: str | None
    why: str  # "new" | "pending" | "requeued" | "stale" | "rejected"
    lane: str | None = None  # the issue's lane label, if it has one
    pr: int | None = None  # rejected: the latest PR closed without merging
    notes: tuple[str, ...] = ()  # requeued: the owner's comments since /consume last wrote


@dataclass(frozen=True)
class Batch:
    lane: str
    chapter: str | None
    issues: tuple[int, ...]


def chapter_of(body: str) -> str | None:
    """The chapter id in the issue form's "Where in the tutorial" field, if it names one."""
    where = _WHERE.search(body)
    match = _CHAPTER.search(where.group(1)) if where else None
    return match.group(1) if match else None


def closes(pr_body: str) -> set[int]:
    return {int(n) for n in _CLOSES.findall(pr_body)}


def _why(issue: dict, open_prs: set[int], closed_prs: dict[int, int], owner: str) -> QueueItem | None:
    number = issue["number"]
    labels = {label["name"] for label in issue["labels"]}
    lane = next((name for name in LANES if name in labels), None)
    item = partial(QueueItem, number, chapter_of(issue["body"]), lane=lane)
    comments = issue["comments"]
    ours = [i for i, comment in enumerate(comments) if MARKER in comment["body"]]
    if number in open_prs:
        return None
    if ours:
        since = comments[ours[-1] + 1 :]
        notes = tuple(comment["body"] for comment in since if comment["author"]["login"] == owner)
        if notes:
            return item("requeued", notes=notes)
    pr = closed_prs.get(number)
    seen = any(f"PR #{pr}" in comments[i]["body"] for i in ours)
    if pr and "needs-sean" not in labels and not seen:
        return item("rejected", pr=pr)
    if "in-progress" in labels:
        return item("stale")
    if "needs-sean" in labels:
        return None
    return item("pending" if lane else "new")


def load_testers(path: str) -> frozenset[str]:
    """The testers' GitHub logins, lowercased. Blank lines and `#` comments are skipped."""
    logins = set()
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        login = line.split("#", 1)[0].strip()
        if not login:
            continue
        if not _LOGIN.match(login):
            raise ValueError(f"line {number} is not a GitHub login: {line.strip()[:40]!r}")
        logins.add(login.lower())
    return frozenset(logins)


def screen(issues: list[dict], owner: str, testers: frozenset[str]) -> tuple[list[dict], list[dict]]:
    """The issues an agent may read, and the ones it may not.

    An issue is kept only when the owner or a listed tester opened it. On a kept issue, only the owner's
    and listed testers' comments are kept (/consume's own comments are the owner's). Everyone else's
    issues come back as {"number", "author"} for Sean's summary, and their text goes no further.
    """
    allowed = testers | {owner.lower()}
    safe, skipped = [], []
    for issue in issues:
        author = issue["author"]["login"]
        if author.lower() not in allowed:
            skipped.append({"number": issue["number"], "author": author})
            continue
        comments = [c for c in issue["comments"] if c["author"]["login"].lower() in allowed]
        safe.append({**issue, "comments": comments})
    return safe, skipped


def queue(issues: list[dict], prs: list[dict], owner: str) -> list[QueueItem]:
    """Open feedback issues that need something this run, in issue order.

    `pending` issues already have a lane (deferred past the cap, or handed off) and go straight to a build.
    Only `owner`'s comments after /consume's last comment requeue an issue. A rejection is handled once:
    /consume's next comment on the issue names the closed PR ("PR #61").
    """
    open_prs = {n for pr in prs if pr["state"] == "OPEN" for n in closes(pr["body"])}
    closed_prs: dict[int, int] = {}
    for pr in prs:
        if pr["state"] == "CLOSED":
            for n in closes(pr["body"]):
                closed_prs[n] = max(closed_prs.get(n, 0), pr["number"])
    found = (_why(issue, open_prs, closed_prs, owner) for issue in sorted(issues, key=lambda i: i["number"]))
    return [item for item in found if item]


def batches(routed: list[dict], cap: int = MAX_PRS_PER_RUN) -> tuple[list[Batch], list[int]]:
    """Group routed issues into PRs: one per lane and chapter; an issue with no chapter goes alone.

    Returns the first `cap` PRs to build (oldest issue first) and the issue numbers left for next run.
    """
    groups: dict[tuple[str, str | int], list[int]] = {}
    for item in routed:
        if item["lane"] not in LANES:
            raise ValueError(f"issue #{item['number']} has lane {item['lane']!r}, expected one of {LANES}")
        key = item["chapter"] if item["chapter"] is not None else item["number"]
        groups.setdefault((item["lane"], key), []).append(item["number"])
    every = sorted(
        (
            Batch(lane, key if isinstance(key, str) else None, tuple(sorted(numbers)))
            for (lane, key), numbers in groups.items()
        ),
        key=lambda b: b.issues[0],
    )
    deferred = sorted(n for batch in every[cap:] for n in batch.issues)
    return every[:cap], deferred


def _load(path: str, keys: dict[str, type], shape_ok: Callable[[dict], bool] = lambda _: True) -> list[dict]:
    """A JSON list of objects, each with these keys and types; anything else raises ValueError."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, list):
        raise ValueError("expected a JSON list")
    for item in data:
        for key, kind in keys.items():
            if not isinstance(item, dict) or not isinstance(item.get(key), kind):
                raise ValueError(f"every entry needs {key!r} ({kind.__name__}): {json.dumps(item)[:80]}")
        if not shape_ok(item):
            raise ValueError(f"labels need a 'name', comments a 'body' and 'author.login': {json.dumps(item)[:80]}")
    return data


def _issue_shape_ok(issue: dict) -> bool:
    labels_ok = all(isinstance(label, dict) and isinstance(label.get("name"), str) for label in issue["labels"])
    return labels_ok and all(
        isinstance(c, dict)
        and isinstance(c.get("body"), str)
        and isinstance(c.get("author"), dict)
        and isinstance(c["author"].get("login"), str)
        for c in issue["comments"]
    )


def _raw_issue_shape_ok(issue: dict) -> bool:
    return isinstance(issue["author"].get("login"), str) and _issue_shape_ok(issue)


ISSUE_KEYS = {"number": int, "body": str, "labels": list, "comments": list}
RAW_ISSUE_KEYS = {**ISSUE_KEYS, "author": dict}
PR_KEYS = {"number": int, "body": str, "state": str}
ROUTED_KEYS = {"number": int, "lane": str}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="consume.py")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("screen")
    t.add_argument("issues")
    t.add_argument("--owner", required=True, help="repo owner's login: always trusted")
    t.add_argument("--testers", default=TESTERS_PATH, help="file of testers' logins, one per line")
    q = sub.add_parser("queue")
    q.add_argument("issues")
    q.add_argument("prs")
    q.add_argument("--owner", required=True, help="repo owner's login: only their replies requeue an issue")
    b = sub.add_parser("batches")
    b.add_argument("routed")
    b.add_argument("--cap", type=int, default=MAX_PRS_PER_RUN)
    args = parser.parse_args(argv)

    current = ""
    try:
        if args.command == "screen":
            current = args.issues
            issues = _load(args.issues, RAW_ISSUE_KEYS, _raw_issue_shape_ok)
            current = args.testers
            safe, skipped = screen(issues, args.owner, load_testers(args.testers))
            print(json.dumps({"issues": safe, "skipped": skipped}, indent=2))
            return 0
        if args.command == "queue":
            current = args.issues
            issues = _load(args.issues, ISSUE_KEYS, _issue_shape_ok)
            current = args.prs
            prs = _load(args.prs, PR_KEYS)
            print(json.dumps([asdict(item) for item in queue(issues, prs, args.owner)], indent=2))
            return 0
        current = args.routed
        build, deferred = batches(_load(args.routed, ROUTED_KEYS), args.cap)
        print(json.dumps({"build": [asdict(batch) for batch in build], "deferred": deferred}, indent=2))
        return 0
    except (OSError, ValueError, KeyError) as error:  # json.JSONDecodeError is a ValueError
        print(f"consume.py: {current}: {error}".replace("\n", " "), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

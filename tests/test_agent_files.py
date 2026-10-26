"""The /consume skill, its agents and Cori's guide are prompt files; these tests keep them wired up."""

from pathlib import Path

import pytest

import consume

GUIDE = Path(".claude/cori/guide.md")
AGENTS = {
    "cori": "sonnet",
    "cori-reviewer": "sonnet",
    "frank": "sonnet",
    "frank-reviewer": "sonnet",
    "gate-runner": "haiku",
}


def frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """The `key: value` lines between the opening `---` lines, and the body after them."""
    _, head, body = path.read_text().split("---\n", 2)
    meta = dict(line.split(": ", 1) for line in head.splitlines() if ": " in line)
    return meta, body


def test_guide_has_a_place_for_lessons_from_review():
    assert "\n## Learned from reviews\n" in GUIDE.read_text()


@pytest.mark.parametrize(("name", "model"), AGENTS.items())
def test_agent_frontmatter(name, model):
    meta, _ = frontmatter(Path(f".claude/agents/{name}.md"))
    assert meta["name"] == name
    assert meta["description"]
    assert meta["model"] == model


@pytest.mark.parametrize("name", ["cori-reviewer", "frank-reviewer", "gate-runner"])
def test_reviewers_cannot_edit(name):
    tools = frontmatter(Path(f".claude/agents/{name}.md"))[0]["tools"]
    assert "Edit" not in tools
    assert "Write" not in tools


@pytest.mark.parametrize("name", ["cori", "frank"])
def test_builders_carry_the_guardrails(name):
    body = frontmatter(Path(f".claude/agents/{name}.md"))[1]
    rules = ("BROWSER=true", "HOME=$(mktemp -d)", "--offline", "UV_PROJECT_ENVIRONMENT", "RESULT: ", "SKIP #")
    assert [rule for rule in (*rules, "never comment on, label, or close") if rule not in body] == []


@pytest.mark.parametrize("name", ["cori", "cori-reviewer"])
def test_cori_and_its_reviewer_read_the_guide_and_rubric(name):
    body = Path(f".claude/agents/{name}.md").read_text()
    assert str(GUIDE) in body
    assert "data/checklists.toml" in body


def test_cori_records_what_it_learns_from_review():
    assert "Learned from reviews" in Path(".claude/agents/cori.md").read_text()


def test_consume_skill_wires_everything():
    meta, body = frontmatter(Path(".claude/skills/consume/SKILL.md"))
    assert meta["name"] == "consume"
    assert meta["description"]
    needed = ("consume.py queue", "consume.py batches", "--dry-run", consume.MARKER, "Closes #", "gh label create")
    assert [n for n in (*needed, *AGENTS, *consume.AGENT_LABELS) if n not in body] == []


def test_consume_never_tags_sean_or_merges():
    body = Path(".claude/skills/consume/SKILL.md").read_text()
    assert "@s3anstanz" not in body
    assert "Never merge" in body
    assert "auto-merge" in body  # to say never to enable it


def test_consume_skill_covers_the_review_findings():
    body = Path(".claude/skills/consume/SKILL.md").read_text()
    needed = (
        "`pending`",  # deferred and handed-off issues come back every run
        "--owner",  # only the owner's replies requeue
        "show origin/main:",  # judge "already fixed" against main, not a local checkout
        "pulls/<pr>/comments",  # inline review comments on a rejected PR
        "PR #<pr>",  # a handled rejection names the PR, so it isn't handled twice
        "ask for a change",  # a closing comment like "not needed" is not a redo
        "Never use `--no-verify`",
    )
    assert [n for n in needed if n not in body] == []


def test_consume_pushes_and_opens_prs_from_inside_the_build_worktree():
    # A session sitting in the shared checkout may not write git there; push and PR run from $WT.
    body = Path(".claude/skills/consume/SKILL.md").read_text()
    assert "EnterWorktree" in body
    assert "ExitWorktree" in body


def test_consume_labels_each_pr_with_the_agent_that_built_it():
    body = Path(".claude/skills/consume/SKILL.md").read_text()
    assert '--label "<lane>"' in body


def test_frank_reviewer_reruns_the_test_on_the_test_only_commit():
    body = Path(".claude/agents/frank-reviewer.md").read_text()
    assert 'worktree add --detach "$PREFIX" <test-commit>' in body
    assert 'worktree remove "$PREFIX"' in body

# Feedback agents: `/consume`, Cori and Frank — Design

Status: DRAFT 2026-10-16, from a brainstorm with Sean. Items marked
*(builder's call)* or *(Claude's call)* were not decided by Sean; everything
else was.

## 1. Why

Tester feedback arrives as GitHub issues labeled `feedback` (from the
tutorial's `f` command or the Feedback form). Today Sean reads each one, then
asks Claude to build a PR for it without first asking whether the issue is a
real bug, a point of confusion, a good idea, or noise. Every issue becomes a
PR, including ones that shouldn't.

Most feedback is about the lesson, not the code: "I didn't get this," "explain
more," "add an example." Of the six open issues on 2026-10-16 (#43–#48, all
Chapter 3), four are copy or curriculum, one may be a real bug (#47), and one
is a product decision (#48, bundle an open-weight model, which collides with
offline-first). PR #39's fixes for #34–#36 were mostly copy too.

So the system is three parts:

- **`/consume`**, the front door: reads every open feedback issue, decides
  what it is, closes the worthless ones, and routes the rest.
- **Cori**, the primary builder: fixes confusing text, missing explanations,
  missing examples, in Sean's voice, without losing the lesson's goal.
- **Frank**, the bug builder: fixes things that are actually broken in code.

Both builders run the same loop: research → validate → plan → build → test →
independent review → fix → PR. A PR opens only after that loop passes.

## 2. Goals, non-goals, anti-goals

**Goals**
- Every open `feedback` issue gets a decision and a written reason, without
  Sean reading it first.
- Copy fixes that read like Sean wrote them and keep the chapter pointed at
  its question.
- PRs that arrive already tested and reviewed, so Sean's review is reading the
  snapshot diff and merging.
- Runnable by hand now; runnable on a schedule later.
- Sean hears about a run once, not once per issue.

**Non-goals**
- Merging. Sean merges every PR.
- Codex review. Sean dropped it for this loop; nothing triggers `@codex review`.
- Non-`feedback` issues (e.g. #11, `freshness` issues). `/consume` ignores them.
- Large product decisions. They go to Sean (`needs-sean`), never built.

**Anti-goals** (failure even if it technically works)
- Copy that reads like AI slop.
- Copy that loses Sean's voice.
- A change that drifts from what the lesson is trying to teach.
- Notification spam: tagging Sean on every issue.
- Closing feedback that had value. Closing needs ≥95% confidence (§4.2).
- Burning usage: an unbounded fan-out of agents.

## 3. Parts and where they live *(Claude's call on names and paths)*

| Part | Path | What it is |
|---|---|---|
| `/consume` | `.claude/skills/consume/SKILL.md` | Front door and orchestrator. Runs in the main session. |
| Cori | `.claude/agents/cori.md` | Copy and curriculum builder subagent. |
| Cori's reviewer | `.claude/agents/cori-reviewer.md` | Read-only reviewer, adapted from Sean's general-purpose copy-reviewer agent. |
| Frank | `.claude/agents/frank.md` | Bug builder subagent. |
| Frank's reviewer | `.claude/agents/frank-reviewer.md` | Read-only code reviewer, fresh context. |
| Voice guide | `.claude/cori/voice-guide.md` | Sean's voice, drawn from his Learn screens. Not under `docs/`, which holds frozen records. |

Command name: `/consume` (Sean's suggestion). Not `/feedback`, which Claude
Code already uses. Not `/frank`, because Frank is now only the bug agent.

Subagents can't dispatch subagents, so `/consume` dispatches the builders
*and* their reviewers and runs the review loop. The builders don't run it.

Everything the agents need, including the guardrails in §7, lives in these
repo files. A scheduled cloud run has none of Sean's `~/.claude` memories,
hooks or agents.

## 4. `/consume`: the front door

### 4.1 Input
Open issues labeled `feedback` that aren't already handled. An issue counts as
handled when it carries `cori`, `frank`, `needs-sean` or `in-progress`, or has
an open PR that closes it. An issue comes back into the queue when Sean
comments on it after the last agent comment. (The exact mechanism is the
builder's call.)

### 4.2 Sorting
Each issue gets exactly one outcome:

| Outcome | When | Action |
|---|---|---|
| **Close** | ≥95% confident it has no value | Comment with the reason, add `wontfix` or `duplicate`, close. |
| **Cori** | Confusing text, missing explanation, example or step, wording | Label `cori`, comment why. |
| **Frank** | Something broken in code: wrong answer check, crash, layout breaking, wrong number | Label `frank`, comment why. |
| **Sean** | Product decision, conflicts with a spec rule, changes a chapter's question or rubric, or the front door isn't sure | Label `needs-sean`, comment with what it found and the decision needed. |

**What counts as ≥95%** *(Claude's call: a concrete stand-in for a
confidence number)*. Close only when one of these holds and the comment cites
the evidence:
- a duplicate of another issue (link it);
- already fixed on `main` (link the PR or commit and quote the current text);
- out of scope by a non-goal in the main spec (`docs/specs/2026-10-09-hands-on-ai-pm-design.md` §1, cite it), *and* there is nothing else in it to act on;
- empty or unintelligible, with nothing to act on.

Anything else isn't 95%, so it gets routed, not closed.

**Hand-offs between builders.** If Frank finds the code is fine and the issue
is really confusion, he hands it to Cori. If Cori finds the fix needs code, Cori
hands it to Frank. One hand-off per issue. A second one goes to `needs-sean`.

### 4.3 Comments and notifications
- Every routing or closing decision leaves a short comment on the issue.
  These comments **do not tag Sean**.
- **One run summary per run**, printed in the terminal at the end of the run
  (see §11.2; no GitHub issue). It lists:
  - closed issues, each with its reason;
  - routed to Cori, to Frank, and to Sean, each with a one-line reason;
  - PRs opened, with CI status;
  - anything that hit the round limit (§5.4) or failed;
  - the agent count and model mix the run used.
- Sean is never tagged directly. Everything, including `needs-sean`, is in
  the summary. Open issues labeled `needs-sean` are his standing to-do list.

### 4.4 Labels
New: `cori`, `frank`, `needs-sean`, `in-progress`. Existing: `wontfix`, `duplicate`. `/consume` creates missing
labels with `gh label create --force`, like `freshness.yml` does.

### 4.5 Dry run *(Claude's call)*
`/consume --dry-run` sorts and prints what it would do (outcome, reason, the
planned PR grouping) and changes nothing on GitHub or disk. The first runs
against #43–#48 use it.

### 4.6 Per-run cap
At most **3 builds per run** *(Claude's call)*. The rest stay labeled and
queued for the next run. Before building, `/consume` prints an estimate of
the agents it will dispatch.

## 5. The shared build loop (Cori and Frank)

### 5.1 Steps
1. **Research.** Read the issue, the screen or code at the "Where in the
   tutorial" location (chapter, step, seed), the chapter's question and rubric
   in `data/checklists.toml`, and the main spec section for that chapter.
   Cori may use the web to check facts, and cites sources in the PR. Any
   price goes in `pricing.py` only.
2. **Validate.** Cori names the rubric point the confusing screen serves and
   says what's actually unclear. Frank reproduces the bug with a failing test.
   If validation fails, the issue goes to a hand-off, `needs-sean`, or a close
   under §4.2's rules. It does not get built.
3. **Plan.** A short plan in the agent's working notes. It also goes in the PR
   description.
4. **Build** in its own worktree off `origin/main`.
5. **Test.** The repo's full gates, all green: `uv run pytest --cov` (≥95%),
   `uv run --python 3.11 pytest`, `uv run ruff check . && uv run ruff format --check .`,
   `uv run mypy`. Regenerate snapshots for any changed screen. Every new
   `**bold**` term needs a `data/glossary.toml` entry.
6. **Review.** `/consume` dispatches the lane's reviewer with fresh context:
   the diff, the issue, and (for Cori) the voice guide and rubric. The reviewer
   reports findings and never rewrites.
7. **Fix and re-review** until the reviewer reports nothing must-fix.
8. **PR.**

### 5.2 PR shape
- **Grouping** *(Claude's call)*: one PR per chapter per lane per run, closing
  every issue it fixes ("Closes #43, closes #44"). This follows PR #39's
  precedent and avoids five PRs fighting over the same lesson file and
  snapshots. A cross-chapter issue gets its own PR.
- The description quotes each issue, names the rubric point (Cori) or the
  failing test (Frank), shows before/after text for copy changes, lists web
  sources, and says what wasn't verified.
- `CHANGELOG.md` entry; snapshot diff included.
- Opened as a normal (non-draft) PR. `/consume` waits for CI. A red CI gets
  one fix attempt, and anything still red goes in the summary.
- Never merges, never enables auto-merge.

### 5.3 Models *(Claude's call, from Sean's usage preferences)*
- Sonnet: the sorting work, Cori, Frank and the reviewers.
- Haiku: running gates, regenerating and reading snapshots.
- Opus: only `/consume`'s own judgment calls (the main session).

### 5.4 Round limit
Two fix rounds after the first review (Sean's global rule: stop after two
failed corrections). After that the issue goes `needs-sean`. The worktree's
work stays on a pushed branch, linked in the summary.

## 6. Cori

- **Scope:** lesson content only. That means Learn screen data in
  `lessons/ch*_*.py` (`title`, `body`, `analogy`, `example`, `why_pm`), quick
  check text and explanations, recaps, "What this shows" captions, hints and
  sample answers in `data/checklists.toml`, and glossary entries. No engine
  or rendering code. A fix that needs code goes to Frank.
- **May add** a Learn screen or example within a chapter when it serves that
  chapter's existing rubric.
- **May not, without Sean** *(Claude's call)*: change a chapter's question,
  add or remove rubric checklist items, or add a step that pulls the chapter
  toward a different question (e.g. #45, "add a step on effort," is probably
  `needs-sean`). These go to `needs-sean`.
- **Lesson goal check:** before writing, Cori states the rubric point. After
  writing, Cori checks that the change makes that point clearer and doesn't
  wander.
- **Voice:** follows `.claude/cori/voice-guide.md`.
- **Spec's chapter shape still holds:** §5.1 Learn screen format, the ≥4 Learn
  screens per chapter, and a quick-check answer can't be given away by a Learn
  screen (see Chapter 7's departures for the precedent).

### 6.1 Voice guide (first task, before Cori touches any screen)
- Drawn from Sean's own Learn screens (the Chapter 1–5 screens, which weren't
  marked `[DRAFT … copy needs Sean's OK]` in the spec). It describes what he
  does: short declarative sentences, the "Think of it like" analogy, a
  concrete example, "Why a PM cares," plain words. Each rule is backed by
  quoted lines.
- Includes a "never" list: AI-slop patterns as they'd show up in this
  tutorial.
- Sean approves it once. Cori builds nothing until he does.

### 6.2 Cori's reviewer
Adapted from `copy-reviewer.md`: the voice-preservation prime directive,
detect-only, changed lines only, quote the defect. Retargeted at this repo's
lesson files. It checks three things, matching Sean's three winces:
1. Slop (patterns from the voice guide's "never" list).
2. Voice drift from the voice guide.
3. Lesson drift: does the change still serve the named rubric point?

It also checks factual accuracy against cited sources.

### 6.3 Repo rule change (ships with Cori)
`CLAUDE.md`'s "**Learn-screen copy is Sean's.** Change it only when he asks."
becomes, in substance: Learn-screen copy changes go through Cori, the voice
guide and Cori's reviewer, and Sean approves the PR. The glossary rule
stays.

## 7. Frank

- **Scope:** code bugs. That covers wrong answer checks, crashes, layout breaks
  at 40/80/120 columns, wrong computed numbers, and data-file parsing.
- **Validate = reproduce:** a failing test first, which the repo already
  requires. If he can't reproduce it, he hands off or routes to `needs-sean`.
- Follows every rule in the repo's `CLAUDE.md`.
- **Frank's reviewer:** a fresh read-only code reviewer that checks the diff
  against the issue, the failing test, and `CLAUDE.md`'s rules.

## 8. Guardrails every agent brief carries

- Own worktree off `origin/main`. Never edit, check out or commit in the
  primary checkout.
- Tutorial runs outside pytest: `BROWSER=true HOME=$(mktemp -d) … --offline`.
  Never type `f` in a scripted run.
- `UV_PROJECT_ENVIRONMENT=<worktree>/.venv` so the dev venv isn't rebuilt.
- Tests never call the API, never touch `~/.config/hands-on-ai-pm/`.
- No silenced errors, no `--no-verify`.
- Only `/consume` comments on, labels, or closes issues. The builders and
  reviewers never touch GitHub issues.
- **Permission:** invoking `/consume` (or its schedule) is Sean's standing
  permission for these agents to create branches, commit, push, open PRs, and
  comment on, label and close `feedback` issues. It isn't permission to merge,
  to touch `main`, or to act on non-`feedback` issues.

## 9. Order of work

1. **Voice guide.** Sean approves it.
2. **`/consume` + Cori + Cori's reviewer**, labels, and
   the `CLAUDE.md` rule change. Dry run on #43–#48, then a real run.
3. **Frank + Frank's reviewer.** #47 is the first real test.
4. **Schedule** via Claude Code's `/schedule` (cloud), only after a few
   manual runs look right. The cadence gets decided then.

## 10. Left to the builder
- How "handled" and "re-queued" are detected (§4.1).
- The exact prompt wording of each agent and reviewer.
- Whether builds within a run go in parallel (separate worktrees) or one at a
  time.

## 11. Settled after the builder check *(Claude's calls, 2026-10-16)*

1. **Local first.** Steps 1–3 of §9 target Sean's machine only. `.claude/` is
   committed to the repo (it isn't gitignored, and the repo is private), so a
   later cloud run can use it. The cloud's needs (`gh` auth, `uv sync` per
   worktree, permissions) are part of step 4, not earlier. `/consume` itself
   only reads the repo and talks to GitHub, so it doesn't need a worktree.
   Every builder does.
2. **No run summary issue** *(Sean, 2026-10-16)*. `/consume` posts as Sean's
   own GitHub account, and GitHub doesn't notify people about their own
   activity, so a summary comment would never reach him. The summary prints in
   the terminal instead. A scheduled run needs a delivery that actually
   reaches Sean (e.g. an email to himself); that's chosen and tested in the
   schedule plan (§9 step 4).
3. **Dry-run acceptance for #43–#48.** Expected routing: #43, #44, #46 → Cori.
   #45 → `needs-sean` (it adds a topic to the chapter). #47 → Frank. #48 →
   `needs-sean`. Nothing closes. Sean reads the dry-run output and can
   overrule any of these.
4. **Cori's reviewer** borrows the *structure* of `copy-reviewer.md`: the
   voice-preservation prime directive, the precedence list, detect-only,
   changed lines only, quote the defect. It copies nothing specific to the original's project.
5. **Voice guide approval** is a first line `approved: YYYY-MM-DD` that Sean
   adds himself. `/consume` refuses to dispatch Cori, including on a
   schedule, when that line is missing, and says so in the summary.
6. **`CLAUDE.md` rule change** ships in the same PR as Cori (§9 step 2), with
   wording drafted in that PR for Sean to approve. Sean asked for this change
   himself in the brainstorm.
7. **No usable location** ("Where in the tutorial" missing or free text) →
   the issue gets its own PR, the same as a cross-chapter issue.
8. **The per-run cap counts PRs**, not issues: at most 3 PRs per run.
9. **Stale state.** At the end of a run `/consume` removes `in-progress` from
   anything it didn't finish. At the start of a run, an `in-progress` issue
   with no open PR is treated as unhandled. An issue whose PR Sean closed
   unmerged goes to `needs-sean` once, and isn't rebuilt.
10. **Red CI** → `/consume` dispatches a fresh builder of the same lane with
    the CI log. That counts as one of the two fix rounds in §5.4.

## 12. No voice guide *(Sean, 2026-10-16, during the build)*

Every Chapter 1–5 lesson commit is co-authored by Claude, and so is the
handoff those chapters came from. A guide that quotes them as "Sean's voice"
would teach Claude's voice. Sean: lessons have right and wrong answers; don't
spend time shaping a voice; let Cori learn through changes, feedback and
research. So:

- `.claude/cori/guide.md` replaces the voice guide. It's a plain writing
  guide: the lesson-goal check, facts, screen shape, plain sentences, and the
  no-slop list. It makes no claims about anyone's voice.
- **No approval gate.** §6.1's "Sean approves it once" and §11.5 are dropped.
  `consume.py` has no `voice` command, and Cori runs from day one.
- **Cori learns from review.** When Sean replies on an issue (a `requeued`
  item) or closes a Cori PR unmerged (a `rejected` item), `/consume` hands
  Cori his comments. Cori does what he asked and adds one line under the
  guide's "Learned from reviews" in that same PR. Cori's reviewer treats those
  lines as rules.
- This supersedes the voice parts of §2 (anti-goals), §6, §6.2, §6.3 and §9
  step 1. The `CLAUDE.md` rule becomes: Learn-screen copy changes go through
  Cori, the guide and Cori's reviewer; Sean approves the PR.
- **A PR closed unmerged** (a `rejected` item, §11.9) goes back to the same
  lane with Sean's PR comments when he left any. With none, it goes to
  `needs-sean` as §11.9 says.
- **A batch with mixed outcomes.** A builder builds what it can and reports
  each issue it skipped on a `SKIP #<n> …` line. `/consume` acts on each one.

## 13. Fixes from the final review *(2026-10-16)*

- **`pending`.** An issue with a lane label and no PR yet (deferred past the
  cap, or handed off) comes back every run and goes straight to a build,
  without being sorted again. Before this fix, "labeled = handled" dropped
  these issues for good.
- **Only the repo owner's replies requeue an issue**, and only those replies
  reach Cori (and so the "Learned from reviews" lines).
- **A rejected PR is redone only when Sean's comments on it ask for a change.**
  "Not needed" or no comment → `needs-sean`. To stop for good, close the
  issue. A handled rejection names the PR ("PR #61") so it isn't handled
  twice.
- **Hand-off limit** is enforced at build time too. A PR's `Closes` lines name
  built issues only. Branch names carry issue numbers and a timestamp. A
  refused push is never bypassed. The sorter reads `origin/main`, not a
  local checkout. Every close is checked against its evidence, including
  closes a builder proposes.

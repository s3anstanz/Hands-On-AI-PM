---
name: consume
description: Work through open tester-feedback issues in hands-on-ai-pm. Sorts each one (close, Cori for copy, Frank for code bugs, or Sean), then builds, tests and reviews fixes and opens PRs. Use when Sean runs /consume; pass --dry-run to only show what it would do.
argument-hint: "[--dry-run]"
disable-model-invocation: true
---

# /consume

You are the front door for tester feedback: GitHub issues labeled `feedback`. You sort every open one, close the worthless ones, route the rest, and run the build loop for Cori (copy) and Frank (code bugs). A PR opens only after a fix passes the gates and a fresh reviewer.

Design: `docs/specs/2026-10-16-feedback-agents-design.md` (§11 and §12 override earlier sections).

**Permission.** Sean running `/consume` is his standing permission to:
- create branches, commit, push, and open PRs;
- comment on, label and close `feedback` issues.

It is **not** permission to:
- merge, enable auto-merge, or touch `main`;
- act on issues without the `feedback` label;
- @-mention anyone.

Never merge. Never enable auto-merge.

**With `--dry-run`:** do steps 1–3, print the plan (step 3's table, the batches, the agent estimate), and stop. Write nothing: no labels, comments, branches or worktrees.

## 1. Set up

```bash
REPO=$(git rev-parse --show-toplevel)
RUN=$(mktemp -d)                 # this run's scratch files
git -C "$REPO" fetch -q origin
```

Unless this is a dry run, make sure the labels exist:

```bash
gh label create cori        --color 1D76DB --description "Feedback for Cori: lesson copy" --force
gh label create frank       --color B60205 --description "Feedback for Frank: code bug" --force
gh label create needs-sean  --color FBCA04 --description "Waiting on Sean's decision" --force
gh label create in-progress --color 5319E7 --description "/consume is building a fix" --force
```

## 2. Queue

```bash
OWNER=$(gh repo view --json owner -q .owner.login)
gh issue list --label feedback --state open --limit 200 --json number,title,body,labels,comments > "$RUN/issues.json"
gh pr list --state all --limit 200 --json number,body,state > "$RUN/prs.json"
cd "$REPO" && uv run python consume.py queue "$RUN/issues.json" "$RUN/prs.json" --owner "$OWNER" > "$RUN/queue.json"
```

`consume.py queue` returns the issues that need something this run. Each has `chapter`, `why`, `lane` (its `cori`/`frank` label, if any), `pr` and `notes`. The `why` is one of:

- `new`: never handled.
- `pending`: already has a lane but no PR yet (deferred past the cap, or handed off). **Don't sort it again.** It goes straight to `routed.json` in its `lane`.
- `requeued`: Sean (`$OWNER`) replied after /consume's last comment. His replies are in `notes`. Other people's comments never requeue an issue.
- `stale`: `in-progress` with no open PR.
- `rejected`: PR `pr` was closed without merging.

If it exits 2, print its one-line error and stop. If the queue is empty, print "Nothing to do" and stop.

## 3. Sort

For each `rejected` item, collect Sean's comments on PR `pr`:
- the conversation: `gh pr view <pr> --json comments,reviews`;
- inline comments on the diff: `gh api repos/{owner}/{repo}/pulls/<pr>/comments`.

Keep only comments by `$OWNER`.

Dispatch **one** `general-purpose` agent with `model: "sonnet"` for every item that isn't `pending`. Give it:
- each issue's full text and comments;
- its `why`, `lane` and `notes`;
- for `rejected` items, Sean's PR comments;
- the rules below.

It returns JSON, one object per issue: `{"number", "outcome", "reason", "evidence"}`. `outcome` is one of `close-wontfix`, `close-duplicate`, `cori`, `frank` or `needs-sean`.

The sorter reads the tutorial **as it is on `main`**, never from a local checkout, because another session may have a different branch checked out:
- `git -C "$REPO" show origin/main:<path>` to read a file;
- `git -C "$REPO" grep <pattern> origin/main` to search.

It changes nothing.

**Rules for the sorter:**
- **Close** only at ≥95% confidence, and only when one of these holds. Cite the evidence.
  - a **duplicate** of another issue (link it);
  - **already fixed** on `main` (link the PR or commit and quote the current text);
  - **out of scope** by a non-goal in `docs/specs/2026-10-09-hands-on-ai-pm-design.md` §1 (cite it), and nothing else in the issue is actionable;
  - **empty** or unintelligible, with nothing to act on.

  Anything else isn't 95%: route it.
- **cori:** confusing text, a missing explanation, a missing example, or wording.
- **frank:** something broken in code. Examples: a wrong answer check, a crash, a layout break, a wrong computed number, a data file that won't parse.
- **needs-sean:**
  - a product decision;
  - a conflict with a spec rule (e.g. offline-first);
  - a change to a chapter's question or rubric, or a new topic;
  - the sorter isn't sure.
- **requeued:** Sean's `notes` outrank everything else on the issue.
- **rejected:** a redo happens only when Sean's PR comments **ask for a change** ("use the sky example," "shorter"). In that case, route the issue to its `lane` again, and the builder gets his comments. Anything else is `needs-sean`: comments that reject the idea ("not needed"), or no comments at all. To stop work for good, Sean closes the issue itself.
- **Hand-offs:** if an earlier /consume comment on the issue says "Handed off to", the issue already bounced between lanes once, so a second bounce is `needs-sean`.

Then write `$RUN/routed.json` (`[{"number", "lane", "chapter"}]`). It holds every `pending` item in its `lane`, plus the `cori` and `frank` outcomes, taking `chapter` from the queue. Run:

```bash
cd "$REPO" && uv run python consume.py batches "$RUN/routed.json" > "$RUN/batches.json"
```

It groups issues into PRs (one per lane and chapter; an issue with no chapter goes alone). It builds at most 3 PRs this run and defers the rest. Deferred issues keep their lane label and come back as `pending` next run.

**Agent estimate.** Print this before building: 1 sorter, plus 3 agents per batch (builder, gate-runner, reviewer), plus up to 3 more per fix round (at most 2 rounds per batch).

On a dry run, print a table (issue, outcome or `pending`, reason), the batches, the deferred issues, and the estimate. Stop.

## 4. Act on the sort

Every comment you post starts with `<!-- consume -->` on its own line. Comments are short, give the reason, and mention no one. A comment about a `rejected` item names the PR as `PR #<pr>`. That's how the next run knows the rejection was handled.

- **Close.** First check the evidence yourself: open the link. This applies to every close, whether the sorter or a builder proposed it. If the evidence doesn't hold up, route the issue instead. Then:
  1. `gh issue comment <n> --body-file …` with the reason and evidence link.
  2. `gh issue edit <n> --add-label wontfix` (or `duplicate`).
  3. `gh issue close <n>`.
- **Route:**
  1. A comment saying where it went and why.
  2. `gh issue edit <n> --add-label <cori|frank|needs-sean>`.
  3. Remove every other label in `cori`, `frank`, `needs-sean`, `in-progress`. An issue carries exactly one of them.

`pending` items need no comment; they already have their lane.

## 5. Build each batch

For each batch in `build`, in order:

1. Run `gh issue edit <n> --add-label in-progress` for each issue in the batch.
2. Create the worktree. The branch name carries the issue numbers and the time, so it can't collide with an earlier run:
   ```bash
   BRANCH=consume/<lane>-<issue numbers joined by ->-$(date +%Y%m%d-%H%M)
   WT="$RUN/$BRANCH"
   git -C "$REPO" worktree add -q -b "$BRANCH" "$WT" origin/main
   UV_PROJECT_ENVIRONMENT="$WT/.venv" uv sync --all-extras -q --project "$WT"
   ```
3. **Builder.** Dispatch the `cori` or `frank` agent with:
   - `$WT`;
   - each issue's full text and comments;
   - Sean's comments (`notes`, or his PR comments for a reworked rejection).

   Read the lines at the end of its reply:
   - `SKIP #<n> <handoff cori|handoff frank|needs-sean|close …> <reason>`: that issue wasn't built.
     - **Hand-off:** if an earlier /consume comment on the issue already says "Handed off to", route it to `needs-sean` instead. Otherwise comment "Handed off to <lane>: <reason>" and swap the lane label (step 4's label rule). It comes back as `pending` in the other lane next run.
     - Otherwise act as in step 4.
   - `RESULT: built <sha>`: continue to the gates. The batch's **built issues** are its issues minus the skipped ones. Only those go to the reviewer and into the PR.
   - Any other `RESULT:` applies to every issue in the batch. Act on it as in step 4 (hand-offs as above), remove `in-progress`, remove the worktree, and move to the next batch.
4. **Gates.** Dispatch `gate-runner` with `$WT`. It returns `GATES: pass` or `GATES: fail`.
5. **Review.** On a pass, dispatch the lane's reviewer (`cori-reviewer` or `frank-reviewer`) with `$WT`, the built issues, and the builder's report. It returns `VERDICT: clean` or `VERDICT: must-fix`.
6. **Fix rounds.** On `GATES: fail` or `VERDICT: must-fix`, dispatch the builder again with `$WT`, the built issues' full text, and that output. Then repeat steps 4–5. You get at most **2 fix rounds**. If it's still failing after that:
   - Push the branch so Sean can see it, from inside the worktree (see step 7): `git push -u origin "$BRANCH"`.
   - The repo's pre-push hook runs the tests, so it may refuse the push. Never use `--no-verify` or bypass a hook. If the push is refused, keep the worktree, don't remove it in step 8, and give its path instead of a branch link.
   - Comment on each issue with the branch link (or "kept locally") and what's still failing.
   - Route it to `needs-sean` (step 4's label rule).
   - Move to the next batch.
7. **PR.** When gates pass and review is clean:
   - **Push and open the PR from inside `$WT`**, never from Sean's checkout. Sean's machine blocks git writes from a session sitting in the shared checkout. Switch in with `EnterWorktree` (`path: $WT`), and run each command on its own, in plain form (no `git -C`, no chained commands). Leave with `ExitWorktree` (`action: "keep"`) before step 8.
   - `git push -u origin "$BRANCH"`. If the hook refuses it, treat it as a gate failure and go back to step 6.
   - `gh pr create --head "$BRANCH" --base main --label "<lane>" --title "<Chapter N: what changed>" --body-file "$RUN/<branch>-pr.md"`. The `cori` or `frank` label says which agent built it. The body has:
     - a `Closes #<n>` line for each **built** issue only, never a skipped one;
     - each built issue's feedback, quoted;
     - the rubric item (Cori) or the failing test (Frank);
     - before/after text (Cori);
     - sources;
     - "What I did not verify";
     - last line: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
   - Never draft, never merge, never enable auto-merge.
   - Run `gh pr checks <pr> --watch`. If it reports no checks yet, wait a minute and retry.
   - If CI is red, dispatch the builder once with the built issues and `gh run view <run-id> --log-failed` output. This counts as a fix round. If none are left, list the PR as red in the summary. Then gates, push, and re-check. If it's still red, list it in the summary.
   - Remove `in-progress` from the built issues. The open PR now marks them handled.
8. Back in the main checkout, remove the worktree: `git -C "$REPO" worktree remove "$WT"`. The branch lives on origin.

## 6. Summary

Print this in the terminal. Don't post it to GitHub: comments come from Sean's own account, and GitHub doesn't notify him about those.

```
/consume: <date>
Closed:        #n reason (evidence link)
To Cori:       #n reason
To Frank:      #n reason
Needs Sean:    #n reason
PRs:           #pr (closes #n, #n): CI green|red
Round limit:   #n branch link: what's failing
Deferred:      #n (next run)
Agents:        <count> (sonnet <n>, haiku <n>)
Waiting on Sean: https://github.com/s3anstanz/Hands-On-AI-PM/issues?q=is:open+label:needs-sean
```

Omit empty lines. Before printing, remove `in-progress` from anything this run didn't finish.

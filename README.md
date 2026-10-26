# Hands-On AI PM

A tutorial you run in your terminal that teaches product managers how large
language models (LLMs) work and what they cost, so you make better calls when
you build with them.

It's hands-on, not a reading list: you watch a model build a sentence one token
at a time, guess what it will do before it does it, answer a real product
question in your own words, and grade yourself against a checklist.

Works **fully offline with no API key**. Nothing is sent anywhere unless you
turn on the optional live mode.

## The goal

Each chapter is built around one question a PM building with AI should be
able to answer, such as *"Explain how an LLM generates text."* You've finished a chapter when you can answer its
question **out loud, in your own words, with a number and a recommendation**.
Reading a model answer and nodding along doesn't count.

## Status

The curriculum is complete: **all eight chapters and the cheat sheet** are
built. Each chapter was tried before the next was written.

| # | Chapter | Question you'll answer | Status |
|---|---|---|---|
| 1 | How an LLM generates text | "Explain how an LLM generates text." | **Ready** (~10 min) |
| 2 | Tokens | "What's a token and why does it matter?" | **Ready** (~8 min) |
| 3 | Temperature | "What does temperature do? When would you set it to 0?" | **Ready** (~10 min) |
| 4 | Hallucinations | "Define hallucination. Users say it's confident but wrong. Fix it." | **Ready** (~8 min) |
| 5 | Small vs. large models | "Small vs. large models: how do you choose?" | **Ready** (~9 min) |
| 6 | Cost at scale | "How do costs change as you scale?" | **Ready** (~10 min) |
| 7 | Context windows | "What's a context window? Paste everything in or fetch what's relevant?" | **Ready** (~8 min) |
| 8 | Design an AI feature | "Design an AI feature for X." | **Ready** (~9 min) |
| C | Cheat sheet + glossary | — | **Ready** (~3 min) |

The full course takes about 75 minutes (the times above add up to 72 for the
chapters plus 3 for the cheat sheet). Each chapter stands alone, so you can do
one per sitting.

## What to expect in a chapter

Every chapter follows the same loop: **teach first, then apply**. You never hit
an exercise that uses an idea you haven't been taught yet.

1. **Question.** The question you'll answer at the end.
2. **Learn.** A few short click-through screens, one idea each, using the real
   terms (token, inference, parameters...). Each screen ends with "Why a PM
   cares".
3. **Recap.** The chapter in a few points on one screen. They're also what a
   strong answer to the chapter's question covers.
4. **Quick check.** One or two ungraded multiple-choice questions. Get one wrong
   and it offers to reopen the screen that covers it.
5. **Hands-on.** Predict what will happen, then run it and compare. In
   Chapter 1 you watch a sentence get built token by token and predict the
   model's top pick twice.
6. **Answer.** Say your answer out loud, then type it. Stuck? Type `h` for a
   hint.
7. **Grade.** With your answer on screen, mark yourself against a checklist of
   what a strong answer covers. Your score is saved and shown on the start
   menu. Then you see a strong sample answer, and say yours out loud once more.
8. **Follow-up.** A harder twist ("But ChatGPT told me about
   yesterday's news. How?"), then what a strong reply mentions.

Chapter 8 is a design exercise. It has no Quick check; the hands-on step is
designing a feature for a random scenario and seeing its cost, speed and risk;
then three reviewer follow-ups instead of one.

A few things worth knowing:

- **Runs vary.** Each run is randomized from a seed (in Chapter 1, which
  example sentence you get, the order of the answer options, and which
  follow-up question you're asked). The seed is
  shown on every screen; `--seed N` replays that exact run. Picking the same
  chapter again in one session gets a fresh seed, so a retry isn't a replay.
- **Probability tables are illustrative.** Claude's API doesn't expose real
  next-token probabilities, so the tables are hand-written and labeled as such
  on screen. The math applied to them is the same math real models use.
- **Prices are real.** They come from the providers' official pricing pages,
  all kept in one file (`pricing.py`), with a "prices checked" date on screen.

## Getting started

You need **Python 3.11 or newer** (check with `python3 --version`) and a normal
terminal (macOS Terminal or iTerm work well). On a Mac, `git` and `make` both
come with Apple's Command Line Tools; if `git` works, so does `make`.

One-time setup:

```bash
git clone https://github.com/s3anstanz/Hands-On-AI-PM.git
cd Hands-On-AI-PM
make setup
```

`make setup` creates a private Python environment in `.venv` and installs the
tutorial's libraries there. The requirements files pin exact, hash-checked
versions (generated from `uv.lock`), so you get the same versions the tests
run against. If you use [uv](https://docs.astral.sh/uv/), `uv sync` does the
same in one step and `uv run python tutorial.py` starts the tutorial.

Then start the tutorial:

```bash
make course
```

Pick `1` from the menu and press **Enter** to move through the screens. Pick
`C` for the cheat sheet. Next time, `cd Hands-On-AI-PM` and run `make course` again.

### On Windows

Windows has no `make`, so use these PowerShell commands instead. Windows is
new and has only had a first tester run, so please report anything that looks
wrong (see [Giving feedback](#giving-feedback)). Use
[Windows Terminal](https://aka.ms/terminal) rather than the old `cmd.exe`
window. You need [Python 3.11 or newer](https://www.python.org/downloads/)
(tick "Add python.exe to PATH" in the installer) and
[git](https://git-scm.com/download/win).

One-time setup:

```powershell
git clone https://github.com/s3anstanz/Hands-On-AI-PM.git
cd Hands-On-AI-PM
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

If `python` isn't found, try `py -m venv .venv`. Then start the tutorial:

```powershell
.venv\Scripts\python tutorial.py
```

Wherever this README says `make course ARGS="--lesson 1"`, run
`.venv\Scripts\python tutorial.py --lesson 1`. With
[uv](https://docs.astral.sh/uv/), `uv sync` and `uv run python tutorial.py`
work the same as on a Mac. Backspace and the arrow keys won't work across a
long answer that wraps onto a second line, because Windows has no `readline`;
typing and Enter work as normal.

### Controls

- **Enter**: next screen
- **b** then Enter: back (you'll see the same numbers as before)
- **q** then Enter: back to the menu (or quit, from the menu or in `--learn`
  mode)
- **f** then Enter: send feedback (see [Giving feedback](#giving-feedback))
- **Ctrl-C**: quit at any time. Scores are saved each time you finish grading a
  chapter.

`b`, `q` and `f` also work where the tutorial asks for a number or says "Enter for
the next token".

### Options

Options go in `ARGS`:

```bash
make course                              # start menu
make course ARGS="--lesson 1"            # jump straight to a chapter
make course ARGS="--lesson cheat"        # the cheat sheet and glossary
make course ARGS="--learn 1"             # refresher: Learn, Recap and Quick check only; nothing saved
make course ARGS="--learn all"           # every chapter's refresher, back to back
make course ARGS="--seed 48213"          # replay an exact run
make course ARGS="--offline"             # never call the API, even if a key is set
make course ARGS="--reset-progress"      # delete saved scores (asks first)
```

`--learn` is meant as a quick refresher.

## Giving feedback

Testing this? Type **f** (or `/feedback`) and Enter at any prompt, including
the start menu. You'll be asked what you'd change, what kind of feedback it is
(bug, confusing, idea, liked it), and for a short title (press Enter to use the
first line of your note), then shown exactly what will be sent.
Your browser then opens a GitHub issue that's already filled in. Check it and
click **Submit new issue**. Nothing is sent until you do. The tutorial also asks once at
the end of each chapter.

Along with your note, the issue says where you were (chapter, step, seed) and
your setup (commit, Python version, OS, terminal width, offline or live). Your
chapter answers are never included. If you're offline or the browser doesn't
open, the note is saved and you're offered it again next time you start. You
can also open an issue directly on GitHub with the **Feedback** form.

## Live mode (optional): Claude grades your answers

Everything works without this. Live mode connects the tutorial to your own
Claude account so Claude can grade your answers too.

**What you need:** a [Claude Console](https://platform.claude.com/) account
with API credits. That's Anthropic's pay-as-you-go API account, and it's
separate from a Claude.ai subscription: **a Claude Free, Pro or Max plan can't
be used here**, because Anthropic doesn't let other apps use Claude.ai logins.
Any Console account works; there's no plan tier to pick.

First, install the live-mode library:

```bash
.venv/bin/pip install -r requirements-live.txt
```

Then connect your Console account in one of two ways.

**Option A: sign in, no key to copy.** Install Anthropic's `ant` command-line
tool (this uses [Homebrew](https://brew.sh/); [other ways to install](https://platform.claude.com/docs/en/cli-sdks-libraries/cli/quickstart))
and log in once. A browser window opens so you can sign in to the Claude
Console and pick a workspace.

```bash
brew install anthropics/tap/ant
ant auth login
make course
```

The login is saved, so next time `make course` is all you need.

**Option B: an API key.** Create a key at
[platform.claude.com/settings/keys](https://platform.claude.com/settings/keys), then:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
make course
```

`export` lasts only for that terminal window. If an API key is set, it's used
instead of an `ant` login. (`ANTHROPIC_AUTH_TOKEN` also works, for a bearer
token from a gateway.)

The menu then shows `Live mode: ON`. In Chapter 1, live mode adds one thing:
after you self-grade, it asks whether Claude should grade your answer too
(about a cent per answer; the estimate is shown with the question). It always
asks before spending, and the footer shows what you've spent this session. If
the call fails (no network, bad key), you get a one-line reason and your
self-score still counts.

Chapter 2 also shows the official Claude token count for its cost comparison.
Counting tokens is free, so it doesn't ask first. Chapter 3 adds a real
temperature run: 20 short requests on an older Claude model, after asking.

To confirm live mode works with your key, run `.venv/bin/python live_check.py`. It
checks every model live mode uses with a free token count (a retired model
fails here), then asks before making one real grading call.

## Where things live

| What | Where |
|---|---|
| Your scores | `~/.config/hands-on-ai-pm/progress.json` (outside the repo, never committed) |
| Unsent feedback notes | `~/.config/hands-on-ai-pm/feedback/` (removed once you say they went through) |
| Every price | `pricing.py` |
| Probability tables | `data/prompts.toml` |
| Hallucination examples (Chapter 4) | `data/hallucination.toml` |
| Product scenarios (Chapters 6-8) | `data/scenarios.toml` |
| Grading checklists and follow-ups | `data/checklists.toml` |
| Glossary (also the cheat sheet's last pages) | `data/glossary.toml` |
| Chapter content | `lessons/` |
| Design spec | `docs/specs/` |

The data files are meant to be edited by hand. To add your own prompt, copy a
`[[prompt]]` block in `data/prompts.toml`, or a `[[case]]` block in
`data/hallucination.toml`. If you break a file, the tutorial names the file
and the entry instead of crashing.

## Project layout

```
Makefile        make setup, make course
tutorial.py     command line and start menu
engine.py       runs a chapter: steps, Enter/b/q navigation, grading
lessons/        chapter content and the cheat sheet
ui.py           bar charts, panels, footer
sampling.py     probabilities, temperature, top-k / top-p
tokens.py       token counting (tokenizer bundled in data/tiktoken/, works offline)
costs.py        cost math: per request, per month, caching, batch
pricing.py      every price and model id
data.py         loads and checks the data/*.toml files
progress.py     saves and loads your scores
live.py         optional Claude calls
feedback.py     f (feedback): prefilled GitHub issues, unsent notes
tests/          pytest suite
freshness.py    flags stale prices and upcoming model/price dates
live_check.py   end-to-end live-mode check with your own key
scripts/        maintenance scripts (requirements sync, git hooks)
.github/        CI workflows, Dependabot config, feedback issue form
```

## Development

Setup, with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras          # app + live mode + dev tools, from uv.lock
uv run pre-commit install     # local guardrails (below)
```

Checks (CI runs the same ones):

```bash
uv run pytest                 # tests; add --cov for coverage (must stay at or above 95%)
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

The tests never call the real API and never touch your saved scores.

How changes land:

- Work on a branch and open a PR. CI must be green before merging (squash).
- `main` is protected on GitHub: it only changes through a PR whose CI checks
  pass, with no force pushes, and this applies to admins too. The branch
  doesn't have to be up to date with `main`; CI runs again on `main` after
  every merge. The local hooks add a second layer: commits and pushes to `main`
  are refused, every commit is scanned for secrets (gitleaks), and every push
  runs the tests.
- After changing dependencies (including on a Dependabot PR), run
  `scripts/sync-requirements.sh` and commit the result.

Keeping it current: prices and model ids change. A monthly workflow runs
`python freshness.py` and opens a GitHub issue when prices are more than 60
days old, or when a date in `pricing.WATCH_DATES` (a model retirement, a
scheduled price change) is near or has passed. Run it locally any time.

`CLAUDE.md` has the project rules for coding agents, and `CHANGELOG.md`
records releases.

## License

All rights reserved. See `LICENSE`.

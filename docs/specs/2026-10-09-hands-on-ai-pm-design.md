# Hands-On AI PM: Design Spec

**Date:** 2026-10-09
**Owner:** Sean Schireson
**Status:** Approved by Sean 2026-10-09
**Source:** Approved design in `llm-tutorial-handoff.md` (2026-10-09). The decisions in that handoff are final. This spec turns them into something buildable; it does not reopen them. Items marked **[APPROVED 2026-10-09]** are details the handoff left open, which Sean approved during spec review.

---

## 1. Goal

A Python tutorial that runs in a normal terminal and teaches product managers how LLMs work and what they cost, so they make better calls when they build with them. The test of success is that **after finishing a chapter, a learner can answer its question out loud, in their own words, with a number and a recommendation.** Reading a one-line answer and nodding along does not count.

### Success criteria
1. `python tutorial.py` runs end to end **with no network and no API key**.
2. All 8 chapters plus the cheat sheet can be completed in **60–75 minutes** in total (raised from 45–60 on 2026-10-09 to make room for teaching first). Each chapter stands alone, so it can be done over several sittings.
3. **Teach first, then apply.** Each chapter teaches its concepts in click-through Learn screens *before* any hands-on step. Then the user predicts, experiments, answers in writing, grades, and handles a follow-up (§5). Nobody should hit an experiment they weren't prepared for.
4. Two runs with different seeds show different numbers. The same `--seed` reproduces a run exactly.
5. Every price comes from one file and shows a "last checked" date on screen.
6. With an API key, optional extras turn on: official Claude token counts, the live temperature run, and Claude grading answers. Without a key, those steps show a short "needs a key" note and are skipped. Nothing breaks.

### Non-goals (from handoff §3.8)
- How training works in depth, fine-tuning, embeddings internals, image tokens.
- **Evals.** Chapter 8 ends with an evals teaser only.
- Real model probabilities. Claude's API doesn't return them (§10.2), so the probability tables are illustrative and say so on screen.

---

## 2. Setup and launch

| Item | Value |
|---|---|
| Folder / repo | `~/hands-on-ai-pm`, its own git repo. Private GitHub repo `s3anstanz/hands-on-ai-pm`, created only with Sean's explicit go-ahead |
| Python | **3.11+** [APPROVED 2026-10-09] (the handoff said 3.10+; see §12) |
| Required deps | `rich`, `tiktoken` |
| Optional deps | `anthropic` (live mode only; imported lazily) |
| Dev deps | `pytest` |
| Install | `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (`requirements-live.txt` adds `anthropic`) |
| Launch | `python tutorial.py` |

### CLI flags
| Flag | Effect |
|---|---|
| *(none)* | Opens the start menu with a fresh random seed |
| `--lesson N` | Jumps straight to chapter N (1–8) or `--lesson cheat` |
| `--learn N` | Learn-only refresher: Chapter N's Learn, Recap and Quick check, with no grading and no progress saved. `--learn all` runs every chapter's (§5.2) |
| `--seed N` | Replays an exact run. The seed is always shown in the header so it can be reused |
| `--offline` | Forces offline mode even when a key is present (useful for testing and for keeping spending at zero) |
| `--reset-progress` | Clears saved scores (asks to confirm first) |

### Controls
- **Enter** = next step, **b** + Enter = back, **q** + Enter = quit to the menu (from the menu, quit the program). **[APPROVED 2026-10-09]** Line-based `input()` rather than single-keypress capture: it's simpler, testable, and works in every terminal. The cost is that `b` and `q` need Enter.
- **Ctrl-C** at any point saves progress and exits cleanly. No traceback.
- **f** + Enter (or `/feedback`) = send feedback, from any prompt that takes `b`/`q` and from the start menu (§14).
- A footer on every screen shows: `Ch 3 · Step 4/11 · seed 48213 · [Enter] next  [b] back  [q] menu  [f] feedback`.

---

## 3. Start menu

```
 HANDS-ON AI PM                                   seed 48213 · prices checked 2026-10-09
 ───────────────────────────────────────────────────────────────────────────────────────
  1  How an LLM generates text          ~10 min  last: 4/5
  2  Tokens and why they matter          ~8 min  last: 5/6
  3  Temperature and sampling           ~10 min  last: 3/6   ← weakest
  4  Hallucinations                      ~8 min  not started
  5  Small vs. large models              ~9 min  not started
  6  Cost at scale                      ~10 min  not started
  7  Context windows                     ~8 min  not started
  8  Design an AI feature                ~9 min  not started
  C  Cheat sheet + glossary              ~3 min
 ───────────────────────────────────────────────────────────────────────────────────────
  Live mode: OFF (no API key found). Everything works offline.  ·  Pick 1–8, C, or q
```

- [BUILT 2026-10-14, plan 2d; needs Sean's OK] Built as shown, with the prompt "Pick a chapter (1, …, 8), C for the cheat sheet, f for feedback, or q to quit" (correction 12). `c` and `C` both open the sheet.
- Shows the last score for each chapter and marks the **weakest two** (the lowest score as a percentage, among chapters that have one). Always fewer marks than scored chapters, so two scored chapters get one mark and one gets none [2026-10-14: both rows showed "weakest" with only two scored].
- Live-mode status line: `ON (ANTHROPIC_API_KEY)`, `ON (ant profile)`, or `OFF`.

---

## 4. Architecture

```
hands-on-ai-pm/
├── tutorial.py            # entry point: argparse, menu, main loop
├── engine.py              # Step/Chapter model, navigation (Enter/b/q), per-step RNG, footer, shared Learn-screen renderer
├── sampling.py            # softmax with temperature, top-p, top-k, sampling, nudging tables
├── tokens.py              # tiktoken (bundled, offline), fallback estimator, Claude estimate, live count_tokens
├── pricing.py             # every price + LAST_CHECKED + source URLs (only file with numbers)
├── costs.py               # cost math: per request, monthly, caching, batch, chat-history growth
├── live.py                # optional Anthropic client: credential detection, temperature run, grading
├── progress.py            # read/write progress JSON
├── lessons/
│   ├── ch1_generation.py
│   ├── ch2_tokens.py
│   ├── ch3_temperature.py
│   ├── ch4_hallucination.py
│   ├── ch5_model_choice.py
│   ├── ch6_cost.py
│   ├── ch7_context.py
│   ├── ch8_design_feature.py
│   └── cheat_sheet.py
├── data/
│   ├── prompts.toml       # ~30 "The sky is ___"-style probability tables (Ch 1, 3)
│   ├── hallucination.toml # wrong-but-likely tables, with and without context (Ch 4)
│   ├── scenarios.toml     # design-exercise scenarios + usage ranges (Ch 8, Ch 6)
│   ├── checklists.toml    # grading checklists + follow-ups per chapter
│   ├── glossary.toml      # every bolded term from Learn screens (cheat sheet)
│   └── tiktoken/          # bundled o200k_base encoding file (offline tokenization)
├── tests/
├── requirements.txt
├── requirements-live.txt
└── README.md
```

### 4.1 Engine model
- A **Chapter** is an ordered list of **Steps**. Each step is a function `render(ctx) -> StepResult`.
- `ctx` holds: the chapter's own random generator, a `state` dict (predictions, answers, experiment results), the console, live-mode status, and progress.
- **Back navigation:** each step's randomness comes from its own random generator, seeded from `(run_seed, chapter, step_index)` using a stable hash (`hashlib`, not Python's `hash()`). Re-rendering a step after going back therefore shows **the same numbers**. Typed answers are kept in `state`, and going back re-shows the previous answer as the default.
- Lessons only describe their content. Navigation, the footer, Ctrl-C handling and saving progress all live in `engine.py`.

### 4.2 Data files (TOML)
**[APPROVED 2026-10-09]** TOML because it's the easiest format to edit by hand (comments, no braces) and Python 3.11+ reads it with the built-in `tomllib`, so there's no extra dependency. Example:

```toml
[[prompt]]
text = "The sky is"
tokens = { blue = 62, clear = 18, dark = 12, gray = 6, ugly = 2 }   # relative weights, normalized at load
fits = "everyday"                                                   # optional tag
```

Validation runs at load time and in tests: at least 3 candidates per prompt, all weights positive, unique words, and at least 30 prompts in the pool.

### 4.3 Progress file
**[APPROVED 2026-10-09]** `~/.config/hands-on-ai-pm/progress.json`, outside the repo so it survives re-clones and never gets committed:

```json
{ "chapters": { "3": { "self": [3, 6], "claude": [4, 6], "at": "2026-10-09T18:22:00", "seed": 48213 } } }
```

The menu shows the most recent score, using Claude's grade when one exists and the self-score otherwise. Only the latest attempt per chapter is kept (a history isn't needed yet).

---

## 5. The chapter loop (applies to every chapter)

**Teach first, then apply.** Each chapter opens with a Learn section of plain click-through screens, so nothing hands-on asks you to use an idea you haven't been taught yet. Approved by Sean on 2026-10-09.

| # | Step | What happens | Saved to |
|---|---|---|---|
| 0 | **Question** | The chapter's question appears in a panel, with "you'll answer this at the end; the Recap lists what a strong answer covers" | — |
| 1 | **Learn** | 4–8 click-through screens (format below). Enter to advance, b to go back. No input required | — |
| 2 | **Recap** | One screen, one point per checklist item, introduced as "This chapter in N points. They're also what a strong answer to <question> covers." [APPROVED 2026-10-14, issue #13]. The **Recap:** lines written for Chapters 2–7 in §6 predate this rule; each is realigned to its checklist when the chapter is built. Chapter 8's Recap is its answer structure, so it's exempt (and its `h` hint is that structure) | — |
| 3 | **Quick check** | 1–2 multiple-choice questions, **ungraded**. A wrong answer shows a one-line explanation and offers to reopen the Learn screen it came from | — |
| 4 | **Predict** | 1–3 predict-the-outcome questions, numbers randomized per run. Free text or a number | `state` |
| 5 | **Experiment** | Run it, then show the result next to the prediction ("You guessed 12/20; actual 17/20"). Each experiment screen has a one-line "what this shows" caption linking back to the idea from Learn | `state` |
| 6 | **Answer** | Type an answer to the chapter's question. Multi-line; a blank line ends it. Minimum of 1 sentence; an empty answer asks "skip grading?" Typing `h` shows the chapter's hint (short cues, not the answer) and asks again [APPROVED 2026-10-14, issue #16] | `state` |
| 7 | **Grade** | Show the user's answer read-only, then the checklist. The user marks each item y/n. If live: "Have Claude grade it too? (~$0.01) [y/N]" → per-item verdict plus one line of feedback. Then, graded or skipped, a strong sample answer and "say it out loud once more" [APPROVED 2026-10-14, issues #15, #16] | progress |
| 8 | **Follow-up** | A harder twist picked at random from the chapter's pool. The user types a short answer, then sees "what a strong answer mentions" | — |

### 5.1 Learn screen format
Every Learn screen has the same shape, so it reads consistently:

```
┌ 3 of 7 · Training vs. answering a request ────────────────────────────┐
│ Body: 3–6 short lines, one idea, plain language.                      │
│ New terms are **bold** the first time they appear.                    │
│                                                                        │
│ Think of it like: an everyday comparison.                              │
│ Example: one concrete case (numbers where possible).                   │
│                                                                        │
│ Why a PM cares: one line connecting it to product decisions.          │
└────────────────────────────────────────────────────────────────────────┘
```

- **Not overly simplified:** screens use the real terms (token, parameters, inference, context window, RAG), and each term is explained the first time it appears.
- **Glossary:** every bolded term goes into `data/glossary.toml` (term, one-line definition, the chapter it's introduced in). The cheat sheet includes the glossary.
- Learn screens are pure content: data in each lesson module (`title`, `body`, `analogy`, `example`, `why_pm`), rendered by one shared function in `engine.py`.

### 5.2 Learn-only mode
- `python tutorial.py --learn N` runs only Chapter N's Learn, Recap and Quick check steps. It's meant as a quick refresher.
- No predict or grade steps, and progress isn't saved.
- `--learn all` runs every chapter's Learn section back to back.

---

## 6. Chapters

Time estimates add up to about **70 minutes**, within the approved 60–75. Each chapter lists:
- **Learn** screens, then the Recap and the Quick check
- **Hands-on** steps
- Predict questions, the grading checklist, and follow-ups

The checklists, follow-ups, hint (`hint`, short cues) and strong sample answer (`sample_answer`) live in `data/checklists.toml`. Every chapter needs all of them; the loader rejects a chapter without them.

### Chapter 1: "Explain how an LLM generates text." (~10 min)
This is the foundation chapter, so it has the biggest Learn section.

**Learn**
1. **What an LLM is.** A **large language model** is a program that has read an enormous amount of text and learned the patterns of which words tend to follow which. It doesn't look answers up in a database or search the web by default. It writes what's likely to come next. *Why a PM cares: it explains both its strengths (fluent, flexible) and its failures (Chapter 4).*
2. **Think of it like autocomplete.** Your phone suggests the next word. An LLM does the same thing, trained on vastly more text and able to keep going for pages. *Example: "Thanks so much for ___" → "your", "the", "everything".*
3. **The vocabulary.**
   - **Prompt:** what you send in.
   - **Response** (or completion): what comes back.
   - **Model:** the trained program itself.
   - **API:** how a product sends prompts to the model over the internet and gets responses back. Products pay per use.
4. **Training vs. answering a request.**
   - **Training** happens once: months of computing, tens to hundreds of millions of dollars, finished before you use the model.
   - **Inference** is the model answering one request. You pay per request.
   - *Think of it like: writing a textbook (once, expensive) vs. a student answering a question from it (every time, cheap).*
5. **Knowledge cutoff, and how chatbots still know today's news** [APPROVED 2026-10-14, issue #12]. Training stops on a date, so the model's own knowledge has a **knowledge cutoff**. Chat apps get around it with **tools** such as web search: the app searches, adds the results to the prompt, and the model reads them before answering. *Why a PM cares: fresh or private information has to come from your product, not the model (Chapter 7).*
6. **Probabilities.** For "The sky is ___", the model gives every possible next word a **probability**, a score for how likely it is. All the scores add up to 100%. A static bar chart: blue 62%, clear 18%, dark 12%, gray 6%, ugly 2%.
7. **One piece at a time.** The model picks one word (really one **token**, a word piece; see Chapter 2), adds it to the text, and then scores the next word given everything so far. It repeats until it's done. A long answer is hundreds of these small picks.
8. **Bigger vs. smaller models.** **Parameters** are the billions of numbers the model learned during training. More parameters usually means more knowledge and better reasoning, but more computing for every word, so it's slower and pricier. A three-row table (small, medium, large) with relative arrows for quality, speed and price.

**Recap:** one token at a time · a probability for every next token, pick one · add the pick and repeat · own knowledge stops at the cutoff; apps add fresh facts to the prompt · bigger = better, but slower and pricier.
**Quick check:**
- "When you ask a model a question, does it look the answer up in a database?" (No: it generates likely text.)
- "ChatGPT just answered a question about yesterday's news. How?" (The app searched the web and added the results to the prompt.)

**Hands-on**
1. **Watch it generate:** start from a prompt in the pool and build a short sentence one token at a time (5–8 steps). At each step show the top 4 candidates as bars, highlight the pick, and append it. Press Enter between steps. Each step uses a small hand-written continuation table in `prompts.toml` (a `[prompt.continuation]` chain on 5 of the prompts).
2. At two of those steps you predict the pick first.

**Predict:** "Your prediction: which word is most likely next?", framed as a gut call ("you've read thousands of sentences like this"). The reveal shows the model's top pick and the odds of yours, not right/wrong [APPROVED 2026-10-14, issue #14].
**Checklist (5):** predicts one token at a time · picks from a probability distribution · appends the token and repeats · knowledge cutoff, and apps add newer information to the prompt · bigger = better but slower/pricier
**Follow-ups:** "Then how does it 'know' facts?" · "But ChatGPT told me about yesterday's news. How?" · "Why does the same prompt give different answers?"

### Chapter 2: "What's a token and why does it matter?" (~8 min)
[APPROVED 2026-10-14, plan PR #19] Measured corrections: on the bundled `o200k_base` tokenizer, plain English is about 0.91 words per token, not 0.75, so the ¾ figure is taught as OpenAI's rule of thumb and the hands-on shows the measured ratio next to it; and the same sentence takes 8 tokens in English, 11 in Spanish, 12 in Japanese and 17 in Hindi, so "2–4× more tokens per word" became "noticeably more tokens, sometimes about twice as many".

**Learn**
1. **What a token is.** Models read text in chunks, not whole words. Each chunk is a **token**. Common words are usually one token; rare or long words get split into pieces. *Example: on OpenAI's public tokenizer, "the" is one token; "antidisestablishmentarianism" is six (ant · idis · est · ablishment · arian · ism). Not the medical term, so Quick check 2 isn't answered on screen.*
2. **Why tokens, not words or letters.** A fixed **vocabulary** of roughly 100K to 200K pieces handles any text: typos, names and brand-new words. Letters alone would make every text long and slow; whole words alone would miss anything new. *Example: on OpenAI's public tokenizer, "Zorblax" is built from Z · or · bl · ax.*
3. **Everything is measured in tokens:** price (dollars per million tokens, input and output counted separately), speed (tokens per second), and the size limit (Chapter 7; "context window" is bolded there, not here).
4. **The rule of thumb, and its catch.** OpenAI's long-standing rule of thumb is a token ≈ ¾ of an English word. The count depends on the **tokenizer**: OpenAI's newest public one fits more English per token; Anthropic's current tokenizer (Claude 4.7 and every newer model) fits less, about 0.555 words per token. *Example, the chapter's line to quote, computed from `pricing.py` and the tokenizer: "By the classic ¾ rule, 1,000 words is about 1,300 tokens. Today's tokenizers range from about 1,100 (OpenAI) to about 1,800 (Claude), so measure your own text."*
5. **What uses more tokens:** rare words, numbers, code, emoji and many non-English languages. The same sentence can take noticeably more tokens in another language, sometimes about twice as many. *Example: 8 tokens in English, 17 in Hindi.*

**Recap (6, one per checklist item):** a token is a chunk of text · the ¾ rule of thumb, and the real ratio depends on the tokenizer · price, speed and size limits are in tokens · rare words, numbers, code, emoji and many languages use more (Hindi about 2.1× English) · vendors' tokenizers count differently · the line to quote above.
**Quick check:**
- "By the ¾-word rule of thumb, about how many tokens is a 1,000-word English document?" (About 1,300.)
- "Which uses more tokens: 'cat' or 'pseudohypoparathyroidism'?"

**Hands-on**
1. **Count the tokens:** predict the token count (a whole number) of a random sentence, then see the split in alternating colors, the measured count, a verdict ("spot on" or "off by N") and what the ¾ rule would have said.
2. **Tokenize your own text:** type anything, one line at a time, and see the split, with words, characters, tokens and the Claude estimate side by side. An empty line moves on, and `b`/`q`/`f` work as at any prompt; markup and special tokens show literally; a long paste is counted in full but only the first 300 characters are drawn. Under 3 words or mostly non-ASCII text gets "no reliable Claude estimate" instead of a range, because Anthropic's ratio is for English. When one color holds several tokens (some emoji and scripts), a note says so. Text with no spaces in a non-Latin script shows "words: n/a (no spaces)"; text with 2+ tokens per word gets "Names, IDs and some scripts split into many pieces: that's where costs surprise you."
3. **Measure the rule:** on three random plain-English paragraphs, words ÷ tokens for OpenAI's rule of thumb (0.75), the measured `o200k_base` ratio (about 0.9) and the Claude estimate (about 0.55), with what 1,000 words comes to under each. "A token is ¾ of a word" depends on the tokenizer, and a tokenizer change is a silent price change.
4. **What splits into many pieces:** a gallery run through the tokenizer: a long rare word, the medical term, `3.14159265`, a code snippet and emoji, with each one's pieces (spaces drawn as `␣`, and a piece that holds several tokens marked like `🚀(2)`, so the count can be checked by eye).
5. **Same sentence, different languages:** predict whether English or Japanese takes more tokens, then see English, Spanish, Japanese and Hindi counted.
6. **Same text, different bills:** one paragraph counted by OpenAI's public tokenizer and as a Claude estimate (both labeled; with a key, the official `count_tokens` count replaces the estimate, and a failure falls back to it with one line), then the input cost of a million such requests on five models, with each model's price per 1M input tokens and `prices checked`. One request is "this paragraph as the whole prompt; input only, no answer". It ends by showing a model that counts more tokens yet costs less, and the recommendation "compare the cost of your real text, per language, not the price per token". The Claude estimate shows as `~N` (a midpoint, not a count). The official count is fetched once per paragraph, after the heading and a "Getting the official Claude count…" line. The footer labels the OpenAI counts as the GPT-4o/GPT-5-era tokenizer, an approximation for GPT-6 (§10.6).

Every hands-on step ends with a one-line "What this shows" caption that points back to a Learn screen (§5 step 5).

If the bundled tokenizer can't load, every step says its counts are rough estimates: "Estimated", not "Measured"; no Pieces column; no language verdict; colors are words, not tokens.

**Predict:** "How many tokens is this sentence?" (random sentence) · "Which costs more tokens: the English or the Japanese version?"
**Checklist (6):** a token is a chunk of text, not a word · ~¾ of an English word on average (and tokenizer-dependent) · billing, speed and limits are all in tokens · code, numbers and non-English text use more · counts differ between vendors' tokenizers · gives a number
**Follow-ups:** "Your product launches in Japan. What happens to your cost?" · "Why not just bill users per word?"

### Chapter 3: "What does temperature do? When would you set it to 0?" (~10 min)
[APPROVED 2026-10-14, plan PR #19] Hands-on 1 and 2 are merged (show the prompt's bars, then predict) so the chapter fits its 10 minutes. The Recap has one point per checklist item.
**Learn**
1. **From probabilities to a pick.** Chapter 1 showed that the model scores every possible next token. Something then has to choose one. That choosing is called **sampling**. *Example: for "The sky is ___", blue 62%, clear 18%, dark 12%; sampling decides which one gets written.*
2. **Temperature: how adventurous the pick is.** **Temperature** is a dial on sampling. Low: almost always the top word. High: less likely words get picked more often. *Think of it like: ordering your usual dish vs. trying something new on the menu. Example (the mechanism): the model divides its scores by the temperature before turning them into odds: below 1 sharpens them, above 1 flattens them, and 0 just takes the top word.*
3. **What temperature does not do.** It doesn't change what the model knows, and it doesn't make answers more correct. *Example: if the most likely answer is wrong, temperature 0 gives you that wrong answer every time (Chapter 4).*
4. **Top-k and top-p:** two ways to cut off the unlikely options before picking. **Top-k** keeps only the k most likely; **top-p** keeps the smallest set whose odds add up to p, for example 90%. *Example: top-k = 2 on the sky example keeps blue and clear.*
5. **Other output controls.** **max_tokens** caps the answer length, and so caps the output cost. A **stop sequence** ends the answer early when a chosen string appears.
6. **Which setting fits which product.** A table (plain lines below 60 columns): Low (0 to 0.3) when the task has one right answer (extraction, classification, medical coding, SQL); Medium (around 0.5) for some variety with the same facts (customer replies); Higher (0.7 to 1) when many answers are good (brainstorming, marketing copy, product names). Medium was added in review because the settings cards grade it.
7. **The newest models fix these settings** (§10.1). Opus 5.5 doesn't accept a temperature at all; Sonnet 5.5 rejects anything but the default; Haiku 5.5 requires temperature 1 and rejects top-k. These models are steered with **effort** (low, medium, high, xhigh, max) and the prompt; effort sets how much the model thinks and spends, not randomness. On models that accept it, near 0 for one-right-answer tasks and about 0.7 to 1 for creative ones; on the newest Claude models, consistency comes from the prompt, examples, structured output and checks. Even temperature 0 isn't fully deterministic on the real API: the servers batch requests together, and tiny rounding differences can flip a close pick. *Why a PM cares: the PM's lever has moved from temperature to effort and prompt design.*

**Recap (6, one per checklist item):** temperature reshapes the odds · low is predictable, high is varied · on models that accept it, near 0 for one-right-answer tasks like extraction or classification · about 0.7 to 1 for creative tasks · it doesn't make answers more correct · top-k/top-p trim unlikely options; the newest Claude models fix temperature, so consistency comes from the prompt, examples, structured output and checks.
**Quick check:**
- "You're extracting invoice totals. Low or high temperature?" (Low.)
- "Your feature calls a model at temperature 0 on the real API. What does that guarantee?" (The top pick each time, though answers can still vary slightly.) It replaced "Does raising temperature make the model smarter?", which reviewers found trivially answerable; the reread points at screen 7.

**Hands-on**
1. **Predict 20 runs:** a random prompt from the pool of 30 (each run nudges the weights; §7.2), its probability bars at temperature 1, then a whole-number prediction at a random temperature (0.2, 0.3, 0.5 or 0.8, inside Claude's 0-1 range). The 20 runs are shown as a tally, with the typical count for those odds.
2. **Turn the dial:** type any temperature from 0 to 2 and see the odds reshape; Enter moves on. The screen says Claude's API takes 0 to 1 on models that still accept it (some other providers go up to 2), so values above 1 are there to exaggerate the effect.
3. **Temperature 0:** predict (a whole number) how many different answers 20 runs give, then see one. In the simulation, temperature 0 always picks the top word; the real API can still vary slightly, and the screen says why (batching and rounding differences).
4. **Top-k and top-p:** the options each one cuts are dimmed and named ("keeps: … · cut: …"), the kept share of the odds is shown ("top-p keeps adding words until they cover at least 90%"), the kept odds are said to be rescaled to 100%, then 20 runs with top-p = 0.9. When top-p keeps every word, the screen says so (and doesn't mention dimmed words).
5. **Guess the right setting:** 4 product cards, always at least one low, one medium and one high (seeded); pick low, medium or high for each, then see our pick and why.
6. **Length limits:** an answer cut off by `max_tokens` (cut at real token boundaries, with the full count labeled as OpenAI's tokenizer) and one ended early by a stop sequence.
Every experiment step ends with a one-line "What this shows" caption pointing back to a Learn screen (§5 step 5).

7. **[Live, optional] Real run:** after asking, with the estimated cost and `prices checked`, send "The sky is" to `claude-haiku-4-5` 10× at temperature 0 and 10× at temperature 1, with `max_tokens` 5. Show the answers side by side and how many differ. The screen explains that the tutorial uses an older model because Opus 5.5 doesn't accept a temperature and Sonnet 5.5 accepts only the default. Answers that differ only in case or punctuation count as the same; the table shows them as written. A failure prints one line and moves on, after showing any batch already paid for. Implementation note: SDK v1.0+ removed `temperature` from the method signature, so it's passed as `extra_body={"temperature": t}` (§10.1).

**Predict:** "At temperature {t}, how many of 20 runs say '{top_word}'?" (t randomized) · "At temperature 0, how many different answers in 20 runs?"
**Checklist (6):** reshapes the probability distribution · low = predictable, high = varied · 0 for tasks with one right answer (extraction, classification) · higher for creative tasks · temperature doesn't make answers more *correct* · mentions top-p or that the newest models fix it (effort)
**Follow-ups:** "Legal wants identical answers every time. Is temperature 0 enough?" · "Marketing says the copy is boring. What do you change?" · "Does temperature 0 stop hallucinations?"

### Chapter 4: "Define hallucination. Users say it's confident but wrong. Fix it." (~8 min)
[DRAFT 2026-10-14, plan 2b; copy needs Sean's OK] Departures: the Recap has one point per checklist item (6); the Quick checks are short scenarios; the Australia odds gain Perth 2 so they add to 100; no per-run nudge (it would let the right answer win at temperature 0); the predict temperature is fixed at 0.7; `hallucination.toml` tags are general, product and medical, with a second medical case (blood type); Learn examples avoid the hands-on cases; Learn 2 drops its italics; the evals teaser is free text, not graded; **retrieval** gets its glossary entry here (Chapter 7 reuses it).
**Learn**
1. **What a hallucination is.** A **hallucination** is an answer that is fluent and confident but false. It can be a made-up fact, a wrong number, a quote nobody said, or a source that doesn't exist. *Example: ask for sources and you can get a real-looking title, authors and year for a paper that was never written.*
2. **Why it happens.** The model is built to write text that sounds likely, not text that has been checked. It has no built-in fact-checker. A wrong answer comes out of the same probability bars as a right one (Chapter 1). *Think of it like: a quiz contestant who always answers, even when guessing, in the same confident voice.* *Example: "Einstein failed math" sounds familiar because it gets repeated a lot. It isn't true.*
3. **Common causes** (a bulleted list). Missing context: the fact it needed wasn't in the prompt (a common cause in products, and the one you control); past the knowledge cutoff, events after the training data ends; a rare fact; a loaded question that assumes an answer exists. *Example: a sales assistant with no price list in its prompt writes a typical price, not yours.*
4. **Why it sounds so sure.** Tone isn't a confidence signal. The model writes just as fluently when it's wrong as when it's right. *Why a PM cares: users trust confident text, so the product has to supply the safeguards.*
5. **The fix toolbox.** 1. Give it the facts: **grounding**, with the relevant documents found first by **retrieval** (Chapter 7). 2. Let it say "I don't know". 3. Ask for citations, and check them. 4. Put a person in the loop when the stakes are high. Set apart below the list: "What doesn't work: temperature 0. It repeats the top answer, right or wrong."
6. **Why it matters more in healthcare, legal and finance.** The higher the cost of one mistake, the more safeguards you need. *Example: a clinical summary with the wrong medication dose looks exactly as polished as a correct one.*

**Recap (6, one per checklist item):** fluent, confident output that is false · the model writes likely text and never checks facts · missing context is a common cause, and the one you control · fix it first by giving the model the facts (grounding, often through retrieval) · safeguards: "I don't know", citations, a person checking high-stakes answers · temperature 0 doesn't fix it: it repeats the top answer, right or wrong.
**Quick check:**
- "Your bot keeps giving the same wrong answer to one question. Someone suggests temperature 0. What happens?" (The same wrong answer, every time.)
- "Your HR assistant tells employees the wrong number of vacation days. What's the most likely cause you control?" (The policy isn't in its prompt.)

**Hands-on** (cases from `hallucination.toml`, at least 5, at least one medical and one other; the loader checks that a wrong answer is the single top pick without context and the right answer with it)
1. **Watch it happen:** a non-medical case's bars (e.g. "The capital of Australia is ___": Sydney 48, Canberra 41, Melbourne 9, Perth 2), the right answer named, a line showing how temperature 0.7 sharpens the top answer's odds, then 20 runs as a tally (bars drawn from the counts).
2. **Temperature 0 doesn't help:** the same prompt, 20 runs at temperature 0: the wrong top answer wins 20 of 20.
3. **Healthcare version:** a medical case ("Patient is allergic to ___" or "The patient's blood type is ___") with nothing about the patient in the prompt: its bars, the sharpening line, then 20 runs at 0.7. The odds favor a common answer, not this patient's.
4. **Add context:** the chart line goes into the prompt ("Chart: allergic to sulfa drugs."), then 20 runs again, compared with step 3's tally.
5. **Evals teaser** (not graded): "How would you measure whether the fix worked?" (one line; b, q and f still work), then one good approach with a number to quote: e.g. 200 real questions with known answers, the wrong-answer rate before and after, a stricter target for medical answers (it points ahead to Chapter 8).

**Predict:** "Out of 20 runs at temperature 0.7, how many give a wrong answer?" · "After adding context, how many are wrong now?"
**Checklist (6):** confident but false output · caused by picking likely text, not checked facts · names the cause: the fact was missing from the prompt · fix: supply facts (retrieval/grounding) · at least two safeguards: "I don't know", citations, human review for high stakes · temperature 0 doesn't fix it, and why (it repeats the top answer)
**Follow-ups:** "You added retrieval and it still makes things up. What next?" · "How do you explain this risk to a hospital customer?" · "Wouldn't a bigger model just fix this?"

### Chapter 5: "Small vs. large models: how do you choose?" (~9 min)
[DRAFT 2026-10-14, plan 2b; copy needs Sean's OK] Departures: the Recap has one point per checklist item (6), and Learn 7 gains "Start from the job" so Recap point 1 is taught first; hands-on 1 draws 3 of 6 jobs, with "tag product reviews" in place of "classify a support ticket" (Quick check 2 asks about tickets); prices and illustrative ratings are two small tables, with GPT-6 Astra and Gemini 3.8 Flash; the race animates only in a real terminal and prints two still frames elsewhere; routing is predict first, then a calculator (Haiku 5.5 vs. Opus 5.5); fast mode uses illustrative Opus timings; full cost compares Haiku 5.5 with Sonnet 5.5 using illustrative error rates and `pricing.REVIEW_HOURLY_USD`; monthly totals are shown to the whole dollar; Learn 2 and 7 examples avoid ticket sorting.
**Learn**
1. **Model families come in sizes.** Claude has Haiku (small), Sonnet (medium) and Opus (large); OpenAI and Google have their own small and large models. Each size is a different point on a tradeoff. *Think of it like: a delivery company with bikes, vans and trucks.*
2. **Quality, speed, cost: pick your balance.** Bigger models are usually better at hard reasoning and obscure facts, but slower and pricier per token. Per token, Opus costs about 40× as much as Haiku (computed from `pricing.py`). Smaller ones are fast, cheap and often good enough for simple, well-defined jobs. *Example: a model that writes excellent legal analysis is wasted on fixing typos.*
3. **Two kinds of speed.** **Time to first token**: how long before anything appears. **Streaming speed**: how fast the words keep arriving after the first one, in tokens per second. Models that reason first can be slow to start even when they stream fast. Some models sell a faster-streaming mode at a higher price. *Think of it like: waiting for a table vs. how fast the food comes once you're seated.*
4. **Routing.** **Routing** sends easy requests to a small model and hard ones to a large one. In many products most requests are easy. The router can be a rule or a small model. *Example: password resets to a small model, billing disputes to a large one.*
5. **Full cost.** Add the people who review and fix answers, retries, and engineering time. A cheaper model that needs more human fixing can cost more overall.
6. **When not to use an LLM.** A simple rule or a database lookup is cheaper, faster and can't make things up. Use them when the task has one exact answer.
7. **How to answer "it depends".** Start from the job: who uses it, how often it runs, and what a mistake costs. Say what the choice depends on, then commit. Template: "I'd use X because Y. I'd switch to Z if W."

**Recap (6, one per checklist item):** start from the job · quality, speed and cost trade off (Opus about 40× Haiku per token) · speed has two parts · route easy requests to a small model, with a rule or a small model sorting them · count the full cost · commit with conditions.
**Quick check:**
- "Users say the app feels slow before anything appears on screen. Which kind of speed is the problem?" (Time to first token.)
- "1M support tickets a day, each sorted into one of 5 categories. Which model do you try first?" (The smallest, moving up only if it isn't good enough.)

**Hands-on**
1. **Start from the job:** 3 jobs drawn from 6 (tag product reviews, draft a contract clause, summarize a clinical note, search suggestions, plan a database migration, draft customer email replies). Pick small, medium or large for each before seeing prices; see our pick, whether yours would overpay or fall short, and why.
2. **Price, quality and speed:** Haiku 5.5, Sonnet 5.5, Opus 5.5, GPT-6 Astra and Gemini 3.8 Flash. Real prices from `pricing.py` (with `prices checked` and each model's note, in plain language) in one table; illustrative quality and speed ratings in another; a pricier model of the same size pays only for a measured win on your task.
3. **Speed race:** two made-up models write the same 400-token answer, one starting fast and streaming slowly, the other thinking for 4 seconds and then streaming 4× as fast (both speeds said on screen). Animated for about 3 seconds in a real terminal; elsewhere, still frames at 2 and 6 seconds. Labeled illustrative.
4. **Predict the saving:** a random workload (requests a day, tokens in and out, 60-90% easy) priced on Opus 5.5; pick the monthly saving from routing the easy share to Haiku 5.5 (4 choices: the saving and three named mistakes, at least one of them larger). The reveal echoes the pick and names the mistake.
5. **Routing calculator:** the same workload at 0%, 50%, 80% and 95% easy, then any share you type (echoed as typed). Per month and Saved always add up to the all-Opus bill.
6. **Fast mode** (Opus 5.5, research preview): 2× the price for up to 2.5× faster streaming, not a faster first token; its Opus timings are a separate illustration from the race; times for a short and a long answer, and the workload's monthly cost both ways.
7. **Full cost:** 2,000 drafts a day on Haiku 5.5 vs. Sonnet 5.5, assuming a person already reads every draft. With illustrative error rates and review time, the cheaper model costs more in total; the screen shows the error rate below which it would win, and a rule of thumb (the small model wins when its answers are nearly as good or mistakes are cheap to catch).

**Predict:** "With {x}% of requests routed to Haiku, what's the monthly saving?" (multiple choice of 4)
**Checklist (6):** starts from the job (who, how often, cost of a mistake) · names the quality/speed/cost tradeoff · separates time to first token from streaming speed, if users wait on it · routes easy requests to small models and says how requests get sorted · counts full cost (human review or retries) · commits to a recommendation consistent with the rest of the answer, with conditions
**Follow-ups:** "Latency now matters twice as much. Does your answer change?" · "Finance cuts your budget in half." · "A new model is 20% better and 3× pricier. Switch?"

### Chapter 6: "How do costs change as you scale?" (~10 min)
[DRAFT 2026-10-14, plan 2c; copy needs Sean's OK] Departures: the Recap has one point per checklist item (6); the quick checks are short scenarios with named mistakes as distractors; Learn 1 says "5×" (computed from `pricing.py`), Learn 4 lists cache-read multipliers per model, Learn 5 says batch answers come back within a day, and every figure on a Learn screen is formatted from `pricing.py`; one product scenario per run (`data/scenarios.toml`, usage labeled illustrative) drives every hands-on step; a new step, "Caching or batch?", holds the second prediction; history growth reports the 10-turn ratio and what doubling to 20 turns does ("grows toward the square"); the calculator is one bar list with a price on each bar, edits one line at a time, marks models with no batch price `*` and requests that don't fit "too long"; per-request costs are shown per 1,000 requests; crossing providers converts token counts with a ratio measured on Chapter 2's paragraphs, with Gemini using the OpenAI count as a labeled stand-in; table names drop "Claude " and " (Preview)"; the sample answer quotes the same 5× (filled in from `pricing.py`) and the same recommendation as the Recap, "cache what repeats and batch what can wait".
**Learn**
1. **How you're billed.** Prices are per million tokens, and **input tokens** (what you send) and **output tokens** (what comes back) are priced separately. On Claude models, an output token costs 5× as much as an input token. *Example: one request on Sonnet 5.5, 2,000 tokens in and 500 out: output is 20% of the tokens but 56% of the cost.*
2. **Hidden tokens.** Every request also carries the **system prompt** (the product's standing instructions) and any **tool definitions**. The user never sees them, but you pay for them on every request. *Think of it like: the fine print stapled to every letter you send.*
3. **Chat history is re-sent every turn.** The model has no memory between requests (more in Chapter 7), so turn 10 re-sends turns 1 to 9, plus the system prompt. Long chats get expensive much faster than their length suggests.
4. **Prompt caching.** When the start of a prompt repeats, the provider can keep it ready. Reading from the cache costs 0.05× the input price on Opus 5.5 and Sonnet 5.5, 0.1× on Haiku 5.5; writing costs 1.25× (5-minute cache) or 2× (1-hour cache), once. *Think of it like: the kitchen pre-prepping the ingredients it uses in every dish.*
5. **Batch.** Work nobody is waiting on can go through the **batch** API: many requests at once, answers within a day, 50% off input and output.
6. **Thinking tokens.** Reasoning models "think" before answering. These **thinking tokens** are billed as output, and the thinking can be longer than the answer.
7. **The temperature myth.** Temperature does not change the price per token. It changes cost only indirectly, if it changes answer length.
8. **Unit economics.** Cost per request, then per user, then per month: the feature's **unit economics**, part of **cost of goods sold** (COGS), and the number a CFO asks for. *Example: a 2,000-in, 500-out request, 20 a day for 30 days, per user on Sonnet 5.5.*

**Recap (6, one per checklist item):** output costs 5× input on Claude · hidden tokens ride along on every request · history is re-sent every turn · the levers: cache what repeats and batch what can wait, then a smaller model and shorter answers · always get to a number per request, user and month · temperature doesn't change the price per token.
**Quick check:**
- "A request sends 1,000 tokens and gets 1,000 tokens back. Which half of the bill is bigger?" (The output.)
- "Your AI bill doubled after launch. Which change cuts it without changing the model?" (Cache the long system prompt; lowering temperature and raising max_tokens are the named mistakes.)

**Hands-on** (one scenario per run from `data/scenarios.toml`: support bot, coding assistant, medical-note summarizer, ad-copy tool, contract reviewer, meeting-notes app)
1. **Input vs. output:** one typical request of the scenario, input and output priced per 1,000 requests on Sonnet 5.5.
2. **History growth:** predict how many times a single-turn chat a 10-turn chat costs; a stacked bar per turn (fixed text, earlier messages, new message); the reveal gives the verdict, then what doubling to 20 turns does.
3. **Cache break-even:** the fewest uses where caching wins, for each Claude 5.5 model and both cache lengths; the scenario's repeated start, a day uncached vs. cached.
4. **Caching or batch?:** predict which saves more a month on Sonnet 5.5 (or about the same, within 10%); bars for no discount, caching and batch.
5. **Cost calculator (playground):** requests per day, input tokens, output tokens, cache-hit %, batch on/off and thinking tokens, starting from the scenario. Every model in `pricing.py` as a bar with its monthly price; pick a line to change, Enter ends the loop.
6. **Crossing providers:** the same requests on Sonnet 5.5, Haiku 5.5, GPT-6 Astra, GPT-6 Luna, Gemini 3.1 Pro and Gemini 3.8 Flash, with token counts converted by tokenizer (§7.4); official Claude count with a key.

**Predict:** "A 10-turn chat costs how many times a single-turn chat?" · "Which saves more here: caching or batch?"
**Checklist (6):** output tokens cost more than input · names at least one hidden cost (system prompt, tool definitions, history) · history re-sent every turn makes long chats disproportionately expensive · names at least two levers (caching, batch, smaller model, shorter answers) · puts a number on it per request, user or month · temperature doesn't change the price per token
**Follow-ups:** "Usage grows 10×. What breaks first?" · "Your CFO asks for cost per active user. Walk me through it." · "A competitor's model is half the price per token. Do you switch?"

### Chapter 7: "What's a context window? Paste everything in or fetch what's relevant?" (~8 min)
[DRAFT 2026-10-14, plan 2c; copy needs Sean's OK] Departures: the Recap has one point per checklist item (5; "no memory between requests" joins "every request pays for the whole window"); the quick checks are short scenarios with the spec's answers; Learn 1's window size (1M) and word count (about 555,000) are computed from `pricing.py`; Learn 2's example avoids Quick check 1's answer, and no Learn screen mentions the 120-token window or a "× cheaper" figure; Learn 5 bolds Retrieval (Chapter 4's glossary entry) and RAG; the forget demo is a simulated clinic chat with a 120-token window counted with the bundled OpenAI tokenizer, one of four profiles (Priya, allergic to sulfa, among them) and six independent questions shuffled per run, with dropped messages dimmed, struck through and marked `✗`, and a canned answer that can't see the allergy; cost per request shows input cost only on Haiku, Sonnet and Opus 5.5 and explains Haiku 5.5's jump past 100K tokens; the recall curve is hand-written and labeled illustrative in the text; paste vs. fetch defines a page as 500 words and always fetches 3 pages on Sonnet 5.5, with monthly totals; the Recap, hint and sample answer quote the same 1M (filled in from `pricing.py`) and the same recommendation, "fetch what's relevant and measure how often the search finds the right piece".
**Learn**
1. **The context window is working memory.** The **context window** is everything the model can see in one request: the system prompt, the chat history, any documents, and the answer it's writing. It has a hard limit in tokens: current Claude models take up to 1M tokens, about 555,000 words (from `pricing.py`). *Think of it like: a desk: the model can use whatever is on it, and nothing else exists for it.*
2. **No memory between requests.** Each request starts from nothing. When a chat seems to remember, it's the app sending the history again (which is why Chapter 6's chat costs grow). *Example: a 13th message carries the system prompt, the 12 earlier messages, the 12 replies and the new message.*
3. **When it fills up,** the app has to drop or summarize the oldest content, or the request is rejected. Dropped content is simply gone as far as the model is concerned. *Example: a long support chat drops the message with the order number.*
4. **Bigger isn't free.** Every request pays for everything in the window again, and long inputs are slower. Models also tend to pay less attention to the middle of a very long input. *Example: a question about one clause doesn't need the whole 300-page contract in every request.*
5. **Paste everything vs. fetch what's relevant.** Pasting every document is simple but expensive and noisy. **Retrieval** runs a search step first and sends only the most relevant pieces; it's often called **RAG**, retrieval-augmented generation. It's cheaper and more focused, but the search can miss the one document that mattered.

**Recap (5, one per checklist item):** the context window is what the model can see in one request, up to 1M tokens on current Claude models · overflow means forgetting · no memory between requests, so every request pays for the whole window · long inputs are slower and the middle gets less attention · retrieval is cheaper and more focused but can miss, so fetch what's relevant and measure how often the search finds the right piece.
**Quick check:**
- "A user comes back a week later: 'As I told you last time...' What can the model see from last week?" (Only what the app puts into this request.)
- "Your support bot fetches the 3 most relevant help pages for each question. It got a refund question wrong, though the refund policy is in your help center. Most likely cause?" (The search didn't fetch the refund page.)

**Hands-on**
1. **Watch it forget:** a simulated clinic chat with a 120-token window. The first message states a name and an allergy; turn by turn the oldest messages fall out (dim, struck through, `✗`), and then the "model" can't answer "what am I allergic to?". Predict the turn first.
2. **Cost per request:** input cost of one request at 2K / 50K / 500K tokens on Haiku, Sonnet and Opus 5.5.
3. **Lost in the middle:** an illustrative "recall by position" curve, strong at the start and end, weaker in the middle.
4. **Paste vs. fetch:** this run's scenario (from `data/scenarios.toml`), pasting all its reference pages vs. fetching 3, per 1,000 requests and per month on Sonnet 5.5. Predict how many times cheaper first.

**Predict:** "After how many turns does your first message fall out?" · "How many times cheaper per request is fetching 3 relevant pages than pasting all {n}?"
**Checklist (5):** everything the model can see in one request, with a hard token limit · overflow drops or summarizes older content, and the model forgets it · every request pays for the whole window again · quality can drop in the middle of very long inputs · names at least one benefit of retrieval and its risk of missing the key document
**Follow-ups:** "The context window doubled for free. Do you still need retrieval?" · "Retrieval missed the key document. Now what?" · "Users want the assistant to remember them across sessions. How?"

### Chapter 8: Design an AI feature, "Design an AI feature for X." (~9 min)
[DRAFT 2026-10-14, plan 2d; copy needs Sean's OK] Departures: (1) 4 Learn screens, not 3: the structure is split into steps 1-5 and 6-9 (§5 needs at least 4, and nine steps don't fit one 40-column screen). (2) Order is commit, grade, then the follow-ups and evals teaser (the §5 loop). (3) Follow-ups are 2 from the scenario's own pool (`[[scenario.followup]]`, at least 3 each) plus 1 general one from `[chapter.8]` in `checklists.toml`. (4) `h` works at the commit prompt, as in every chapter, not at every design prompt; the structure is also the Recap. (5) Models offered are Claude Haiku, Sonnet and Opus 5.5; the step asks temperature only for a model that accepts it, and effort otherwise (today: effort, with a line saying why). (6) Context strategy gains "None: rely on what the model already knows". (7) Risk rule: high when the task needs facts and (no context or temperature at least 0.7); medical and legal go one level up, capped at high, with a "have a clinician/lawyer review it" note. (8) Speed is the model's start at medium effort times an effort factor, plus reading the uncached prompt; the large model's start is Chapter 5's `OPUS_FIRST_TOKEN_SECONDS`. All illustrative and labeled. (9) The sample answer walks the structure without a specific scenario, because the scenario changes every run. (13) The evals teaser takes a typed reply, then shows what a strong answer mentions, then the "future chapter" note.
**Learn**
1. **What a strong design covers:** structured thinking, focus on the user, named tradeoffs, real numbers, and a recommendation you commit to. Not memorized facts.
2. **The structure: 1 to 5:** the user and the **job to be done**, requirements, model, settings (temperature or effort), context.
3. **The structure: 6 to 9:** cost, risks and safeguards, recommendation, how you'd measure it (**evals**).
4. **A worked example:** a travel site summarizing guest reviews for 50,000 hotel pages, walked through the nine steps, with its monthly cost computed from `pricing.py`. It isn't one of the scenarios.

**Recap (9):** the nine steps of the structure. It is also the `h` hint at the answer prompt.
**Quick check:** none. The exercise is the check.

**Hands-on**
1. **The brief:** a random scenario from `scenarios.toml` (at least 6: support bot, coding assistant, medical-note summarizer, ad-copy tool, contract reviewer, meeting-notes app) with seeded usage numbers (users, requests, tokens, reference material), labeled illustrative, and what's at stake: who is waiting, whether it needs facts, high stakes for medical and legal.
2. **Your design:** model, effort (or temperature), context strategy (none / paste everything / fetch what's relevant) and caching/batch. `b` returns here with each earlier pick as the Enter default.
3. **The outcome:** your design echoed, the monthly cost and cost per user (computed with `costs.py`), an illustrative time to first token with a verdict for the scenario (or "batch doesn't fit here" / "batch is the right call"), the hallucination risk with the reason, and a table of the same choices on each model.
4. **Commit:** type the recommendation and the reasoning, then grade against the checklist.
5. **3 reviewer follow-ups** (2 scenario, 1 general), each showing your design, then what a strong reply mentions.
6. **Evals teaser:** "How would you prove the cheaper model is good enough?" with a note that a future chapter covers it.

**Checklist (8):** starts with the user and the job to be done · model size with a reason · temperature or effort with a reason · context strategy with a reason · monthly cost as a number · how long users wait, or that nobody waits · hallucination risk and a safeguard · commits and says what would change it

### Cheat sheet + glossary (~3 min)
[DRAFT 2026-10-14, plan 2d; copy needs Sean's OK] Departures: (10) two pages, not one: "The chapters in one line each", then "Key numbers" (with `prices checked`); glossary pages hold at most 18 wrapped lines each, so there are more of them on a narrow terminal. (11) The tokenizer ratio is shown as stored in `pricing.py` (0.555, not "~0.55"), and the key numbers add the cache-write ratios and each Claude 5.5 model's input and output price. All computed from `pricing.py`, so they never go out of sync.
- **Page 1:** one line per chapter.
- **Page 2:** the key numbers: ¾ word per token on OpenAI's tokenizer and 0.555 on current Claude, output ≈ 5× input, cache read 0.05–0.1× and writes 1.25× or 2×, batch 50%, the 1M context window, each model's price.
- **Page 3+:** the glossary, alphabetical, from `data/glossary.toml`.
- Opened with `C` on the menu or `--lesson cheat` (`--learn` takes chapters only). Enter, `b`, `q` and `f` work as in a chapter; nothing is graded or saved.

---

## 7. Data and randomness

### 7.1 Seed
- No `--seed`: generate a 5-digit seed and show it in the header and footer. `--seed N` reproduces everything: prompt picks, nudges, predict numbers, scenarios, and the 20× samples.
- The per-step random generator is derived from the seed (§4.1). User input doesn't affect later randomness, except where the user picks a value (e.g. a temperature), which is then used directly.

### 7.2 Probability tables
- About **30 prompts** in `data/prompts.toml` (variety: sky/weather, food, sports, business clichés, a medical phrase, a code completion).
- **Nudge per run:** multiply each weight by a random factor (log-normal, σ ≈ 0.15), then renormalize. The top word usually stays on top but its share moves (e.g. blue 55–68%).
- **Math (sampling.py):** `p_i ∝ exp(log(w_i) / T)`. T = 0 is handled as argmax (always the top word). Top-k keeps the k highest; top-p keeps the smallest set whose total ≥ p. Then renormalize and sample.
- Every probability screen shows the label: *"Illustrative odds, computed with the same math real models use."*

### 7.3 Randomized questions
Predict questions are templates with placeholders filled from the step's random generator, with ranges set per question (e.g. temperature ∈ {0.2, 0.3, 0.5, 0.8, 1.2}, requests/day ∈ [1K, 500K] on a log scale).

### 7.4 Tokenization (tokens.py)
| Mode | Source | Label on screen |
|---|---|---|
| OpenAI-style count | `tiktoken.get_encoding("o200k_base")`, **bundled in `data/tiktoken/`**, with `TIKTOKEN_CACHE_DIR` set before import, so it never touches the network. Call the encoding by name: `encoding_for_model("gpt-6-…")` doesn't resolve, because tiktoken has no GPT-6 mapping | "OpenAI's public tokenizer (GPT-4o/GPT-5 era)" |
| Claude estimate | From Anthropic's documented ratio for the current tokenizer: 1M tokens ≈ 555K words ≈ 2.5M characters. Estimate = words ÷ 0.555 and characters ÷ 2.5, shown as a range | "estimate: Claude's tokenizer isn't public" |
| Claude count (live) | `client.messages.count_tokens(model=..., messages=[...]).input_tokens`. Free, and specific to the model passed in | "official Claude count (count_tokens)" |
| Fallback | If tiktoken fails to import or load: `max(words / 0.75, chars / 4)` | "rough estimate (tokenizer unavailable)" |

- Colored splits in Chapter 2 come from tiktoken's token boundaries. They're labeled as OpenAI's tokenizer, and the screen notes that Claude splits text differently.
- The handoff's "tiktoken undercounts Claude by ~15–20%" claim has **no Anthropic source** (§13). It is not used.

---

## 8. Pricing (pricing.py)

- One module, one `LAST_CHECKED = "YYYY-MM-DD"` and a `SOURCES` dict of URLs. No other file contains a price.
- Per model: `provider`, `display_name`, `api_id`, `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h`, `batch_discount`, optional `tiers` (threshold-based input/output prices), `context_window`, `max_output`, `tiktoken_factor` (Claude estimate range), `accepts_temperature` (bool), `illustrative` speed/quality ratings (clearly separated from real prices).
- Every screen that shows a price shows `prices checked {LAST_CHECKED}`.
- It also holds an illustrative reviewer hourly cost (`REVIEW_HOURLY_USD`, Chapter 5's full-cost example), commented as not from a pricing page and labeled illustrative on screen.
- **Tiered pricing** (Haiku 5.5, and possibly Gemini) is chosen by prompt size per request in `costs.py`.

### 8.1 Values (verified on live official pages, 2026-10-09)
All prices are USD per 1M tokens, standard tier. The build re-checks them and updates `LAST_CHECKED`.

| Model | API id | Input | Output | Cache read | Cache write 5m / 1h | Context | Max out | Temperature? |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | `claude-opus-5-5` | $4 | $20 | $0.20 (0.05×) | $5 / $8 | 1M | 128K | none (any value → 400; corrected 2026-10-14, §10.1) |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | $2 | $10 | **$0.10** (0.05×) | $2.50 / $4 | 1M | 128K | default only (non-default → 400) |
| Claude Haiku 5.5 | `claude-haiku-5-5` | $0.10 (≤100K) / $0.50 (>100K) | $0.50 / $2.50 | $0.01 / $0.05 (0.1×) | $0.125 / $0.20 (≤100K); $0.625 / $1 (>100K) | 1M | 128K | must be 1; any `top_k` → 400 |
| Claude Haiku 4.5 *(live demo only)* | `claude-haiku-4-5` | $1 | $5 | $0.10 | $1.25 / $2 | 200K | 64K | **yes** (legacy model, see §10.1) |
| OpenAI GPT-6 Astra | `gpt-6-astra` | $10 (≤272K) / $20 | $50 / $75 | $1.00 / $2.00 | n/a | 1.05M | 128K | — |
| OpenAI GPT-6 Luna | `gpt-6-luna` | $0.10 (≤272K) / $0.20 | $0.50 / $0.75 | $0.01 / $0.02 | n/a | 1.05M | 128K | — |
| Gemini 3.1 Pro *(Preview)* | `gemini-3.1-pro-preview` | $2 (≤200K) / $4 | $12 / $18 (incl. thinking) | $0.20 / $0.40 (+$4.50/1M/hr storage) | n/a | 1M | 65K | — |
| Gemini 3.8 Flash | `gemini-3.8-flash` | $0.75 | $3.75 | $0.075 (+$0.50/1M/hr) | n/a | 1M | 65K | — |

**Rules that `costs.py` must implement:**
- **Haiku 5.5 tier:** chosen per request from the *total* prompt tokens, including cache reads and writes. A request over 100K pays the higher rate for the whole request.
- **OpenAI and Gemini tiers:** the same per-request threshold logic (272K for GPT-6, 200K for Gemini Pro).
- **Batch:** 50% off input and output for Claude. Not combinable with Opus fast mode.
- **Opus 5.5 fast mode:** $8 / $40, up to 2.5× output tokens per second. It speeds up *streaming*, not time to first word (a good Chapter 5 point). Research preview.
- **Thinking tokens:** billed as output.

**Date-sensitive notes shown on screen:**
- **Gemini 3.8 Flash prices double on 2027-01-01** (to $1.50 / $7.50 / $0.15). `pricing.py` holds a `note` field per model, shown next to its price.
- Gemini 3.1 Pro is a Preview model.

**Sources:**
- platform.claude.com/docs/en/about-claude/pricing
- …/models/{opus-5-5,sonnet-5-5,haiku-5-5,haiku-4-5}/overview
- …/build-with-claude/fast-mode
- developers.openai.com/api/docs/pricing
- ai.google.dev/gemini-api/docs/pricing

---

## 9. Live mode (optional, live.py)

- **Detection:** `ANTHROPIC_API_KEY`, then `ANTHROPIC_AUTH_TOKEN`, then an `ant auth login` profile. For the profile check, try constructing the client and do nothing else; no network calls at startup. `anthropic` is imported only when live mode is used.
- **Each paid action asks first,** showing the estimated cost: "Run 20 real requests on Haiku 4.5? Estimated cost < $0.001 [y/N]". `count_tokens` is free, so it runs without asking.
- **Running cost total** for the session is shown in the footer when live mode is on.
- **Features:** (a) official Claude token counts (Ch 2, 6); (b) the live temperature run (Ch 3) on `claude-haiku-4-5`; (c) Claude grading.
- **SDK version:** pin `anthropic>=1.0,<2` in `requirements-live.txt`. In v1.0+ the sampling parameters are only reachable through `extra_body` (§10.1).
- **Grading:** **[APPROVED 2026-10-09]** `claude-sonnet-5-5`. A system prompt holds the checklist; the user's answer is the input. It returns JSON with one `{item, met: bool, why}` per item plus `feedback` (one sentence), using structured output so it parses reliably. About 1.5K input and 300 output tokens, so about $0.006 per answer at the cached prices.
- **Failures** (no network, bad key, rate limit, model unavailable): a one-line message, then fall back to the offline path. The chapter never crashes.

---

## 10. Gotchas built into the design

1. **The 5.5 models reject custom temperature** (verified 2026-10-09).
   - **At the API:** Opus 5.5 and Sonnet 5.5 return 400 for non-default values.
   - **Correction (2026-10-14):** Opus 5.5 returns 400 for any `temperature`, `top_p` or `top_k`, the default value included (Opus 4.7 and later; claude-api reference, `sdk-upgrade.md`). Sonnet 5.5 and Haiku 5.5 reject only values other than their defaults. Haiku 5.5 requires temperature = 1, rejects any `top_k`, and rejects sending `temperature` and `top_p` together. Haiku 4.5 still accepts all three.
   - **In the Python SDK v1.0+ (released 2026-08-20):** `temperature`, `top_p` and `top_k` were removed from the method signatures. Passing them raises `TypeError` for *every* model before any request is sent. The live demo uses `extra_body={"temperature": t}`.
   - **Haiku 4.5 is "Active (legacy)",** with retirement "not sooner than 2026-10-15" and a promised 60+ days' notice. The demo model id lives in `pricing.py` (`LIVE_TEMPERATURE_MODEL`). If the API returns "model not found", the step says the demo model was retired and skips. It never crashes.
   - `pricing.py` stores `accepts_temperature` per model, so the code never sends temperature to a model that rejects it.
2. **No probabilities from Claude's API.** The tables are illustrative (§7.2), and the live run shows sampled answers, not probabilities.
3. **tiktoken downloads its files on first use.** The `o200k_base` file is bundled and `TIKTOKEN_CACHE_DIR` points at it, with a fallback estimator. A test runs tokenization with the network blocked.
4. **Temperature doesn't change the per-token price.** Stated as a myth in Chapter 6 and checked in the Chapter 3 follow-ups.
5. **Claude's tokenizer isn't public and changed recently** (about 30% more tokens from Claude 4.7 onward). Offline Claude counts are estimates from Anthropic's documented ratio. With a key, `count_tokens` gives the official count.
6. **tiktoken has no GPT-6 mapping.** Always call `get_encoding("o200k_base")` explicitly and label it as an approximation for GPT-6.
7. **Prices change on known dates** (Gemini 3.8 Flash on 2027-01-01). Each model has a `note` field, and the "prices checked" date is on every price screen.

---

## 11. Testing

### Automated (pytest)
| Area | Tests |
|---|---|
| `sampling.py` | Softmax sums to 1 · T→0 = argmax · higher T = higher entropy · top-k/top-p keep the right set · same seed → same samples |
| `costs.py` | Hand-computed fixtures: per-request cost, monthly cost, output vs. input, cache read/write and break-even, batch 50%, tiered pricing crossing the threshold, chat-history growth formula, thinking tokens as output |
| `tokens.py` | Bundled encoding loads **with network access blocked** (patch the socket) · known strings give known counts · fallback estimator used when tiktoken import fails · Claude estimate is labeled and in range |
| `pricing.py` | Every model has every required field · output ≥ input · LAST_CHECKED is a valid date |
| data files | TOML parses · ≥30 prompts · ≥6 scenarios · every chapter has a checklist and ≥2 follow-ups · weights positive |
| `engine.py` | Back navigation re-renders the same numbers · q returns to the menu · Ctrl-C saves progress |
| `progress.py` | Round trip · missing or corrupt file → fresh start (with a warning, not a crash) |
| Learn content | Every Learn screen has `title`, `body`, `why_pm` · every chapter has ≥4 Learn screens, a Recap, and (except Ch 8) ≥1 Quick check · every **bold** term in Learn text has a glossary entry · `--learn N` writes no progress |
| Smoke | Each chapter runs end to end with scripted input (Enter through, sample answers, self-grade) in offline mode, with no exceptions |
| `live.py` | With a mocked client: temperature run, grading JSON parse, every failure falls back offline. Never calls the real API in tests |

### Manual
- A run-through of every chapter in a real terminal (macOS Terminal/iTerm), offline, at 80 and 120 columns.
- With a key, if Sean has one: the live temperature run, official token counts, and one Claude grade.

---

## 12. Decisions resolved during spec review (2026-10-09)
1. **Python 3.11+.** Python 3.10 reaches end of life in Oct 2026, and 3.11 has built-in TOML reading.
2. **Line-based controls:** `b` + Enter and `q` + Enter.
3. **Progress file** in `~/.config/hands-on-ai-pm/`.
4. **Grader model:** Sonnet 5.5, about $0.006 per answer.
5. **Teach-first chapter structure,** a 60–75 minute target, and `--learn` mode (§5).

---

## 13. Changes from the handoff after live verification (2026-10-09)
1. **Sonnet 5.5 cache read is $0.10, not $0.20.** The 0.05× cache-read rate applies to Sonnet 5.5 as well as Opus 5.5.
2. **Haiku 5.5 cache read confirmed:** $0.01 (≤100K) / $0.05 (>100K). The tiered pricing is confirmed.
3. **The temperature rejection is for non-default values only** (Opus and Sonnet 5.5). Haiku 5.5 is stricter. (Corrected 2026-10-14: Opus 5.5 rejects any value; see §10.1.)
4. **The SDK v1.0+ removed the sampling parameters,** so the live demo uses `extra_body`.
5. **Haiku 4.5 is legacy** and could be retired from about December 2026. The demo degrades gracefully.
6. **"tiktoken undercounts Claude 15–20%" is unsourced** and has been dropped. The documented fact used instead: current Claude tokenizers produce about 30% more tokens and about 0.55 words per token.
7. **OpenAI and Google models chosen:** GPT-6 Astra and GPT-6 Luna; Gemini 3.1 Pro (Preview) and Gemini 3.8 Flash.
8. **Teach-first structure (Sean, 2026-10-09):** every chapter now opens with Learn → Recap → Quick check before any hands-on step. There's a glossary, a `--learn N` refresher mode, and the time target is 60–75 minutes.
9. **New teaching points:**
   - Temperature 0 isn't fully deterministic on the real API.
   - Fast mode speeds up streaming, not time to first word.
   - The "¾ word" rule depends on the tokenizer.

---

## 14. Tester feedback [APPROVED 2026-10-09]
Testers are added to the repo with the GitHub Read role (the repo moves to an organization for this) and send feedback without leaving the tutorial.
- **Entry points:** `f` or `/feedback` at any prompt that takes `b`/`q` (footer, number and choice prompts, pauses) and at the start menu; plus one `[y/N]` question at the end of each full chapter run (not `--learn`).
- **Flow:** free text → kind (Bug, Confusing, Idea, Liked it) → a preview of everything that will be sent → the browser opens GitHub's new-issue page, prefilled through `.github/ISSUE_TEMPLATE/feedback.yml` → the user clicks Submit → "Did it go through?" Then the tutorial returns to the same prompt.
- **Sent with the note:** where (chapter, step, seed, or "Start menu") and setup (commit, Python, OS, terminal width, offline/live). Never the user's answers or credentials.
- **No token, no API call:** issues are created by the user in their own browser session, so nothing secret ships in the repo and each issue is attributed to its tester. The link never sets labels (Read users can't); the form's `labels: [feedback]` does.
- **Offline-first still holds:** each note is saved under `~/.config/hands-on-ai-pm/feedback/` until the user confirms it went through, and unsent notes are offered at the next start. No browser → the link is printed. Very long notes are trimmed to fit a GitHub link, with a warning to paste the rest.

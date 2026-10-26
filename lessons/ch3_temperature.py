"""Chapter 3: "What does temperature do? When would you set it to 0?" (spec §6, Chapter 3)

Hands-on: reshape a prompt's odds with temperature, predict
20 runs, trim with top-k/top-p, match settings to products, see length limits,
and (with a key) run a real model at temperature 0 and 1.
"""

import re
from itertools import zip_longest

from rich.markup import escape
from rich.table import Table

import costs
import pricing
import sampling
import tokens
import ui
from engine import Chapter, Ctx, LearnScreen, QuickCheck, make_rng

NONDETERMINISM = "the servers batch requests together, and tiny rounding differences can flip a close pick"
SETTINGS_ROWS = (
    ("Low (0 to 0.3)", "One right answer", "Extraction, classification, medical coding, SQL"),
    ("Medium (around 0.5)", "Some variety, same facts", "Customer replies"),
    ("Higher (0.7 to 1)", "Many good answers", "Brainstorming, marketing copy, product names"),
)
TABLE_MIN_WIDTH = 60  # narrower than this, a three-column table splits words like "Extraction," from their commas


def _settings_table(ctx: Ctx) -> None:
    if ctx.console.width < TABLE_MIN_WIDTH:
        for row in SETTINGS_ROWS:
            ctx.console.print(f"• {escape(' · '.join(row))}")
        return
    table = Table(show_header=True, header_style="bold")
    for column in ("Temperature", "When the task has", "Examples"):
        table.add_column(column)
    for row in SETTINGS_ROWS:
        table.add_row(*row)
    ctx.console.print(table)


LEARN = (
    LearnScreen(
        title="From probabilities to a pick",
        body=(
            "Chapter 1 showed that the model scores every possible next token.\nChoosing one is called **sampling**."
        ),
        example='For "The sky is ___": blue 62%, clear 18%, dark 12%. Sampling decides which one gets written.',
        why_pm="Variety in answers comes from sampling, not from the model changing its mind.",
    ),
    LearnScreen(
        title="Temperature: how adventurous the pick is",
        body=(
            "**Temperature** is a dial on sampling.\n"
            "Low: almost always the top token.\n"
            "High: less likely tokens get picked more often."
        ),
        analogy="ordering your usual dish vs. trying something new on the menu.",
        example=(
            "The model divides its scores by the temperature before turning them into odds. "
            "Below 1 sharpens the odds, above 1 flattens them, and 0 takes the top token."
        ),
        why_pm="One setting decides whether your product sounds consistent or creative.",
    ),
    LearnScreen(
        title="What temperature does not do",
        body=(
            "It doesn't change what the model knows or make answers more correct.\n"
            "It only changes how the model picks among options it already has."
        ),
        example="If the top answer is wrong, temperature 0 gives you that wrong answer every time (Chapter 4).",
        why_pm="Don't use temperature to fix accuracy. Fix the inputs instead.",
    ),
    LearnScreen(
        title="Top-k and top-p",
        body=(
            "Two ways to cut unlikely options before the pick.\n"
            "**Top-k** keeps the k most likely tokens. You pick k: k = 2 keeps the top two.\n"
            "**Top-p** adds tokens from the top down until their odds reach p, then stops. You pick p: p = 90% "
            "means stop at 90%.\n"
            'You\'ll try both in "Cut the tail" later in this chapter.'
        ),
        example=(
            "Sky example, top-k = 2 keeps blue and clear. "
            "Top-p = 90%: blue 62% is short of 90%; add clear, 80%, still short; add dark, 92%, so it stops. "
            "It keeps those three."
        ),
        why_pm="Both limit how odd an answer can get and keep some variety.",
    ),
    LearnScreen(
        title="Other output controls",
        body=(
            "**max_tokens** is a hard cap: the answer is cut off there, and that caps the output cost.\n"
            "A **stop sequence** ends the answer when a chosen string appears."
        ),
        example=(
            "A product card shows a one-line summary. The prompt asks for one line, and a stop sequence at "
            "the line break ends the answer there. max_tokens is the safety net: if the model rambles anyway, "
            "it is cut off at the cap, so set it above the longest line you expect."
        ),
        why_pm="You pay for every output token, so length is a cost lever.",
    ),
    LearnScreen(
        title="Which setting fits which product",
        body=(
            "Low when the task has one right answer.\n"
            "Medium when some variety helps but the facts must stay the same.\n"
            "Higher when many answers are good and variety helps."
        ),
        why_pm="Ask one question: does this task have one right answer?",
        visual=_settings_table,
    ),
    LearnScreen(
        title="The newest models fix these settings",
        body=(
            "Opus 5.5 doesn't accept a temperature at all. Sonnet 5.5 rejects anything but the default. "
            "Haiku 5.5 requires temperature 1 and rejects top-k.\n"
            "These models are steered with **effort** (low, medium, high, xhigh, max) and the prompt. "
            "Effort sets how much the model thinks and spends, not randomness.\n"
            "On models that accept it, use temperature near 0 for one-right-answer tasks and 0.7 to 1 for "
            "creative ones. On the newest models, get consistency from the prompt, examples, structured "
            "output and checks.\n"
            f"Even temperature 0 isn't fully deterministic on the real API: {NONDETERMINISM}."
        ),
        why_pm="Your lever has moved from temperature to effort and prompt design. Spend your tuning time there.",
    ),
)

RECAP = (
    "Temperature reshapes the odds the model picks from.",
    "Low temperature is predictable. High is varied.",
    "On models that accept it, use near 0 for one-right-answer tasks like extraction or classification.",
    "Use about 0.7 to 1 for creative tasks like brainstorming or marketing copy.",
    "It doesn't make answers more correct; it only changes the pick.",
    "Top-k and top-p trim unlikely options. The newest Claude models fix temperature, so consistency comes from "
    "the prompt, examples, structured output and checks.",
)

CHECKS = (
    QuickCheck(
        question="You're extracting invoice totals. Low or high temperature?",
        options=("Low", "High", "It doesn't matter"),
        answer=0,
        explanation="One right answer means you want the top pick every time.",
        screen=6,
    ),
    QuickCheck(
        question="Your feature calls a model at temperature 0 on the real API. What does that guarantee?",
        options=(
            "The same answer every time",
            "The top pick each time, though answers can still vary slightly",
            "The correct answer",
        ),
        answer=1,
        explanation=(
            f"Temperature 0 takes the top pick, but {NONDETERMINISM}. The top pick can also be wrong (Learn 3)."
        ),
        screen=7,
    ),
)

TEMPERATURES = (0.2, 0.3, 0.5, 0.8)  # inside Claude's 0-1 range
RUNS = 20
SETTINGS = ("low", "medium", "high")
CARDS = (
    ("Pull the invoice total out of a PDF", "low", "One right answer: you want the same total every time."),
    ("Sort support tickets into 5 categories", "low", "Classification has one right label per ticket."),
    ("Turn a doctor's note into billing codes", "low", "Medical coding has to be exact and repeatable."),
    ("Write a SQL query from a question", "low", "You want the same, tested query every time."),
    ("Suggest 10 names for a new product", "high", "Variety is the point: you want many different ideas."),
    ("Draft three versions of an ad headline", "high", "You want options that differ from each other."),
    ("Brainstorm blog post ideas", "high", "Unusual picks are welcome when brainstorming."),
    (
        "Write a friendly reply to a customer",
        "medium",
        "Some variety keeps it natural. The facts come from the prompt, not the setting.",
    ),
    ("Summarize a meeting for the team", "low", "A summary should stick to what was said."),
)
MAX_TOKENS_DEMO = 12
LONG_ANSWER = (
    "Our refund policy lets you return any item within 30 days for a full refund, as long as it is unused "
    "and in its original packaging. After 30 days we offer store credit instead."
)
STOP_DEMO = "Answer: Paris\nExplanation: Paris has been the capital of France since the 10th century."


def chosen_prompt(ctx: Ctx) -> tuple[str, dict[str, float]]:
    """This run's prompt and nudged odds. Seeded on its own, so every step sees the same one."""
    rng = make_rng(ctx.seed, "3/prompt", 0)
    prompt = rng.choice(ctx.data.prompts)
    return prompt.text, sampling.nudge(prompt.weights, rng)


def _bars(ctx: Ctx, probs: dict[str, float], title: str, counts: dict[str, int] | None = None) -> None:
    """The odds as bars or, with `counts`, the tally of the runs. The top pick by the odds is highlighted."""
    shown = probs if counts is None else {word: counts[word] / RUNS for word in probs}
    ctx.console.print(f"\n[bold]{escape(title)}[/bold]")
    ctx.console.print(ui.bar_chart(shown, width=ctx.console.width, highlight=sampling.top_word(probs), counts=counts))


def temperature_predict(ctx: Ctx) -> None:
    text, probs = chosen_prompt(ctx)
    t = ctx.rng.choice(TEMPERATURES)
    top = sampling.top_word(probs)
    ctx.console.print("[bold]Predict the runs[/bold]: guess how often the top token wins at a new temperature.")
    ctx.console.print(f"Prompt: [bold]{escape(text)}[/bold] ___")
    _bars(ctx, probs, "The odds as trained (temperature 1)")
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    guess = int(
        ctx.ask_number(
            f"Your prediction (an estimate, not graded): at temperature {t:g}, how many of {RUNS} runs say '{top}'?",
            "guess_runs",
            0,
            RUNS,
            integer=True,
        )
    )
    reshaped = sampling.apply_temperature(probs, t)
    counts = sampling.sample_many(reshaped, RUNS, ctx.rng)
    _bars(ctx, reshaped, f"At temperature {t:g}: {RUNS} runs", counts=counts)
    ctx.console.print(
        f"'{escape(top)}' came up {counts[top]} of {RUNS} times. You guessed {guess}. "
        f"Its odds are now {reshaped[top]:.0%}, and odds times runs gives the typical count: "
        f"{reshaped[top]:.0%} of {RUNS} is about {round(reshaped[top] * RUNS)}. "
        f"Any {RUNS} runs vary a little, so a guess near that is a good one."
    )
    ctx.console.print(ui.shows(f"temperature {t:g} reshapes the odds, not what the model knows (Learn 2)."))


def temperature_slider(ctx: Ctx) -> None:
    text, probs = chosen_prompt(ctx)
    ctx.console.print(f"[bold]Turn the dial[/bold] on: {escape(text)} ___")
    ctx.console.print("Try 0, 0.3, 1 and 2 and watch the bars.")
    ctx.console.print(
        "[dim]Claude's API takes 0 to 1 on models that accept a temperature. Some other providers go up to 2. "
        "Here, values above 1 exaggerate the effect.[/dim]"
    )
    while True:
        t = ctx.ask_number_or_skip("Temperature", "slider", 0, 2)
        if t is None:
            ctx.console.print(ui.shows("low temperature sharpens the odds, high flattens them (Learn 2)."))
            return
        _bars(ctx, sampling.apply_temperature(probs, t), f"At temperature {t:g}")
        ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")


def zero_predict(ctx: Ctx) -> None:
    text, probs = chosen_prompt(ctx)
    guess = int(
        ctx.ask_number(
            f"Your prediction: at temperature 0, how many different answers appear in {RUNS} runs of '{text} ___'? "
            "(Count each answer once, the top one included.)",
            "guess_distinct",
            1,
            RUNS,
            integer=True,
        )
    )
    at_zero = sampling.apply_temperature(probs, 0)
    counts = sampling.sample_many(at_zero, RUNS, ctx.rng)
    distinct = sum(1 for count in counts.values() if count)
    _bars(ctx, at_zero, f"At temperature 0: {RUNS} runs", counts=counts)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    noun = "answer" if distinct == 1 else "answers"
    ctx.console.print(
        f"{distinct} different {noun} in {RUNS} runs. You guessed {guess}. "
        f"That's the ideal case. The real API can still vary slightly at 0: {NONDETERMINISM}."
    )
    ctx.console.print(ui.shows("temperature 0 always takes the top token, right or wrong (Learn 3 and 7)."))


def trim(ctx: Ctx) -> None:
    text, probs = chosen_prompt(ctx)
    ranked = sorted(probs, key=lambda word: -probs[word])
    nucleus = sampling.top_p(probs, 0.9)
    ctx.console.print("[bold]Cut the tail[/bold]: see which options top-k and top-p remove before the pick.")
    for name, trimmed in (("Top-k = 2", sampling.top_k(probs, 2)), ("Top-p = 0.9", nucleus)):
        kept = [word for word in ranked if trimmed[word] > 0]
        cut = [word for word in ranked if trimmed[word] == 0]
        ctx.console.print(f"\n[bold]{name}[/bold] on: {escape(text)} ___")
        ctx.console.print(ui.bar_chart(probs, width=ctx.console.width, dimmed=frozenset(cut)))
        named_cut = f" · cut: {', '.join(cut)}" if cut else ""
        ctx.console.print(f"{name} keeps: {escape(', '.join(kept) + named_cut)}")
    top_p_keeps_all = all(p > 0 for p in nucleus.values())
    if top_p_keeps_all:
        ctx.console.print(
            "Here top-p = 0.9 keeps every word, because it takes all of them to reach 90%. The odds don't change."
        )
    else:
        covered = sum(probs[word] for word in ranked if nucleus[word] > 0)
        ctx.console.print(
            f"The kept words cover {covered:.0%} of the odds. Top-p adds words until they reach at least 90%."
        )
        ctx.console.print("The kept odds are then rescaled to add up to 100%, so each kept word's chance goes up.")
    counts = sampling.sample_many(nucleus, RUNS, ctx.rng)
    _bars(ctx, nucleus, f"Top-p = 0.9: {RUNS} runs", counts=counts)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    if not top_p_keeps_all:
        ctx.console.print("Dimmed words can't be picked at all, however lucky the roll.")
    ctx.console.print(ui.shows("top-k and top-p cut unlikely options before the pick (Learn 4)."))


def pick_cards(ctx: Ctx) -> list[tuple[str, str, str]]:
    """Four cards: one low, one medium and one high, plus one more, in a seeded order."""
    picked = [ctx.rng.choice([card for card in CARDS if card[1] == setting]) for setting in SETTINGS]
    picked.append(ctx.rng.choice([card for card in CARDS if card not in picked]))
    ctx.rng.shuffle(picked)
    return picked


def cards(ctx: Ctx) -> None:
    ctx.console.print("[bold]Pick the setting[/bold] for each product. Go with your gut.")
    for n, (task, setting, reason) in enumerate(pick_cards(ctx), 1):
        ctx.console.print(f"\n{n}. {escape(task)}")
        for i, option in enumerate(SETTINGS, 1):
            ctx.console.print(f"   {i}. {option}")
        pick = SETTINGS[ctx.ask_choice("Low, medium or high temperature?", len(SETTINGS), key=f"card{n}")]
        verdict = "Same as ours" if pick == setting else f"We'd pick {setting}"
        ctx.console.print(f"{verdict}: {escape(reason)}")
    ctx.console.print(ui.shows("the setting follows from whether the task has one right answer (Learn 6)."))


def length_limits(ctx: Ctx) -> None:
    cut, held = "", 0
    for piece, n in tokens.split_with_counts(LONG_ANSWER):
        if held + n > MAX_TOKENS_DEMO:
            break
        cut, held = cut + piece, held + n
    ctx.console.print(f"[bold]max_tokens = {MAX_TOKENS_DEMO}[/bold]")
    if not tokens.encoding_available():
        ctx.console.print(
            f"[dim]The tokenizer isn't available, so the cut is drawn at about {MAX_TOKENS_DEMO} words, not exact tokens.[/dim]"
        )
    ctx.console.print(f"{escape(cut)}[dim] ▌ (cut off: the answer stops mid-sentence)[/dim]")
    count, label = tokens.openai_count(LONG_ANSWER)
    ctx.console.print(
        f"[dim]You pay for {MAX_TOKENS_DEMO} output tokens instead of {count}. Counted with {escape(label)}.[/dim]"
    )
    ctx.console.print("\n[bold]Stop sequence = a new line[/bold]")
    ctx.console.print(f"{escape(STOP_DEMO.split(chr(10))[0])}[dim] ▌ (stopped at the line break)[/dim]")
    ctx.console.print("Use both when a feature only needs a short answer.")
    ctx.console.print(ui.shows("length is a cost lever, separate from temperature (Learn 5)."))


LIVE_PROMPT = "The sky is"
LIVE_TEMPERATURES = (0.0, 1.0)
LIVE_RUNS_EACH = 10
LIVE_INPUT_TOKENS = 40  # system prompt + "The sky is", rounded up
LIVE_OUTPUT_TOKENS = 5  # max_tokens in live.temperature_run


def live_cost_estimate() -> float:
    model = pricing.by_api_id(pricing.LIVE_TEMPERATURE_MODEL)
    usage = costs.Usage(input_tokens=LIVE_INPUT_TOKENS, output_tokens=LIVE_OUTPUT_TOKENS)
    return costs.request_cost(model, usage).total * LIVE_RUNS_EACH * len(LIVE_TEMPERATURES)


def same_answer(answer: str) -> str:
    """What counts as the same answer: "Blue", "blue." and "BLUE!" are one answer."""
    return re.sub(r"[^\w\s]", "", answer).strip().lower()


def live_run(ctx: Ctx) -> None:
    total = LIVE_RUNS_EACH * len(LIVE_TEMPERATURES)
    if ctx.live is None:
        ctx.console.print(
            f"[dim]Live extra (needs an Anthropic key): send '{LIVE_PROMPT}' to a real model {total} times, "
            "half at temperature 0 and half at 1. See README, Live mode.[/dim]"
        )
        return
    model = pricing.by_api_id(pricing.LIVE_TEMPERATURE_MODEL)
    ask = (
        f"Run {total} real requests on {model.display_name}? Estimated cost "
        f"{costs.format_usd(live_cost_estimate())} (prices checked {pricing.LAST_CHECKED})"
    )
    if not ctx.ask_yes_no(ask):
        ctx.console.print("Skipped. Nothing was sent.")
        return
    results: dict[float, list[str]] = {}
    for t in LIVE_TEMPERATURES:
        answers = ctx.live.temperature_run(LIVE_PROMPT, t, LIVE_RUNS_EACH)
        if answers:
            results[t] = answers
        if len(answers) < LIVE_RUNS_EACH:  # a call failed: keep what was paid for, skip the rest
            break
    distinct = {t: len({same_answer(answer) for answer in answers}) for t, answers in results.items()}
    if results:  # show what was already paid for, even if a later batch failed
        table = Table(show_header=True, header_style="bold")
        for t in results:
            table.add_column(f"Temperature {t:g}")
        for row in zip_longest(*results.values(), fillvalue=""):
            table.add_row(*(escape(answer) for answer in row))
        ctx.console.print(table)
        for t, n in distinct.items():
            ctx.console.print(f"Temperature {t:g}: {n} different answer{'' if n == 1 else 's'}")
    if len(results.get(LIVE_TEMPERATURES[-1], [])) < LIVE_RUNS_EACH:
        ctx.console.print(f"[yellow]Live run unavailable: {escape(ctx.live.last_error)}.[/yellow]")
        return
    low, high = (distinct[t] for t in LIVE_TEMPERATURES)
    ctx.console.print(
        f"[dim]Here temperature 0 gave {low} different answer{'' if low == 1 else 's'} and temperature 1 gave "
        f"{high}. Usually 0 is more consistent than 1. This run uses {escape(model.display_name)}, an older model, "
        "because Opus 5.5 doesn't accept a temperature at all and Sonnet 5.5 rejects anything but the "
        "default. Even at 0 the real API can vary slightly.[/dim]"
    )
    ctx.console.print(ui.shows("on a real model, temperature 0 is usually more consistent than 1 (Learn 2 and 7)."))


CHAPTER = Chapter(
    id="3",
    title="Temperature: how the model picks",
    minutes=10,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(temperature_predict, temperature_slider, zero_predict, trim, cards, length_limits, live_run),
)

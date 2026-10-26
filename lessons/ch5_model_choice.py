"""Chapter 5: "Small vs. large models: how do you choose?" (spec §6, Chapter 5)

Hands-on: pick a size for three jobs, compare real prices, race two made-up
models, predict and then calculate the saving from routing, price fast mode,
and count the full cost. Every dollar figure is computed from pricing.py at
run time; speeds, error rates and quality ratings are illustrative and say so.
"""

import dataclasses
import math
import random
import time

from rich.console import Group
from rich.live import Live
from rich.markup import escape
from rich.table import Table
from rich.text import Text

import costs
import pricing
import ui
from engine import Chapter, Ctx, LearnScreen, QuickCheck, make_rng

SMALL, LARGE = "haiku-5-5", "opus-5-5"
# How many times Haiku's per-token price Opus charges (input and output alike), from pricing.py.
PRICE_RATIO = pricing.get(LARGE).input / pricing.get(SMALL).input

LEARN = (
    LearnScreen(
        title="Model families come in sizes",
        body=(
            "Most AI companies sell a family of models in several sizes.\n"
            "Claude has Haiku (small), Sonnet (medium) and Opus (large). OpenAI and Google sell small and large models too.\n"
            "Each size is a different point on a tradeoff."
        ),
        analogy="a delivery company with bikes, vans and trucks. The right one depends on the load.",
        why_pm="Model size is one of the most common AI product decisions, and one of the easiest to get wrong.",
    ),
    LearnScreen(
        title="Quality, speed, cost: pick your balance",
        body=(
            "Bigger models are usually better at hard reasoning and obscure facts. They are also slower and pricier.\n"
            f"Per token, Opus costs about {PRICE_RATIO:g}× as much as Haiku.\n"
            "Smaller models are fast and cheap, and often good enough for simple, well-defined jobs.\n"
            "You rarely get all three at once."
        ),
        example="A model that writes excellent legal analysis is wasted on fixing typos.",
        why_pm="Every model choice gives up some quality, speed or cost. Decide which one this job can spare.",
    ),
    LearnScreen(
        title="Two kinds of speed",
        body=(
            "**Time to first token**: how long before anything appears.\n"
            "**Streaming speed**: how fast words arrive after that, in tokens per second.\n"
            "A model that reasons before answering starts slowly, even if it streams fast.\n"
            "Some models sell faster streaming at a higher price."
        ),
        analogy="waiting for a table vs. how fast the food comes once you're seated.",
        example="A chat reply is judged on how soon it starts. A report generated overnight is judged only on when it's done.",
        why_pm="Find out which one your users feel. Paying to speed up the other changes little they notice.",
    ),
    LearnScreen(
        title="Routing",
        body=(
            "**Routing** sends each request to the model that fits it: easy ones to a small model, "
            "hard ones to a large one.\n"
            "In many products most requests are easy, so most traffic can go to the cheap model.\n"
            "The router can be a simple rule, or a small model that sorts requests first."
        ),
        example="A support assistant answers password resets with a small model and hands billing disputes to a large one.",
        why_pm="Routing can cut the bill a lot without users noticing, if the easy requests really are easy.",
    ),
    LearnScreen(
        title="Full cost",
        body=(
            "Token price is only part of the cost. Add the people who review and fix answers, retries when "
            "an answer fails, and engineering time.\n"
            "A cheaper model that needs more human fixing can cost more overall."
        ),
        example="A reviewer spending a few minutes fixing each bad draft can cost more than all the tokens.",
        why_pm="Finance asks what the feature costs, not what a token costs. Count the people too.",
    ),
    LearnScreen(
        title="When not to use an LLM",
        body=(
            "A simple rule or a database lookup is cheaper and faster than any model, "
            "and it can't make things up.\n"
            "Use one when the task has a single exact answer you can look up or compute."
        ),
        example="Checking that an order number has 10 digits, or looking up an order's status, needs no model at all.",
        why_pm='"We don\'t need an LLM for this part" cuts cost and removes a way to be wrong.',
    ),
    LearnScreen(
        title='How to answer "it depends"',
        body=(
            '"It depends" is a fine start but a weak answer.\n'
            "Start from the job: who uses it, how often it runs, and what a mistake costs. "
            "Say what the choice depends on, then commit.\n"
            "Template: \"I'd use X because Y. I'd switch to Z if W.\""
        ),
        example=(
            "\"I'd use Sonnet for drafting replies because quality matters and volume is moderate. "
            "I'd route simple questions to Haiku once we've measured that it handles them.\""
        ),
        why_pm="Your team needs a decision with conditions, not a survey of options.",
    ),
)

RECAP = (
    "Start from the job: who uses it, how often it runs, and what a mistake costs.",
    f"Quality, speed and cost trade off: bigger models are better but slower and pricier (Opus costs about {PRICE_RATIO:g}× Haiku per token).",
    "Speed has two parts: time to first token and streaming speed.",
    "Route easy requests to a small model and hard ones to a large one. A rule or a small model does the sorting.",
    "Count the full cost: human review, retries and engineering, not just tokens.",
    "Commit with conditions: \"I'd use X because Y. I'd switch to Z if W.\"",
)

CHECKS = (
    QuickCheck(
        question="Users say the app feels slow before anything appears on screen. Which kind of speed is the problem?",
        options=("Time to first token", "Streaming speed", "Neither: it's the network"),
        answer=0,
        explanation="The wait before the first word is time to first token. Faster streaming wouldn't change it.",
        screen=3,
    ),
    QuickCheck(
        question="1M support tickets a day, each sorted into one of 5 categories. Which model do you try first?",
        options=(
            "The largest, to be safe",
            "The smallest, moving up only if it isn't good enough",
            "The medium one: always the safe middle",
        ),
        answer=1,
        explanation="It's simple, high volume and easy to check. Start small, measure, and move up only where it falls short.",
        screen=4,
    ),
)

SIZES = ("small", "medium", "large")
JOBS = (
    (
        "Tag 50,000 product reviews as positive or negative",
        "small",
        "A simple label at high volume, so small is usually good enough.",
    ),
    (
        "Draft a clause for a supplier contract",
        "large",
        "It's rare, high stakes and nuanced, so pay for the best and have a lawyer review.",
    ),
    (
        "Summarize a clinical note for the next doctor",
        "medium",
        "Not the hardest task, but mistakes are costly. Test mid-size and keep a clinician checking.",
    ),
    ("Suggest search terms as the user types", "small", "It runs on every keystroke and must feel instant."),
    (
        "Plan a tricky database migration with an engineer",
        "large",
        "Hard, multi-step reasoning that runs rarely, so quality wins.",
    ),
    (
        "Draft replies to customer emails for an agent to send",
        "medium",
        "Good writing at volume, and a person checks each draft.",
    ),
)
TABLE_MODELS = ("haiku-5-5", "sonnet-5-5", "opus-5-5", "gpt-6-astra", "gemini-3-8-flash")

# Two made-up models for the speed race: (name, seconds to first token, tokens per second). Illustrative.
RACERS = (("Quick starter", 0.5, 50), ("Thinks first", 4.0, 200))
RACE_TOKENS = 400
STILLS = (2.0, 6.0)  # simulated seconds shown when the console can't animate
SIM_STEP = 0.5  # simulated seconds per animation frame
FRAME_SECONDS = 0.15  # real seconds per animation frame

REQUESTS_PER_DAY = (20_000, 50_000, 100_000, 200_000)
INPUT_TOKENS = (1_500, 2_000, 3_000)
OUTPUT_TOKENS = (300, 500, 800)
EASY_SHARES = (0.6, 0.7, 0.8, 0.9)
TABLE_SHARES = (0.0, 0.5, 0.8, 0.95)

# Opus 5.5 speeds for the fast-mode step. Illustrative; the speedup itself comes from pricing.py.
OPUS_FIRST_TOKEN_SECONDS = 2.0
OPUS_TOKENS_PER_SECOND = 60
ANSWER_LENGTHS = (50, 1_000)

# The full-cost example. Illustrative rates; the review hour's cost is in pricing.py.
FULL_COST_MODELS = ("haiku-5-5", "sonnet-5-5")
TASKS_PER_DAY = 2_000
TASK_USAGE = costs.Usage(input_tokens=3_000, output_tokens=600)
NEEDS_FIXING = {"haiku-5-5": 0.12, "sonnet-5-5": 0.04}
MINUTES_PER_FIX = 6


def whole_usd(amount: float) -> str:
    """Monthly totals to the dollar, so wide numbers still fit a 40-column table."""
    return f"${amount:,.0f}"


def short_name(key: str) -> str:
    return pricing.get(key).display_name.removeprefix("Claude ")


def pick_sizes(ctx: Ctx) -> None:
    ctx.console.print("[bold]Start from the job[/bold]. Pick a size for each before you see any prices.")
    for n, (job, size, reason) in enumerate(ctx.rng.sample(JOBS, 3), 1):
        ctx.console.print(f"\n{n}. {escape(job)}")
        for i, option in enumerate(SIZES, 1):
            ctx.console.print(f"   {i}. {option}")
        pick = SIZES[ctx.ask_choice("Small, medium or large?", len(SIZES), key=f"job{n}")]
        if pick == size:
            verdict = "Same as ours."
        elif SIZES.index(pick) > SIZES.index(size):
            verdict = f"We'd start with {size}. {pick.capitalize()} would work, but it costs more and is slower than this job needs."
        else:
            verdict = (
                f"We'd start with {size}. {pick.capitalize()} is cheaper and faster, but would likely fall short here."
            )
        ctx.console.print(f"{verdict} {escape(reason)}")
    ctx.console.print("\nThe job decides the size. Next: prices and speeds.")
    ctx.console.print(
        ui.shows(
            "the job decides the size: start with who uses it, how often it runs and what a mistake costs (Learn 7)."
        )
    )


def _stars(rating: int) -> str:
    return "●" * rating + "○" * (5 - rating)


def comparison_table(ctx: Ctx) -> None:
    ctx.console.print("[bold]Price, quality and speed[/bold]")
    prices = Table(show_header=True, header_style="bold", title="Price per 1M tokens")
    ratings = Table(show_header=True, header_style="bold", title="Ratings out of 5 (illustrative)")
    for column in ("Model", "Input", "Output"):
        prices.add_column(column, justify="left" if column == "Model" else "right")
    for column in ("Model", "Quality", "Speed"):
        ratings.add_column(column)
    for key in TABLE_MODELS:
        model = pricing.get(key)
        name = escape(short_name(key))
        prices.add_row(name, costs.format_usd(model.input), costs.format_usd(model.output))
        ratings.add_row(name, _stars(model.quality), _stars(model.speed))
    ctx.console.print(prices)
    ctx.console.print(f"[dim]Real list prices (prices checked {pricing.LAST_CHECKED}).[/dim]")
    for key in TABLE_MODELS:
        model = pricing.get(key)
        if model.note:
            ctx.console.print(f"[dim]{escape(short_name(key))}: {escape(model.note)}[/dim]")
    ctx.console.print(ratings)
    ctx.console.print("[dim]Relative ratings to show the tradeoff, not measurements.[/dim]")
    small, large = pricing.get(SMALL), pricing.get(LARGE)
    ctx.console.print(
        f"Per token, {escape(short_name(LARGE))} costs {large.input / small.input:g}× {escape(short_name(SMALL))}. "
        "That gap is why routing matters."
    )
    ctx.console.print("Within one size, pay more only for a measured win on your task, not for a reputation.")
    ctx.console.print(
        ui.shows("bigger models cost more per token, so picking a size is also picking a price (Learn 2).")
    )


def tokens_shown(seconds: float, first_token: float, per_second: float) -> int:
    """How much of the race answer is on screen after `seconds`."""
    if seconds < first_token:
        return 0
    # The first token is on screen from the stated first-token time; streaming fills in the rest.
    return min(RACE_TOKENS, max(1, int((seconds - first_token) * per_second)))


def finish_time(first_token: float, per_second: float) -> float:
    return first_token + RACE_TOKENS / per_second


def race_frame(seconds: float, width: int) -> Table:
    bar_width = max(8, min(30, width - 30))
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    for name, first_token, per_second in RACERS:
        shown = tokens_shown(seconds, first_token, per_second)
        filled = math.floor(shown / RACE_TOKENS * bar_width + 0.5)  # halves round up, as in ui.bar_chart
        label = "thinking..." if shown == 0 else f"{shown}/{RACE_TOKENS}"
        table.add_row(name, Text("█" * filled + "·" * (bar_width - filled), style="cyan"), label)
    return table


def speed_race(ctx: Ctx) -> None:
    ctx.console.print("[bold]Two kinds of speed: a race[/bold]")
    ctx.console.print(f"Two made-up models write the same {RACE_TOKENS}-token answer.")
    (quick, quick_first, quick_rate), (thinker, thinker_first, thinker_rate) = RACERS
    ctx.console.print(
        f"{quick}: first token after {quick_first:g} s, then {quick_rate:g} tokens a second. "
        f"{thinker}: thinks for {thinker_first:g} s, then {thinker_rate:g} tokens a second, "
        f"{thinker_rate / quick_rate:g}× as fast."
    )
    end = max(finish_time(first, rate) for _, first, rate in RACERS)
    if ctx.console.is_terminal:
        with Live(console=ctx.console, auto_refresh=False) as live:
            for frame in range(math.ceil(end / SIM_STEP) + 1):
                seconds = min(frame * SIM_STEP, end)
                clock = Text(f"Time: {seconds:.1f} s")
                live.update(Group(clock, race_frame(seconds, ctx.console.width)), refresh=True)
                time.sleep(FRAME_SECONDS)
    else:
        for seconds in STILLS:
            ctx.console.print(f"\nAfter {seconds:g} seconds:")
            ctx.console.print(race_frame(seconds, ctx.console.width))
    table = Table(show_header=True, header_style="bold")
    table.add_column("Model")
    table.add_column("First token", justify="right")
    table.add_column("Done", justify="right")
    for name, first, rate in RACERS:
        table.add_row(name, f"{first:g} s", f"{finish_time(first, rate):g} s")
    ctx.console.print(table)
    ctx.console.print("[dim]Illustrative: two made-up models to show the shape, not measurements.[/dim]")
    ctx.console.print(
        "In a chat, users feel the first token, so the quick starter feels faster even though it finishes later. "
        "For a report nobody watches, only the finish matters."
    )
    ctx.console.print(ui.shows("time to first token and streaming speed are separate things to optimize (Learn 3)."))


def workload(ctx: Ctx) -> tuple[int, costs.Usage, float]:
    """This run's requests per day, request size and easy share. Seeded on its own, shared by the routing steps."""
    rng = make_rng(ctx.seed, "5/workload", 0)
    usage = costs.Usage(input_tokens=rng.choice(INPUT_TOKENS), output_tokens=rng.choice(OUTPUT_TOKENS))
    return rng.choice(REQUESTS_PER_DAY), usage, rng.choice(EASY_SHARES)


def saving_options(all_large: float, share: float, price_ratio: float, rng: random.Random) -> list[tuple[float, str]]:
    """The right monthly saving first (with no mistake), then three wrong ones, each a named mistake.

    `price_ratio` is small ÷ large per request. At least one wrong option is larger than the right one,
    so picking the biggest number isn't a strategy.
    """
    small, large = short_name(SMALL), short_name(LARGE)
    larger = [
        (all_large * share, f"treats {small} as free, but it still costs about 1/{1 / price_ratio:.0f} of {large}"),
        (all_large * (1 - price_ratio), "moves all the traffic, not just the easy share"),
    ]
    smaller = [
        (all_large * (1 - share) * (1 - price_ratio), "moves the hard share instead of the easy one"),
        (all_large * share / 2, f"assumes {small} costs half as much as {large}, not about 1/{1 / price_ratio:.0f}"),
    ]
    first = rng.choice(larger)
    rest = rng.sample([option for option in larger + smaller if option is not first], 2)
    return [(all_large * share * (1 - price_ratio), ""), first, *rest]


def routing_predict(ctx: Ctx) -> None:
    per_day, usage, share = workload(ctx)
    small, large = pricing.get(SMALL), pricing.get(LARGE)
    all_large = costs.monthly_cost(large, usage, per_day)
    ratio = costs.request_cost(small, usage).total / costs.request_cost(large, usage).total
    ctx.console.print("[bold]Predict the saving[/bold]")
    ctx.console.print(
        f"{per_day:,} requests a day, each about {usage.input_tokens:,} tokens in and {usage.output_tokens:,} out.\n"
        f"Everything on {escape(short_name(LARGE))}: {whole_usd(all_large)} a month.\n"
        f"{share:.0%} of the requests are easy enough for {escape(short_name(SMALL))}."
    )
    options = saving_options(all_large, share, ratio, ctx.rng)
    right = options[0][0]
    ctx.rng.shuffle(options)
    for i, (amount, _) in enumerate(options, 1):
        ctx.console.print(f"  {i}. {whole_usd(amount)} a month")
    picked, mistake = options[
        ctx.ask_choice("Your prediction: how much does routing them save?", len(options), "saving")
    ]
    why = (
        f"{escape(short_name(SMALL))} costs about 1/{1 / ratio:.0f} as much per request, "
        f"so moving {share:.0%} of the traffic saves nearly {share:.0%} of the bill."
    )
    if not mistake:
        ctx.console.print(f"Right. You picked {whole_usd(picked)}: {right / all_large:.0%} of the bill. {why}")
    else:
        ctx.console.print(
            f"You picked {whole_usd(picked)}. That number {escape(mistake)}. "
            f"The saving is {whole_usd(right)}, {right / all_large:.0%} of the bill. {why}"
        )
    ctx.console.print(
        ui.shows("routing the easy share to a small model saves nearly that share of the bill (Learn 4).")
    )
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")


def routing_row(per_day: int, usage: costs.Usage, share: float) -> tuple[int, int]:
    """(Per month, Saved), in whole dollars. Rounded once and subtracted, so they add up to the all-large bill."""
    small, large = pricing.get(SMALL), pricing.get(LARGE)
    all_large = round(costs.monthly_cost(large, usage, per_day))
    per_month = round(costs.routed_monthly_cost(small, large, usage, per_day, share))
    return per_month, all_large - per_month


def routing_calculator(ctx: Ctx) -> None:
    per_day, usage, _ = workload(ctx)
    ctx.console.print("[bold]Routing calculator[/bold]")
    ctx.console.print(
        f"Same workload. Easy requests go to {escape(short_name(SMALL))}, the rest to {escape(short_name(LARGE))}."
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Easy share", justify="right")
    table.add_column("Per month", justify="right")
    table.add_column("Saved", justify="right")
    for share in TABLE_SHARES:
        per_month, saved = routing_row(per_day, usage, share)
        table.add_row(f"{share:.0%}", whole_usd(per_month), whole_usd(saved))
    ctx.console.print(table)
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")
    while True:
        percent = ctx.ask_number_or_skip("Try your own easy share, in %", "share", 0, 100)
        if percent is None:
            break
        per_month, saved = routing_row(per_day, usage, percent / 100)
        ctx.console.print(f"{percent:g}% easy: {whole_usd(per_month)} a month, {whole_usd(saved)} saved.")
    ctx.console.print(
        "This only holds if the small model handles those requests well. Measure that on real traffic first."
    )
    ctx.console.print(
        ui.shows("the saving grows with the easy share, as long as the easy requests really are easy (Learn 4).")
    )


def fast_mode(ctx: Ctx) -> None:
    per_day, usage, _ = workload(ctx)
    opus = pricing.get(LARGE)
    fast = dataclasses.replace(
        opus, input=pricing.OPUS_FAST_MODE_INPUT, output=pricing.OPUS_FAST_MODE_OUTPUT, batch_discount=0.0
    )
    fast_rate = OPUS_TOKENS_PER_SECOND * pricing.OPUS_FAST_MODE_SPEEDUP
    ctx.console.print(f"[bold]Fast mode on {escape(short_name(LARGE))}[/bold] (research preview)")
    ctx.console.print(
        f"Pay {pricing.OPUS_FAST_MODE_INPUT / opus.input:g}× the price for up to "
        f"{pricing.OPUS_FAST_MODE_SPEEDUP:g}× faster streaming. It doesn't shorten the wait for the first token."
    )
    ctx.console.print(
        f"[dim]The race models were made up. The {escape(short_name(LARGE))} timings below are a separate "
        "illustration.[/dim]"
    )
    table = Table(show_header=True, header_style="bold")
    table.add_column("Answer", justify="right")
    table.add_column("Standard", justify="right")
    table.add_column("Fast mode", justify="right")
    for length in ANSWER_LENGTHS:
        standard = OPUS_FIRST_TOKEN_SECONDS + length / OPUS_TOKENS_PER_SECOND
        quick = OPUS_FIRST_TOKEN_SECONDS + length / fast_rate
        table.add_row(f"{length:,} tokens", f"{standard:.1f} s", f"{quick:.1f} s")
    ctx.console.print(table)
    ctx.console.print("[dim]Times are illustrative. The speedup is the most fast mode offers.[/dim]")
    ctx.console.print(
        f"For this run's workload: {whole_usd(costs.monthly_cost(opus, usage, per_day))} a month standard, "
        f"{whole_usd(costs.monthly_cost(fast, usage, per_day))} in fast mode "
        f"(prices checked {pricing.LAST_CHECKED})."
    )
    ctx.console.print(
        "Worth it when someone is waiting on a long answer, like live coding help. "
        "Not worth it for short answers or background jobs."
    )
    ctx.console.print(ui.shows("pay for speed only where users feel it (Learn 3)."))


def full_cost(ctx: Ctx) -> None:
    ctx.console.print("[bold]The full cost[/bold]")
    cheap, better = FULL_COST_MODELS
    ctx.console.print(
        f"{TASKS_PER_DAY:,} drafts a day, each about {TASK_USAGE.input_tokens:,} tokens in and "
        f"{TASK_USAGE.output_tokens:,} out. Say {escape(short_name(cheap))} gets {NEEDS_FIXING[cheap]:.0%} of "
        f"drafts wrong and {escape(short_name(better))} {NEEDS_FIXING[better]:.0%} (illustrative rates).\n"
        f"A person fixes each wrong draft: {MINUTES_PER_FIX} minutes, at {whole_usd(pricing.REVIEW_HOURLY_USD)} "
        "an hour (illustrative). A person already reads every draft, so finding bad ones adds nothing. "
        "Only fixing them costs extra."
    )
    totals: dict[str, float] = {}
    table = Table(show_header=True, header_style="bold")
    table.add_column("Per month")
    for key in FULL_COST_MODELS:
        table.add_column(escape(short_name(key)), justify="right")
    rows: dict[str, list[str]] = {"Need fixing": [], "Tokens": [], "Review": [], "Total": []}
    for key in FULL_COST_MODELS:
        tokens = costs.monthly_cost(pricing.get(key), TASK_USAGE, TASKS_PER_DAY)
        fixes = TASKS_PER_DAY * costs.DAYS_PER_MONTH * NEEDS_FIXING[key]
        review = fixes * MINUTES_PER_FIX / 60 * pricing.REVIEW_HOURLY_USD
        totals[key] = tokens + review
        rows["Need fixing"].append(f"{NEEDS_FIXING[key]:.0%}")
        rows["Tokens"].append(whole_usd(tokens))
        rows["Review"].append(whole_usd(review))
        rows["Total"].append(whole_usd(totals[key]))
    for label, cells in rows.items():
        table.add_row(label, *cells)
    ctx.console.print(table)
    ctx.console.print(
        f"[dim]prices checked {pricing.LAST_CHECKED}. Error rates and the reviewer's hourly cost are illustrative.[/dim]"
    )
    review_per_error_rate = TASKS_PER_DAY * costs.DAYS_PER_MONTH * MINUTES_PER_FIX / 60 * pricing.REVIEW_HOURLY_USD
    cheap_tokens = costs.monthly_cost(pricing.get(cheap), TASK_USAGE, TASKS_PER_DAY)
    flip = (totals[better] - cheap_tokens) / review_per_error_rate
    ctx.console.print(
        f"{escape(short_name(cheap))} is far cheaper per token, but costs {totals[cheap] / totals[better]:.1f}× "
        f"as much in total once review is counted. It would win only if its error rate were below {flip:.1%}, "
        f"close to {escape(short_name(better))}'s own {NEEDS_FIXING[better]:.0%}."
    )
    ctx.console.print(
        "Rule of thumb: the small model wins when its answers are nearly as good, or mistakes are cheap to catch. "
        "When a person has to fix each mistake, quality wins. So start small and measure: "
        "the error rate tells you which side you're on."
    )
    ctx.console.print(ui.shows("count the people who fix mistakes, not just the tokens (Learn 5)."))


CHAPTER = Chapter(
    id="5",
    title="Small vs. large models: how to choose",
    minutes=9,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(pick_sizes, comparison_table, speed_race, routing_predict, routing_calculator, fast_mode, full_cost),
)

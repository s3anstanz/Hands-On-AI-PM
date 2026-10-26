"""Chapter 6: "How do costs change as you scale?" (spec §6, Chapter 6)

Hands-on: price one request of a random product scenario, watch chat history
grow, find caching's break-even, pick caching or batch, play with a cost
calculator across every model, and compare providers' tokenizers. Every price
and ratio on screen comes from pricing.py through costs.py at run time.
"""

import dataclasses

from rich.markup import escape
from rich.table import Table
from rich.text import Text

import costs
import pricing
import tokens
import ui
from data import Scenario, Workload
from engine import Chapter, Ctx, LearnScreen, QuickCheck, make_rng, show_number
from lessons.ch2_tokens import PARAGRAPHS

REFERENCE = pricing.get("sonnet-5-5")  # the model every worked example uses
CLAUDE_5_5 = tuple(pricing.get(key) for key in ("opus-5-5", "sonnet-5-5", "haiku-5-5"))
WORKED_IN, WORKED_OUT = 2_000, 500
WORKED = costs.request_cost(REFERENCE, costs.Usage(input_tokens=WORKED_IN, output_tokens=WORKED_OUT))
WORKED_REQUESTS_PER_DAY = 20  # one user's requests, for the unit-economics example
HIDDEN_SYSTEM, HIDDEN_MESSAGES = 1_500, 100_000  # the hidden-tokens example


def times(value: float) -> str:
    """0.05 -> "0.05×", 1.25 -> "1.25×", 5.0 -> "5×"."""
    return f"{value:.3g}×"


def cache_read_by_model() -> str:
    """Models with the same cache-read multiplier share a group: "0.05× on Opus 5.5 and Sonnet 5.5, 0.1× on Haiku 5.5"."""
    groups: dict[str, list[str]] = {}
    for model in CLAUDE_5_5:
        groups.setdefault(times(model.cache_read / model.input), []).append(ui.model_label(model.display_name))
    parts = []
    for shown, names in groups.items():
        joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
        parts.append(f"{shown} on {joined}")
    return ", ".join(parts)


# The same on every Claude 5.5 model; tests/test_ch6.py fails if pricing.py ever makes that untrue.
OUTPUT_TIMES = times(REFERENCE.output / REFERENCE.input)
WRITE_5M_TIMES = times((REFERENCE.cache_write_5m or 0.0) / REFERENCE.input)
WRITE_1H_TIMES = times((REFERENCE.cache_write_1h or 0.0) / REFERENCE.input)
BATCH_OFF = f"{REFERENCE.batch_discount:.0%}"
RECOMMENDATION = "cache what repeats and batch what can wait"  # the advice the Recap and sample answer share

LEARN = (
    LearnScreen(
        title="How you're billed",
        body=(
            "Prices are per million tokens. **Input tokens** (what you send) and **output tokens** "
            "(what comes back) have separate prices.\n"
            f"On Claude models, an output token costs {OUTPUT_TIMES} as much as an input token."
        ),
        example=(
            f"One request on {REFERENCE.display_name}: {WORKED_IN:,} tokens in, {WORKED_OUT:,} out. "
            f"Input costs {costs.format_usd(WORKED.input)}, output {costs.format_usd(WORKED.output)}, "
            f"total {costs.format_usd(WORKED.total)}. Output is {WORKED_OUT / (WORKED_IN + WORKED_OUT):.0%} "
            f"of the tokens but {WORKED.output / WORKED.total:.0%} of the cost "
            f"(prices checked {pricing.LAST_CHECKED})."
        ),
        why_pm="Output tokens cost more, so answer length is one of your biggest cost levers.",
    ),
    LearnScreen(
        title="Hidden tokens",
        body=(
            "Every request also carries the **system prompt** (the product's standing instructions) "
            "and any **tool definitions** (descriptions of the tools the model may call).\n"
            "Users never see them, but you pay for them on every request."
        ),
        analogy="fine print stapled to every letter: nobody reads it, but it adds to the postage.",
        example=(
            f"A support bot with a {HIDDEN_SYSTEM:,}-token system prompt and {HIDDEN_MESSAGES:,} messages a day "
            f"sends {HIDDEN_SYSTEM * HIDDEN_MESSAGES // 1_000_000:,} million input tokens a day "
            "before anyone types a word."
        ),
        why_pm="Trimming a bloated system prompt is one of the cheapest savings available.",
    ),
    LearnScreen(
        title="Chat history is re-sent every turn",
        body=(
            "The model has no memory between requests (more in Chapter 7). "
            "To continue a chat, the app sends the whole conversation again.\n"
            "So turn 10 re-sends turns 1 to 9, plus the system prompt. "
            "Long chats cost far more than their length suggests."
        ),
        example="Turn 1 sends one message. Turn 10 sends nineteen: your ten and the model's nine replies.",
        why_pm="Plan for long chats: summarize old turns, cap the history, or cache it.",
    ),
    LearnScreen(
        title="Prompt caching",
        body=(
            "When the start of a prompt repeats across requests, the provider can keep it ready "
            "instead of reading it from scratch. That's **prompt caching**.\n"
            f"Reading from the cache costs a fraction of the input price: {cache_read_by_model()}.\n"
            f"Writing to the cache costs extra, once: {WRITE_5M_TIMES} the input price for a 5-minute cache, "
            f"{WRITE_1H_TIMES} for a 1-hour cache."
        ),
        analogy="a kitchen prepping the ingredients every dish uses.",
        why_pm="Cache the long system prompt or shared document that every request repeats.",
    ),
    LearnScreen(
        title="Batch",
        body=(
            "Work nobody is waiting on can go through the **batch** API. "
            "You send many requests at once and collect the answers later, within a day.\n"
            f"On Claude models, batch costs {BATCH_OFF} less, for input and output."
        ),
        example="Overnight summaries of yesterday's tickets, or tags for a backlog of documents.",
        why_pm="If no user is waiting on the answer, you're probably overpaying by not batching.",
    ),
    LearnScreen(
        title="Thinking tokens",
        body=(
            'Reasoning models can "think" before they answer, writing steps the user may never see. '
            "These **thinking tokens** are billed as output, at the output price.\n"
            "The thinking can be longer than the answer."
        ),
        example="A 300-token answer that took 2,000 tokens of thinking is billed as 2,300 output tokens.",
        why_pm="Higher effort (Chapter 3) means more thinking tokens. Use it where better answers pay for it.",
    ),
    LearnScreen(
        title="The temperature myth",
        body=(
            "Temperature doesn't change the price per token. Temperature 0 costs the same per token as 1.\n"
            "It affects the bill only if it changes how long the answers are."
        ),
        why_pm="When someone suggests lowering temperature to save money, point them to caching, batch and shorter answers.",
    ),
    LearnScreen(
        title="Unit economics",
        body=(
            "Work up from one request to cost per user, then per month. "
            "That chain is the feature's **unit economics**.\n"
            "The AI bill is part of **cost of goods sold** (COGS): what it costs to serve each customer. "
            "A CFO will ask for it."
        ),
        example=(
            f"{costs.format_usd(WORKED.total)} a request × {WORKED_REQUESTS_PER_DAY} requests a day × "
            f"{costs.DAYS_PER_MONTH} days = "
            f"{costs.format_usd(WORKED.total * WORKED_REQUESTS_PER_DAY * costs.DAYS_PER_MONTH)} "
            f"per user per month on {REFERENCE.display_name} (prices checked {pricing.LAST_CHECKED})."
        ),
        why_pm="Cost per user next to revenue per user shows whether the feature pays for itself.",
    ),
)

RECAP = (
    f"Input and output tokens have separate prices. On Claude models, an output token costs {OUTPUT_TIMES} as much as an input token.",
    "Hidden tokens add up: the system prompt and tool definitions ride along on every request.",
    "Chat history is re-sent every turn, so long chats cost far more than their length suggests.",
    f"The levers: {RECOMMENDATION}, route easy requests to a smaller model, and keep answers short.",
    "Always get to a number: cost per request, per user, per month.",
    "Temperature doesn't change the price per token.",
)

CHECKS = (
    QuickCheck(
        question="A request sends 1,000 tokens and gets 1,000 tokens back. Which half of the bill is bigger?",
        options=(
            "The input: prompts are the bigger part of the bill",
            "Neither: the same number of tokens costs the same",
            "The output",
        ),
        answer=2,
        explanation=(
            f"An output token costs {OUTPUT_TIMES} as much as an input token on Claude models, so equal counts "
            "don't mean equal cost. Input often dominates real bills only because prompts are much longer."
        ),
        screen=1,
    ),
    QuickCheck(
        question="Your AI bill doubled after launch. Which change cuts it without changing the model?",
        options=(
            "Cache the long system prompt every request repeats",
            "Lower the temperature to 0",
            "Raise max_tokens so answers finish properly",
        ),
        answer=0,
        explanation=(
            "Cached reads cost a fraction of normal input. Temperature doesn't change the price per token, "
            "and a higher max_tokens only allows longer, pricier answers."
        ),
        screen=4,
    ),
)

# --- Hands-on -------------------------------------------------------------------------------------

CHAT_TURNS = 10
PER_THOUSAND = 1_000  # per-request costs are fractions of a cent, so tables show 1,000 requests
SAME_WITHIN = 0.1  # caching and batch "save about the same" when within 10% of each other
LEVERS = ("Caching the repeated start", f"Batch ({BATCH_OFF} off, answers later)", "About the same")
HISTORY_STYLES = (("█", "magenta", "fixed text"), ("▒", "yellow", "earlier messages"), ("░", "green", "new message"))


def chosen_scenario(ctx: Ctx) -> tuple[Scenario, Workload]:
    """This run's scenario and numbers. Seeded on their own, so every step of the chapter sees the same ones."""
    rng = make_rng(ctx.seed, f"{ctx.chapter.id}/scenario", 0)
    scenario = rng.choice(ctx.data.scenarios)
    return scenario, scenario.draw(rng)


def _prices_checked(ctx: Ctx) -> None:
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")


def _model_notes(ctx: Ctx, models: list[pricing.Model]) -> None:
    """Each priced model's note from pricing.py (spec §8.1: shown wherever its price is)."""
    for model in models:
        if model.note:
            ctx.console.print(f"[dim]{escape(ui.model_label(model.display_name))}: {escape(model.note)}[/dim]")


def _cache_notes(ctx: Ctx, settings: dict[str, float], models: list[pricing.Model]) -> None:
    """Say where the cache discount was not applied, or could not be checked."""
    usage = calculator_usage(settings)
    skipped = [m for m in models if m.min_cache_tokens and 0 < usage.cache_read_tokens < m.min_cache_tokens]
    if skipped:
        names = ", ".join(escape(ui.model_label(m.display_name)) for m in skipped)
        ctx.console.print(
            f"[dim]Cached part is under the minimum cacheable length, so it's billed as regular input: {names}.[/dim]"
        )
    if any(m.min_cache_tokens is None for m in models):
        ctx.console.print("[dim]Caching minimums aren't modeled for OpenAI and Google models.[/dim]")


def scenario_label(scenario: Scenario) -> str:
    """The scenario's name, marked so its made-up usage numbers never pass for measurements."""
    return f"{escape(scenario.name)} (illustrative usage)"


def verdict(guess: float, actual: float, unit: str = "") -> str:
    """ "You guessed 10×; actual 14×; off by 4×." actual is the figure as shown, already rounded."""
    shown = f"You guessed {show_number(guess)}{unit}; actual {show_number(actual)}{unit}"
    off = abs(guess - actual)
    return f"{shown}: spot on." if off == 0 else f"{shown}; off by {show_number(off)}{unit}."


def input_vs_output(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    cost = costs.request_cost(REFERENCE, costs.Usage(work.input_tokens, work.output_tokens))
    ctx.console.print("[bold]Input vs. output[/bold]")
    ctx.console.print(
        f"Your scenario this run: [bold]{escape(scenario.name)}[/bold]. {escape(scenario.pitch)} "
        "The usage numbers are illustrative; the prices are real."
    )
    ctx.console.print(
        f"A typical request: {work.input_tokens:,} tokens in, {work.output_tokens:,} out. "
        f"Cost of {PER_THOUSAND:,} of them on {REFERENCE.display_name}:\n"
    )
    table = ui.compact_table("", "Tokens", "Per 1M", f"Per {PER_THOUSAND:,}")
    parts = (round(cost.input * PER_THOUSAND, 2), round(cost.output * PER_THOUSAND, 2))  # round once, then add
    for name, count, rate, part in (
        ("Input", work.input_tokens, REFERENCE.input, parts[0]),
        ("Output", work.output_tokens, REFERENCE.output, parts[1]),
    ):
        table.add_row(name, f"{count:,}", costs.format_usd(rate), costs.format_usd(part))
    table.add_row("Total", f"{work.input_tokens + work.output_tokens:,}", "", costs.format_usd(sum(parts)))
    ctx.console.print(table)
    _prices_checked(ctx)
    token_share = work.output_tokens / (work.input_tokens + work.output_tokens)
    ctx.console.print(f"Output is {token_share:.0%} of the tokens and {parts[1] / sum(parts):.0%} of the cost.")
    ctx.console.print(
        ui.shows(
            f"an output token costs {OUTPUT_TIMES} as much as an input token, so answer length moves the bill "
            "more than its share of tokens suggests (Learn 1)."
        )
    )


def _history_bars(ctx: Ctx, system: int, message: int) -> Table:
    sent = costs.chat_input_per_turn(CHAT_TURNS, system, message)
    label_width = len(f"Turn {CHAT_TURNS}")
    shown_width = len(f"{sent[-1]:,}")
    bar_width = max(10, min(40, ctx.console.width - label_width - shown_width - 2))
    table = Table.grid(padding=(0, 1))
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(justify="right", no_wrap=True)
    for turn, total in enumerate(sent, 1):
        ends = [system, total - message, total]  # system | earlier messages | new message
        cells = [round(end / sent[-1] * bar_width) for end in ends]
        bar = Text()
        start = 0
        for (char, style, _), cell in zip(HISTORY_STYLES, cells, strict=True):
            bar.append(char * (cell - start), style=style)
            start = cell
        table.add_row(f"Turn {turn}", bar, f"{total:,}")
    return table


def history_growth(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    system, message = work.system_tokens, work.output_tokens
    ctx.console.print("[bold]Chat history adds up[/bold]")
    ctx.console.print(
        f"{scenario_label(scenario)}: {system:,} tokens of fixed text (system prompt and the like), "
        f"and about {message:,} tokens per message, from the user or the model."
    )
    guess = ctx.ask_number(
        f"Your prediction: a {CHAT_TURNS}-turn chat costs how many times a single-turn chat?",
        "guess_chat",
        1,
        100,
        integer=True,
    )
    ctx.console.print(f"\nInput tokens sent on each turn of a {CHAT_TURNS}-turn chat:")
    ctx.console.print(_history_bars(ctx, system, message))
    ctx.console.print("[dim]" + "  ".join(f"{char} {name}" for char, _, name in HISTORY_STYLES) + "[/dim]")
    one = round(costs.chat_cost(REFERENCE, 1, system, message) * PER_THOUSAND, 2)
    ten = round(costs.chat_cost(REFERENCE, CHAT_TURNS, system, message) * PER_THOUSAND, 2)
    twenty = round(costs.chat_cost(REFERENCE, 2 * CHAT_TURNS, system, message) * PER_THOUSAND, 2)
    ratio = round(ten / one)  # from the figures shown, so the two dollar amounts and the ratio agree
    ctx.console.print(
        f"On {REFERENCE.display_name}, {PER_THOUSAND:,} chats of {CHAT_TURNS} turns cost "
        f"{costs.format_usd(ten)}, and {PER_THOUSAND:,} single-turn chats cost "
        f"{costs.format_usd(one)}. That's {ratio}× the cost for {CHAT_TURNS}× the messages."
    )
    ctx.console.print(verdict(guess, ratio, "×"))
    ctx.console.print(
        f"Twice as long ({2 * CHAT_TURNS} turns) costs {twenty / ten:.1f}× as much as {CHAT_TURNS} turns, not 2×. "
        "Each turn re-sends everything before it, so cost grows faster than length."
    )
    _prices_checked(ctx)
    ctx.console.print(ui.shows("every turn re-sends the whole chat, so cost grows faster than turns (Learn 3)."))


def cache_break_even(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    ctx.console.print("[bold]When does caching pay off?[/bold]")
    ctx.console.print(
        "Writing to the cache costs more than reading the same tokens normally, so caching pays off "
        "only after enough reuse. The fewest uses where caching wins:"
    )
    table = ui.compact_table("Model", "5-min cache", "1-hour cache")
    for model in CLAUDE_5_5:
        table.add_row(
            ui.model_label(model.display_name),
            f"{costs.cache_break_even_uses(model, '5m')} uses",
            f"{costs.cache_break_even_uses(model, '1h')} uses",
        )
    ctx.console.print(table)
    system, per_day = work.system_tokens, work.requests_per_day
    uncached = costs.request_cost(REFERENCE, costs.Usage(system, 0)).total * per_day
    write = costs.request_cost(REFERENCE, costs.Usage(0, 0, cache_write_tokens=system)).total
    read = costs.request_cost(REFERENCE, costs.Usage(0, 0, cache_read_tokens=system)).total
    cached = write + read * (per_day - 1)
    ctx.console.print(
        f"{scenario_label(scenario)}: the {system:,} tokens every request repeats "
        f"go out {per_day:,} times a day. "
        f"On {REFERENCE.display_name} that costs {costs.format_usd(uncached)} a day uncached and "
        f"{costs.format_usd(cached)} cached: one write, then reads, if steady traffic keeps the cache warm."
    )
    _prices_checked(ctx)
    ctx.console.print(
        ui.shows(
            f"a 5-minute cache pays for its write after {costs.cache_break_even_uses(REFERENCE, '5m')} uses, "
            "so cache any prompt start that every request repeats (Learn 4)."
        )
    )


def lever_costs(work: Workload) -> tuple[float, float, float]:
    """Monthly cost on the reference model, to the cent: as is, with the repeated start cached, and batched.

    Rounded here, once, so the savings on screen are the differences of the figures on screen.
    """
    per_day = work.requests_per_day
    full = costs.Usage(work.input_tokens, work.output_tokens)
    cached = costs.Usage(
        work.input_tokens - work.system_tokens, work.output_tokens, cache_read_tokens=work.system_tokens
    )
    batched = dataclasses.replace(full, batch=True)
    return (
        round(costs.monthly_cost(REFERENCE, full, per_day), 2),
        round(costs.monthly_cost(REFERENCE, cached, per_day), 2),
        round(costs.monthly_cost(REFERENCE, batched, per_day), 2),
    )


def lever_verdict(work: Workload) -> int:
    """Index into LEVERS: which saves more on the reference model, or about the same."""
    full, cached, batched = lever_costs(work)
    by_caching, by_batch = full - cached, full - batched
    if abs(by_caching - by_batch) <= SAME_WITHIN * max(by_caching, by_batch):
        return 2
    return 0 if by_caching > by_batch else 1


def caching_or_batch(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    ctx.console.print("[bold]Caching or batch?[/bold]")
    ctx.console.print(
        f"{scenario_label(scenario)}: {work.requests_per_day:,} requests a day, "
        f"{work.input_tokens:,} tokens in (the first {work.system_tokens:,} the same every time), "
        f"{work.output_tokens:,} out."
    )
    for i, option in enumerate(LEVERS, 1):
        ctx.console.print(f"  {i}. {escape(option)}")
    pick = ctx.ask_choice("Your prediction: which saves more here?", len(LEVERS), key="guess_lever")
    full, cached, batched = lever_costs(work)
    rows = [("No discount", full), ("Caching", cached), ("Batch", batched)]
    ctx.console.print(f"\nPer month on {REFERENCE.display_name}:")
    ctx.console.print(ui.value_bars([(name, cost, costs.format_usd(cost)) for name, cost in rows], ctx.console.width))
    _prices_checked(ctx)
    answer = lever_verdict(work)
    ctx.console.print(
        f"Caching saves {costs.format_usd(full - cached)} a month; batch saves {costs.format_usd(full - batched)}."
    )
    if pick == answer:
        said = "Right."
    elif answer == len(LEVERS) - 1:  # "about the same": either lever was nearly right
        said = f"Close: the two are within {SAME_WITHIN:.0%} of each other."
    else:
        said = "Not quite."
    ctx.console.print(f"You predicted {LEVERS[pick].lower()}; actual: {LEVERS[answer].lower()}. {said}")
    ctx.console.print(
        ui.shows(
            f"caching pays most when a big shared start repeats. Batch takes {BATCH_OFF} off everything, "
            "but only for work nobody is waiting on. You can use both (Learn 4 and 5)."
        )
    )


FIELDS = (  # (state name, label, low, high)
    ("requests", "Requests per day", 1, 10_000_000),
    ("input", "Input tokens per request", 1, 1_000_000),
    ("output", "Output tokens per request", 1, 128_000),
    ("cache_hit", "Cache-hit % of input", 0, 100),
    ("batch", "Batch", 0, 1),
    ("thinking", "Thinking tokens per request", 0, 128_000),
)


def calculator_defaults(work: Workload) -> dict[str, float]:
    return {
        "requests": work.requests_per_day,
        "input": work.input_tokens,
        "output": work.output_tokens,
        "cache_hit": round(100 * work.system_tokens / work.input_tokens),
        "batch": 0,
        "thinking": 0,
    }


def calculator_usage(settings: dict[str, float]) -> costs.Usage:
    total_in = int(settings["input"])
    cached = round(total_in * settings["cache_hit"] / 100)
    return costs.Usage(
        input_tokens=total_in - cached,
        output_tokens=int(settings["output"]),
        cache_read_tokens=cached,
        thinking_tokens=int(settings["thinking"]),
        batch=bool(settings["batch"]),
    )


def calculator_rows(settings: dict[str, float]) -> list[tuple[pricing.Model, float | None, bool]]:
    """(model, monthly cost or None when the request doesn't fit the model, priced without batch)."""
    usage = calculator_usage(settings)
    rows: list[tuple[pricing.Model, float | None, bool]] = []
    for model in pricing.MODELS.values():
        answer = usage.output_tokens + usage.thinking_tokens
        if usage.prompt_tokens + answer > model.context_window or answer > model.max_output:
            rows.append((model, None, False))
            continue
        no_batch = usage.batch and not costs.supports_batch(model)
        priced = costs.apply_cache_minimum(model, dataclasses.replace(usage, batch=False) if no_batch else usage)
        rows.append((model, costs.monthly_cost(model, priced, int(settings["requests"])), no_batch))
    return rows


def calculator_caption(rows: list[tuple[pricing.Model, float | None, bool]]) -> str:
    priced = [monthly for _, monthly, _ in rows if monthly]
    if len(priced) < 2:
        return "a request this long doesn't fit most models' limits; Chapter 7 is about that limit."
    spread = round(max(priced) / min(priced))
    return (
        f"the same workload costs {spread:,}× as much on the priciest model as on the cheapest, "
        "so model choice (Chapter 5) is a cost lever too."
    )


def _field_value(name: str, value: float) -> str:
    if name == "batch":
        return "on" if value else "off"
    if name == "cache_hit":
        return f"{show_number(value)}%"
    return f"{int(value):,}"


def _show_calculator(ctx: Ctx, settings: dict[str, float], users: int) -> None:
    fields = Table.grid(padding=(0, 1))
    fields.add_column(no_wrap=True)
    fields.add_column(justify="right", no_wrap=True)
    for i, (name, label, _, _) in enumerate(FIELDS, 1):
        fields.add_row(f"{i}. {label}", _field_value(name, settings[name]))
    ctx.console.print(fields)
    rows = calculator_rows(settings)
    bars = []
    for model, monthly, no_batch in rows:
        label = ui.model_label(model.display_name) + ("*" if no_batch else "")
        bars.append((label, monthly or 0.0, costs.format_usd(monthly) if monthly is not None else "too long"))
    ctx.console.print(f"\nPer month ({costs.DAYS_PER_MONTH} days):")
    ctx.console.print(ui.value_bars(bars, ctx.console.width))
    if any(no_batch for _, _, no_batch in rows):
        ctx.console.print("[dim]* No batch price in pricing.py for this model, so it's shown at full price.[/dim]")
    if any(monthly is None for _, monthly, _ in rows):
        ctx.console.print("[dim]too long: more tokens than this model can take in one request (Chapter 7).[/dim]")
    _cache_notes(ctx, settings, [model for model, monthly, _ in rows if monthly is not None])
    _model_notes(ctx, [model for model, monthly, _ in rows if monthly is not None])
    reference = next(monthly for model, monthly, _ in rows if model is REFERENCE)
    if reference is not None:
        per_request = reference / (settings["requests"] * costs.DAYS_PER_MONTH)
        ctx.console.print(
            f"On {REFERENCE.display_name}: {costs.format_usd(per_request * PER_THOUSAND)} per {PER_THOUSAND:,} requests, "
            f"{costs.format_usd(reference / users)} per user per month ({users:,} daily users)."
        )
    _prices_checked(ctx)


def calculator(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    for name, value in calculator_defaults(work).items():
        ctx.state.setdefault(f"calc_{name}", value)
    ctx.console.print("[bold]Cost calculator[/bold]")
    ctx.console.print(
        f"Starting numbers: {scenario_label(scenario)}. Change any line and every model's bill updates. "
        "Cache-hit % starts at the share of input that every request repeats."
    )
    while True:
        settings = {name: ctx.state[f"calc_{name}"] for name, *_ in FIELDS}
        _show_calculator(ctx, settings, work.users)
        line = ctx.ask_number_or_skip("Change which line?", "calc_line", 1, len(FIELDS), integer=True)
        if line is None:
            ctx.console.print(ui.shows(calculator_caption(calculator_rows(settings))))
            return
        name, label, low, high = FIELDS[int(line) - 1]
        if name == "batch":
            ctx.state["calc_batch"] = 0 if ctx.state["calc_batch"] else 1
            continue
        ctx.ask_number(label, f"calc_{name}", low, high, integer=name != "cache_hit")


CROSSING = ("sonnet-5-5", "haiku-5-5", "gpt-6-astra", "gpt-6-luna", "gemini-3-1-pro", "gemini-3-8-flash")


def crossing_providers(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    sample = " ".join(PARAGRAPHS)
    openai, label = tokens.openai_count(sample)
    low, high = tokens.claude_estimate(sample)
    official = ctx.live.count_tokens(sample, pricing.GRADER_MODEL) if ctx.live is not None else None
    ctx.console.print("[bold]Crossing providers[/bold]")
    if ctx.live is not None and official is None:
        ctx.console.print(
            f"[yellow]Official Claude count unavailable: {escape(ctx.live.last_error)}. Using the estimate.[/yellow]"
        )
    claude = official if official is not None else round((low + high) / 2)
    source = "official, from count_tokens" if official is not None else tokens.CLAUDE_ESTIMATE_LABEL
    ratio = openai / claude
    ctx.console.print(
        f"The calculator used one token count for every model, but tokenizers differ. "
        f"All six of Chapter 2's sample paragraphs, {tokens.word_count(sample)} words, are {openai:,} tokens on "
        f"{escape(label)} and about {claude:,} on Claude ({escape(source)})."
    )
    ctx.console.print(
        f"{scenario_label(scenario)}: {work.input_tokens:,} tokens in and {work.output_tokens:,} out per request "
        f"on Claude are about {round(work.input_tokens * ratio):,} and {round(work.output_tokens * ratio):,} "
        "on OpenAI's tokenizer."
    )
    ctx.console.print(
        "\nThe same requests per month, with no caching or batch. Google's tokenizer isn't bundled, "
        "so the Gemini rows (†) use the OpenAI count:"
    )
    table = ui.compact_table("Model", "Tokens", "Per month")
    for key in CROSSING:
        model = pricing.get(key)
        scale = 1.0 if model.provider == "anthropic" else ratio
        usage = costs.Usage(round(work.input_tokens * scale), round(work.output_tokens * scale))
        mark = "†" if model.provider == "google" else ""
        table.add_row(
            escape(ui.model_label(model.display_name)) + mark,
            f"{usage.input_tokens:,}",
            costs.format_usd(costs.monthly_cost(model, usage, work.requests_per_day)),
        )
    ctx.console.print(table)
    ctx.console.print("[dim]† OpenAI's count, as a stand-in for Google's.[/dim]")
    _model_notes(ctx, [pricing.get(key) for key in CROSSING])
    _prices_checked(ctx)
    ctx.console.print(
        ui.shows(
            "tokenizers count the same text differently, so compare the cost of your own text, "
            "not the price per token (Chapter 2)."
        )
    )


CHAPTER = Chapter(
    id="6",
    title="Cost at scale: what drives the bill",
    minutes=10,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(input_vs_output, history_growth, cache_break_even, caching_or_batch, calculator, crossing_providers),
    figures={"output_times": OUTPUT_TIMES},
)

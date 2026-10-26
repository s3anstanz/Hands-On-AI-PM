"""Chapter 8: Design an AI feature, "Design an AI feature for X." (spec §6, Chapter 8)

Hands-on: a random scenario with seeded usage numbers, your design choices,
then what the design costs, how fast it starts and how likely it is to make
things up. After grading: three reviewer follow-ups and the evals teaser.
Costs come from costs.py; speeds are illustrative and labeled so.
"""

from dataclasses import dataclass

from rich.markup import escape

import costs
import pricing
import ui
from data import FollowUp, Scenario, Workload
from engine import Chapter, Ctx, LearnScreen, Step, make_rng
from lessons.ch5_model_choice import OPUS_FIRST_TOKEN_SECONDS
from lessons.ch6_cost import chosen_scenario, scenario_label

MODEL_CHOICES = ("haiku-5-5", "sonnet-5-5", "opus-5-5")  # small to large; their cache and batch prices are modeled
EFFORTS = ("low", "medium", "high")
TEMPERATURES = (0.0, 0.5, 1.0)  # offered only for a model that accepts temperature
HIGH_TEMPERATURE = 0.7  # Chapter 3: "higher (0.7 to 1)" is the creative range
CONTEXTS = ("none", "paste", "fetch")
SAVINGS = ("neither", "caching", "batch", "both")
FETCHED_TOKENS = 3_000  # fetch what's relevant: about three pages of the reference material
FOLLOWUPS = 3  # two from the scenario, one from the chapter's general pool

# Illustrative, not measured (labeled on screen).
CACHE_HIT_RATE = 0.9  # share of requests that find the fixed start of the prompt already cached
THINKING_PER_ANSWER_TOKEN = {"low": 0.0, "medium": 1.0, "high": 3.0}
# Time to first token at medium effort (the default on Opus 5.5 and Haiku 5.5), before reading the prompt.
# The large model is Chapter 5's illustrative Opus 5.5, imported so the two chapters can't disagree;
# the others stay inside Chapter 5's race (0.5 to 4 s to start).
FIRST_TOKEN_AT_MEDIUM_SECONDS = {"small": 0.5, "medium": 1.0, "large": OPUS_FIRST_TOKEN_SECONDS}
EFFORT_WAIT = {"low": 0.5, "medium": 1.0, "high": 2.0}  # more effort, more thinking before the first token
READING_TOKENS_PER_SECOND = 50_000  # uncached prompt tokens the model reads before it can start
WAIT_OK_SECONDS = 2.0
WAIT_TOO_LONG_SECONDS = 10.0

# The Learn worked example. It must not be one of the scenarios in data/scenarios.toml.
EXAMPLE_MODEL = "haiku-5-5"
EXAMPLE_HOTELS = 50_000
EXAMPLE_USAGE = costs.Usage(input_tokens=6_500, output_tokens=120, batch=True)  # 6,000 of reviews + instructions
EXAMPLE_REQUESTS_PER_DAY = round(EXAMPLE_HOTELS / 7)  # one summary per hotel per week


def example_monthly_cost() -> float:
    return costs.monthly_cost(pricing.get(EXAMPLE_MODEL), EXAMPLE_USAGE, EXAMPLE_REQUESTS_PER_DAY)


LEARN = (
    LearnScreen(
        title="What a strong design covers",
        body=(
            "A strong design isn't a list of facts. It covers five things: "
            "structure, focus on the user, named tradeoffs, real numbers, "
            "and a decision you commit to.\n"
            '"It depends" is a fine start if you say on what, then decide.'
        ),
        analogy="a contractor's quote. It says what you need, what it costs and what they'd do, not every option.",
        why_pm="Real design reviews use this same structure.",
    ),
    LearnScreen(
        title="The structure: 1 to 5",
        body=(
            "1. The user and the **job to be done**: who it's for and what has to go right.\n"
            "2. Requirements: quality, speed, cost, and how bad a mistake would be.\n"
            "3. Model: the smallest one that meets the quality bar, and why.\n"
            "4. Settings: temperature or effort, matched to the task.\n"
            "5. Context: what the model must see, pasted or fetched."
        ),
        why_pm="Reviewers listen first for whether you start from the user, not the model.",
    ),
    LearnScreen(
        title="The structure: 6 to 9",
        body=(
            "6. Cost: users × requests × tokens × price, per month and per user.\n"
            "7. Risks and safeguards: what goes wrong (often a confident wrong answer) and what catches it.\n"
            "8. Recommendation: commit. \"I'd use X because Y. I'd switch to Z if W.\"\n"
            "9. Measurement: **evals** before launch, live metrics after."
        ),
        why_pm="End on a number, a decision and a check. That's what makes it a PM answer.",
    ),
    LearnScreen(
        title="A worked example",
        body=(
            f"A travel site wants a three-line summary of guest reviews on each of its {EXAMPLE_HOTELS:,} hotel pages.\n"
            "1 and 2. Travelers decide fast. Summaries must match the reviews and be cheap. Nobody waits: they run weekly.\n"
            "3 and 4. Haiku 5.5, because summarizing is easy work. Low effort.\n"
            "5. Paste that hotel's reviews: about 6,000 tokens.\n"
            f"6. Batch, once a week: about {costs.format_usd(example_monthly_cost())} a month "
            f"(prices checked {pricing.LAST_CHECKED}).\n"
            "7. Risk: an invented complaint. Safeguards: each point quotes a review, and readers can flag a summary.\n"
            "8. Haiku in batch; switch to Sonnet if the spot checks fail.\n"
            "9. Each week, check 100 summaries against their reviews and watch the flag rate."
        ),
        why_pm="Nine short lines, one number, one decision: aim for that shape.",
    ),
)

RECAP = (
    "The user and the job to be done.",
    "Requirements: quality, speed, cost and risk.",
    "Model choice, with a reason.",
    "Settings: temperature or effort, with a reason.",
    "Context: paste everything or fetch what's relevant.",
    "Cost: a number per month and per user.",
    "Risks and safeguards.",
    "Recommendation: commit, and say what would change it.",
    "Measurement: evals before launch, live metrics after.",
)


@dataclass(frozen=True)
class Design:
    model: pricing.Model
    effort: str | None  # models with a fixed temperature
    temperature: float | None  # models that accept one
    context: str  # one of CONTEXTS
    caching: bool
    batch: bool


def chosen_design(ctx: Ctx) -> Design:
    model = pricing.get(MODEL_CHOICES[ctx.state["model"]])
    saving = SAVINGS[ctx.state["saving"]]
    return Design(
        model=model,
        effort=None if model.accepts_temperature else EFFORTS[ctx.state["effort"]],
        temperature=TEMPERATURES[ctx.state["temperature"]] if model.accepts_temperature else None,
        context=CONTEXTS[ctx.state["context"]],
        caching=saving in ("caching", "both"),
        batch=saving in ("batch", "both"),
    )


def usage_for(work: Workload, design: Design) -> costs.Usage:
    """One request. Only the system prompt is the fixed start that caching reuses; documents, pasted or fetched,
    are reference material that can change every request, so they are always uncached input."""
    docs = {"none": 0, "paste": work.docs_tokens, "fetch": min(FETCHED_TOKENS, work.docs_tokens)}[design.context]
    fixed = work.system_tokens
    varying = work.input_tokens - work.system_tokens + docs
    cache_read = round(fixed * CACHE_HIT_RATE) if design.caching else 0
    cache_write = fixed - cache_read if design.caching else 0
    thinking = round(work.output_tokens * THINKING_PER_ANSWER_TOKEN[design.effort]) if design.effort else 0
    return costs.Usage(
        input_tokens=varying + (0 if design.caching else fixed),
        output_tokens=work.output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        thinking_tokens=thinking,
        batch=design.batch,
    )


def first_token_seconds(model: pricing.Model, effort: str | None, usage: costs.Usage) -> float:
    """Illustrative: the model's start at medium effort, scaled by effort, plus reading the uncached prompt.
    A model that takes temperature instead of effort starts as at medium."""
    reading = (usage.input_tokens + usage.cache_write_tokens) / READING_TOKENS_PER_SECOND
    return FIRST_TOKEN_AT_MEDIUM_SECONDS[model.size] * EFFORT_WAIT[effort or "medium"] + reading


def hallucination_risk(needs_facts: bool, context: str, high_temperature: bool, domain: str) -> str:
    """Spec §6: high when the task needs facts and context is missing or temperature is high;
    one level higher for medical and legal (a mistake there can hurt someone)."""
    levels = ("low", "medium", "high")
    level = 2 if needs_facts and (context == "none" or high_temperature) else 0
    if domain in ("medical", "legal"):
        level = min(level + 1, 2)
    return levels[level]


def _generated(usage: costs.Usage) -> int:
    return usage.output_tokens + usage.thinking_tokens


def fits(model: pricing.Model, usage: costs.Usage) -> bool:
    """The prompt and everything generated share the context window; the answer alone has its own limit."""
    return usage.prompt_tokens + _generated(usage) <= model.context_window and _generated(usage) <= model.max_output


def _batch_discount() -> float:
    return max(pricing.get(key).batch_discount for key in MODEL_CHOICES)


def _describe(design: Design) -> str:
    setting = f"effort {design.effort}" if design.effort else f"temperature {design.temperature:g}"
    context = {"none": "no documents", "paste": "paste everything", "fetch": "fetch what's relevant"}[design.context]
    saving = [name for name, on in (("caching", design.caching), ("batch", design.batch)) if on] or [
        "no caching or batch"
    ]
    return " · ".join([design.model.display_name, setting, context, *saving])


def brief(ctx: Ctx) -> None:
    s, work = chosen_scenario(ctx)
    ctx.console.print(f"[bold]Design an AI feature for: {scenario_label(s)}[/bold]")
    ctx.console.print(f"{escape(s.pitch)}\n")
    ctx.console.print(
        f"Users: {work.users:,} a day, {work.requests_per_user:,} requests each "
        f"({work.requests_per_day:,} requests a day)."
    )
    ctx.console.print(
        f"Each request: about {work.input_tokens:,} tokens in ({work.system_tokens:,} of them a fixed "
        f"system prompt) and {work.output_tokens:,} out."
    )
    ctx.console.print(f"Reference material: {work.docs_tokens:,} tokens of documents the answers may need.")
    ctx.console.print(
        "Someone is waiting for each answer."
        if s.latency == "interactive"
        else "It runs in the background: nobody is waiting for each answer."
    )
    ctx.console.print(
        "Answers have to match facts the model must be given."
        if s.needs_facts
        else "It's creative work: there's no single right answer."
    )
    if s.domain != "general":
        who = "a patient" if s.domain == "medical" else "a client"
        ctx.console.print(f"[bold]High stakes:[/bold] a wrong answer can hurt {who}.")
    ctx.console.print("\n[dim]Take a moment: who is the user, and what has to go right? Then make your choices.[/dim]")


def _options(ctx: Ctx, title: str, options: list[str]) -> None:
    ctx.console.print(f"\n[bold]{escape(title)}[/bold]")
    for i, option in enumerate(options, 1):
        ctx.console.print(f"  {i}. {escape(option)}")


def design(ctx: Ctx) -> None:
    s, work = chosen_scenario(ctx)
    ctx.console.print(f"[bold]Your design[/bold] for the {escape(s.name)}")
    models = [pricing.get(key) for key in MODEL_CHOICES]
    _options(
        ctx,
        "Model",
        [
            f"{m.display_name} ({m.size}): {costs.format_usd(m.input)} in, {costs.format_usd(m.output)} out per 1M tokens"
            for m in models
        ],
    )
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")
    model = models[ctx.ask_choice("Model", len(models), key="model")]
    if model.accepts_temperature:
        _options(ctx, "Temperature", [f"{t:g}" for t in TEMPERATURES])
        ctx.ask_choice("Temperature", len(TEMPERATURES), key="temperature")
    else:
        ctx.console.print(
            f"\n{escape(model.display_name)} doesn't let you change temperature (Chapter 3). "
            "You steer it with effort: how much it thinks before answering."
        )
        _options(ctx, "Effort", list(EFFORTS))
        ctx.ask_choice("Effort", len(EFFORTS), key="effort")
    _options(
        ctx,
        "Context",
        [
            "None: rely on what the model already knows",
            f"Paste everything: all {work.docs_tokens:,} tokens, every request",
            f"Fetch what's relevant: about {min(FETCHED_TOKENS, work.docs_tokens):,} tokens a request",
        ],
    )
    ctx.ask_choice("Context", len(CONTEXTS), key="context")
    _options(
        ctx,
        "Caching and batch",
        [
            "Neither",
            "Prompt caching: reuse the fixed start of the prompt",
            f"Batch: {_batch_discount():.0%} off, answers come back later",
            "Both",
        ],
    )
    ctx.ask_choice("Caching and batch", len(SAVINGS), key="saving")


def _wait_verdict(seconds: float, interactive: bool) -> str:
    if not interactive:
        return f"Nobody is waiting, so batch would take {_batch_discount():.0%} off."
    if seconds <= WAIT_OK_SECONDS:
        return "Fine for someone waiting."
    if seconds <= WAIT_TOO_LONG_SECONDS:
        return "Users will notice the wait: stream the answer and show progress."
    return "Too slow for someone waiting: try a smaller model, less effort or a shorter prompt."


def _risk_reason(scenario: Scenario, choice: Design, high_temperature: bool) -> str:
    if not scenario.needs_facts:
        reason = "Creative work has no single fact to get wrong, but check any claims before they go out."
    elif choice.context == "none":
        reason = "It needs facts it wasn't given, so it will fill the gaps with likely-sounding text."
    elif high_temperature:
        reason = "A high temperature picks less likely words more often, and here a wrong word is a wrong fact."
    elif choice.context == "fetch":
        reason = "The facts are in the prompt, as long as the search finds them."
    else:
        reason = "The facts are in the prompt, though the middle of a long prompt gets less attention."
    if scenario.domain != "general":
        reviewer = "a clinician" if scenario.domain == "medical" else "a lawyer"
        reason += f" Raised a level for the stakes: have {reviewer} review it."
    return reason


def outcome(ctx: Ctx) -> None:
    (s, work), choice = chosen_scenario(ctx), chosen_design(ctx)
    usage = usage_for(work, choice)
    ctx.console.print(f"[bold]Your design:[/bold] {escape(_describe(choice))}\n")
    if not fits(choice.model, usage):
        total = usage.prompt_tokens + _generated(usage)
        if total > choice.model.context_window:
            ctx.console.print(
                f"[yellow]Doesn't fit: {total:,} tokens a request, prompt and answer, is over the "
                f"{choice.model.context_window:,}-token window.[/yellow]"
            )
            ctx.console.print("[yellow]Fetch what's relevant instead.[/yellow]")
        else:
            ctx.console.print(
                f"[yellow]Doesn't fit: an answer of {_generated(usage):,} tokens is more than the "
                f"{choice.model.max_output:,}-token output limit.[/yellow]"
            )
            ctx.console.print("[yellow]Ask for a shorter answer or less effort.[/yellow]")
    else:
        monthly = costs.monthly_cost(choice.model, usage, work.requests_per_day)
        ctx.console.print(
            f"[bold]Monthly cost:[/bold] {costs.format_usd(monthly)}, about "
            f"{costs.format_usd(monthly / work.users)} per user a month (prices checked {pricing.LAST_CHECKED})."
        )
        if any(usage.prompt_tokens > tier.above for tier in choice.model.tiers):
            ctx.console.print(f"[dim]{escape(choice.model.note)}[/dim]")
    interactive = s.latency == "interactive"
    if choice.batch:
        ctx.console.print("[bold]Speed:[/bold] batch answers come back within hours, not seconds.")
        if interactive:
            ctx.console.print("[yellow]Batch doesn't fit here: someone is waiting for each answer.[/yellow]")
        else:
            ctx.console.print("[green]Nobody is waiting, so batch is the right call.[/green]")
    else:
        seconds = first_token_seconds(choice.model, choice.effort, usage)
        ctx.console.print(
            f"[bold]Time to first token:[/bold] about {seconds:.1f} s (illustrative). {_wait_verdict(seconds, interactive)}"
        )
    high_temperature = choice.temperature is not None and choice.temperature >= HIGH_TEMPERATURE
    risk = hallucination_risk(s.needs_facts, choice.context, high_temperature, s.domain)
    ctx.console.print(
        f"[bold]Hallucination risk:[/bold] {risk.upper()}. {escape(_risk_reason(s, choice, high_temperature))}"
    )
    ctx.console.print("\n[bold]Same choices, each model[/bold] (← yours)")
    table = ui.compact_table("Model", "Per month", "First token")
    for key in MODEL_CHOICES:
        model = pricing.get(key)
        other = usage_for(work, Design(model, choice.effort, None, choice.context, choice.caching, choice.batch))
        if not fits(model, other):
            cost = "doesn't fit"
        else:
            cost = costs.format_usd(costs.monthly_cost(model, other, work.requests_per_day))
        start = "batch" if choice.batch else f"{first_token_seconds(model, choice.effort, other):.1f} s"
        mark = " ←" if model.key == choice.model.key else ""
        table.add_row(escape(ui.model_label(model.display_name)) + mark, cost, start)
    ctx.console.print(table)
    ctx.console.print(
        "[dim]Speeds and the thinking-token and cache-hit numbers are illustrative; prices are real.[/dim]"
    )
    ctx.console.print(
        ui.shows("model, effort, context and caching trade cost, speed and risk against each other (Learn 2 and 3).")
    )
    ctx.console.print(
        f"\nType b to change a choice. Next, commit: your recommendation for the {escape(s.name)}, "
        "with your reasons and the numbers above."
    )


def chosen_followups(ctx: Ctx) -> list[FollowUp]:
    """Two of the scenario's own follow-ups, then one of the chapter's general ones."""
    rng = make_rng(ctx.seed, "8/followups", 0)
    scenario, _ = chosen_scenario(ctx)
    return [*rng.sample(scenario.followups, FOLLOWUPS - 1), rng.choice(ctx.rubric.followups)]


def _followup_step(number: int) -> Step:
    def step(ctx: Ctx) -> None:
        followup = chosen_followups(ctx)[number - 1]
        ctx.console.print(f"[bold]Follow-up {number} of {FOLLOWUPS}[/bold]")
        ctx.console.print(f"[dim]Your design: {escape(_describe(chosen_design(ctx)))}[/dim]\n")
        ctx.console.print(f"[bold]Reviewer:[/bold] {escape(followup.question)}")
        ctx.ask_multiline("Your reply", f"followup{number}")
        ctx.console.print(f"[bold magenta]A strong answer mentions:[/bold magenta] {escape(followup.strong)}")

    return step


def evals_teaser(ctx: Ctx) -> None:
    ctx.console.print("[bold]One last question[/bold]")
    ctx.console.print("[bold]Reviewer:[/bold] How would you prove the cheaper model is good enough?")
    ctx.ask_multiline("Your reply", "evals")
    ctx.console.print(
        "[bold magenta]A strong answer mentions:[/bold magenta] evals. Collect a few hundred real cases with "
        "known good answers. Set the pass bar before you look. Run both models on them and compare the "
        "scores and the kinds of mistakes. Keep running them after launch and after every change."
    )
    ctx.console.print("[dim]Evals are a topic of their own. A future chapter covers them.[/dim]")


CHAPTER = Chapter(
    id="8",
    title="Design an AI feature",
    minutes=9,
    learn=LEARN,
    recap=RECAP,
    checks=(),
    hands_on=(brief, design, outcome),
    after_grade=(*(_followup_step(n) for n in range(1, FOLLOWUPS + 1)), evals_teaser),
)

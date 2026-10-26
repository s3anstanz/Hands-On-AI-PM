"""Chapter 7: "What's a context window? Paste everything in or fetch what's relevant?" (spec §6, Chapter 7)

Hands-on: watch a tiny window forget the user's allergy, price requests of
growing size, see the illustrative "lost in the middle" curve, and compare
pasting every document with fetching three pages. Window sizes and prices come
from pricing.py; token counts from tokens.py.
"""

from rich.markup import escape
from rich.text import Text

import costs
import pricing
import tokens
import ui
from engine import Chapter, Ctx, LearnScreen, QuickCheck
from lessons.ch6_cost import PER_THOUSAND, REFERENCE, chosen_scenario, scenario_label, verdict

CLAUDE_WINDOW = max(m.context_window for m in pricing.MODELS.values() if m.provider == "anthropic")
CLAUDE_WINDOW_WORDS = int(round(CLAUDE_WINDOW * pricing.CLAUDE_WORDS_PER_TOKEN, -3))
RECOMMENDATION = "fetch what's relevant and measure how often the search finds the right piece"


def short_tokens(count: int) -> str:
    """2000 -> "2K", 1000000 -> "1M"."""
    if count >= 1_000_000 and count % 1_000_000 == 0:
        return f"{count // 1_000_000}M"
    if count >= 1_000 and count % 1_000 == 0:
        return f"{count // 1_000}K"
    return f"{count:,}"


LEARN = (
    LearnScreen(
        title="The context window is working memory",
        body=(
            "The **context window** is everything the model can see in one request: the system prompt, "
            "the chat history, any documents, and the answer it's writing.\n"
            f"It has a hard limit, counted in tokens. Current Claude models take up to "
            f"{short_tokens(CLAUDE_WINDOW)} tokens, about {CLAUDE_WINDOW_WORDS:,} words."
        ),
        analogy="a desk. The model can use what's on it, and nothing else exists.",
        why_pm="You decide what goes in the window, so what the model can use is a product decision.",
    ),
    LearnScreen(
        title="No memory between requests",
        body=(
            "Each request starts from nothing. The model keeps nothing from earlier requests.\n"
            "When a chat seems to remember, the app is sending the history again each time. "
            "That's why Chapter 6's chat costs grow with every turn."
        ),
        example=(
            "On a user's 13th message, the request carries the system prompt, the 12 earlier messages, "
            "the model's 12 replies and the new message."
        ),
        why_pm="Memory is a feature you build. Decide what to store, what to resend and what to forget.",
    ),
    LearnScreen(
        title="When it fills up",
        body=(
            "When a chat or a pile of documents outgrows the window, the app must drop the oldest content "
            "or summarize it. Otherwise the request is rejected.\n"
            "To the model, dropped content is gone."
        ),
        example="A long support chat drops its oldest messages. If one held the order number, the model can no longer see it.",
        why_pm="Decide what must never be dropped, like an allergy or an order number, and keep it pinned or summarized.",
    ),
    LearnScreen(
        title="Bigger isn't free",
        body=(
            "Every request pays for everything in the window again, and long inputs are slower.\n"
            "Models also pay less attention to the middle of a very long input than to its start and end."
        ),
        example="A question about one clause doesn't need all 300 pages of the contract.",
        why_pm="A big window is a capability, not a strategy. Fill it only when the task needs it.",
    ),
    LearnScreen(
        title="Paste everything vs. fetch what's relevant",
        body=(
            "Pasting every document into the prompt is simple, but expensive and noisy.\n"
            "**Retrieval** searches first and sends only the most relevant pieces. "
            "It's often called **RAG**, retrieval-augmented generation.\n"
            "It's cheaper and more focused, but the search can miss the one document that mattered."
        ),
        analogy="handing over the whole filing cabinet vs. the three folders someone needs, picked by an assistant who sometimes grabs the wrong one.",
        why_pm="Products with many documents usually use retrieval, so measure how often its search finds the right piece.",
    ),
)

RECAP = (
    f"The context window is everything the model can see in one request, with a hard limit in tokens: "
    f"up to {short_tokens(CLAUDE_WINDOW)} tokens on current Claude models.",
    "When it overflows, the oldest content is dropped or summarized, and the model forgets it.",
    "The model has no memory between requests, so every request sends the whole window again and pays for it.",
    "Very long inputs are slower, and content in the middle gets less attention.",
    "Retrieval sends only the relevant pieces. It's cheaper and more focused, but the search can miss what mattered. "
    f"So {RECOMMENDATION}.",
)

CHECKS = (
    QuickCheck(
        question='A user comes back a week later: "As I told you last time..." What can the model see from last week?',
        options=(
            "Everything: it remembers past chats",
            "Only what the app puts into this request",
            "Nothing: past chats can never be used",
        ),
        answer=1,
        explanation="The model has no memory between requests. It sees last week only if the app stored that chat or a summary and sends it now.",
        screen=2,
    ),
    QuickCheck(
        question=(
            "Your support bot fetches the 3 most relevant help pages per question. It answered a refund question "
            "wrong, though the refund policy is in your help center. Most likely cause?"
        ),
        options=(
            "The search didn't fetch the refund page",
            "The context window is too small",
            "The temperature is too low",
        ),
        answer=0,
        explanation="Retrieval is only as good as its search. If the right page isn't fetched, the model never sees it.",
        screen=5,
    ),
)

# --- Hands-on -------------------------------------------------------------------------------------

WINDOW = 120  # a deliberately tiny window, so it fills in a few turns
PROFILES = (("Priya", "sulfa drugs"), ("Marco", "penicillin"), ("Aiko", "latex"), ("Sam", "peanuts"))
FIRST = "Hi, I'm {name}. Please remember: I'm allergic to {allergy}."
FIRST_REPLY = "Got it, {name}. I've noted your {allergy} allergy."
CHAT = (  # independent questions, so any order reads naturally
    ("Is there parking?", "Yes, behind the building."),
    ("Can I book a checkup next week?", "Yes: Tuesday at 10 or Thursday at 3."),
    ("How early should I arrive?", "About 15 minutes early, to fill in a short form."),
    ("Do I need to fast before a checkup?", "No fasting needed. Do bring a list of the medicines you take now."),
    ("Can my daughter come into the exam room with me?", "Of course. Family members are welcome in the exam room."),
    (
        "What should I bring?",
        "Your insurance card, a photo ID, a list of your medicines, and any recent test results "
        "or letters from other doctors you've seen this year.",
    ),
)
QUESTION = "Quick question before my visit: what am I allergic to?"
SIZES = (2_000, 50_000, 500_000)
SIZE_MODELS = tuple(pricing.get(key) for key in ("haiku-5-5", "sonnet-5-5", "opus-5-5"))
RECALL = (  # illustrative: the shape of the effect, not a measurement
    ("Start", 0.95),
    ("10%", 0.88),
    ("20%", 0.80),
    ("30%", 0.72),
    ("40%", 0.66),
    ("50%", 0.63),
    ("60%", 0.66),
    ("70%", 0.73),
    ("80%", 0.81),
    ("90%", 0.89),
    ("End", 0.96),
)
RECALL_LABEL = "Illustrative: the shape of a known effect, not a measurement of any model."
WORDS_PER_PAGE = 500
PAGE_TOKENS = round(WORDS_PER_PAGE / pricing.CLAUDE_WORDS_PER_TOKEN)  # one page, in Claude tokens
FETCHED_PAGES = 3


def message_tokens(text: str) -> int:
    return tokens.openai_count(text)[0]


def input_cost(model: pricing.Model, size: int) -> float:
    return costs.request_cost(model, costs.Usage(input_tokens=size, output_tokens=0)).total


def window_start(messages: list[tuple[str, str]], window: int = WINDOW) -> int:
    """Index of the oldest message the model still sees: the app keeps the newest messages that fit."""
    total = 0
    for i in range(len(messages) - 1, -1, -1):
        total += message_tokens(messages[i][1])
        if total > window:
            return i + 1
    return 0


def _show_window(ctx: Ctx, heading: str, messages: list[tuple[str, str]], start: int) -> None:
    used = sum(message_tokens(text) for _, text in messages[start:])
    ctx.console.print(f"\n[bold]{escape(heading)}[/bold] · window {used}/{WINDOW} tokens")
    for i, (who, text) in enumerate(messages):
        if i < start:
            ctx.console.print(Text(f"✗ {who}: {text}", style="dim strike"))
        else:
            ctx.console.print(Text(f"  {who}: {text}"))


def watch_it_forget(ctx: Ctx) -> None:
    name, allergy = ctx.rng.choice(PROFILES)
    chat = list(CHAT)
    ctx.rng.shuffle(chat)
    turns = [(FIRST.format(name=name, allergy=allergy), FIRST_REPLY.format(name=name, allergy=allergy)), *chat]
    first_turn = message_tokens(turns[0][0]) + message_tokens(turns[0][1])
    later = round(sum(message_tokens(q) + message_tokens(a) for q, a in chat) / len(chat))
    ctx.console.print("[bold]Watch it forget[/bold]")
    ctx.console.print(
        f"A simulated clinic chat with a tiny window of {WINDOW} tokens. Your first message and its reply "
        f"take {first_turn} tokens. Each later question and answer takes about {later}. "
        "When the window is full, the app drops the oldest messages."
    )
    guess = ctx.ask_number(
        "Your prediction: after how many turns does your first message fall out?",
        "guess_turns",
        1,
        len(turns),
        integer=True,
    )
    messages: list[tuple[str, str]] = []
    gone_after = 0
    for turn, (user, reply) in enumerate(turns, 1):
        messages += [("You", user), ("Assistant", reply)]
        start = window_start(messages)
        if start > 0 and not gone_after:
            gone_after = turn
        _show_window(ctx, f"Turn {turn}", messages, start)
        if turn < len(turns):
            ctx.pause("Enter for the next turn")
    messages.append(("You", QUESTION))
    sees_it = window_start(messages) < 2  # the first message or the reply that repeats the allergy
    answer = (
        f"You're allergic to {allergy}."
        if sees_it
        else "I don't see an allergy anywhere in our chat. Could you tell me again?"
    )
    ctx.console.print(f"\nYou: {escape(QUESTION)}")
    ctx.console.print(f"Assistant: {escape(answer)}")
    ctx.console.print("[dim]✗ = out of the window: the model can't see it.[/dim]")
    ctx.console.print(
        f"Your first message fell out after {gone_after} turns. {verdict(guess, gone_after)} "
        f"Real windows hold up to {short_tokens(CLAUDE_WINDOW)} tokens, but long chats fill them too, "
        "so apps summarize old turns or pin key facts like this one."
    )
    ctx.console.print(ui.shows("once the allergy falls out of the window, the model can't see it (Learn 3)."))


def cost_per_request(ctx: Ctx) -> None:
    ctx.console.print("[bold]Bigger windows, bigger bills[/bold]")
    ctx.console.print("Input cost of one request, at three sizes:\n")
    table = ui.compact_table("Size", *(ui.model_label(m.display_name) for m in SIZE_MODELS))
    for size in SIZES:
        row = [costs.format_usd(input_cost(model, size)) for model in SIZE_MODELS]
        table.add_row(short_tokens(size), *row)
    ctx.console.print(table)
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")
    haiku = SIZE_MODELS[0]
    middle, big = SIZES[1], SIZES[2]

    def growth(model: pricing.Model) -> float:
        return input_cost(model, big) / input_cost(model, middle)

    ctx.console.print(
        f"From {short_tokens(middle)} to {short_tokens(big)} the input is {big // middle}× bigger. "
        f"On {ui.model_label(REFERENCE.display_name)} the cost grows {growth(REFERENCE):.0f}× too; "
        f"on {ui.model_label(haiku.display_name)} it grows {growth(haiku):.0f}×, because a prompt over "
        f"{haiku.tiers[0].above:,} tokens pays the higher rate on the whole request."
    )
    ctx.console.print("And you pay that on every request.")
    ctx.console.print(ui.shows("a bigger prompt is a bigger bill on every request (Learn 4)."))


def recall_curve(ctx: Ctx) -> None:
    ctx.console.print("[bold]Lost in the middle[/bold]")
    ctx.console.print(f"How often the model uses a fact, by where it sits in a very long input. {RECALL_LABEL}\n")
    ctx.console.print(ui.value_bars([(where, p, f"{p:.0%}") for where, p in RECALL], ctx.console.width))
    ctx.console.print(
        "Put what matters most at the start or end of a long prompt, or send less, "
        "so nothing important sits in the middle."
    )
    ctx.console.print(ui.shows("the middle of a long input gets less attention than the start and end (Learn 4)."))


def paste_vs_fetch(ctx: Ctx) -> None:
    scenario, work = chosen_scenario(ctx)
    pages = max(FETCHED_PAGES + 1, round(work.docs_tokens / PAGE_TOKENS))
    ctx.console.print("[bold]Paste everything or fetch what's relevant?[/bold]")
    ctx.console.print(
        f"{scenario_label(scenario)}: {escape(scenario.pitch)} Its reference material is about {pages:,} pages "
        f"({work.docs_tokens:,} tokens, at about {PAGE_TOKENS:,} tokens a page). Each request also has "
        f"{work.input_tokens:,} tokens of its own and a {work.output_tokens:,}-token answer."
    )
    guess = ctx.ask_number(
        f"Your prediction: how many times cheaper per request is fetching {FETCHED_PAGES} relevant pages "
        f"than pasting all {pages:,}?",
        "guess_fetch",
        1,
        100,
        integer=True,
    )
    options = (
        ("Paste all", work.input_tokens + work.docs_tokens),
        (f"Fetch {FETCHED_PAGES} pages", work.input_tokens + FETCHED_PAGES * PAGE_TOKENS),
    )
    table = ui.compact_table("", "Tokens in", f"Per {PER_THOUSAND:,}")
    per_thousand = []  # rounded once; the ratio and the monthly totals come from these shown figures
    for label, sent in options:
        price = round(costs.request_cost(REFERENCE, costs.Usage(sent, work.output_tokens)).total * PER_THOUSAND, 2)
        per_thousand.append(price)
        table.add_row(label, f"{sent:,}", costs.format_usd(price))
    ctx.console.print(f"\nThe cost of {PER_THOUSAND:,} requests on {REFERENCE.display_name}:")
    ctx.console.print(table)
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}[/dim]")
    ratio = round(per_thousand[0] / per_thousand[1])
    per_month = [round(k * work.requests_per_day * costs.DAYS_PER_MONTH / PER_THOUSAND, 2) for k in per_thousand]
    ctx.console.print(
        f"Fetching is {ratio}× cheaper per request. {verdict(guess, ratio, '×')} "
        f"At {work.requests_per_day:,} requests a day that's {costs.format_usd(per_month[0])} vs. "
        f"{costs.format_usd(per_month[1])} a month."
    )
    haiku = SIZE_MODELS[0]
    if options[0][1] > haiku.tiers[0].above:
        ctx.console.print(
            f"On {ui.model_label(haiku.display_name)}, the pasted request is over {haiku.tiers[0].above:,} tokens, "
            "so the whole request would pay the higher rate."
        )
    ctx.console.print(
        "The catch: if the search misses the page that mattered, the model never sees it. "
        "Measure how often it finds the right page."
    )
    ctx.console.print(ui.shows("sending only what's relevant cuts the bill on every request (Learn 5)."))


CHAPTER = Chapter(
    id="7",
    title="Context windows: what the model can see",
    minutes=8,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(watch_it_forget, cost_per_request, recall_curve, paste_vs_fetch),
    figures={"window": short_tokens(CLAUDE_WINDOW), "window_words": f"{CLAUDE_WINDOW_WORDS:,}"},
)

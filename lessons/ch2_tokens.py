"""Chapter 2: "What's a token and why does it matter?" (spec §6, Chapter 2)

Hands-on: count tokens, measure the words-per-token rule, see what
splits into many pieces, and price the same text on different vendors. Every
count on screen is measured by tokens.py, never typed into copy.
"""

from rich.markup import escape
from rich.table import Table
from rich.text import Text

import costs
import pricing
import tokens
import ui
from engine import Chapter, Ctx, LearnScreen, QuickCheck

SENTENCES = (
    "Please send me the latest sales report by Friday.",
    "Our app helps nurses schedule their shifts.",
    "The new pricing page goes live next Tuesday.",
    "Can you summarize this customer email in two lines?",
    "Most users finish onboarding in under five minutes.",
    "The model drafts a reply and an agent approves it.",
)
PARAGRAPHS = (
    "Product managers decide what gets built and why. They talk to customers, study the data, and work with "
    "engineers and designers to ship features that solve real problems. A good roadmap balances quick wins "
    "with bigger bets.",
    "The new onboarding flow cut the time to first value from three days to forty minutes. Support tickets "
    "about account setup dropped by half in the first month, and more trial users converted to paid plans.",
    "When the model is unsure, it still writes fluent sentences. That is why the team added citations to every "
    "answer and a button that lets users flag a response that looks wrong.",
    "Our quarterly planning starts with the company goals. Each team proposes a few outcomes, estimates the "
    "effort, and agrees on the metrics that will tell us whether the work paid off.",
    "The pharmacy app reminds patients when a refill is due and explains each medication in plain language. "
    "Doctors can see whether patients picked up their prescriptions.",
    "Customers in the beta asked for shorter summaries, so the assistant now gives a three sentence overview "
    "first and offers the full report as a link at the bottom.",
)
HARD = (
    ("Long rare word", "antidisestablishmentarianism"),
    ("Medical term", "pseudohypoparathyroidism"),
    ("Number", "3.14159265"),
    ("Code", "for i in range(10): print(i**2)"),
    ("Emoji", "Great job! 🎉👏🏽🚀"),
)
LANGUAGES = (
    ("English", "The meeting is moved to Thursday afternoon."),
    ("Spanish", "La reunión se cambió al jueves por la tarde."),
    ("Japanese", "会議は木曜日の午後に変更されました。"),
    ("Hindi", "बैठक गुरुवार दोपहर तक स्थगित कर दी गई है।"),
)
PRICED_MODELS = ("opus-5-5", "sonnet-5-5", "haiku-5-5", "gpt-6-astra", "gpt-6-luna")
REQUESTS = 1_000_000
MAX_SHOWN = 300
SPLIT_STYLES = ("black on bright_cyan", "black on bright_yellow")
NARROW = 60  # below this width, tables cap some columns so Rich wraps them instead of cropping the border


def _tokens_per_1000_words(words_per_token: float) -> int:
    """Tokens in 1,000 words, rounded to the nearest hundred for copy."""
    return int(round(1000 / words_per_token, -2))


# The numbers the chapter teaches. Ratios come from pricing.py at import. Token counts are measured facts
# about the bundled o200k_base tokenizer, fixed here so a learner on the fallback estimator is taught the
# same numbers the checklist grades against; test_taught_numbers_match_the_bundled_tokenizer re-measures them.
RULE_1000 = _tokens_per_1000_words(pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN)
OPENAI_1000 = 1_100  # 1,000 words of PARAGRAPHS, rounded to the nearest hundred
CLAUDE_1000 = _tokens_per_1000_words(pricing.CLAUDE_WORDS_PER_TOKEN)
ENGLISH_TOKENS = 8  # LANGUAGES["English"]
HINDI_TOKENS = 17  # LANGUAGES["Hindi"]
HINDI_X = HINDI_TOKENS / ENGLISH_TOKENS
QUOTE_LINE = (
    f"By the classic ¾ rule, 1,000 words is about {RULE_1000:,} tokens. Today's tokenizers range from about "
    f"{OPENAI_1000:,} (OpenAI) to about {CLAUDE_1000:,} (Claude), so measure your own text."
)

LEARN = (
    LearnScreen(
        title="What a token is",
        body=(
            "Models read text in chunks, not whole words. Each chunk is a **token**.\n"
            "Common words are usually one token. Rare or long words split into pieces."
        ),
        analogy="Lego bricks. A common word is one big brick; a rare word takes several small ones.",
        example=(
            'On OpenAI\'s public tokenizer, "the" is one token and "antidisestablishmentarianism" is six: '
            "ant · idis · est · ablishment · arian · ism."
        ),
        why_pm="Expect names, part numbers and jargon to use more tokens than their word count suggests.",
    ),
    LearnScreen(
        title="Why tokens, not words or letters",
        body=(
            "A model has a fixed **vocabulary** of roughly 100K to 200K pieces.\n"
            "Whole words plus word pieces cover any text, including typos, names and brand-new words.\n"
            "Letters alone make text long and slow. Whole words alone miss anything new."
        ),
        analogy="a phrasebook plus an alphabet. Use a whole phrase when you have one; spell out the rest.",
        example="A made-up name like \"Zorblax\" still works: on OpenAI's public tokenizer it's built from Z · or · bl · ax.",
        why_pm="The model never rejects odd input. It just spends more tokens on it.",
    ),
    LearnScreen(
        title="Everything is measured in tokens",
        body=(
            "Price: dollars per million tokens. Input and output are counted separately.\n"
            "Speed: tokens per second.\n"
            "Size limit: how much a model can read at once, also in tokens (Chapter 7)."
        ),
        example="A 2,000-token prompt and a 500-token answer: those two numbers set the cost, the speed and whether it fits.",
        why_pm="Every cost estimate for your product starts with a token count.",
    ),
    LearnScreen(
        title="The rule of thumb, and its catch",
        body=(
            "OpenAI's long-standing rule of thumb: a token is about ¾ of an English word.\n"
            "The real ratio depends on the **tokenizer**, the part that cuts text into tokens. "
            "Each company and model generation has its own.\n"
            "OpenAI's newest public tokenizer fits more English into each token. "
            "Anthropic's current tokenizer (Claude 4.7 and every newer model) fits less, "
            f"about {pricing.CLAUDE_WORDS_PER_TOKEN:g} words per token."
        ),
        example=QUOTE_LINE,
        why_pm="A tokenizer change is a silent price change: same prompt, same price per token, more tokens.",
    ),
    LearnScreen(
        title="What uses more tokens",
        body=(
            "Rare words, numbers, code, emoji and many non-English languages split into more pieces.\n"
            "The same sentence can take noticeably more tokens in another language, sometimes about twice as many."
        ),
        example=(
            f'On OpenAI\'s public tokenizer, "{dict(LANGUAGES)["English"]}" is {ENGLISH_TOKENS} tokens. '
            f"The same sentence in Hindi is {HINDI_TOKENS}."
        ),
        why_pm="The same feature can cost more in some languages, so budget per language, not just per user.",
    ),
)

RECAP = (
    "A token is a chunk of text: a word or a piece of one.",
    "OpenAI's rule of thumb is about ¾ of an English word per token. The real ratio depends on the tokenizer.",
    "Price, speed and size limits are all counted in tokens.",
    f"Rare words, numbers, code, emoji and many other languages use more tokens (Hindi takes about {HINDI_X:.1f}× English).",
    "Different companies' tokenizers count the same text differently, so the bill differs too.",
    f"Put a number on it. {QUOTE_LINE}",
)

CHECKS = (
    QuickCheck(
        question="By the ¾-word rule of thumb, about how many tokens is a 1,000-word English document?",
        options=("About 750", "About 1,300", "About 4,000"),
        answer=1,
        explanation=(
            f"1,000 ÷ {pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN:g} ≈ "
            f"{1000 / pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN:,.0f}. A token is less than a word, so you "
            f"get more tokens than words. Today's tokenizers give about {OPENAI_1000:,} to {CLAUDE_1000:,}, so measure your own text."
        ),
        screen=4,
    ),
    QuickCheck(
        question="Which of these uses the most tokens?",
        options=('"extraordinarily"', '"2024-10-14"', '"refrigerator"'),
        answer=1,
        explanation=(
            "The date. Numbers and punctuation split into small pieces, so a 10-character date takes more "
            "tokens than a 15-letter word made of common chunks. Length in letters is a poor guide."
        ),
        screen=5,
    ),
)

NO_CLAUDE_ESTIMATE = "no reliable Claude estimate for this text (Anthropic's ratio is for English)"
MANY_PIECES = "Names, IDs and some scripts split into many pieces: that's where costs surprise you."


def colored_split(text: str) -> Text:
    """The text with alternating background colors, one per token. Text never parses markup."""
    out = Text()
    for i, piece in enumerate(tokens.split_for_display(text)):
        out.append(piece, style=SPLIT_STYLES[i % 2])
    return out


def merges_tokens(text: str) -> bool:
    """True when some drawn piece holds several tokens (emoji and some scripts split mid-character)."""
    return tokens.encoding_available() and any(n > 1 for _, n in tokens.split_with_counts(text))


def color_key() -> str:
    if tokens.encoding_available():
        return "Each color is one token."
    return f"Each color is a word, not a token: {tokens.FALLBACK_LABEL}."


def print_merged_note(ctx: Ctx, text: str) -> None:
    if merges_tokens(text):
        ctx.console.print("[dim]Some emoji and scripts merge several tokens into one color.[/dim]")


def per_request(amount: float) -> str:
    """One request's cost. Six decimals, because a short prompt on a cheap model is a few millionths of a dollar."""
    return f"${amount:.6f}"


def claude_range(text: str) -> str:
    low, high = tokens.claude_estimate(text)
    return f"{low}" if low == high else f"{low}-{high}"


def words_part(text: str) -> str:
    """The word count, except for text with no spaces in a non-Latin script, where "1 word" would mislead."""
    visible = text.strip()
    if not any(ch.isspace() for ch in visible) and sum(not ch.isascii() for ch in visible) * 2 > len(visible):
        return "words: n/a (no spaces)"
    words = tokens.word_count(text)
    return f"{words} word{'' if words == 1 else 's'}"


def count_line(text: str) -> str:
    count, label = tokens.openai_count(text)
    claude = (
        f"Claude: about {claude_range(text)} tokens ({tokens.CLAUDE_ESTIMATE_LABEL})"
        if tokens.claude_estimate_reliable(text)
        else NO_CLAUDE_ESTIMATE
    )
    return escape(f"{words_part(text)} · {len(text)} characters · {count} tokens ({label}) · {claude}")


def predict_tokens(ctx: Ctx) -> None:
    sentence = ctx.rng.choice(SENTENCES)
    ctx.console.print("[bold]Count the tokens[/bold]")
    ctx.console.print(f"\n{escape(sentence)}")
    guess = int(
        ctx.ask_number("Your prediction: how many tokens is this sentence?", "guess_tokens", 1, 100, integer=True)
    )
    count, label = tokens.openai_count(sentence)
    words = tokens.word_count(sentence)
    off = abs(guess - count)
    ctx.console.print(colored_split(sentence))
    ctx.console.print(
        f"{count} tokens on {escape(label)}, for {words} words. "
        f"You guessed {guess}: {'spot on' if off == 0 else f'off by {off}'}."
    )
    rule = round(words / pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN)
    ctx.console.print(f"The ¾ rule would say about {rule}. Short common words are about one token each.")
    ctx.console.print(f"[dim]{escape(color_key())}[/dim]")
    print_merged_note(ctx, sentence)
    ctx.console.print(ui.shows("common words are about one token each, so word count is a fair first guess (Learn 1)."))


def try_your_own(ctx: Ctx) -> None:
    ctx.console.print("[bold]Tokenize your own text[/bold]")
    ctx.console.print(f"Type anything: a sentence, a product name, an email address. {escape(color_key())}")
    while True:
        text = ctx.ask_line("Your text, one line at a time (Enter to move on)")
        if not text.strip():
            ctx.console.print(ui.shows("unusual text costs more tokens than its word count suggests (Learn 5)."))
            return
        ctx.console.print(colored_split(text[:MAX_SHOWN]))
        if len(text) > MAX_SHOWN:
            ctx.console.print(f"[dim](showing the first {MAX_SHOWN} characters; the counts are for all of it)[/dim]")
        ctx.console.print(count_line(text))
        print_merged_note(ctx, text)
        if tokens.openai_count(text)[0] >= 2 * max(1, tokens.word_count(text)):
            ctx.console.print(MANY_PIECES)


def measure_rule(ctx: Ctx) -> None:
    sample = ctx.rng.sample(PARAGRAPHS, 3)
    words = sum(tokens.word_count(p) for p in sample)
    counted = sum(tokens.openai_count(p)[0] for p in sample)
    label = tokens.openai_count(sample[0])[1]
    kind = "Measured" if tokens.encoding_available() else "Estimated"
    rule = pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN
    claude = pricing.CLAUDE_WORDS_PER_TOKEN
    ctx.console.print("[bold]Measure the rule[/bold]")
    ctx.console.print(f"Three paragraphs of plain English, {words} words in all:\n")
    for paragraph in sample:
        ctx.console.print(f"[dim]{escape(paragraph)}[/dim]\n")
    ctx.console.print("Three ways to predict the tokens in these same words, scaled to 1,000 words:")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Way of counting", overflow="fold")
    table.add_column("Words/token", justify="right", min_width=len("Words/token"))
    table.add_column("1,000 words", justify="right", max_width=8 if ctx.console.width < NARROW else None)
    table.add_row("OpenAI's rule of thumb", f"{rule:.2f}", f"{round(1000 / rule):,} tokens")
    table.add_row(f"{kind}: {escape(label)}", f"{words / counted:.2f}", f"{round(1000 * counted / words):,} tokens")
    table.add_row(f"Claude ({escape(tokens.CLAUDE_ESTIMATE_LABEL)})", f"{claude:g}", f"{round(1000 / claude):,} tokens")
    ctx.console.print(table)
    ctx.console.print(
        f"Not the same: {round(1000 / rule):,} vs {round(1000 * counted / words):,} vs {round(1000 / claude):,} "
        "tokens for the same words."
    )
    ctx.console.print(ui.shows("same words, three token counts, because ¾ is only a rule of thumb (Learn 4)."))


def shown_pieces(text: str) -> str:
    """The pieces joined by dots: spaces drawn as ␣, and a piece holding several tokens marked like 🚀(2)."""
    return " · ".join(
        piece.replace(" ", "␣") + (f"({n})" if n > 1 else "") for piece, n in tokens.split_with_counts(text)
    )


def gallery(ctx: Ctx) -> None:
    pieces = tokens.encoding_available()
    ctx.console.print("[bold]What splits into many pieces[/bold]")
    table = Table(show_header=True, header_style="bold")
    table.add_column("Example")
    table.add_column("Tokens", justify="right")
    if pieces:
        table.add_column("Pieces", overflow="fold")
    for label, text in HARD:
        cells = [escape(label), str(tokens.openai_count(text)[0])]
        if pieces:
            cells.append(escape(shown_pieces(text)))
        table.add_row(*cells)
    ctx.console.print(table)
    if pieces:
        merged = next(((p, n) for _, text in HARD for p, n in tokens.split_with_counts(text) if n > 1), None)
        note = (
            f" {merged[0]}({merged[1]}) is one piece holding {merged[1]} tokens: some emoji and scripts split "
            "mid-character."
            if merged is not None
            else ""
        )
        ctx.console.print(f"[dim]␣ is a space.{escape(note)}[/dim]")
    else:
        ctx.console.print("[dim]The tokenizer isn't available, so the split into pieces can't be shown.[/dim]")
    ctx.console.print(f"[dim]Counted with {escape(tokens.openai_count('x')[1])}. Claude splits text differently.[/dim]")
    ctx.console.print(
        ui.shows("rare words, numbers, code and emoji split into many pieces, so they cost more (Learn 5).")
    )


def languages(ctx: Ctx) -> None:
    texts = dict(LANGUAGES)
    counts = {name: tokens.openai_count(text)[0] for name, text in LANGUAGES}
    english, japanese = counts["English"], counts["Japanese"]
    ctx.console.print("[bold]Same sentence, different languages[/bold]")
    ctx.console.print(f"English: {escape(texts['English'])}")
    ctx.console.print(f"Japanese: {escape(texts['Japanese'])}")
    options = ("The English version", "The Japanese version", "About the same")
    for i, option in enumerate(options, 1):
        ctx.console.print(f"  {i}. {option}")
    pick = ctx.ask_choice("Your prediction: which uses more tokens?", len(options), key="lang_guess")
    ctx.console.print(f"You predicted {options[pick][0].lower()}{options[pick][1:]}.")
    if tokens.encoding_available():
        table = Table(show_header=True, header_style="bold")
        table.add_column("Language")
        table.add_column("Tokens", justify="right")
        table.add_column("× English", justify="right")
        for name, _ in LANGUAGES:
            table.add_row(name, str(counts[name]), f"{counts[name] / english:.1f}×")
        ctx.console.print(table)
        ctx.console.print(f"[dim]Counted with {escape(tokens.openai_count('x')[1])}.[/dim]")
    else:  # a word-based estimate can't compare languages, so show the measured facts the chapter teaches
        ctx.console.print(
            f"On OpenAI's public tokenizer: English {ENGLISH_TOKENS} tokens, Hindi {HINDI_TOKENS} ({HINDI_X:.1f}×)."
        )
        ctx.console.print(
            f"[dim]Measured with the bundled tokenizer, which isn't available here. A {tokens.FALLBACK_LABEL} can't compare languages.[/dim]"
        )
    if not tokens.encoding_available():
        pass  # nothing to compare without the tokenizer
    elif japanese > english:
        hindi = f" and Hindi {counts['Hindi'] / english:.1f}×" if "Hindi" in counts else ""
        ctx.console.print(f"Japanese takes {japanese / english:.1f}×{hindi} the tokens of English here.")
    elif japanese < english:
        ctx.console.print("English takes more tokens here.")
    else:
        ctx.console.print("They take the same number of tokens here.")
    ctx.console.print(ui.shows("many languages need more tokens for the same meaning (Learn 5)."))


def official_count(ctx: Ctx, text: str) -> int | None:
    """Claude's own count, with a key. count_tokens is free, so it runs without asking.

    A success is kept in ctx.state, so going back to this step doesn't call the API again.
    """
    if ctx.live is None:
        return None
    cached = ctx.state.get("official_count")
    if cached is not None and cached[0] == text:
        return cached[1]
    ctx.console.print("[dim]Getting the official Claude count…[/dim]")
    count = ctx.live.count_tokens(text, pricing.GRADER_MODEL)
    if count is None:
        ctx.console.print(
            f"[yellow]Official Claude count unavailable: {escape(ctx.live.last_error)}. Using the estimate.[/yellow]"
        )
        return None
    ctx.state["official_count"] = (text, count)
    return count


def different_bills(ctx: Ctx) -> None:
    text = ctx.rng.choice(PARAGRAPHS)
    openai, label = tokens.openai_count(text)
    low, high = tokens.claude_estimate(text)
    ctx.console.print("[bold]Same text, different bills[/bold]")
    official = official_count(ctx, text)
    ctx.console.print(f"[dim]{escape(text)}[/dim]\n")
    ctx.console.print("One request is this paragraph as the whole prompt. Input only, no answer.")
    ctx.console.print(f"{escape(label)}: {openai} tokens")
    ctx.console.print(f"Claude ({escape(tokens.CLAUDE_ESTIMATE_LABEL)}): about {claude_range(text)} tokens")
    if official is not None:
        ctx.console.print(f"Claude 5.5 models, official count (count_tokens): {official} tokens")
    claude = official if official is not None else round((low + high) / 2)
    claude_cell = f"{claude:,}" if official is not None else f"~{claude:,}"  # a midpoint, not a measured count
    table = Table(show_header=True, header_style="bold")
    narrow = ctx.console.width < NARROW
    table.add_column("Model", max_width=6 if narrow else None)  # "Sonnet" is its longest word
    if not narrow:  # at 40 columns the token and price columns are dropped; the lines around the table state them
        table.add_column("Tokens", justify="right")
        table.add_column("$/1M tokens", justify="right")
    table.add_column("1 request", justify="right", min_width=len("$0.000000"))
    table.add_column(f"{REQUESTS // 1_000_000}M requests", justify="right", min_width=len("requests"))
    bills = []  # (name, tokens shown, tokens, cost)
    for key in PRICED_MODELS:
        model = pricing.get(key)
        count = claude if model.provider == "anthropic" else openai
        cost = costs.request_cost(model, costs.Usage(input_tokens=count, output_tokens=0)).total * REQUESTS
        cell = claude_cell if model.provider == "anthropic" else f"{openai:,}"
        bills.append((model.display_name, cell, count, cost))
        shown = [] if narrow else [cell, costs.format_usd(model.input)]
        table.add_row(escape(model.display_name), *shown, per_request(cost / REQUESTS), costs.format_usd(cost))
    ctx.console.print(table)
    source = "official" if official is not None else "estimates"
    openai_note = (
        "OpenAI counts use its public GPT-4o / GPT-5 era tokenizer, an approximation for GPT-6."
        if tokens.encoding_available()
        else f"OpenAI counts are a {tokens.FALLBACK_LABEL}."
    )
    ctx.console.print(f"[dim]prices checked {pricing.LAST_CHECKED}. Claude counts are {source}; {openai_note}[/dim]")
    name, cell, count, cost = bills[0]
    ctx.console.print(
        f"One {escape(name)} request: {cell} tokens × {costs.format_usd(pricing.get(PRICED_MODELS[0]).input)} "
        f"per million = {per_request(cost / REQUESTS)}. A million of them: {costs.format_usd(cost)}."
    )
    cheaper = next(
        (
            (more, fewer)
            for more in sorted(bills, key=lambda bill: bill[3])
            for fewer in sorted(bills, key=lambda bill: -bill[3])
            if more[2] > fewer[2] and more[3] < fewer[3]
        ),
        None,
    )
    if cheaper is not None:
        (more_name, more_cell, _, _), (fewer_name, fewer_cell, _, _) = cheaper
        ctx.console.print(
            f"{escape(more_name)} counts {more_cell} tokens to {escape(fewer_name)}'s {fewer_cell}, "
            "yet costs less, because its price per token is lower."
        )
    ctx.console.print("So compare the cost of your real text, per language, not the price per token.")
    ctx.console.print(ui.shows("the bill is tokens times price, and both differ by vendor (Learn 3 and 4)."))


CHAPTER = Chapter(
    id="2",
    title="Tokens: what models read and bill",
    minutes=8,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(predict_tokens, try_your_own, measure_rule, gallery, languages, different_bills),
)

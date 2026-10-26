"""Chapter 1: "Explain how an LLM generates text." (spec §6, Chapter 1)

The foundation chapter, so it has the biggest Learn section. Hands-on: watch a
sentence get built one token at a time, guessing the top pick twice.
"""

from rich.markup import escape
from rich.table import Table

import sampling
import ui
from engine import Chapter, Ctx, LearnScreen, QuickCheck

SKY = {"blue": 62, "clear": 18, "dark": 12, "gray": 6, "ugly": 2}
PREDICT_AT = (0, 2)  # demo steps where you guess before the reveal
ATTACHED = ".,!?;:%"


def join_token(text: str, token: str) -> str:
    return text + token if token[0] in ATTACHED else f"{text} {token}"


def _sky_bars(ctx: Ctx) -> None:
    ctx.console.print(ui.bar_chart(sampling.normalize(SKY), width=ctx.console.width))
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")


def _size_table(ctx: Ctx) -> None:
    table = Table(show_header=True, header_style="bold")
    for column in ("Size", "Quality", "Speed", "Price"):
        table.add_column(column)
    table.add_row("Small", "↑", "↑↑↑", "$")
    table.add_row("Medium", "↑↑", "↑↑", "$$")
    table.add_row("Large", "↑↑↑", "↑", "$$$")
    ctx.console.print(table)
    ctx.console.print("[dim]Relative, not measured. Chapter 5 puts real prices next to these.[/dim]")


LEARN = (
    LearnScreen(
        title="What an LLM is",
        body=(
            "A **large language model** (LLM) is a program that has read an enormous amount of text "
            "and learned the patterns of which words tend to follow which.\n"
            "It doesn't look answers up in a database, and it doesn't search the web unless a product wires that in.\n"
            "It writes whatever is most likely to come next."
        ),
        analogy="a very well-read person finishing your sentence: fluent and usually right, but working from memory, not from a reference book.",
        example='Ask "What\'s the capital of France?" and it writes "Paris" because that continuation was overwhelmingly common in what it read, not because it checked.',
        why_pm="This one idea explains both the strengths (fluent, flexible) and the failures (confident mistakes, Chapter 4).",
    ),
    LearnScreen(
        title="Think of it like autocomplete",
        body=(
            "Your phone suggests the next word as you type. An LLM does the same job: given some text, guess what comes next.\n"
            "The difference is scale: it was trained on vastly more text, and it can keep going for pages instead of one word."
        ),
        analogy="autocomplete that has read a large share of the internet and many books.",
        example='"Thanks so much for ___" → "your", "the", "everything". Your phone and an LLM both rank options like these.',
        why_pm="When an LLM product surprises you, ask: what would a very good autocomplete write here?",
    ),
    LearnScreen(
        title="The vocabulary",
        body=(
            "**Prompt**: the text you send in (instructions, a question, documents).\n"
            "**Response**: the text that comes back (also called a completion).\n"
            "**Model**: the trained program itself, for example Claude Sonnet 5.5.\n"
            "**API**: how a product sends prompts to a model over the internet and gets responses back. Products pay per use."
        ),
        example="A support app sends the customer's message plus its own instructions as the prompt, through the API, to a model, and shows the response in the chat window.",
        why_pm="These four words come up in every AI product conversation, and engineers expect you to use them precisely.",
    ),
    LearnScreen(
        title="Training vs. answering a request",
        body=(
            "**Training** happens once, before you ever use the model: months of computing that cost tens to hundreds of millions of dollars.\n"
            "**Inference** is the model answering one request. It happens every time a user hits send, and it's what you pay for per use."
        ),
        analogy="writing a textbook (once, slow, expensive) vs. a student answering a question from it (every time, quick, cheap).",
        why_pm="Training cost is the lab's problem. Inference cost is your product's cost of goods sold (Chapter 6).",
    ),
    LearnScreen(
        title="Knowledge cutoff, and how chatbots still know today's news",
        body=(
            "Training stops on a date, so the model's own knowledge has a **knowledge cutoff**.\n"
            "Chat apps like ChatGPT and Claude get around it with **tools** such as web search: the app searches first, "
            "adds the results to the prompt, and the model reads them before answering.\n"
            "The model didn't learn the news; it was handed it."
        ),
        analogy="a student who stopped studying in June, taking an open-book test with today's newspaper on the desk.",
        example=(
            "Ask Claude about yesterday's game: it searches, reads the article, and summarizes it. "
            "Call the same model through the API without search, and it can only guess or say it doesn't know."
        ),
        why_pm=(
            "Fresh or private information has to come from your product, not the model. "
            "Fetching it is a design choice with its own cost and failure modes (Chapter 7)."
        ),
    ),
    LearnScreen(
        title="Probabilities",
        body=(
            'For "The sky is ___", the model gives every possible next word a **probability**: a score for how likely it is.\n'
            "All the scores add up to 100%. Common, sensible continuations get high scores; odd ones get tiny scores."
        ),
        example="Below: blue 62%, clear 18%, dark 12%, gray 6%, ugly 2%.",
        why_pm="Everything you'll see in this tutorial (variety, creativity, mistakes) comes from how the model picks from these scores.",
        visual=_sky_bars,
    ),
    LearnScreen(
        title="One piece at a time",
        body=(
            "The model picks one **token** (a word or a piece of a word; Chapter 2 covers these), adds it to the text, "
            "and then scores the next token given everything so far.\n"
            "It repeats until the answer is done. A long answer is hundreds of these small picks in a row."
        ),
        analogy="laying a path one stone at a time, choosing each stone by looking at the path behind you.",
        example="The sky is → blue → and → clear → today → .",
        why_pm="Longer answers mean more picks, which means more time and more cost. Answer length is a product lever.",
    ),
    LearnScreen(
        title="Bigger vs. smaller models",
        body=(
            "**Parameters** are the billions of numbers a model learned during training: its stored knowledge and skill.\n"
            "More parameters usually means more knowledge and better reasoning, but more computing for every token, "
            "so the model is slower and pricier."
        ),
        example="Claude comes in three sizes: Haiku (small), Sonnet (medium) and Opus (large).",
        why_pm="Choosing a model size is a quality-speed-cost tradeoff (Chapter 5). Bigger isn't automatically better for your product.",
        visual=_size_table,
    ),
)

RECAP = (
    "It predicts one token (a word or word piece) at a time.",
    "It gives every possible next token a probability and picks from them.",
    "It adds the pick and repeats until the answer is done.",
    "Its own knowledge stops at the training cutoff; apps add fresh facts, like search results, to the prompt.",
    "Bigger models are better, but slower and pricier.",
)

CHECKS = (
    QuickCheck(
        question="When you ask a model a question, does it look the answer up in a database?",
        options=(
            "Yes, it searches a database of facts",
            "No, it writes the most likely continuation",
            "Only for facts, not for opinions",
        ),
        answer=1,
        explanation="It generates likely text from patterns learned in training. Products can add search, but the model itself doesn't look things up.",
        screen=1,
    ),
    QuickCheck(
        question="ChatGPT just answered a question about yesterday's news. How?",
        options=(
            "It was retrained overnight",
            "The app searched the web and added the results to the prompt",
            "Its knowledge cutoff is today",
        ),
        answer=1,
        explanation=(
            "The model's own knowledge stops at its training cutoff. "
            "The app fetched the news and handed it to the model in the prompt."
        ),
        screen=5,
    ),
)


def generation_demo(ctx: Ctx) -> None:
    prompt = ctx.rng.choice([p for p in ctx.data.prompts if p.continuation])
    tables = (prompt.weights, *prompt.continuation)
    text = prompt.text
    ctx.console.print("[bold]Watch it generate[/bold]")
    ctx.console.print(
        "The model scores every candidate for the next token, takes one, and repeats. "
        "Here it always takes the top one; Chapter 3 shows what happens when it doesn't."
    )
    ctx.console.print(
        "Predict first, then see the model's odds. Go with your gut: you've read thousands of "
        "sentences like this, the same kind of text the model learned from."
    )
    ctx.console.print(f"\nPrompt: [bold]{escape(text)}[/bold]")
    for step, weights in enumerate(tables):
        probs = sampling.normalize(weights)
        top4 = dict(sorted(probs.items(), key=lambda item: item[1], reverse=True)[:4])
        pick = sampling.top_word(probs)
        if step in PREDICT_AT:
            options = list(top4)
            ctx.rng.shuffle(options)
            ctx.console.print(f"\nSo far: {escape(text)} ___")
            for i, word in enumerate(options, 1):
                ctx.console.print(f"  {i}. {escape(word)}")
            question = "Your prediction: which word is most likely next?"
            guess = options[ctx.ask_choice(question, len(options), key=f"guess{step}")]
            if guess == pick:
                ctx.console.print(f"[green]Same as the model: {escape(repr(pick))}, at {probs[pick]:.0%}.[/green]")
            else:
                ctx.console.print(
                    f"The model's top pick is {escape(repr(pick))} ({probs[pick]:.0%}). "
                    f"Yours, {escape(repr(guess))}, got {probs[guess]:.0%}. "
                    "Several words fit here; the model just ranks them."
                )
        ctx.console.print(ui.bar_chart(top4, width=ctx.console.width, highlight=pick))
        text = join_token(text, pick)
        ctx.console.print(f"→ {escape(text)}")
        if step < len(tables) - 1:
            ctx.pause("Enter for the next token")
    ctx.console.print(f"\n[dim]{ui.ILLUSTRATIVE} Showing the top 4 candidates.[/dim]")
    ctx.console.print("That's all generation is: score, pick, append, repeat. A long answer is hundreds of rounds.")


CHAPTER = Chapter(
    id="1",
    title="How an LLM generates text",
    minutes=10,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(generation_demo,),
)

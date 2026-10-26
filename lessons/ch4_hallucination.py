"""Chapter 4: "Define hallucination. Users say it's confident but wrong. Fix it." (spec §6, Chapter 4)

Hands-on: watch a likely-but-wrong answer win, see temperature 0 make it win
every time, watch a model guess a fact from a patient's chart, then add the
chart and run it again. Cases come from data/hallucination.toml; all odds are illustrative.
"""

from rich.markup import escape

import sampling
import ui
from data import Hallucination
from engine import Chapter, Ctx, LearnScreen, QuickCheck, make_rng

LEARN = (
    LearnScreen(
        title="What a hallucination is",
        body=(
            "A **hallucination** is an answer that is fluent and confident but false.\n"
            "It might be a made-up fact, a wrong number, a quote nobody said, or a source that doesn't exist."
        ),
        example="Ask for sources and you may get a real-looking title, authors and year for a paper that was never written.",
        why_pm="Users can't spot a hallucination by reading it, so your product has to catch it.",
    ),
    LearnScreen(
        title="Why it happens",
        body=(
            "The model writes text that is likely, not text that has been checked. It has no built-in fact-checker.\n"
            "A wrong answer comes from the same probability bars as a right one (Chapter 1). "
            "Sometimes the most likely token is simply wrong."
        ),
        analogy="a quiz contestant who always answers, in the same confident voice, even when guessing.",
        example='"Einstein failed math" is repeated so often that it sounds right. It isn\'t true.',
        why_pm="No setting turns this off, so you design around it.",
    ),
    LearnScreen(
        title="Common causes",
        body=(
            "• Missing context: the fact it needed wasn't in the prompt. It's a common cause in "
            "products, and the one you control.\n"
            "• Past the knowledge cutoff: events after the training data ends.\n"
            "• A rare fact: one the model saw only a few times.\n"
            '• A loaded question: one that assumes an answer exists, like "Which study proves this?"'
        ),
        example="A sales assistant has no price list in its prompt. Asked what the premium plan costs, it writes a typical price, not yours.",
        why_pm="Check what you put in the prompt before you blame the model.",
    ),
    LearnScreen(
        title="Why it sounds so sure",
        body=(
            "Tone isn't a confidence signal. The model writes as fluently when it's wrong as when it's right.\n"
            "It can't flag its own guesses unless the product is built to check."
        ),
        analogy="a smooth salesperson who sounds the same whether the claim is true or not.",
        why_pm="Users trust confident text, so your product has to supply the safeguards.",
    ),
    LearnScreen(
        title="The fix toolbox",
        body=(
            "1. Give it the facts. **Grounding** means putting the right documents in the prompt and telling the "
            "model to answer only from them. Finding those documents first is **retrieval** (Chapter 7).\n"
            "2. Let it say \"I don't know\" when the facts aren't there.\n"
            "3. Ask for citations, and check them.\n"
            "4. Put a person in the loop when the stakes are high.\n\n"
            "What doesn't work: temperature 0. It repeats the top answer, right or wrong."
        ),
        example='A drug-information bot answers only from the label text it was given, cites the section, and says "not in the label" otherwise.',
        why_pm="These are product decisions, not model settings.",
    ),
    LearnScreen(
        title="Why it matters more in healthcare, legal and finance",
        body=(
            "In some fields one wrong answer is costly: a patient harmed, a contract broken, money lost.\n"
            "The costlier one mistake is, the more safeguards you need and the more often a person checks."
        ),
        example="A clinical summary with the wrong dose looks as polished as a correct one.",
        why_pm="Set the bar by the cost of one mistake, not by average quality.",
    ),
)

RECAP = (
    "A hallucination is fluent, confident output that is false.",
    "It happens because the model writes likely text and never checks facts.",
    "Missing context is a common cause, and the one you control.",
    "Fix it first by giving the model the facts: grounding, often through retrieval.",
    'Add safeguards: let it say "I don\'t know", ask for citations, and have a person check high-stakes answers.',
    "Temperature 0 doesn't fix it: it repeats the top answer, right or wrong.",
)

CHECKS = (
    QuickCheck(
        question="Your bot keeps giving one wrong answer. Someone suggests temperature 0. What happens?",
        options=(
            "The wrong answer stops",
            "You get the same wrong answer, every time",
            "The model starts checking its facts",
        ),
        answer=1,
        explanation="Temperature 0 always takes the top pick. If that pick is wrong, you get it every time.",
        screen=5,
    ),
    QuickCheck(
        question="Your HR assistant gives employees the wrong number of vacation days. Which cause do you control?",
        options=(
            "Its temperature is too high",
            "The vacation policy isn't in its prompt",
            "The model is too small",
        ),
        answer=1,
        explanation="Without your policy in the prompt, it writes a typical answer, not your company's.",
        screen=3,
    ),
)

RUNS = 20
TEMPERATURE = 0.7


def chosen_cases(ctx: Ctx) -> tuple[Hallucination, Hallucination]:
    """This run's everyday case and medical case. Seeded on their own, so every step sees the same pair."""
    everyday = [c for c in ctx.data.hallucinations if c.tag != "medical"]
    medical = [c for c in ctx.data.hallucinations if c.tag == "medical"]
    return make_rng(ctx.seed, "4/case", 0).choice(everyday), make_rng(ctx.seed, "4/case", 1).choice(medical)


def tally(ctx: Ctx, weights: dict[str, float], temperature: float, key: str) -> tuple[dict[str, float], dict[str, int]]:
    """Odds at this temperature and 20 runs. Seeded by `key`, so a later step can repeat an earlier tally."""
    probs = sampling.apply_temperature(sampling.normalize(weights), temperature)
    return probs, sampling.sample_many(probs, RUNS, make_rng(ctx.seed, f"4/{key}", 0))


def _bars(ctx: Ctx, probs: dict[str, float], answer: str | None, counts: dict[str, int] | None = None) -> None:
    """The odds as bars or, with `counts`, the tally of the runs (bar and number both from the counts)."""
    shown = probs if counts is None else {word: counts[word] / RUNS for word in probs}
    ctx.console.print(ui.bar_chart(shown, width=ctx.console.width, highlight=answer, counts=counts))


def _sharpening(ctx: Ctx, weights: dict[str, float]) -> None:
    """Why the tally can beat the bars: temperature below 1 makes the top answer more likely still."""
    base = sampling.normalize(weights)
    top = sampling.top_word(base)
    sharp = sampling.apply_temperature(base, TEMPERATURE)
    ctx.console.print(
        f"At temperature {TEMPERATURE:g} the odds sharpen: {escape(repr(top))} goes from "
        f"{base[top]:.0%} to {sharp[top]:.0%}."
    )


def watch_it_happen(ctx: Ctx) -> None:
    case, _ = chosen_cases(ctx)
    ctx.console.print("[bold]Watch it happen[/bold]")
    ctx.console.print(f"Prompt: [bold]{escape(case.prompt)}[/bold] ___")
    _bars(ctx, sampling.normalize(case.without), case.answer)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    ctx.console.print(f"The right answer is {escape(repr(case.answer))}. It isn't the model's top pick.")
    guess = ctx.ask_number(
        f"Your prediction: out of {RUNS} runs at temperature {TEMPERATURE:g}, how many give a wrong answer?",
        "guess_wrong",
        0,
        RUNS,
        integer=True,
    )
    probs, counts = tally(ctx, case.without, TEMPERATURE, "everyday")
    wrong = RUNS - counts[case.answer]
    _sharpening(ctx, case.without)
    ctx.console.print(f"\n[bold]{RUNS} runs at temperature {TEMPERATURE:g}[/bold]")
    _bars(ctx, probs, case.answer, counts)
    ctx.console.print(
        f"Wrong answers: {wrong} of {RUNS}. You guessed {guess:g}. "
        "Each wrong one reads as confidently as the right one."
    )
    ctx.console.print(ui.shows("a wrong answer comes from the same odds as a right one (Learn 2)."))


def temperature_zero(ctx: Ctx) -> None:
    case, _ = chosen_cases(ctx)
    probs, counts = tally(ctx, case.without, 0, "everyday-zero")
    top = sampling.top_word(probs)
    ctx.console.print("[bold]Does temperature 0 help?[/bold]")
    ctx.console.print(f"Same prompt, {RUNS} runs at temperature 0: {escape(case.prompt)} ___")
    _bars(ctx, probs, case.answer, counts)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    ctx.console.print(
        f"{escape(repr(top))} came up {counts[top]} of {RUNS} times. "
        f"The right answer, {escape(repr(case.answer))}, came up {counts[case.answer]}."
    )
    ctx.console.print(
        "Temperature 0 doesn't fix a hallucination. Here it makes the most likely answer win every time, "
        "and that answer is wrong. (A real API can still vary a little.)"
    )
    ctx.console.print(ui.shows("temperature changes how the model picks, not what it knows (Learn 5)."))


def healthcare(ctx: Ctx) -> None:
    _, case = chosen_cases(ctx)
    probs, counts = tally(ctx, case.without, TEMPERATURE, "medical-without")
    top = sampling.top_word(probs)
    ctx.console.print("[bold]The healthcare version[/bold]")
    ctx.console.print("A note-writing assistant fills in one line. The prompt has nothing about this patient.")
    ctx.console.print(f"Prompt: [bold]{escape(case.prompt)}[/bold] ___")
    _bars(ctx, sampling.normalize(case.without), None)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    _sharpening(ctx, case.without)
    ctx.console.print(f"\n[bold]{RUNS} runs at temperature {TEMPERATURE:g}[/bold]")
    _bars(ctx, probs, case.answer, counts)
    ctx.console.print(
        f"The chart says {escape(repr(case.answer))}. {counts[case.answer]} of {RUNS} runs said so. "
        f"The odds favor {escape(repr(top))}, a common answer, not this patient's."
    )
    ctx.console.print(ui.shows("with the fact missing, the model fills the gap with a typical answer (Learn 3)."))


def add_context(ctx: Ctx) -> None:
    _, case = chosen_cases(ctx)
    _, before = tally(ctx, case.without, TEMPERATURE, "medical-without")
    ctx.console.print("[bold]Add the context[/bold]")
    ctx.console.print("Now the prompt starts with the fact from the chart:")
    ctx.console.print(f"[bold]{escape(case.context)}\n{escape(case.prompt)}[/bold] ___")
    guess = ctx.ask_number(
        f"Your prediction: out of {RUNS} runs at temperature {TEMPERATURE:g}, how many are wrong now?",
        "guess_wrong_after",
        0,
        RUNS,
        integer=True,
    )
    probs, after = tally(ctx, case.with_context, TEMPERATURE, "medical-with")
    ctx.console.print(f"\n[bold]{RUNS} runs at temperature {TEMPERATURE:g}, with the chart[/bold]")
    _bars(ctx, probs, case.answer, after)
    ctx.console.print(f"[dim]{ui.ILLUSTRATIVE}[/dim]")
    ctx.console.print(
        f"Wrong answers: {RUNS - before[case.answer]} of {RUNS} without the chart, "
        f"{RUNS - after[case.answer]} with it. You guessed {guess:g}."
    )
    ctx.console.print(
        "The model didn't get smarter. It was handed the fact. "
        "Grounding cuts mistakes sharply but not always to zero, so high-stakes answers still need a person."
    )
    ctx.console.print(ui.shows("grounding, giving the model the facts, is the first fix (Learn 5)."))


def evals_teaser(ctx: Ctx) -> None:
    ctx.console.print("[bold]One more question[/bold] (not graded)")
    reply = ctx.ask_line("How would you measure whether the fix worked? Type a line, or press Enter to skip.")
    if reply.strip():
        ctx.state["measure"] = reply.strip()
    ctx.console.print(
        "One good way: run a fixed set of questions with known answers, say 200 real user questions, "
        "before and after the fix, and compare the wrong-answer rate. "
        "Hold medical answers to a stricter target, with clinicians checking them. "
        "A test like this is an eval, and its numbers are what you bring to a launch decision. "
        "Chapter 8 comes back to evals."
    )
    ctx.console.print(ui.shows("the costlier one mistake is, the stricter the target (Learn 6)."))


CHAPTER = Chapter(
    id="4",
    title="Hallucinations: confident but wrong",
    minutes=8,
    learn=LEARN,
    recap=RECAP,
    checks=CHECKS,
    hands_on=(watch_it_happen, temperature_zero, healthcare, add_context, evals_teaser),
)

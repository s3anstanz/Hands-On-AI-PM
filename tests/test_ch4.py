import math
import re

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import data
import engine
import sampling
import ui
from lessons import ch4_hallucination as ch4

BUNDLE = data.load_all()
EVERYDAY = [c for c in BUNDLE.hallucinations if c.tag != "medical"]
MEDICAL = [c for c in BUNDLE.hallucinations if c.tag == "medical"]


def make_ctx(io, seed=1, bundle=BUNDLE):
    return engine.Ctx(io=io, seed=seed, chapter=ch4.CHAPTER, data=bundle)


def run_step(step, io, seed=1, bundle=BUNDLE):
    ctx = make_ctx(io, seed, bundle)
    step(ctx)
    return ctx


def test_every_step_sees_the_same_pair_of_cases():
    first = ch4.chosen_cases(make_ctx(ScriptedIO(), seed=9))
    again = ch4.chosen_cases(make_ctx(ScriptedIO(), seed=9))
    assert first == again
    assert first[0].tag != "medical" and first[1].tag == "medical"


def test_watch_it_happen_counts_the_wrong_answers():
    io = ScriptedIO(overrides={"number": ["7"]})
    ctx = run_step(ch4.watch_it_happen, io, seed=4)
    case, _ = ch4.chosen_cases(ctx)
    _, counts = ch4.tally(ctx, case.without, ch4.TEMPERATURE, "everyday")
    asked = "".join(p for _, p in io.prompts)
    assert "out of 20 runs at temperature 0.7, how many give a wrong answer?" in asked
    assert f"Wrong answers: {20 - counts[case.answer]} of 20. You guessed 7." in io.output
    assert f"The right answer is '{case.answer}'" in io.output
    assert ctx.state["guess_wrong"] == 7


def test_temperature_zero_picks_the_wrong_answer_every_time():
    io = ScriptedIO()
    ctx = run_step(ch4.temperature_zero, io, seed=4)
    case, _ = ch4.chosen_cases(ctx)
    top = sampling.top_word(sampling.normalize(case.without))
    assert f"'{top}' came up 20 of 20 times. The right answer, '{case.answer}', came up 0." in io.output


def test_add_context_repeats_the_healthcare_tally():
    healthcare_io, context_io = ScriptedIO(), ScriptedIO(overrides={"number": ["1"]})
    ctx = run_step(ch4.healthcare, healthcare_io, seed=6)
    run_step(ch4.add_context, context_io, seed=6)
    _, case = ch4.chosen_cases(ctx)
    _, before = ch4.tally(ctx, case.without, ch4.TEMPERATURE, "medical-without")
    _, after = ch4.tally(ctx, case.with_context, ch4.TEMPERATURE, "medical-with")
    assert f"{before[case.answer]} of 20 runs said so." in healthcare_io.output
    assert (
        f"Wrong answers: {20 - before[case.answer]} of 20 without the chart, {20 - after[case.answer]} with it. "
        "You guessed 1."
    ) in context_io.output
    assert case.context in context_io.output


def test_evals_teaser_asks_then_explains():
    io = ScriptedIO(overrides={"optional": ["test it on real questions"]}, width=200)
    ctx = run_step(ch4.evals_teaser, io)
    assert ctx.state["measure"] == "test it on real questions"
    assert io.output.index("not graded") < io.output.index("How would you measure")
    assert "is an eval" in io.output
    assert "say 200 real user questions" in io.output  # a number to bring to a launch decision


@pytest.mark.parametrize("word, move", [("b", "back"), ("q", "quit")])
def test_evals_teaser_honors_nav_words(word, move):
    with pytest.raises(engine.LeaveStep) as left:
        run_step(ch4.evals_teaser, ScriptedIO(overrides={"optional": [word]}))
    assert left.value.move == move


@pytest.mark.parametrize("case", BUNDLE.hallucinations, ids=[c.prompt for c in BUNDLE.hallucinations])
def test_context_moves_the_odds_to_the_right_answer(case):
    without = sampling.apply_temperature(sampling.normalize(case.without), ch4.TEMPERATURE)
    with_context = sampling.apply_temperature(sampling.normalize(case.with_context), ch4.TEMPERATURE)
    assert with_context[case.answer] > without[case.answer]
    assert sampling.top_word(sampling.apply_temperature(without, 0)) != case.answer


@pytest.mark.parametrize("case", BUNDLE.hallucinations, ids=[c.prompt for c in BUNDLE.hallucinations])
@pytest.mark.parametrize("width", (40, 120))
def test_every_case_renders_in_its_steps(case, width):
    partner = MEDICAL[0] if case.tag != "medical" else EVERYDAY[0]
    bundle = data.Bundle(prompts=[], rubrics=BUNDLE.rubrics, glossary=[], hallucinations=[case, partner])
    steps = (ch4.healthcare, ch4.add_context) if case.tag == "medical" else (ch4.watch_it_happen, ch4.temperature_zero)
    for step in steps:
        io = ScriptedIO(width=width)
        run_step(step, io, bundle=bundle)
        assert case.answer in io.output
        assert not [line for line in io.output.splitlines() if cell_len(line) > width]


def test_candidate_names_fit_the_bar_chart():
    for case in BUNDLE.hallucinations:
        for word in (*case.without, *case.with_context):
            assert len(word) <= 14, f"{word!r} would be cut off in the bars"


def test_hands_on_order():
    assert ch4.CHAPTER.hands_on == (
        ch4.watch_it_happen,
        ch4.temperature_zero,
        ch4.healthcare,
        ch4.add_context,
        ch4.evals_teaser,
    )


@pytest.mark.parametrize("step", (ch4.watch_it_happen, ch4.temperature_zero, ch4.healthcare, ch4.add_context))
def test_every_step_with_odds_says_they_are_illustrative(step):
    io = ScriptedIO(width=200)
    run_step(step, io)
    assert ui.ILLUSTRATIVE in io.output


BAR_ROW = re.compile(r"^\s*(.+?) ([█·]+) +(\d+)×$")


@pytest.mark.parametrize("step", (ch4.watch_it_happen, ch4.temperature_zero, ch4.healthcare, ch4.add_context))
@pytest.mark.parametrize("seed", range(12))
def test_tally_bars_are_drawn_from_the_counts(step, seed):
    io = ScriptedIO(width=120)
    run_step(step, io, seed=seed)
    rows = [BAR_ROW.match(line) for line in io.output.splitlines()]
    tallies = [(int(m[3]), m[2].count("█")) for m in rows if m]
    assert tallies
    for count, filled in tallies:
        assert filled == math.floor(count / ch4.RUNS * 30 + 0.5), (count, filled)  # 30 cells at 120 columns


@pytest.mark.parametrize("seed", range(12))
def test_healthcare_caption_matches_the_odds_not_a_claim_about_the_sample(seed):
    io = ScriptedIO(width=200)
    ctx = run_step(ch4.healthcare, io, seed=seed)
    _, case = ch4.chosen_cases(ctx)
    top = sampling.top_word(sampling.normalize(case.without))
    assert f"The odds favor '{top}'" in io.output
    assert "the model writes the most common answer" not in io.output


@pytest.mark.parametrize("step, pick", [(ch4.watch_it_happen, 0), (ch4.healthcare, 1)])
def test_reveal_explains_how_temperature_sharpens_the_odds(step, pick):
    io = ScriptedIO(width=200)
    ctx = run_step(step, io, seed=4)
    case = ch4.chosen_cases(ctx)[pick]
    base = sampling.normalize(case.without)
    top = sampling.top_word(base)
    sharp = sampling.apply_temperature(base, ch4.TEMPERATURE)
    assert f"'{top}' goes from {base[top]:.0%} to {sharp[top]:.0%}" in io.output


@pytest.mark.parametrize("step, key", [(ch4.watch_it_happen, "guess_wrong"), (ch4.add_context, "guess_wrong_after")])
def test_run_count_predictions_take_whole_numbers(step, key):
    io = ScriptedIO(overrides={"number": ["7.5", "7"]}, width=200)
    ctx = run_step(step, io)
    assert "Please type a whole number from 0 to 20." in io.output
    assert ctx.state[key] == 7 and "You guessed 7." in io.output


@pytest.mark.parametrize("step", ch4.CHAPTER.hands_on)
def test_every_hands_on_step_says_what_it_shows(step):
    io = ScriptedIO(width=200)
    run_step(step, io)
    caption = next(line for line in io.output.splitlines() if line.startswith("What this shows: "))
    assert re.search(r"\(Learn \d\)\.$", caption), caption

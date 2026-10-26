import dataclasses
import itertools

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import costs
import data
import engine
import pricing
from lessons import ch7_context as ch7

BUNDLE = data.load_all()


def run_step(step, io, seed=1, bundle=BUNDLE):
    ctx = engine.Ctx(io=io, seed=seed, chapter=ch7.CHAPTER, data=bundle)
    step(ctx)
    return ctx


def flat(io):
    return " ".join(io.output.split())


def test_learn_copy_takes_the_window_from_pricing():
    assert pricing.get("sonnet-5-5").context_window == ch7.CLAUDE_WINDOW
    assert f"up to {ch7.short_tokens(ch7.CLAUDE_WINDOW)} tokens" in ch7.LEARN[0].body
    assert f"{ch7.CLAUDE_WINDOW_WORDS:,} words" in ch7.LEARN[0].body


@pytest.mark.parametrize("count, text", [(2_000, "2K"), (500_000, "500K"), (1_000_000, "1M"), (1_234, "1,234")])
def test_short_tokens(count, text):
    assert ch7.short_tokens(count) == text


def test_window_keeps_the_newest_messages_that_fit():
    messages = [("You", "one two three"), ("Assistant", "four five six"), ("You", "seven eight nine")]
    each = ch7.message_tokens("one two three")
    assert ch7.window_start(messages, window=3 * each) == 0
    assert ch7.window_start(messages, window=2 * each) == 1
    assert ch7.window_start(messages, window=each - 1) == 3


def test_learn_screens_dont_give_away_the_predictions():
    learn = " ".join(f"{s.body} {s.example} {s.analogy} {s.why_pm}" for s in ch7.LEARN)
    assert "×" not in learn and "times cheaper" not in learn
    assert str(ch7.WINDOW) not in learn


def test_the_first_message_always_falls_out_before_the_question():
    for name, allergy in ch7.PROFILES:
        first = (ch7.FIRST.format(name=name, allergy=allergy), ch7.FIRST_REPLY.format(name=name, allergy=allergy))
        messages = [
            (who, text) for pair in (first, *ch7.CHAT) for who, text in zip(("You", "Assistant"), pair, strict=True)
        ]
        assert ch7.window_start(messages) > 0
        assert ch7.message_tokens(first[0]) + ch7.message_tokens(first[1]) <= ch7.WINDOW


def test_the_allergy_is_out_of_the_window_by_the_question_in_every_order():
    # The canned answer says it can't see the allergy, so the first message and the reply that
    # repeats the allergy must both be gone, whatever order the questions come in.
    for name, allergy in ch7.PROFILES:
        first = (ch7.FIRST.format(name=name, allergy=allergy), ch7.FIRST_REPLY.format(name=name, allergy=allergy))
        for order in itertools.permutations(ch7.CHAT):
            pairs = (first, *order)
            messages = [(who, text) for pair in pairs for who, text in zip(("You", "Assistant"), pair, strict=True)]
            assert ch7.window_start([*messages, ("You", ch7.QUESTION)]) >= 2, (name, order)


def test_watch_it_forget_reveals_the_turn_and_the_failed_answer():
    io = ScriptedIO(overrides={"number": ["4"]}, width=120)
    ctx = run_step(ch7.watch_it_forget, io, seed=3)
    assert ctx.state["guess_turns"] == 4
    turn = int(flat(io).split("Your first message fell out after ")[1].split(" ")[0])
    assert ch7.verdict(4, turn) in flat(io)
    assert "A simulated clinic chat" in flat(io)
    assert "✗ You: Hi, I'm" in io.output
    assert "I don't see an allergy anywhere in our chat." in flat(io)
    assert [kind for kind, _ in io.prompts].count("pause") == len(ch7.CHAT)


def test_the_fall_out_turn_varies_with_the_seed():
    turns = set()
    for seed in range(30):
        io = ScriptedIO(width=120)
        run_step(ch7.watch_it_forget, io, seed=seed)
        turns.add(flat(io).split("Your first message fell out after ")[1].split(" ")[0])
    assert len(turns) > 1


def test_cost_per_request_shows_the_haiku_tier_jump():
    io = ScriptedIO(width=120)
    run_step(ch7.cost_per_request, io)
    haiku = pricing.get("haiku-5-5")
    jump = ch7.input_cost(haiku, 500_000) / ch7.input_cost(haiku, 50_000)
    assert f"it grows {jump:.0f}×" in flat(io)
    assert costs.format_usd(ch7.input_cost(pricing.get("opus-5-5"), 500_000)) in io.output
    assert f"prices checked {pricing.LAST_CHECKED}" in io.output


def test_recall_curve_is_labeled_illustrative():
    io = ScriptedIO(width=120)
    run_step(ch7.recall_curve, io)
    assert ch7.RECALL_LABEL in flat(io)
    assert io.output.index(ch7.RECALL_LABEL.split(":")[0]) < io.output.index("█")  # in the text, before the bars
    values = [p for _, p in ch7.RECALL]
    middle = values[len(values) // 2]
    assert middle == min(values) and values[0] > middle < values[-1]


def only(scenario_id):
    return dataclasses.replace(BUNDLE, scenarios=[s for s in BUNDLE.scenarios if s.id == scenario_id])


@pytest.mark.parametrize("scenario_id", [s.id for s in BUNDLE.scenarios])
def test_paste_vs_fetch_for_every_scenario(scenario_id):
    io = ScriptedIO(overrides={"number": ["5"]}, width=40)
    bundle = only(scenario_id)
    run_step(ch7.paste_vs_fetch, io, bundle=bundle)
    _, work = ch7.chosen_scenario(engine.Ctx(io=ScriptedIO(), seed=1, chapter=ch7.CHAPTER, data=bundle))
    paste = costs.request_cost(ch7.REFERENCE, costs.Usage(work.input_tokens + work.docs_tokens, work.output_tokens))
    fetch = costs.request_cost(
        ch7.REFERENCE, costs.Usage(work.input_tokens + ch7.FETCHED_PAGES * ch7.PAGE_TOKENS, work.output_tokens)
    )
    paste_k, fetch_k = round(paste.total * 1000, 2), round(fetch.total * 1000, 2)  # as shown, per 1,000
    ratio = round(paste_k / fetch_k)
    assert f"Fetching is {ratio}× cheaper per request." in flat(io)
    assert ch7.verdict(5, ratio, "×") in flat(io)
    month = [round(k * work.requests_per_day * costs.DAYS_PER_MONTH / 1000, 2) for k in (paste_k, fetch_k)]
    assert f"that's {costs.format_usd(month[0])} vs. {costs.format_usd(month[1])} a month" in flat(io)
    assert f"prices checked {pricing.LAST_CHECKED}" in io.output


def test_every_scenario_fits_the_claude_window_when_pasted():
    for scenario in BUNDLE.scenarios:
        assert scenario.input_tokens[1] + scenario.docs_tokens[1] + scenario.output_tokens[1] <= ch7.CLAUDE_WINDOW


def test_hands_on_order():
    assert ch7.CHAPTER.hands_on == (ch7.watch_it_forget, ch7.cost_per_request, ch7.recall_curve, ch7.paste_vs_fetch)


@pytest.mark.parametrize("scenario_id", [s.id for s in BUNDLE.scenarios])
def test_every_step_fits_40_columns_and_says_what_it_shows(scenario_id):
    for step in ch7.CHAPTER.hands_on:
        io = ScriptedIO(width=40)
        run_step(step, io, bundle=only(scenario_id))
        assert all(cell_len(line) <= 40 for line in io.output.splitlines()), step.__name__
        assert "What this shows:" in flat(io), step.__name__
    io = ScriptedIO(width=120)
    run_step(ch7.paste_vs_fetch, io, bundle=only(scenario_id))
    assert "(illustrative usage)" in flat(io)


def test_learn_recap_and_sample_answer_agree_on_the_figure_and_the_advice():
    rubric = engine.Ctx(io=ScriptedIO(), seed=1, chapter=ch7.CHAPTER, data=BUNDLE).rubric
    figure = f"up to {ch7.short_tokens(ch7.CLAUDE_WINDOW)} tokens"
    assert figure in ch7.LEARN[0].body and figure in ch7.RECAP[0] and figure in rubric.sample_answer
    assert f"{ch7.CLAUDE_WINDOW_WORDS:,} words" in rubric.sample_answer
    assert ch7.short_tokens(ch7.CLAUDE_WINDOW) in rubric.hint
    assert ch7.RECOMMENDATION in ch7.RECAP[4] and ch7.RECOMMENDATION in rubric.sample_answer


def test_the_tradeoff_item_is_gradable():
    assert BUNDLE.rubrics["7"].checklist[4].startswith("Names at least one benefit of retrieval")


@pytest.mark.parametrize("step, key", [("watch_it_forget", "guess_turns"), ("paste_vs_fetch", "guess_fetch")])
def test_predictions_take_whole_numbers(step, key):
    io = ScriptedIO(overrides={"number": ["2.5", "3"]}, width=120)
    ctx = run_step(getattr(ch7, step), io)
    assert ctx.state[key] == 3
    assert "Please type a whole number from 1 to" in io.output


def test_captions_tie_back_to_a_learn_screen():
    for step, screen in zip(ch7.CHAPTER.hands_on, (3, 4, 4, 5), strict=True):
        io = ScriptedIO(width=120)
        run_step(step, io)
        assert f"(Learn {screen})" in flat(io).split("What this shows: ")[1], step.__name__

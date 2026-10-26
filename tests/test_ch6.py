import dataclasses
from types import SimpleNamespace

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import costs
import data
import engine
import pricing
import ui
from lessons import ch6_cost as ch6

BUNDLE = data.load_all()


def run_step(step, io, live=None, seed=1, bundle=BUNDLE):
    ctx = engine.Ctx(io=io, seed=seed, chapter=ch6.CHAPTER, data=bundle, live=live)
    step(ctx)
    return ctx


def flat(io):
    """The output with line wrapping undone, so phrase checks don't depend on where Rich breaks lines."""
    return " ".join(io.output.split())


def scenario_for(seed):
    return ch6.chosen_scenario(engine.Ctx(io=ScriptedIO(), seed=seed, chapter=ch6.CHAPTER, data=BUNDLE))


def only(scenario_id):
    return dataclasses.replace(BUNDLE, scenarios=[s for s in BUNDLE.scenarios if s.id == scenario_id])


def test_learn_ratios_hold_on_every_claude_5_5_model():
    # Learn screen 1 and 4 state one output and one cache-write multiplier for all Claude 5.5 models.
    for model in ch6.CLAUDE_5_5:
        assert ch6.times(model.output / model.input) == ch6.OUTPUT_TIMES
        assert ch6.times((model.cache_write_5m or 0) / model.input) == ch6.WRITE_5M_TIMES
        assert ch6.times((model.cache_write_1h or 0) / model.input) == ch6.WRITE_1H_TIMES
        assert model.batch_discount == ch6.REFERENCE.batch_discount


def test_learn_copy_is_computed_from_pricing():
    billed, caching, batch, unit = (ch6.LEARN[i] for i in (0, 3, 4, 7))
    assert f"costs {ch6.OUTPUT_TIMES} as much" in billed.body
    assert costs.format_usd(ch6.WORKED.total) in billed.example and pricing.LAST_CHECKED in billed.example
    assert ch6.cache_read_by_model() in caching.body
    assert f"{ch6.REFERENCE.batch_discount:.0%} less" in batch.body
    assert pricing.LAST_CHECKED in unit.example
    assert "$" not in " ".join(f"{s.body} {s.why_pm} {s.analogy}" for s in ch6.LEARN)


def test_cache_read_groups_models_with_the_same_multiplier():
    assert ch6.cache_read_by_model() == "0.05× on Opus 5.5 and Sonnet 5.5, 0.1× on Haiku 5.5"


def test_learn_screens_dont_give_away_the_predictions():
    learn = " ".join(f"{s.body} {s.example} {s.analogy} {s.why_pm}" for s in ch6.LEARN)
    assert "× a single" not in learn and "times a single" not in learn
    assert "saves more" not in learn


def test_same_seed_same_scenario():
    assert scenario_for(9) == scenario_for(9)
    assert len({scenario_for(seed)[0].id for seed in range(40)}) > 1


def test_input_vs_output_shows_both_halves_with_the_date():
    io = ScriptedIO(width=120)
    run_step(ch6.input_vs_output, io, seed=3)
    scenario, work = scenario_for(3)
    cost = costs.request_cost(ch6.REFERENCE, costs.Usage(work.input_tokens, work.output_tokens))
    assert scenario.name in flat(io)
    assert costs.format_usd(cost.output * ch6.PER_THOUSAND) in flat(io)
    assert f"{cost.output / cost.total:.0%} of the cost" in flat(io)
    assert f"prices checked {pricing.LAST_CHECKED}" in flat(io)


def test_history_growth_reveals_the_ratio_after_the_guess():
    io = ScriptedIO(overrides={"number": ["10"]}, width=120)
    ctx = run_step(ch6.history_growth, io, seed=4)
    _, work = scenario_for(4)
    one = costs.chat_cost(ch6.REFERENCE, 1, work.system_tokens, work.output_tokens)
    ten = costs.chat_cost(ch6.REFERENCE, 10, work.system_tokens, work.output_tokens)
    ratio = round(round(ten * ch6.PER_THOUSAND, 2) / round(one * ch6.PER_THOUSAND, 2))
    assert f"That's {ratio}× the cost for 10× the messages." in flat(io)
    assert ch6.verdict(10, ratio, "×") in flat(io)
    assert ctx.state["guess_chat"] == 10
    assert io.output.count("Turn ") == ch6.CHAT_TURNS
    last = costs.chat_input_per_turn(ch6.CHAT_TURNS, work.system_tokens, work.output_tokens)[-1]
    assert f"{last:,}" in flat(io)


def test_cache_break_even_for_each_claude_model():
    io = ScriptedIO(width=120)
    run_step(ch6.cache_break_even, io, seed=2)
    for model in ch6.CLAUDE_5_5:
        assert f"{costs.cache_break_even_uses(model, '5m')} uses" in flat(io)
    assert f"prices checked {pricing.LAST_CHECKED}" in flat(io)


@pytest.mark.parametrize("scenario_id", [s.id for s in BUNDLE.scenarios])
def test_caching_or_batch_names_the_bigger_saving(scenario_id):
    io = ScriptedIO(width=120)
    run_step(ch6.caching_or_batch, io, bundle=only(scenario_id))
    _, work = ch6.chosen_scenario(engine.Ctx(io=ScriptedIO(), seed=1, chapter=ch6.CHAPTER, data=only(scenario_id)))
    full, cached, batched = ch6.lever_costs(work)
    assert f"Caching saves {costs.format_usd(full - cached)} a month" in flat(io)
    assert f"batch saves {costs.format_usd(full - batched)}" in flat(io)
    answer = ch6.lever_verdict(work)
    shown = f"You predicted caching the repeated start; actual: {ch6.LEVERS[answer].lower()}."
    said = {0: " Right.", 1: " Not quite.", 2: " Close: the two are within 10% of each other."}[answer]
    assert shown + said in flat(io)


def test_lever_costs_are_whole_cents_so_the_savings_add_up():
    for seed in range(50):
        for cost in ch6.lever_costs(scenario_for(seed)[1]):
            assert cost == round(cost, 2)


@pytest.mark.parametrize(
    "guess, actual, shown",
    [
        (10, 14, "You guessed 10×; actual 14×; off by 4×."),
        (20, 14, "You guessed 20×; actual 14×; off by 6×."),
        (14, 14, "You guessed 14×; actual 14×: spot on."),
        (2.5, 3, "You guessed 2.5×; actual 3×; off by 0.5×."),
        (5, 6, "You guessed 5; actual 6; off by 1."),
    ],
)
def test_verdict(guess, actual, shown):
    unit = "" if shown.endswith("off by 1.") else "×"
    assert ch6.verdict(guess, actual, unit) == shown


def test_quick_checks_vary_the_answer_slot_and_quote_the_ratio():
    assert len({check.answer for check in ch6.CHECKS}) == len(ch6.CHECKS)
    assert ch6.OUTPUT_TIMES in ch6.CHECKS[0].explanation


@pytest.mark.parametrize("scenario_id", [s.id for s in BUNDLE.scenarios])
def test_input_vs_output_parts_add_up_to_the_total(scenario_id):
    for seed in range(20):
        io = ScriptedIO(width=120)
        run_step(ch6.input_vs_output, io, seed=seed, bundle=only(scenario_id))
        rows = {
            line.split()[0]: line.split()[-1]
            for line in io.output.splitlines()
            if line.split() and line.split()[0] in ("Input", "Output", "Total") and line.rstrip()[-1].isdigit()
        }
        cents = {name: round(float(shown.strip("$").replace(",", "")) * 100) for name, shown in rows.items()}
        assert cents["Input"] + cents["Output"] == cents["Total"]


def test_every_verdict_comes_up_across_seeds():
    # The prediction is only worth asking if the answer depends on the scenario.
    assert {ch6.lever_verdict(scenario_for(seed)[1]) for seed in range(300)} == {0, 1, 2}


def test_hands_on_order_so_far():
    assert ch6.CHAPTER.hands_on[:4] == (
        ch6.input_vs_output,
        ch6.history_growth,
        ch6.cache_break_even,
        ch6.caching_or_batch,
    )


def test_calculator_shows_every_model_and_ends_on_enter():
    io = ScriptedIO(width=120)
    run_step(ch6.calculator, io, seed=5)
    for model in pricing.MODELS.values():
        assert ui.model_label(model.display_name) in flat(io)
    assert [kind for kind, _ in io.prompts] == ["optional"]
    assert f"prices checked {pricing.LAST_CHECKED}" in flat(io)


def test_calculator_recomputes_after_a_change():
    io = ScriptedIO(overrides={"optional": ["1", ""], "number": ["1,000"]}, width=120)
    ctx = run_step(ch6.calculator, io, seed=5)
    assert ctx.state["calc_requests"] == 1000
    settings = {name: ctx.state[f"calc_{name}"] for name, *_ in ch6.FIELDS}
    sonnet = next(cost for model, cost, _ in ch6.calculator_rows(settings) if model is ch6.REFERENCE)
    assert costs.format_usd(sonnet) in flat(io).split("Change which line?")[1]


def test_calculator_batch_toggle_marks_models_without_a_batch_price():
    io = ScriptedIO(overrides={"optional": ["5", ""]}, width=120)
    ctx = run_step(ch6.calculator, io, seed=5)
    assert ctx.state["calc_batch"] == 1
    assert "GPT-6 Astra*" in flat(io)
    assert "No batch price in pricing.py for this model" in flat(io)


def test_calculator_flags_requests_too_long_for_a_model():
    settings = {"requests": 10, "input": 500_000, "output": 1_000, "cache_hit": 0, "batch": 0, "thinking": 0}
    rows = {model.key: cost for model, cost, _ in ch6.calculator_rows(settings)}
    assert rows["haiku-4-5"] is None  # a 200K window
    assert rows["sonnet-5-5"] is not None


def test_calculator_handles_every_extreme_without_crashing():
    for batch in (0, 1):  # every model, with and without batch and cache prices
        for hit in (0, 100):
            for size in (1, 1_000_000):
                settings = {"requests": 10_000_000, "input": size, "output": 1, "cache_hit": hit, "batch": batch}
                assert len(ch6.calculator_rows({**settings, "thinking": 0})) == len(pricing.MODELS)
    io = ScriptedIO(
        overrides={"optional": ["2", "3", "6", "4", ""], "number": ["1000000", "128000", "128000", "100"]}, width=40
    )
    run_step(ch6.calculator, io, seed=5)
    assert "too long" in flat(io)


@pytest.mark.parametrize("prompt_kind, replies", [("optional", ["q"]), ("number", ["q"])])
def test_q_at_either_calculator_prompt_leaves_the_step(prompt_kind, replies):
    overrides = {"optional": ["2"], prompt_kind: replies} if prompt_kind == "number" else {prompt_kind: replies}
    with pytest.raises(engine.LeaveStep):
        run_step(ch6.calculator, ScriptedIO(overrides=overrides, width=120), seed=5)


def test_calculator_usage_splits_cached_input():
    usage = ch6.calculator_usage({"input": 4000, "output": 300, "cache_hit": 25, "batch": 1, "thinking": 50})
    assert (usage.input_tokens, usage.cache_read_tokens, usage.thinking_tokens, usage.batch) == (3000, 1000, 50, True)


def test_calculator_counts_are_whole_numbers_but_cache_hit_is_not():
    replies = ["1.9", "7", "2.5", "8", "3.5", "9", "40.5", "1.5", "2"]
    io = ScriptedIO(overrides={"optional": ["1", "2", "3", "4", "6", ""], "number": replies}, width=120)
    ctx = run_step(ch6.calculator, io, seed=5)
    assert [ctx.state[f"calc_{n}"] for n in ("requests", "input", "output", "cache_hit", "thinking")] == [
        7,
        8,
        9,
        40.5,
        2,
    ]
    assert io.output.count("Please type a whole number") == 4


def _small_prefix_settings(cache_hit):
    return {"requests": 10, "input": 1000, "output": 100, "cache_hit": cache_hit, "batch": 0, "thinking": 0}


def test_cache_discount_needs_the_models_minimum_cacheable_prefix():
    sonnet, haiku = pricing.get("sonnet-5-5"), pricing.get("haiku-4-5")
    assert sonnet.min_cache_tokens and haiku.min_cache_tokens
    below = {**_small_prefix_settings(0), "input": sonnet.min_cache_tokens * 2}
    full = {name: cost for model, cost, _ in ch6.calculator_rows({**below, "cache_hit": 100}) for name in [model.key]}
    none = {name: cost for model, cost, _ in ch6.calculator_rows({**below, "cache_hit": 0}) for name in [model.key]}
    assert full["sonnet-5-5"] < none["sonnet-5-5"]  # at or above its minimum: discounted
    assert full["haiku-4-5"] == none["haiku-4-5"]  # under Haiku 4.5's larger minimum: regular input


def test_cache_minimum_boundary_is_inclusive():
    model = pricing.get("haiku-4-5")
    minimum = model.min_cache_tokens
    assert minimum
    at = costs.Usage(input_tokens=0, output_tokens=1, cache_read_tokens=minimum)
    under = costs.Usage(input_tokens=0, output_tokens=1, cache_read_tokens=minimum - 1)
    assert costs.apply_cache_minimum(model, at) == at
    assert costs.apply_cache_minimum(model, under) == costs.Usage(input_tokens=minimum - 1, output_tokens=1)
    assert costs.apply_cache_minimum(pricing.get("gpt-6-luna"), under) == under  # no figure verified: untouched


def test_calculator_says_when_other_providers_minimums_are_not_modeled():
    io = ScriptedIO(width=120)
    run_step(ch6.calculator, io, seed=5)
    assert "Caching minimums aren't modeled for OpenAI and Google" in flat(io)


def fake_live(count=None, error=""):
    return SimpleNamespace(count_tokens=lambda text, model_id: count, spent=0.0, last_error=error)


def test_crossing_providers_offline_uses_the_estimate():
    io = ScriptedIO(width=120)
    run_step(ch6.crossing_providers, io, seed=6)
    for key in ch6.CROSSING:
        assert ui.model_label(pricing.get(key).display_name) in flat(io)
    assert "estimate: Claude's tokenizer isn't public" in flat(io)
    assert "Prices double on 2027-01-01" in flat(io)  # the Gemini Flash note
    assert f"prices checked {pricing.LAST_CHECKED}" in flat(io)


def test_crossing_providers_live_uses_the_official_count():
    io = ScriptedIO(width=120)
    run_step(ch6.crossing_providers, io, live=fake_live(count=300), seed=6)
    assert "about 300 on Claude (official, from count_tokens)" in flat(io)


def test_crossing_providers_live_failure_falls_back():
    io = ScriptedIO(width=120)
    run_step(ch6.crossing_providers, io, live=fake_live(error="no network"), seed=6)
    assert "Official Claude count unavailable: no network. Using the estimate." in flat(io)


@pytest.mark.parametrize("scenario_id", [s.id for s in BUNDLE.scenarios])
def test_every_scenario_runs_every_step_at_40_columns(scenario_id):
    for step in ch6.CHAPTER.hands_on:
        io = ScriptedIO(width=40)
        run_step(step, io, bundle=only(scenario_id))
        assert all(cell_len(line) <= 40 for line in io.output.splitlines()), step.__name__
        assert "What this shows:" in flat(io), step.__name__
        assert "(illustrative usage)" in flat(io) or "usage numbers are illustrative" in flat(io), step.__name__


def test_hands_on_order():
    assert ch6.CHAPTER.hands_on == (
        ch6.input_vs_output,
        ch6.history_growth,
        ch6.cache_break_even,
        ch6.caching_or_batch,
        ch6.calculator,
        ch6.crossing_providers,
    )


def test_calculator_caption_quotes_the_spread_between_models():
    io = ScriptedIO(width=120)
    ctx = run_step(ch6.calculator, io, seed=5)
    settings = {name: ctx.state[f"calc_{name}"] for name, *_ in ch6.FIELDS}
    priced = [cost for _, cost, _ in ch6.calculator_rows(settings) if cost]
    spread = round(max(priced) / min(priced))
    assert f"What this shows: the same workload costs {spread:,}× as much on the priciest model" in flat(io)


def test_calculator_caption_when_no_model_can_take_the_request():
    io = ScriptedIO(overrides={"optional": ["3", "6", ""], "number": ["128000", "128000"]}, width=120)
    run_step(ch6.calculator, io, seed=5)
    assert "What this shows: a request this long doesn't fit" in flat(io)


@pytest.mark.parametrize(
    "answer, pick, said",
    [
        (0, "1", "actual: caching the repeated start. Right."),
        (1, "1", "actual: batch (50% off, answers later). Not quite."),
        (2, "2", "actual: about the same. Close: the two are within 10% of each other."),
    ],
)
def test_lever_reveal_gives_a_verdict(answer, pick, said):
    seed = next(seed for seed in range(300) if ch6.lever_verdict(scenario_for(seed)[1]) == answer)
    io = ScriptedIO(overrides={"choice": [pick]}, width=120)
    run_step(ch6.caching_or_batch, io, seed=seed)
    assert said in flat(io)


def test_learn_recap_and_sample_answer_agree_on_the_figure_and_the_advice():
    # The learner leaves with one number (output costs 5× input) and one recommendation to say out loud.
    rubric = engine.Ctx(io=ScriptedIO(), seed=1, chapter=ch6.CHAPTER, data=BUNDLE).rubric
    figure = f"costs {ch6.OUTPUT_TIMES} as much as an input token"
    assert figure in ch6.LEARN[0].body and figure in ch6.RECAP[0] and figure in rubric.sample_answer
    assert ch6.OUTPUT_TIMES in rubric.hint
    assert ch6.RECOMMENDATION in ch6.RECAP[3] and ch6.RECOMMENDATION in rubric.sample_answer


def test_list_items_in_the_checklist_say_how_many_count():
    # "Names levers: a, b, c, d" can't be graded from a typed answer; "names at least two of" can.
    checklist = BUNDLE.rubrics["6"].checklist
    assert checklist[1].startswith("Names at least one hidden cost") and checklist[3].startswith("Names at least two")


def test_the_chat_prediction_takes_whole_numbers():
    io = ScriptedIO(overrides={"number": ["2.5", "5"]}, width=120)
    ctx = run_step(ch6.history_growth, io, seed=4)
    assert ctx.state["guess_chat"] == 5
    assert "Please type a whole number from 1 to 100." in io.output


def test_captions_tie_back_to_a_learn_screen():
    for step, screen in ((ch6.input_vs_output, 1), (ch6.history_growth, 3), (ch6.cache_break_even, 4)):
        io = ScriptedIO(width=120)
        run_step(step, io)
        caption = flat(io).split("What this shows: ")[1]
        assert f"(Learn {screen})" in caption, step.__name__


def test_calculator_shows_each_model_note_next_to_its_price():
    # Spec §8.1: a model's note (e.g. Gemini 3.8 Flash's 2027-01-01 price change) is shown wherever its price is.
    io = ScriptedIO(width=120)
    run_step(ch6.calculator, io, seed=5)
    for model in pricing.MODELS.values():
        if model.note:
            assert f"{ui.model_label(model.display_name)}: {model.note}" in flat(io), model.key
    assert "2027-01-01" in flat(io)


def test_no_cache_note_when_nothing_is_cached():
    io = ScriptedIO(width=120)
    ctx = engine.Ctx(io=io, seed=5, chapter=ch6.CHAPTER, data=BUNDLE)
    settings = {"requests": 10, "input": 4000, "output": 300, "cache_hit": 0, "batch": 0, "thinking": 0}
    ch6._cache_notes(ctx, settings, list(pricing.MODELS.values()))
    assert "minimum cacheable" not in flat(io)

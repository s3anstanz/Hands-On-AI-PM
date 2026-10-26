import math
import re

import pytest
from helpers import ScriptedIO
from rich.console import Console

import costs
import data
import engine
import pricing
from lessons import ch5_model_choice as ch5

BUNDLE = data.load_all()


def make_ctx(io, seed=1):
    return engine.Ctx(io=io, seed=seed, chapter=ch5.CHAPTER, data=BUNDLE)


def run_step(step, io, seed=1):
    ctx = make_ctx(io, seed)
    step(ctx)
    return ctx


def test_pick_sizes_reveals_three_jobs():
    io = ScriptedIO(overrides={"choice": ["1", "2", "3"]}, width=200)
    run_step(ch5.pick_sizes, io)
    shown = [job for job in ch5.JOBS if job[0] in io.output]
    assert len(shown) == 3
    for _, _, reason in shown:
        assert reason in io.output


def test_every_job_has_a_size_and_a_reason():
    assert len(ch5.JOBS) >= 6
    assert all(size in ch5.SIZES and job and reason for job, size, reason in ch5.JOBS)
    assert not any("ticket" in job for job, _, _ in ch5.JOBS)  # Quick check 2 already asks about tickets


def test_comparison_table_shows_real_prices_and_labels_the_ratings():
    io = ScriptedIO(width=120)
    run_step(ch5.comparison_table, io)
    out = io.output
    for key in ch5.TABLE_MODELS:
        model = pricing.get(key)
        assert ch5.short_name(key) in out and costs.format_usd(model.output) in out
    assert {pricing.get(key).provider for key in ch5.TABLE_MODELS} == {"anthropic", "openai", "google"}
    assert f"prices checked {pricing.LAST_CHECKED}" in out
    assert "Ratings out of 5 (illustrative)" in out
    assert f"Per token, Opus 5.5 costs {ch5.PRICE_RATIO:g}× Haiku 5.5." in out
    assert ch5.PRICE_RATIO == 40  # hand-checked against pricing.py


def test_race_math():
    assert ch5.tokens_shown(1.0, first_token=4.0, per_second=200) == 0
    assert ch5.tokens_shown(2.0, first_token=0.5, per_second=50) == 75
    assert ch5.tokens_shown(60.0, first_token=0.5, per_second=50) == ch5.RACE_TOKENS
    assert ch5.finish_time(0.5, 50) == 8.5 and ch5.finish_time(4.0, 200) == 6.0


def test_speed_race_shows_stills_without_sleeping_when_not_a_terminal(monkeypatch):
    monkeypatch.setattr(ch5.time, "sleep", lambda seconds: pytest.fail("slept outside a terminal"))
    io = ScriptedIO(width=80)
    run_step(ch5.speed_race, io)
    assert "After 2 seconds:" in io.output and "After 6 seconds:" in io.output
    assert "thinking..." in io.output and "75/400" in io.output
    assert "Illustrative: two made-up models" in io.output


def test_speed_race_animates_in_a_terminal(monkeypatch):
    naps = []
    monkeypatch.setattr(ch5.time, "sleep", naps.append)
    io = ScriptedIO(width=80)
    io.console = Console(file=io.console.file, width=80, force_terminal=True, color_system=None)
    run_step(ch5.speed_race, io)
    end = max(ch5.finish_time(first, rate) for _, first, rate in ch5.RACERS)
    assert len(naps) == math.ceil(end / ch5.SIM_STEP) + 1 and set(naps) == {ch5.FRAME_SECONDS}
    assert f"Time: {end:.1f} s" in io.output
    assert "After 2 seconds:" not in io.output


def test_workload_is_shared_by_the_routing_steps():
    assert ch5.workload(make_ctx(ScriptedIO(), seed=3)) == ch5.workload(make_ctx(ScriptedIO(), seed=3))


def saving(ctx):
    per_day, usage, share = ch5.workload(ctx)
    small, large = pricing.get(ch5.SMALL), pricing.get(ch5.LARGE)
    all_large = costs.monthly_cost(large, usage, per_day)
    return all_large, all_large - costs.routed_monthly_cost(small, large, usage, per_day, share)


@pytest.mark.parametrize("seed", range(40))
def test_saving_options_are_distinct_named_mistakes_and_one_is_larger(seed):
    all_large, right = saving(make_ctx(ScriptedIO(), seed=seed))
    _, _, share = ch5.workload(make_ctx(ScriptedIO(), seed=seed))
    ratio = 1 / ch5.PRICE_RATIO
    options = ch5.saving_options(all_large, share, ratio, make_rng_for(seed))
    assert options[0] == (pytest.approx(right), "")
    assert len({ch5.whole_usd(amount) for amount, _ in options}) == 4
    assert all(mistake for _, mistake in options[1:])
    assert any(amount > right for amount, _ in options[1:])  # picking the biggest number isn't a strategy


def make_rng_for(seed):
    return engine.make_rng(seed, "test", 0)


def test_the_right_saving_sits_at_different_ranks():
    ranks = set()
    for seed in range(40):
        all_large, right = saving(make_ctx(ScriptedIO(), seed=seed))
        _, _, share = ch5.workload(make_ctx(ScriptedIO(), seed=seed))
        amounts = sorted(
            amount for amount, _ in ch5.saving_options(all_large, share, 1 / ch5.PRICE_RATIO, make_rng_for(seed))
        )
        ranks.add(amounts.index(min(amounts, key=lambda a: abs(a - right))))
    assert len(ranks) > 1


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("choice", ["1", "2", "3", "4"])
def test_routing_predict_echoes_the_pick_and_names_the_mistake(seed, choice):
    io = ScriptedIO(overrides={"choice": [choice]}, width=200)
    ctx = run_step(ch5.routing_predict, io, seed=seed)
    _, right = saving(ctx)
    listed = [
        line.split(". ", 1)[1].removesuffix(" a month")
        for line in io.output.splitlines()
        if line[:4] in ("  1.", "  2.", "  3.", "  4.")
    ]
    picked = listed[int(choice) - 1]
    assert f"You picked {picked}" in io.output
    if picked == ch5.whole_usd(right):
        assert "Right." in io.output
    else:
        assert f"The saving is {ch5.whole_usd(right)}" in io.output and "That number " in io.output
    assert f"prices checked {pricing.LAST_CHECKED}" in io.output


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("share", (*ch5.TABLE_SHARES, 0.3, 0.505, 0.996))
def test_routing_rows_add_up_to_the_all_large_bill(seed, share):
    per_day, usage, _ = ch5.workload(make_ctx(ScriptedIO(), seed=seed))
    per_month, saved = ch5.routing_row(per_day, usage, share)
    all_large, _ = ch5.routing_row(per_day, usage, 0.0)
    assert per_month + saved == all_large


def test_routing_calculator_echoes_the_share_typed():
    io = ScriptedIO(overrides={"optional": ["30", "50.5", "150", ""]}, width=120)
    ctx = run_step(ch5.routing_calculator, io, seed=2)
    per_day, usage, _ = ch5.workload(ctx)
    for typed, share in (("30", 0.3), ("50.5", 0.505)):
        per_month, saved = ch5.routing_row(per_day, usage, share)
        assert f"{typed}% easy: {ch5.whole_usd(per_month)} a month, {ch5.whole_usd(saved)} saved." in io.output
    assert "Please type a number from 0 to 100, or press Enter to move on." in io.output


def test_fast_mode_prices_come_from_pricing():
    io = ScriptedIO(width=120)
    ctx = run_step(ch5.fast_mode, io, seed=2)
    per_day, usage, _ = ch5.workload(ctx)
    opus = pricing.get("opus-5-5")
    fast = (
        usage.input_tokens * pricing.OPUS_FAST_MODE_INPUT + usage.output_tokens * pricing.OPUS_FAST_MODE_OUTPUT
    ) / 1e6
    assert f"{ch5.whole_usd(fast * per_day * 30)} in fast mode" in io.output
    assert f"{ch5.whole_usd(costs.monthly_cost(opus, usage, per_day))} a month standard" in io.output
    assert "Pay 2× the price for up to 2.5× faster streaming" in io.output
    for length in ch5.ANSWER_LENGTHS:
        standard = ch5.OPUS_FIRST_TOKEN_SECONDS + length / ch5.OPUS_TOKENS_PER_SECOND
        quick = ch5.OPUS_FIRST_TOKEN_SECONDS + length / (ch5.OPUS_TOKENS_PER_SECOND * pricing.OPUS_FAST_MODE_SPEEDUP)
        row = next(line for line in io.output.splitlines() if f" {length:,} tokens " in line)
        assert row.split("│")[2:4] == [f"{standard:.1f} s".rjust(9) + " ", f"{quick:.1f} s".rjust(10) + " "]
    assert "made up" in io.output  # the race models aren't Opus
    assert "Claude" not in io.output


def test_full_cost_counts_review():
    io = ScriptedIO(width=120)
    run_step(ch5.full_cost, io)
    assert "$43,236" in io.output and "$15,120" in io.output  # hand-checked: 60,000 drafts a month
    assert "costs 2.9× as much in total" in io.output
    assert f"prices checked {pricing.LAST_CHECKED}" in io.output
    assert "$60 an hour" in io.output
    before_table = io.output.split("┏")[0]
    assert "illustrative" in before_table and "reads every draft" in before_table  # the hidden assumption
    assert "below 4.2%" in io.output  # hand-checked: (15,120 - 36) / 360,000 per 100% = 4.19%


def test_lesson_copy_types_no_dollar_figures():
    import re
    from pathlib import Path

    source = Path(ch5.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\$\d", source), "dollar figures come from pricing.py"


def test_hands_on_order():
    assert ch5.CHAPTER.hands_on == (
        ch5.pick_sizes,
        ch5.comparison_table,
        ch5.speed_race,
        ch5.routing_predict,
        ch5.routing_calculator,
        ch5.fast_mode,
        ch5.full_cost,
    )


def test_race_bars_round_halves_up_like_the_odds_bars():
    console = Console(width=40, color_system=None)
    with console.capture() as capture:
        console.print(ch5.race_frame(4.5, width=40))  # Thinks first: 100 of 400 tokens on a 10-cell bar
    thinks_first = next(line for line in capture.get().splitlines() if "Thinks first" in line)
    assert "███·······" in thinks_first


def test_race_says_the_streaming_speeds():
    io = ScriptedIO(width=200)
    run_step(ch5.speed_race, io)
    assert "then 50 tokens a second" in io.output and "then 200 tokens a second, 4× as fast" in io.output


@pytest.mark.parametrize("seed", range(5))
def test_hands_on_uses_short_model_names(seed):
    for step in ch5.CHAPTER.hands_on:
        io = ScriptedIO(width=200)
        run_step(step, io, seed=seed)
        assert "Claude " not in io.output, step.__name__


@pytest.mark.parametrize(
    "size, pick, why",
    [("small", "3", "costs more and is slower"), ("large", "1", "would likely fall short")],
)
def test_job_feedback_says_why_a_pick_is_or_isnt_defensible(size, pick, why, monkeypatch):
    job = next(j for j in ch5.JOBS if j[1] == size)
    monkeypatch.setattr(ch5, "JOBS", (job, job, job))
    io = ScriptedIO(overrides={"choice": [pick] * 3}, width=200)
    run_step(ch5.pick_sizes, io)
    assert why in io.output and job[2] in io.output


def test_comparison_footnotes_are_plain_and_say_when_a_pricier_model_pays():
    io = ScriptedIO(width=200)
    run_step(ch5.comparison_table, io)
    for jargon in ("standard tier", "higher rate", "Cache storage"):
        assert jargon not in io.output
    assert "Prices double on 2027-01-01" in io.output
    assert "measured win on your task" in io.output


@pytest.mark.parametrize("step", ch5.CHAPTER.hands_on)
def test_every_hands_on_step_says_what_it_shows(step):
    io = ScriptedIO(width=200)
    run_step(step, io)
    caption = next(line for line in io.output.splitlines() if line.startswith("What this shows: "))
    assert re.search(r"\(Learn \d( and \d)?\)\.$", caption), caption


@pytest.mark.parametrize("racer", ch5.RACERS, ids=[r[0] for r in ch5.RACERS])
def test_the_first_token_shows_at_the_stated_first_token_time(racer):
    # The race states each model's time to first token; the frame at that moment must show a token,
    # not "thinking..." (Codex review on #29).
    _, first_token, per_second = racer
    assert ch5.tokens_shown(first_token - ch5.SIM_STEP, first_token, per_second) == 0
    assert ch5.tokens_shown(first_token, first_token, per_second) == 1
    end = ch5.finish_time(first_token, per_second)
    assert ch5.tokens_shown(end, first_token, per_second) == ch5.RACE_TOKENS
    assert ch5.tokens_shown(end - 0.01, first_token, per_second) < ch5.RACE_TOKENS

import dataclasses
import itertools
import re

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import costs
import data
import engine
import pricing
from lessons import ch8_design_feature as ch8

BUNDLE = data.load_all()
SCENARIOS = {s.id: s for s in BUNDLE.scenarios}


def bundle_with(*scenarios):
    return dataclasses.replace(BUNDLE, scenarios=list(scenarios))


def make_ctx(io, seed=1, bundle=BUNDLE, **state):
    ctx = engine.Ctx(io=io, seed=seed, chapter=ch8.CHAPTER, data=bundle)
    ctx.state.update(state)
    return ctx


def scenario(**changes):
    return dataclasses.replace(SCENARIOS["support-bot"], **changes)


def workload(**changes):
    base = data.Workload(
        users=1_000,
        requests_per_user=4,
        input_tokens=2_000,
        output_tokens=400,
        system_tokens=1_200,
        docs_tokens=50_000,
    )
    return dataclasses.replace(base, **changes)


def design(model="sonnet-5-5", effort="medium", temperature=None, context="fetch", caching=False, batch=False):
    return ch8.Design(pricing.get(model), effort, temperature, context, caching, batch)


def test_worked_example_is_computed_and_not_a_scenario():
    example = ch8.LEARN[3]
    assert costs.format_usd(ch8.example_monthly_cost()) in example.body
    assert f"prices checked {pricing.LAST_CHECKED}" in example.body
    for s in BUNDLE.scenarios:
        assert "hotel" not in f"{s.name} {s.pitch}".lower()
    assert not re.search(r"\$\d", "".join(s.body + s.example for s in ch8.LEARN[:3]))


def test_the_draw_is_seeded_and_every_step_sees_the_same_one():
    first = ch8.chosen_scenario(make_ctx(ScriptedIO(), seed=9))
    assert first == ch8.chosen_scenario(make_ctx(ScriptedIO(), seed=9))
    picks = {ch8.chosen_scenario(make_ctx(ScriptedIO(), seed=seed))[0].id for seed in range(40)}
    assert len(picks) >= 4  # different seeds give different scenarios


@pytest.mark.parametrize(
    "needs_facts, context, hot, domain, expected",
    [
        (False, "none", False, "general", "low"),
        (False, "none", True, "general", "low"),
        (True, "none", False, "general", "high"),
        (True, "paste", True, "general", "high"),
        (True, "fetch", True, "general", "high"),
        (True, "paste", False, "general", "low"),
        (True, "fetch", False, "general", "low"),
        (True, "fetch", False, "medical", "medium"),
        (True, "paste", False, "legal", "medium"),
        (True, "none", False, "medical", "high"),
        (False, "none", False, "legal", "medium"),
    ],
)
def test_hallucination_risk_rule(needs_facts, context, hot, domain, expected):
    assert ch8.hallucination_risk(needs_facts, context, hot, domain) == expected


def test_usage_none_sends_only_the_request():
    usage = ch8.usage_for(workload(), design(context="none", effort="low"))
    assert usage == costs.Usage(input_tokens=2_000, output_tokens=400)


def test_usage_paste_with_caching_caches_only_the_system_prompt():
    usage = ch8.usage_for(workload(), design(context="paste", effort="low", caching=True))
    assert usage.cache_read_tokens == round(1_200 * ch8.CACHE_HIT_RATE)
    assert usage.cache_write_tokens == 1_200 - usage.cache_read_tokens
    assert usage.input_tokens == 2_000 - 1_200 + 50_000  # the documents change every request: uncached
    assert usage.prompt_tokens == 2_000 + 50_000


def test_paste_all_with_caching_prices_the_documents_at_the_uncached_rate():
    model = pricing.get("sonnet-5-5")
    work = workload()
    cached = ch8.usage_for(work, design(context="paste", effort="low", caching=True))
    docs_cached_too = costs.Usage(
        input_tokens=2_000 - 1_200,
        output_tokens=400,
        cache_read_tokens=round(51_200 * ch8.CACHE_HIT_RATE),
        cache_write_tokens=51_200 - round(51_200 * ch8.CACHE_HIT_RATE),
    )
    assert costs.request_cost(model, cached).total > costs.request_cost(model, docs_cached_too).total


def test_paste_all_with_caching_still_reads_the_documents_before_the_first_token():
    model = pricing.get("sonnet-5-5")
    paste = ch8.usage_for(workload(), design(context="paste", effort="low", caching=True))
    start = ch8.first_token_seconds(model, "low", paste)
    start_without_docs = ch8.first_token_seconds(
        model, "low", ch8.usage_for(workload(), design(context="none", effort="low", caching=True))
    )
    assert start - start_without_docs >= 50_000 / ch8.READING_TOKENS_PER_SECOND


def test_usage_fetch_adds_a_few_pages_and_effort_adds_thinking():
    usage = ch8.usage_for(workload(), design(context="fetch", effort="high", batch=True))
    assert usage.input_tokens == 2_000 + ch8.FETCHED_TOKENS
    assert usage.thinking_tokens == 400 * ch8.THINKING_PER_ANSWER_TOKEN["high"]
    assert usage.batch
    tiny = ch8.usage_for(workload(docs_tokens=500), design(context="fetch"))
    assert tiny.input_tokens == 2_000 + 500  # can't fetch more than there is


def test_usage_with_a_temperature_model_has_no_thinking():
    usage = ch8.usage_for(workload(), design(model="haiku-4-5", effort=None, temperature=0.0))
    assert usage.thinking_tokens == 0


def test_first_token_seconds_scales_with_effort_and_reads_the_uncached_prompt():
    model = pricing.get("opus-5-5")
    usage = costs.Usage(input_tokens=100_000, output_tokens=500, cache_write_tokens=50_000, cache_read_tokens=900_000)
    reading = 150_000 / ch8.READING_TOKENS_PER_SECOND  # cache reads aren't re-read
    assert ch8.first_token_seconds(model, "medium", usage) == pytest.approx(2.0 + reading)
    assert ch8.first_token_seconds(model, "high", usage) == pytest.approx(4.0 + reading)
    assert ch8.first_token_seconds(model, None, usage) == ch8.first_token_seconds(model, "medium", usage)


def test_opus_timing_is_chapter_5s():
    from lessons import ch5_model_choice as ch5

    opus = pricing.get("opus-5-5")  # medium is Opus 5.5's default effort, which Chapter 5's timing stands for
    assert ch8.first_token_seconds(opus, "medium", costs.Usage(0, 0)) == ch5.OPUS_FIRST_TOKEN_SECONDS
    assert ch8.first_token_seconds(opus, "high", costs.Usage(0, 0)) <= 4.0  # Chapter 5's slowest starter


def test_brief_shows_the_numbers_and_the_stakes():
    medical = SCENARIOS["medical-note-summarizer"]
    io = ScriptedIO(width=120)
    ctx = make_ctx(io, bundle=bundle_with(medical))
    ch8.brief(ctx)
    _, d = ch8.chosen_scenario(ctx)
    out = io.output
    assert f"Design an AI feature for: {medical.name}" in out
    assert f"({d.requests_per_day:,} requests a day)" in out and f"{d.docs_tokens:,} tokens" in out
    assert "High stakes: a wrong answer can hurt a patient." in out
    assert "nobody is waiting" in out
    assert "(illustrative usage)" in out  # the numbers are drawn, not measured


def test_design_asks_effort_on_models_that_fix_temperature():
    io = ScriptedIO(overrides={"choice": ["2", "3", "3", "2"]})
    ctx = make_ctx(io)
    ch8.design(ctx)
    asked = [p for kind, p in io.prompts if kind == "choice"]
    assert [p.split(" [")[0] for p in asked] == ["Model", "Effort", "Context", "Caching and batch"]
    assert "Claude Sonnet 5.5 doesn't let you change temperature (Chapter 3)." in io.output
    assert f"prices checked {pricing.LAST_CHECKED}" in io.output
    assert ch8.chosen_design(ctx) == design(model="sonnet-5-5", effort="high", context="fetch", caching=True)


def test_design_asks_temperature_where_the_model_takes_it(monkeypatch):
    monkeypatch.setattr(ch8, "MODEL_CHOICES", ("haiku-4-5", "sonnet-5-5"))
    io = ScriptedIO(overrides={"choice": ["1", "3", "1", "1"]})
    ctx = make_ctx(io)
    ch8.design(ctx)
    asked = [p.split(" [")[0] for kind, p in io.prompts if kind == "choice"]
    assert asked == ["Model", "Temperature", "Context", "Caching and batch"]
    choice = ch8.chosen_design(ctx)
    assert choice.temperature == 1.0 and choice.effort is None


def test_going_back_to_the_design_offers_each_earlier_pick():
    io = ScriptedIO(overrides={"choice": ["2", "3", "3", "2", "", "", "", ""]})
    ctx = make_ctx(io)
    ch8.design(ctx)
    first = ch8.chosen_design(ctx)
    ch8.design(ctx)
    assert ch8.chosen_design(ctx) == first
    assert "(Enter keeps: 2)" in [p for kind, p in io.prompts if kind == "choice"][4]


def run_outcome(scenario_obj, width=120, seed=1, **state):
    io = ScriptedIO(width=width)
    ctx = make_ctx(io, seed=seed, bundle=bundle_with(scenario_obj), **state)
    ch8.outcome(ctx)
    return io.output, ctx


def test_outcome_cost_comes_from_costs_py():
    out, ctx = run_outcome(SCENARIOS["support-bot"], model=1, effort=1, context=2, saving=1)
    (_, d), choice = ch8.chosen_scenario(ctx), ch8.chosen_design(ctx)
    monthly = costs.monthly_cost(choice.model, ch8.usage_for(d, choice), d.requests_per_day)
    assert (
        f"Monthly cost: {costs.format_usd(monthly)}, about {costs.format_usd(monthly / d.users)} per user a month"
        in out
    )
    assert f"prices checked {pricing.LAST_CHECKED}" in out
    assert "(illustrative)" in out and "Same choices, each model" in out
    assert "What this shows:" in out


def test_outcome_table_row_for_your_model_matches_the_headline():
    out, ctx = run_outcome(SCENARIOS["support-bot"], model=1, effort=1, context=2, saving=1)
    (_, d), choice = ch8.chosen_scenario(ctx), ch8.chosen_design(ctx)
    monthly = costs.format_usd(costs.monthly_cost(choice.model, ch8.usage_for(d, choice), d.requests_per_day))
    row = next(line for line in out.splitlines() if "Sonnet 5.5" in line and "←" in line)
    assert monthly in row


def test_outcome_without_documents_on_a_facts_task_is_high_risk():
    out, _ = run_outcome(SCENARIOS["support-bot"], model=0, effort=0, context=0, saving=0)
    assert "Hallucination risk: HIGH." in out


def test_outcome_flags_batch_when_someone_is_waiting():
    out, _ = run_outcome(scenario(latency="interactive"), model=0, effort=0, context=2, saving=2)
    assert "Batch doesn't fit here: someone is waiting for each answer." in out


def test_outcome_suggests_batch_when_nobody_waits():
    out, _ = run_outcome(scenario(latency="background"), model=0, effort=0, context=2, saving=0)
    assert "Nobody is waiting, so batch would take 50% off." in out


def test_outcome_confirms_batch_when_nobody_waits():
    out, _ = run_outcome(scenario(latency="background"), model=0, effort=0, context=2, saving=2)
    assert "Nobody is waiting, so batch is the right call." in out


def test_outcome_says_when_pasting_everything_does_not_fit():
    huge = scenario(docs_tokens=(2_000_000, 2_000_000))
    out, _ = run_outcome(huge, model=1, effort=0, context=1, saving=0)
    assert "Doesn't fit:" in out and "Fetch what's relevant instead." in out
    assert out.count("doesn't fit") == len(ch8.MODEL_CHOICES)  # every row of the table


def test_outcome_notes_haiku_tier_when_the_prompt_crosses_it():
    big = scenario(docs_tokens=(200_000, 200_000))
    out, _ = run_outcome(big, model=0, effort=0, context=1, saving=0)
    assert pricing.get("haiku-5-5").note in out


@pytest.mark.parametrize("scenario_id", list(SCENARIOS))
def test_every_scenario_renders_every_design_at_40_columns(scenario_id):
    s = SCENARIOS[scenario_id]
    for model, effort, context, saving in itertools.product(
        range(len(ch8.MODEL_CHOICES)), range(len(ch8.EFFORTS)), range(len(ch8.CONTEXTS)), range(len(ch8.SAVINGS))
    ):
        out, _ = run_outcome(s, width=40, model=model, effort=effort, context=context, saving=saving)
        assert "Hallucination risk:" in out
        assert all(cell_len(line) <= 40 for line in out.splitlines())


def test_high_temperature_on_a_facts_task_is_high_risk(monkeypatch):
    monkeypatch.setattr(ch8, "MODEL_CHOICES", ("haiku-4-5", "sonnet-5-5"))
    out, _ = run_outcome(SCENARIOS["support-bot"], model=0, temperature=2, context=2, saving=0)
    assert "Hallucination risk: HIGH. A high temperature picks less likely words more often" in out
    assert "temperature 1" in out  # the design line names the setting


def test_hands_on_order():
    assert ch8.CHAPTER.hands_on == (ch8.brief, ch8.design, ch8.outcome)


def test_follow_ups_are_two_from_the_scenario_and_one_general():
    for seed in range(20):
        ctx = make_ctx(ScriptedIO(), seed=seed)
        picks = ch8.chosen_followups(ctx)
        own = ch8.chosen_scenario(ctx)[0].followups
        assert len(picks) == ch8.FOLLOWUPS == 3
        assert picks[0] in own and picks[1] in own and picks[0] != picks[1]
        assert picks[2] in BUNDLE.rubrics["8"].followups
        assert picks == ch8.chosen_followups(make_ctx(ScriptedIO(), seed=seed))


def test_full_run_asks_three_follow_ups_then_the_evals_teaser():
    io = ScriptedIO(width=120)
    ctx = engine.Ctx(io=io, seed=8808, chapter=ch8.CHAPTER, data=BUNDLE)
    assert engine.run_chapter(ctx) == "done"
    out = io.output
    assert [f"Follow-up {n} of 3" in out for n in (1, 2, 3)] == [True] * 3
    assert out.count("Reviewer:") == 4  # three follow-ups and the evals question
    assert out.index("Self-score:") < out.index("Follow-up 1 of 3") < out.index("How would you prove the cheaper")
    assert "A future chapter covers them." in out
    for n in (1, 2, 3):
        assert ctx.state[f"followup{n}"]


def test_after_grade_is_three_follow_ups_then_the_teaser():
    assert len(ch8.CHAPTER.after_grade) == ch8.FOLLOWUPS + 1
    assert ch8.CHAPTER.after_grade[-1] is ch8.evals_teaser


def test_outcome_counts_the_answer_against_the_context_window():
    # The prompt alone fits; prompt plus answer doesn't.
    s = scenario(docs_tokens=(990_000, 990_000), output_tokens=(20_000, 20_000))
    out, _ = run_outcome(s, model=1, effort=0, context=1, saving=0)
    assert "Doesn't fit:" in out and "Monthly cost" not in out
    assert "prompt and answer" in out


def test_outcome_says_when_the_answer_is_longer_than_the_model_can_write():
    s = scenario(output_tokens=(200_000, 200_000))
    out, _ = run_outcome(s, model=1, effort=0, context=2, saving=0)
    assert "Doesn't fit:" in out and "output limit" in out and "Monthly cost" not in out


def test_thinking_tokens_count_toward_the_limits():
    work = workload(output_tokens=60_000)
    assert ch8.fits(pricing.get("sonnet-5-5"), ch8.usage_for(work, design(effort="low")))
    assert not ch8.fits(pricing.get("sonnet-5-5"), ch8.usage_for(work, design(effort="high")))  # 4 x 60,000 > 128,000

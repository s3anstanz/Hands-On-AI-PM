import math
import re

import pytest
from helpers import ScriptedIO

import data
import engine
import pricing
import sampling
import tokens
import ui
from lessons import ch3_temperature as ch3

BUNDLE = data.load_all()


def run_step(step, io, live=None, seed=1, bundle=BUNDLE):
    ctx = engine.Ctx(io=io, seed=seed, chapter=ch3.CHAPTER, data=bundle, live=live)
    step(ctx)
    return ctx


def test_every_step_uses_the_same_prompt_for_a_seed():
    first = ch3.chosen_prompt(engine.Ctx(io=ScriptedIO(), seed=9, chapter=ch3.CHAPTER, data=BUNDLE))
    again = ch3.chosen_prompt(engine.Ctx(io=ScriptedIO(), seed=9, chapter=ch3.CHAPTER, data=BUNDLE))
    assert first == again
    assert abs(sum(first[1].values()) - 1) < 1e-9


def test_temperature_predict_reveals_the_tally():
    io = ScriptedIO(overrides={"number": ["7"]})
    run_step(ch3.temperature_predict, io, seed=4)
    _, probs = ch3.chosen_prompt(engine.Ctx(io=ScriptedIO(), seed=4, chapter=ch3.CHAPTER, data=BUNDLE))
    top = sampling.top_word(probs)
    assert f"how many of 20 runs say '{top}'?" in "".join(p for _, p in io.prompts)
    assert "You guessed 7." in io.output and "came up" in io.output


@pytest.mark.parametrize("prompt", BUNDLE.prompts, ids=[p.text for p in BUNDLE.prompts])
def test_every_prompt_renders_at_every_predict_temperature(prompt):
    bundle = data.Bundle(prompts=[prompt], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    for seed in range(6):  # several seeds, so several of the predict temperatures
        io = ScriptedIO(width=40)
        run_step(ch3.temperature_predict, io, seed=seed, bundle=bundle)
        assert "came up" in io.output


@pytest.mark.parametrize("step", ["temperature_predict", "temperature_slider", "zero_predict", "trim"])
def test_every_screen_with_bars_labels_them_illustrative(step):
    io = ScriptedIO(overrides={"optional": ["1", ""]})
    run_step(getattr(ch3, step), io)
    assert ui.ILLUSTRATIVE in io.output


def tally_rows(output, title):
    """(word, filled bar cells, count) for each row of the chart under `title`."""
    rows = []
    for line in output.split(title, 1)[1].splitlines()[1:]:
        row = re.fullmatch(r"\s*(.+?) ([█·]+) +(\d+)×", line)
        if row is None:
            break
        rows.append((row[1], row[2].count("█"), int(row[3])))
    return rows


@pytest.mark.parametrize("seed", range(5))
def test_run_tallies_draw_the_bars_from_the_counts(seed):
    io = ScriptedIO(width=40)  # bar width 10
    run_step(ch3.temperature_predict, io, seed=seed)
    title = next(line for line in io.output.splitlines() if line.startswith("At temperature") and "runs" in line)
    rows = tally_rows(io.output, title)
    assert sum(count for _, _, count in rows) == ch3.RUNS
    assert all(filled == math.floor(count / ch3.RUNS * 10 + 0.5) for _, filled, count in rows)


def test_slider_shows_the_reshaped_odds():
    io = ScriptedIO(overrides={"optional": ["0", ""]})
    run_step(ch3.temperature_slider, io)
    assert "100%" in io.output and "×" not in io.output


def test_trim_says_when_top_p_keeps_every_word():
    keeps_all = data.PromptTable("Even", "test", {"a": 30, "b": 25, "c": 25, "d": 20}, ())
    bundle = data.Bundle(prompts=[keeps_all], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    io = ScriptedIO()
    run_step(ch3.trim, io, bundle=bundle)
    assert (
        "Here top-p = 0.9 keeps every word, because it takes all of them to reach 90%. The odds don't change."
        in io.output
    )
    assert "dimmed" not in io.output
    assert "rescaled" not in io.output and "goes up" not in io.output  # nothing was cut, so no chance rises


def test_trim_explains_dimmed_words_when_top_p_drops_some():
    drops_one = data.PromptTable("Skewed", "test", {"a": 80, "b": 15, "c": 5}, ())
    bundle = data.Bundle(prompts=[drops_one], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    io = ScriptedIO()
    run_step(ch3.trim, io, bundle=bundle)
    assert "Dimmed words can't be picked at all, however lucky the roll." in io.output
    assert "Top-p = 0.9 keeps: a, b · cut: c" in io.output  # named, so no-color terminals show the cut too
    covered = re.search(
        r"The kept words cover (\d+)% of the odds\. Top-p adds words until they reach at least 90%\.", io.output
    )
    assert covered and int(covered[1]) >= 90
    assert "The kept odds are then rescaled to add up to 100%" in io.output
    assert "keeps every word" not in io.output


@pytest.mark.parametrize("typed, title", [("1e-310", "At temperature 1e-310"), ("-0", "At temperature 0\n")])
def test_slider_survives_tiny_and_negative_zero_temperatures(typed, title):
    io = ScriptedIO(overrides={"optional": [typed, ""]})
    run_step(ch3.temperature_slider, io)
    assert title in io.output and "100%" in io.output
    assert "-0" not in io.output and "nan" not in io.output.lower()


def test_slider_reshapes_until_enter():
    io = ScriptedIO(overrides={"optional": ["0", "2", "3", ""]})
    run_step(ch3.temperature_slider, io)
    assert io.output.count("At temperature") >= 2
    assert "Please type a number from 0 to 2, or press Enter to move on." in io.output


def test_temperature_zero_gives_one_answer():
    io = ScriptedIO(overrides={"number": ["5"]})
    run_step(ch3.zero_predict, io)
    assert "1 different answer in 20 runs" in io.output and "You guessed 5." in io.output


def test_trim_lists_what_top_k_and_top_p_keep():
    io = ScriptedIO()
    run_step(ch3.trim, io, seed=2)
    _, probs = ch3.chosen_prompt(engine.Ctx(io=ScriptedIO(), seed=2, chapter=ch3.CHAPTER, data=BUNDLE))
    kept_k = [w for w, p in sampling.top_k(probs, 2).items() if p > 0]
    assert "Top-k = 2 keeps: " + ", ".join(sorted(kept_k, key=lambda w: -probs[w])) in io.output
    assert "Top-p = 0.9 keeps: " in io.output


def test_cards_reveal_every_reason():
    io = ScriptedIO(overrides={"choice": ["1", "2", "3", "1"]}, width=120)
    run_step(ch3.cards, io)
    shown = [card for card in ch3.CARDS if card[0] in io.output]
    assert len(shown) == 4
    for _, _, reason in shown:
        assert reason in io.output


def show_settings(width):
    io = ScriptedIO(width=width)
    screen = next(s for s in ch3.LEARN if s.visual is not None)
    screen.visual(engine.Ctx(io=io, seed=1, chapter=ch3.CHAPTER, data=BUNDLE))
    return io.output


def test_settings_are_plain_lines_on_narrow_terminals():
    out = show_settings(40)
    assert "┃" not in out and "…" not in out
    flat = " ".join(out.split())
    for setting, when, examples in ch3.SETTINGS_ROWS:
        assert f"{setting} · {when} · {examples}" in flat
    assert all(not line.startswith(",") for line in out.splitlines())  # "Extraction," keeps its comma


def test_settings_are_a_table_on_wide_terminals():
    out = show_settings(80)
    assert "┃ Temperature" in out and all(row[0] in out for row in ch3.SETTINGS_ROWS)


def test_settings_table_teaches_every_setting_the_cards_grade():
    labels = [row[0].lower() for row in ch3.SETTINGS_ROWS]
    assert all(any(label.startswith(setting) for label in labels) for setting in ch3.SETTINGS)
    assert all(word in ch3.LEARN[5].body for word in ("Low", "Medium", "Higher"))


def test_cards_match_the_settings_copy():
    cards = {task: (setting, reason) for task, setting, reason in ch3.CARDS}
    assert cards["Write a SQL query from a question"] == ("low", "You want the same, tested query every time.")
    assert cards["Summarize a meeting for the team"] == ("low", "A summary should stick to what was said.")


def test_learn_copy_matches_the_api_reference():
    # sdk-upgrade.md: Opus 4.7 and later 400 on any sampling parameter, the default included;
    # Sonnet 5.5 and Haiku 5.5 reject only non-default values (Haiku 5.5 allows temperature 1 only).
    assert "Opus 5.5 doesn't accept a temperature at all. Sonnet 5.5 rejects anything but the default." in (
        ch3.LEARN[6].body
    )
    assert "Haiku 5.5 requires temperature 1 and rejects top-k." in ch3.LEARN[6].body
    assert not any(pricing.get(key).accepts_temperature for key in ("opus-5-5", "sonnet-5-5", "haiku-5-5"))
    assert "caps the output cost" in ch3.LEARN[4].body
    glossary = {g.term: g.definition for g in BUNDLE.glossary}
    assert "caps the output cost" in glossary["max_tokens"]


def test_every_card_has_a_valid_setting():
    assert len(ch3.CARDS) >= 6
    assert all(setting in ch3.SETTINGS and task and reason for task, setting, reason in ch3.CARDS)


def test_length_limits_cut_with_real_tokens():
    io = ScriptedIO(width=120)
    run_step(ch3.length_limits, io)
    assert "max_tokens = 12" in io.output
    assert "Answer: Paris" in io.output and "Explanation" not in io.output.split("Stop sequence")[1]
    count, label = tokens.openai_count(ch3.LONG_ANSWER)
    flat = " ".join(io.output.split())
    assert f"You pay for 12 output tokens instead of {count}. Counted with {label}." in flat


def test_length_limits_cut_never_holds_more_than_max_tokens(monkeypatch):
    # a piece made of 2 tokens must not push the cut past max_tokens
    monkeypatch.setattr(tokens, "split_with_counts", lambda text: [("a", 5), ("b", 5), ("c", 2), ("d", 1)])
    io = ScriptedIO(width=120)
    run_step(ch3.length_limits, io)
    assert "abc ▌" in io.output and "abcd" not in io.output


def test_length_limits_without_the_tokenizer_say_the_cut_is_in_words(monkeypatch):
    monkeypatch.setattr(tokens, "_encoding", False)
    io = ScriptedIO(width=120)
    run_step(ch3.length_limits, io)
    assert "about 12 words" in " ".join(io.output.split())


def test_hands_on_order_offline():
    assert ch3.CHAPTER.hands_on[:6] == (
        ch3.temperature_predict,
        ch3.temperature_slider,
        ch3.zero_predict,
        ch3.trim,
        ch3.cards,
        ch3.length_limits,
    )
    assert ch3.CHAPTER.hands_on[6] is ch3.live_run


class FakeLive:
    def __init__(self, answers=None, error=""):
        self.calls = []
        self.answers = answers
        self.last_error = error
        self.spent = 0.0

    def temperature_run(self, prompt, temperature, n):
        self.calls.append((prompt, temperature, n))
        if self.answers is None:
            return []
        return self.answers.get(temperature, [])[:n]  # fewer than n means the batch failed; last_error says why


def test_live_run_offline_just_explains():
    io = ScriptedIO()
    run_step(ch3.live_run, io)
    assert "needs an Anthropic key" in io.output
    assert not any(kind == "yesno" for kind, _ in io.prompts)


def test_live_run_asks_with_the_cost_first_and_shows_both_temperatures():
    fake = FakeLive({0.0: ["blue"] * 10, 1.0: ["blue"] * 6 + ["clear"] * 3 + ["gray"]})
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=fake)
    ask = next(p for kind, p in io.prompts if kind == "yesno")
    assert "Run 20 real requests on Claude Haiku 4.5?" in ask
    assert f"prices checked {pricing.LAST_CHECKED}" in ask
    assert fake.calls == [("The sky is", 0.0, 10), ("The sky is", 1.0, 10)]
    assert "Temperature 0: 1 different answer" in io.output and "Temperature 1: 3 different answers" in io.output


def test_live_run_declined_spends_nothing():
    fake = FakeLive({0.0: ["blue"] * 10, 1.0: ["blue"] * 10})
    io = ScriptedIO(overrides={"yesno": ["n"]})
    run_step(ch3.live_run, io, live=fake)
    assert fake.calls == []


def test_live_run_failure_is_one_line_and_moves_on():
    fake = FakeLive(None, error="model not found: claude-haiku-4-5 may have been retired")
    io = ScriptedIO(overrides={"yesno": ["y"]})
    run_step(ch3.live_run, io, live=fake)
    assert "Live run unavailable: model not found: claude-haiku-4-5 may have been retired." in io.output
    assert len(fake.calls) == 1


def test_live_cost_estimate_comes_from_pricing():
    model = pricing.by_api_id(pricing.LIVE_TEMPERATURE_MODEL)
    per_request = model.input * 40 / 1_000_000 + model.output * 5 / 1_000_000
    assert abs(ch3.live_cost_estimate() - per_request * 20) < 1e-12


def test_live_run_keeps_the_paid_answers_when_the_second_batch_fails():
    fake = FakeLive({0.0: ["blue"] * 10}, error="rate limited; try again in a minute")
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=fake)
    out = io.output
    assert "Temperature 0" in out and "blue" in out and "Temperature 0: 1 different answer" in out
    assert "Temperature 1:" not in out
    assert "Live run unavailable: rate limited; try again in a minute." in out
    assert out.index("Temperature 0: 1 different answer") < out.index("Live run unavailable")


def test_live_run_shows_the_partial_batch_that_failed_midway():
    fake = FakeLive({0.0: ["blue"] * 10, 1.0: ["blue", "clear", "gray"]}, error="rate limited; try again in a minute")
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=fake)
    out = io.output
    assert "Temperature 1: 3 different answers" in out and "clear" in out and "gray" in out
    assert "Live run unavailable: rate limited; try again in a minute." in out
    assert "Here temperature" not in out  # no closing verdict on an incomplete run


@pytest.mark.parametrize(
    "zero, one, said",
    [
        (
            ["blue"] * 10,
            ["blue"] * 6 + ["clear"] * 3 + ["gray"],
            "temperature 0 gave 1 different answer and temperature 1 gave 3.",
        ),
        (
            ["blue"] * 5 + ["gray"] * 5,
            ["blue"] * 10,
            "temperature 0 gave 2 different answers and temperature 1 gave 1.",
        ),
    ],
)
def test_live_run_caption_reports_what_happened(zero, one, said):
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=FakeLive({0.0: zero, 1.0: one}))
    flat = " ".join(io.output.split())
    assert f"Here {said} Usually 0 is more consistent than 1." in flat


def test_live_run_counts_answers_ignoring_case_and_punctuation():
    fake = FakeLive({0.0: ["Blue", "blue.", "BLUE!"] + ["blue"] * 7, 1.0: ["blue"] * 5 + ["Clear."] * 5})
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=fake)
    assert "Temperature 0: 1 different answer" in io.output and "Temperature 1: 2 different answers" in io.output
    assert "blue." in io.output and "BLUE!" in io.output  # the table shows what the model wrote


NONDETERMINISM = "the servers batch requests together, and tiny rounding differences can flip a close pick"


def test_learn_explains_the_mechanism_and_when_to_set_zero():
    assert ch3.LEARN[1].example == (
        "The model divides its scores by the temperature before turning them into odds. "
        "Below 1 sharpens the odds, above 1 flattens them, and 0 takes the top token."
    )
    body = ch3.LEARN[6].body
    assert (
        "On models that accept it, use temperature near 0 for one-right-answer tasks and 0.7 to 1 for "
        "creative ones. On the newest models, get consistency from the prompt, examples, structured output "
        "and checks." in body
    )
    assert f"Even temperature 0 isn't fully deterministic on the real API: {NONDETERMINISM}." in body


def test_recap_and_sample_answer_say_when_zero_applies():
    assert "on models that accept it" in ch3.RECAP[2].lower() and "0.7 to 1" in ch3.RECAP[3]
    assert "prompt, examples, structured output and checks" in ch3.RECAP[5]
    rubric = BUNDLE.rubrics["3"]
    assert rubric.sample_answer.rstrip().endswith(
        "I'd start at 0 for extraction and about 0.7 for ad copy, and check with a small eval."
    )
    assert "can't set it" in rubric.sample_answer
    assert any("Opus 5.5" in f.question and "consistent" in f.question for f in rubric.followups)


def test_rubric_items_accept_paraphrase_and_require_both_ends():
    items = BUNDLE.rubrics["3"].checklist
    assert len(items) == 6
    assert "how random or spread out the picks are" in items[0]
    assert "both ends" in items[1]
    assert "says it trims unlikely options" in items[5]


def test_quick_check_2_tests_what_zero_guarantees():
    check = ch3.CHECKS[1]
    assert "temperature 0" in check.question and "guarantee" in check.question
    assert "can still vary slightly" in check.options[check.answer]
    assert ch3.LEARN[check.screen - 1].title == "The newest models fix these settings"  # where the reason is taught


def test_predict_temperatures_stay_in_claudes_range():
    assert all(0 < t <= 1 for t in ch3.TEMPERATURES)


def test_dial_says_what_range_the_api_takes():
    io = ScriptedIO()
    run_step(ch3.temperature_slider, io)
    flat = " ".join(io.output.split())
    assert (
        "Claude's API takes 0 to 1 on models that accept a temperature. Some other providers go up to 2. "
        "Here, values above 1 exaggerate the effect." in flat
    )


def test_zero_predict_explains_why_the_real_api_still_varies():
    io = ScriptedIO()
    run_step(ch3.zero_predict, io)
    assert NONDETERMINISM in " ".join(io.output.split())


@pytest.mark.parametrize("step", ["temperature_predict", "zero_predict"])
def test_count_predictions_take_whole_numbers_only(step):
    io = ScriptedIO(overrides={"number": ["7.5", "7"]})
    run_step(getattr(ch3, step), io)
    assert "Please type a whole number from" in io.output and "You guessed 7" in io.output


def test_predict_reveal_reads_cleanly():
    io = ScriptedIO(overrides={"number": ["7"]})
    run_step(ch3.temperature_predict, io, seed=4)
    flat = " ".join(io.output.split())
    assert (
        f"Any {ch3.RUNS} runs vary a little, so a guess near that is a good one." in flat
        and "every 20 runs" not in flat
    )


@pytest.mark.parametrize("seed", range(30))
def test_cards_always_include_low_medium_and_high(seed):
    io = ScriptedIO()
    run_step(ch3.cards, io, seed=seed)
    shown = [card for card in ch3.CARDS if card[0] in io.output]
    assert len(shown) == 4 and {setting for _, setting, _ in shown} == set(ch3.SETTINGS)


def test_customer_reply_reason_puts_the_facts_in_the_prompt():
    reason = dict((task, reason) for task, _, reason in ch3.CARDS)["Write a friendly reply to a customer"]
    assert reason == "Some variety keeps it natural. The facts come from the prompt, not the setting."


@pytest.mark.parametrize(
    "step", ["temperature_predict", "temperature_slider", "zero_predict", "trim", "cards", "length_limits"]
)
def test_every_experiment_has_one_what_this_shows_caption(step):
    io = ScriptedIO(overrides={"optional": ["0.5", ""]})
    run_step(getattr(ch3, step), io)
    assert io.output.count("What this shows:") == 1


def test_live_run_caption_and_closing_line_match_learn_7():
    fake = FakeLive({0.0: ["blue"] * 10, 1.0: ["blue"] * 10})
    io = ScriptedIO(overrides={"yesno": ["y"]}, width=120)
    run_step(ch3.live_run, io, live=fake)
    flat = " ".join(io.output.split())
    assert (
        "because Opus 5.5 doesn't accept a temperature at all and Sonnet 5.5 rejects anything but the default" in flat
    )
    assert flat.count("What this shows:") == 1

import random
import re

import pytest

import data


def write(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


VALID_PROMPT = '[[prompt]]\ntext = "P{n}"\ntokens = {{ "a" = 3, "b" = 2, "c" = 1 }}\n'


def test_real_files_load_and_validate():
    bundle = data.load_all()
    assert len(bundle.prompts) >= data.MIN_PROMPTS
    chains = [p for p in bundle.prompts if p.continuation]
    assert len(chains) >= 5
    assert all(len(p.continuation) >= 2 for p in chains)  # Chapter 1 predicts at steps 0 and 2
    assert "1" in bundle.rubrics
    assert len(bundle.rubrics["1"].checklist) == 5
    assert {g.term.lower() for g in bundle.glossary} >= {"token", "inference", "api"}


def test_too_few_candidates(tmp_path):
    write(tmp_path, "prompts.toml", '[[prompt]]\ntext = "x"\ntokens = { "a" = 1, "b" = 2 }\n')
    with pytest.raises(data.DataError, match=r"prompts.toml: prompt #1 \(x\) needs at least 3"):
        data.load_prompts(tmp_path)


@pytest.mark.parametrize("weight", ["-1", "0", "true", '"high"', "nan", "inf"])
def test_bad_weight(tmp_path, weight):
    write(tmp_path, "prompts.toml", f'[[prompt]]\ntext = "x"\ntokens = {{ "a" = {weight}, "b" = 2, "c" = 1 }}\n')
    with pytest.raises(data.DataError, match="weight for 'a' must be a positive number"):
        data.load_prompts(tmp_path)


def test_weight_beyond_float_range_is_one_line(tmp_path):
    # TOML reads a 309-digit integer as an exact int; it must become a DataError, not an OverflowError (Codex, #21).
    huge = "9" * 309
    write(tmp_path, "prompts.toml", f'[[prompt]]\ntext = "x"\ntokens = {{ "a" = {huge}, "b" = 2, "c" = 1 }}\n')
    with pytest.raises(data.DataError, match="weight for 'a' is too large"):
        data.load_prompts(tmp_path)


def test_chain_tie_rejected(tmp_path):
    write(
        tmp_path,
        "prompts.toml",
        '[[prompt]]\ntext = "x"\ntokens = { "a" = 3, "b" = 2, "c" = 1 }\n'
        'continuation = [ { "d" = 2, "e" = 2, "f" = 1 } ]\n',
    )
    with pytest.raises(data.DataError, match="continuation step 1 needs one clear top candidate"):
        data.load_prompts(tmp_path)


def test_duplicate_prompt_rejected(tmp_path):
    write(tmp_path, "prompts.toml", VALID_PROMPT.format(n=1) * 2)
    with pytest.raises(data.DataError, match="duplicate"):
        data.load_prompts(tmp_path)


def test_needs_thirty_prompts(tmp_path):
    write(tmp_path, "prompts.toml", "".join(VALID_PROMPT.format(n=n) for n in range(2)))
    with pytest.raises(data.DataError, match="needs at least 30 prompts, found 2"):
        data.load_prompts(tmp_path)


def test_bad_toml_names_the_file(tmp_path):
    write(tmp_path, "prompts.toml", "[[prompt]\ntext = ")
    with pytest.raises(data.DataError, match=r"prompts\.toml: not valid TOML"):
        data.load_prompts(tmp_path)


def test_missing_file(tmp_path):
    with pytest.raises(data.DataError, match=r"checklists\.toml: file not found"):
        data.load_rubrics(tmp_path)


def test_rubric_needs_followups(tmp_path):
    write(tmp_path, "checklists.toml", '[chapter.1]\nquestion = "Q?"\nchecklist = ["a", "b", "c"]\n')
    with pytest.raises(data.DataError, match="chapter 1 needs at least 2 follow-ups"):
        data.load_rubrics(tmp_path)


def test_glossary_duplicates_rejected(tmp_path):
    entry = '[[term]]\nterm = "Token"\ndefinition = "d"\nchapter = "1"\n'
    write(tmp_path, "glossary.toml", entry + entry.replace("Token", "token"))
    with pytest.raises(data.DataError, match="duplicate term 'token'"):
        data.load_glossary(tmp_path)


@pytest.mark.parametrize(
    "name, text, message",
    [
        ("prompts.toml", "prompt = 5\n", r"prompts.toml: 'prompt' must be a list of \[\[prompt\]\] tables"),
        (
            "prompts.toml",
            '[[prompt]]\ntext = "x"\ntokens = { "a" = 3, "b" = 2, "c" = 1 }\ncontinuation = 5\n',
            r"prompts.toml: prompt #1 \(x\) continuation must be a list of tables",
        ),
        ("checklists.toml", 'chapter = "oops"\n', r"checklists.toml: 'chapter' must be a table"),
        ("glossary.toml", "term = 5\n", r"glossary.toml: 'term' must be a list of \[\[term\]\] tables"),
    ],
)
def test_wrong_shape_names_the_file(tmp_path, name, text, message):
    write(tmp_path, name, text)
    loader = {
        "prompts.toml": data.load_prompts,
        "checklists.toml": data.load_rubrics,
        "glossary.toml": data.load_glossary,
    }
    with pytest.raises(data.DataError, match=message):
        loader[name](tmp_path)


def test_needs_a_continuation_chain(tmp_path):
    write(tmp_path, "prompts.toml", "".join(VALID_PROMPT.format(n=n) for n in range(30)))
    with pytest.raises(data.DataError, match="needs at least one prompt with a continuation chain"):
        data.load_prompts(tmp_path)


def test_demo_chains_are_5_to_8_steps():
    for prompt in data.load_all().prompts:
        if prompt.continuation:
            assert 5 <= 1 + len(prompt.continuation) <= 8, prompt.text


@pytest.mark.parametrize("missing", ["hint", "sample_answer"])
def test_rubric_needs_a_hint_and_a_sample_answer(tmp_path, missing):
    fields = {"hint": 'hint = "a · b"\n', "sample_answer": 'sample_answer = "A strong answer."\n'}
    followups = '[[chapter.1.followup]]\nquestion = "q"\nstrong = "s"\n' * 2
    head = '[chapter.1]\nquestion = "Q?"\nchecklist = ["a", "b", "c"]\n'
    text = head + "".join(v for k, v in fields.items() if k != missing) + followups
    write(tmp_path, "checklists.toml", text)
    with pytest.raises(data.DataError, match=f"checklists.toml: chapter 1 {missing.replace('_', ' ')} is missing text"):
        data.load_rubrics(tmp_path)


CASE = """[[case]]
prompt = "P{n}"
tag = "{tag}"
answer = "right"
without = {{ "wrong" = 5, "right" = 3, "other" = 1 }}
context = "Fact: right."
with_context = {{ "right" = 9, "wrong" = 1, "other" = 1 }}
"""


def cases(n=5, medical=1):
    return "".join(CASE.format(n=i, tag="medical" if i < medical else "general") for i in range(n))


def test_real_hallucination_cases_load_and_validate():
    found = data.load_all().hallucinations
    assert len(found) >= data.MIN_HALLUCINATIONS
    assert {c.tag for c in found} == set(data.HALLUCINATION_TAGS)
    assert any(c.prompt == "The capital of Australia is" for c in found)
    assert any(c.prompt == "Patient is allergic to" and c.answer == "sulfa drugs" for c in found)
    mountain = next(c for c in found if c.answer == "Mauna Kea")
    assert "sea floor" in mountain.prompt  # the prompt says what's measured, so the right answer is gettable


def test_bundle_defaults_to_no_hallucination_cases():
    assert data.Bundle(prompts=[], rubrics={}, glossary=[]).hallucinations == []


@pytest.mark.parametrize(
    "old, new, message",
    [
        ('prompt = "P0"', 'prompt = " "', r"case #1 \(no prompt\) prompt is missing text"),
        ('prompt = "P1"', 'prompt = "P0"', r"case #2 \(P0\) is a duplicate"),
        ('tag = "medical"', 'tag = "legal"', r"case #1 \(P0\) tag must be one of general, product, medical"),
        ('answer = "right"', 'answer = ""', r"case #1 \(P0\) answer is missing text"),
        (
            'without = { "wrong" = 5, "right" = 3, "other" = 1 }',
            'without = { "wrong" = 5, "right" = 3 }',
            r"case #1 \(P0\) without needs at least 3 candidates",
        ),
        (
            '"wrong" = 5, "right" = 3',
            '"wrong" = 5, "right" = -3',
            r"case #1 \(P0\) without: weight for 'right' must be",
        ),
        ('context = "Fact: right."', 'context = ""', r"case #1 \(P0\) context is missing text"),
        (
            '"right" = 9, "wrong" = 1',
            '"right" = 9, "wrong" = "lots"',
            r"case #1 \(P0\) with_context: weight for 'wrong'",
        ),
        (
            '"wrong" = 5, "right" = 3, "other" = 1',
            '"wrong" = 5, "else" = 3, "other" = 1',
            r"case #1 \(P0\) answer 'right' must be one of the without candidates",
        ),
        (
            '"right" = 9, "wrong" = 1, "other" = 1',
            '"else" = 9, "wrong" = 1, "other" = 1',
            r"case #1 \(P0\) answer 'right' must be one of the with_context candidates",
        ),
        ('"wrong" = 5, "right" = 3', '"wrong" = 5, "right" = 5', r"case #1 \(P0\) without has a tie for the top"),
        ('"right" = 9, "wrong" = 1', '"right" = 9, "wrong" = 9', r"case #1 \(P0\) with_context has a tie for the top"),
        (
            '"wrong" = 5, "right" = 3',
            '"wrong" = 3, "right" = 5',
            r"case #1 \(P0\) without context, a wrong answer must be the most likely",
        ),
        (
            '"right" = 9, "wrong" = 1',
            '"right" = 1, "wrong" = 9',
            r"case #1 \(P0\) with context, the right answer must be the most likely",
        ),
        (  # Codex review on #25: ranked first, but its share fell, so context didn't cut mistakes
            '"right" = 9, "wrong" = 1, "other" = 1',
            '"right" = 2, "wrong" = 1.9, "other" = 1.8',
            r"case #1 \(P0\) with context, the right answer needs at least half the odds",
        ),
    ],
)
def test_bad_hallucination_case_names_the_entry(tmp_path, old, new, message):
    text = cases()
    assert old in text
    write(tmp_path, "hallucination.toml", text.replace(old, new, 1))
    with pytest.raises(data.DataError, match=f"hallucination.toml: {message}"):
        data.load_hallucinations(tmp_path)


@pytest.mark.parametrize(
    "text, message",
    [
        ("case = 5\n", r"'case' must be a list of \[\[case\]\] tables"),
        ("case = [5]\n", r"case #1 must be a \[\[case\]\] table"),
        (cases(n=4), "needs at least 5 cases, found 4"),
        (cases(medical=0), "needs at least one medical case and one other case"),
        (cases(medical=5), "needs at least one medical case and one other case"),
    ],
)
def test_hallucination_file_shape(tmp_path, text, message):
    write(tmp_path, "hallucination.toml", text)
    with pytest.raises(data.DataError, match=f"hallucination.toml: {message}"):
        data.load_hallucinations(tmp_path)


def top_two_gap(weights):
    total = sum(weights.values())
    first, second = sorted(weights.values(), reverse=True)[:2]
    return (first - second) / total


def test_every_prompt_has_a_clear_top_word():
    # Chapter 3 asks how often the top word comes up; nudging (sigma 0.15) turns a gap under 10 points
    # into a near-tie in a fifth to a third of runs.
    close = [p.text for p in data.load_prompts() if top_two_gap(p.weights) < 0.10]
    assert not close, close


def test_weights_too_large_to_add_up_are_rejected(tmp_path):
    write(tmp_path, "prompts.toml", '[[prompt]]\ntext = "x"\ntokens = { "a" = 1e308, "b" = 1e308, "c" = 1 }\n')
    with pytest.raises(data.DataError, match=r"prompts.toml: prompt #1 \(x\): weights are too large"):
        data.load_prompts(tmp_path)


def test_a_file_that_is_not_utf8_names_the_file(tmp_path):
    (tmp_path / "prompts.toml").write_bytes(b'[[prompt]]\ntext = "caf\xe9"\n')
    with pytest.raises(data.DataError, match=r"^prompts\.toml: not valid UTF-8 text$"):
        data.load_prompts(tmp_path)


def test_every_prompt_needs_one_clear_top_candidate(tmp_path):
    # Chapter 3 asks about "the" top word, so a tie is rejected on every prompt, not only on chains.
    write(tmp_path, "prompts.toml", '[[prompt]]\ntext = "x"\ntokens = { "a" = 3, "b" = 3, "c" = 1 }\n')
    with pytest.raises(data.DataError, match=r"prompt #1 \(x\) needs one clear top candidate"):
        data.load_prompts(tmp_path)


VALID_SCENARIO = """[[scenario]]
id = "s{n}"
name = "Scenario {n}"
pitch = "A product."
users = [100, 1000]
requests_per_user = [1, 5]
input_tokens = [1000, 3000]
output_tokens = [100, 500]
system_tokens = [500, 1000]
docs_tokens = [10000, 50000]
domain = "general"
needs_facts = true
latency = "interactive"
"""
VALID_FOLLOWUPS = """
[[scenario.followup]]
question = "Q{k}?"
strong = "S{k}."
"""


def scenario_text(n, followups=3):
    return VALID_SCENARIO.format(n=n) + "".join(VALID_FOLLOWUPS.format(k=k) for k in range(followups)) + "\n"


def scenarios(count=6, **changes):
    text = "".join(scenario_text(n) for n in range(count))
    for key, value in changes.items():
        text = re.sub(rf"^{key} = .*$", f"{key} = {value}", text, count=1, flags=re.M)
    return text


def test_real_scenarios_load():
    loaded = data.load_all().scenarios
    assert len(loaded) >= data.MIN_SCENARIOS
    ids = {s.id for s in loaded}
    assert {
        "support-bot",
        "coding-assistant",
        "medical-note-summarizer",
        "ad-copy-tool",
        "contract-reviewer",
        "meeting-notes",
    } <= ids


def test_bundle_scenarios_default_to_empty():
    real = data.load_all()
    assert data.Bundle(prompts=real.prompts, rubrics=real.rubrics, glossary=real.glossary).scenarios == []


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"id": '"Support Bot"'}, r"scenario #1 \(Support Bot\) id must be lowercase words joined by hyphens"),
        ({"name": '""'}, r"scenario #1 \(s0\) name is missing text"),
        ({"users": "[1000, 100]"}, r"scenario #1 \(s0\) users must be \[low, high\]"),
        ({"input_tokens": "[1000]"}, r"scenario #1 \(s0\) input_tokens must be \[low, high\]"),
        ({"output_tokens": "[0, 100]"}, r"scenario #1 \(s0\) output_tokens must be \[low, high\]"),
        ({"docs_tokens": "[true, 5]"}, r"scenario #1 \(s0\) docs_tokens must be \[low, high\]"),
        ({"requests_per_user": '"lots"'}, r"scenario #1 \(s0\) requests_per_user must be \[low, high\]"),
        ({"system_tokens": "[500, 4000]"}, r"scenario #1 \(s0\) system_tokens can't go above input_tokens"),
    ],
)
def test_bad_scenario_names_the_entry(tmp_path, changes, message):
    write(tmp_path, "scenarios.toml", scenarios(**changes))
    with pytest.raises(data.DataError, match="scenarios.toml: " + message):
        data.load_scenarios(tmp_path)


def test_scenario_missing_a_range(tmp_path):
    write(tmp_path, "scenarios.toml", scenarios().replace("docs_tokens = [10000, 50000]\n", "", 1))
    with pytest.raises(data.DataError, match=r"scenario #1 \(s0\) docs_tokens must be \[low, high\]"):
        data.load_scenarios(tmp_path)


def test_duplicate_scenario_id(tmp_path):
    write(tmp_path, "scenarios.toml", scenarios() + scenario_text(0))
    with pytest.raises(data.DataError, match=r"scenario #7 \(s0\) is a duplicate id"):
        data.load_scenarios(tmp_path)


def test_needs_six_scenarios(tmp_path):
    write(tmp_path, "scenarios.toml", scenarios(count=5))
    with pytest.raises(data.DataError, match="needs at least 6 scenarios, found 5"):
        data.load_scenarios(tmp_path)


@pytest.mark.parametrize(
    "text, message",
    [
        ("scenario = 5\n", r"'scenario' must be a list of \[\[scenario\]\] tables"),
        ("scenario = [5]\n", r"scenario #1 must be a \[\[scenario\]\] table"),
    ],
)
def test_scenarios_wrong_shape(tmp_path, text, message):
    write(tmp_path, "scenarios.toml", text)
    with pytest.raises(data.DataError, match="scenarios.toml: " + message):
        data.load_scenarios(tmp_path)


def test_draw_stays_in_range_and_keeps_the_fixed_part_inside_the_input():
    for scenario in data.load_all().scenarios:
        for seed in range(200):
            work = scenario.draw(random.Random(seed))
            low, high = scenario.users
            assert low * 0.95 <= work.users <= high * 1.05  # two-figure rounding can nudge past an edge
            assert scenario.requests_per_user[0] <= work.requests_per_user <= scenario.requests_per_user[1]
            assert work.system_tokens <= work.input_tokens
            assert work.requests_per_day == work.users * work.requests_per_user


def test_draw_is_reproducible():
    scenario = data.load_all().scenarios[0]
    assert scenario.draw(random.Random(5)) == scenario.draw(random.Random(5))


@pytest.mark.parametrize(
    "value, rounded", [(1, 1), (99.4, 99), (150, 150), (1549, 1500), (12_345, 12_000), (99_999, 100_000)]
)
def test_two_figure_rounding(value, rounded):
    assert data.two_figures(value) == rounded


def test_rubric_figures_fill_in_named_placeholders():
    rubric = data.ChapterRubric(
        question="Q {x}?",
        checklist=("Says {x}",),
        followups=(data.FollowUp("F {z}?", "Strong {x} and {y}"),),
        hint="h {x}",
        sample_answer="Output costs {x} as much.",
    )
    assert rubric.figure_names() == {"x", "y", "z"}  # follow-up questions count too (Codex review on #30)
    filled = rubric.filled({"x": "5×", "y": "1M", "z": "10×"})
    assert filled.sample_answer == "Output costs 5× as much."
    assert (filled.question, filled.checklist, filled.hint) == ("Q 5×?", ("Says 5×",), "h 5×")
    assert filled.followups[0] == data.FollowUp("F 10×?", "Strong 5× and 1M")
    assert rubric.filled({}) == rubric


def test_scenarios_carry_the_chapter_8_fields():
    scenarios_by_id = {s.id: s for s in data.load_all().scenarios}
    assert scenarios_by_id["medical-note-summarizer"].domain == "medical"
    assert scenarios_by_id["contract-reviewer"].domain == "legal"
    assert scenarios_by_id["ad-copy-tool"].needs_facts is False
    assert {s.latency for s in scenarios_by_id.values()} == {"interactive", "background"}
    for s in scenarios_by_id.values():
        assert len(s.followups) >= 3, s.id


def test_hand_built_scenarios_default_the_chapter_8_fields():
    s = data.Scenario("x", "X", "p", (1, 2), (1, 2), (1, 2), (1, 2), (1, 2), (1, 2))
    assert (s.domain, s.needs_facts, s.latency, s.followups) == ("general", True, "interactive", ())


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"domain": '"finance"'}, r"scenario #1 \(s0\) domain must be one of: general, medical, legal"),
        ({"latency": '"slow"'}, r"scenario #1 \(s0\) latency must be one of: interactive, background"),
        ({"needs_facts": '"yes"'}, r"scenario #1 \(s0\) needs_facts must be true or false"),
    ],
)
def test_bad_chapter_8_field_names_the_scenario(tmp_path, changes, message):
    write(tmp_path, "scenarios.toml", scenarios(**changes))
    with pytest.raises(data.DataError, match="scenarios.toml: " + message):
        data.load_scenarios(tmp_path)


def test_scenario_missing_a_chapter_8_field(tmp_path):
    write(tmp_path, "scenarios.toml", scenarios().replace('latency = "interactive"\n', "", 1))
    with pytest.raises(data.DataError, match=r"scenario #1 \(s0\) latency must be one of"):
        data.load_scenarios(tmp_path)


def test_scenario_needs_three_followups(tmp_path):
    text = scenarios().replace(scenario_text(0), scenario_text(0, followups=2), 1)
    write(tmp_path, "scenarios.toml", text)
    with pytest.raises(data.DataError, match=r"scenario #1 \(s0\) needs at least 3 follow-ups"):
        data.load_scenarios(tmp_path)


def test_scenario_followup_without_text(tmp_path):
    text = scenarios().replace('strong = "S1."', 'strong = ""', 1)
    write(tmp_path, "scenarios.toml", text)
    with pytest.raises(data.DataError, match=r"scenario #1 \(s0\) follow-up 2 strong is missing text"):
        data.load_scenarios(tmp_path)

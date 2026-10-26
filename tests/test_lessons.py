import dataclasses
import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import data
import engine
import pricing
from lessons import CHAPTERS
from lessons.ch1_generation import join_token

BUNDLE = data.load_all()
BOLD = re.compile(r"\*\*(.+?)\*\*")


def test_every_chapter_is_well_formed():
    for cid, chapter in CHAPTERS.items():
        assert chapter.id == cid
        assert len(chapter.learn) >= 4, cid
        assert chapter.recap, cid
        assert chapter.checks or cid == "8", f"chapter {cid} needs at least one quick check"
        assert cid in BUNDLE.rubrics, f"checklists.toml has no chapter {cid}"
        for screen in chapter.learn:
            assert screen.title and screen.body and screen.why_pm, screen.title
        for check in chapter.checks:
            assert 0 <= check.answer < len(check.options)
            assert 1 <= check.screen <= len(chapter.learn)


def test_every_bold_term_is_in_the_glossary():
    terms = {g.term.lower() for g in BUNDLE.glossary}
    for chapter in CHAPTERS.values():
        for screen in chapter.learn:
            for text in (screen.body, screen.analogy, screen.example, screen.why_pm):
                for term in BOLD.findall(text):
                    assert term.lower() in terms, f"add {term!r} to data/glossary.toml"


def test_join_token():
    assert join_token("The sky is", "blue") == "The sky is blue"
    assert join_token("The sky is blue", ".") == "The sky is blue."
    assert join_token("grew by", "12%") == "grew by 12%"


def run_ch1(io, seed=4242, learn_only=False):
    scored = []
    ctx = engine.Ctx(io=io, seed=seed, chapter=CHAPTERS["1"], data=BUNDLE, on_scored=lambda s, c: scored.append((s, c)))
    return engine.run_chapter(ctx, learn_only=learn_only), scored


def test_chapter_1_runs_end_to_end():
    io = ScriptedIO()
    result, scored = run_ch1(io)
    assert result == "done"
    out = io.output
    assert "Explain how an LLM generates text." in out
    assert "8 of 8 · Bigger vs. smaller models" in out
    assert "Your prediction: which word is most likely next?" in "".join(p for _, p in io.prompts)
    assert "That's all generation is" in out
    assert len(scored) == 1 and scored[0][0].out_of == 5


def test_chapter_1_same_seed_same_story():
    first, second = ScriptedIO(), ScriptedIO()
    run_ch1(first, seed=99)
    run_ch1(second, seed=99)
    assert first.output == second.output


def test_chapter_1_learn_only():
    io = ScriptedIO()
    result, scored = run_ch1(io, learn_only=True)
    assert result == "done" and scored == []
    assert "That's all generation is" not in io.output


def test_chapter_1_narrow_terminal():
    io = ScriptedIO(width=40)
    assert run_ch1(io)[0] == "done"


def test_bracket_tokens_render_literally_on_a_wrong_guess():
    chain = data.PromptTable("arr", "code", {"[/x]": 5, "[i]": 3, "b": 2, "c": 1}, ({"d": 3, "e": 2, "f": 1},) * 2)
    bundle = data.Bundle(prompts=[chain], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    outputs = []
    for seed in range(12):
        io = ScriptedIO()
        ctx = engine.Ctx(io=io, seed=seed, chapter=CHAPTERS["1"], data=bundle)
        CHAPTERS["1"].hands_on[0](ctx)
        outputs.append(io.output)
    assert any("top pick is '[/x]'" in out for out in outputs)


DEMO_PROMPTS = [p for p in BUNDLE.prompts if p.continuation]


@pytest.mark.parametrize("prompt", DEMO_PROMPTS, ids=[p.text for p in DEMO_PROMPTS])
@pytest.mark.parametrize("width", (40, 120))
def test_every_demo_prompt_builds_its_sentence(prompt, width):
    bundle = data.Bundle(prompts=[prompt], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    io = ScriptedIO(width=width)
    ctx = engine.Ctx(io=io, seed=1, chapter=CHAPTERS["1"], data=bundle)
    CHAPTERS["1"].hands_on[0](ctx)
    pauses = [kind for kind, _ in io.prompts if kind == "pause"]
    assert len(pauses) == len(prompt.continuation)  # one pause between each of the 1 + N picks
    assert "That's all generation is" in io.output


def test_demo_prompts_are_not_spoiled_by_the_learn_screens():
    learn_text = " ".join(f"{s.body} {s.example} {s.analogy}" for s in CHAPTERS["1"].learn)
    for prompt in BUNDLE.prompts:
        if prompt.continuation:
            assert prompt.text not in learn_text, f"{prompt.text!r} is shown in a Learn screen before the demo"


def test_recap_has_one_point_per_checklist_item():
    rubrics = data.load_rubrics()
    for chapter_id, chapter in CHAPTERS.items():
        if chapter_id == "8":
            continue  # its Recap is the answer structure (spec §5); see test_chapter_8_recap_is_the_answer_structure
        assert len(chapter.recap) == len(rubrics[chapter_id].checklist), chapter_id


def test_demo_asks_for_a_prediction_and_shows_both_odds():
    chain = data.PromptTable(
        "Pick", "test", {"alpha": 50, "beta": 30, "gamma": 15, "delta": 5}, ({"x": 2, "y": 1},) * 2
    )
    bundle = data.Bundle(prompts=[chain], rubrics=BUNDLE.rubrics, glossary=BUNDLE.glossary)
    outputs = []
    for seed in range(20):
        io = ScriptedIO()
        ctx = engine.Ctx(io=io, seed=seed, chapter=CHAPTERS["1"], data=bundle)
        CHAPTERS["1"].hands_on[0](ctx)
        outputs.append(io.output)
    assert all("Predict first, then see the model's odds. Go with your gut" in out for out in outputs)
    assert not any("Not this time" in out for out in outputs)
    assert any("Same as the model: 'alpha', at 50%." in out for out in outputs)
    assert any("The model's top pick is 'alpha' (50%). Yours, 'gamma', got 15%." in out for out in outputs)


def test_chapter_1_explains_how_chat_apps_know_recent_news():
    chapter, rubric = CHAPTERS["1"], BUNDLE.rubrics["1"]
    screen = next(s for s in chapter.learn if s.title == "Knowledge cutoff, and how chatbots still know today's news")
    assert "web search" in screen.body and "**knowledge cutoff**" in screen.body
    news_check = next(c for c in chapter.checks if "yesterday's news" in c.question)
    assert "searched the web" in news_check.options[news_check.answer]
    assert chapter.learn[news_check.screen - 1] is screen
    assert any("web search" in item for item in rubric.checklist)
    assert any("ChatGPT told me about yesterday's news" in f.question for f in rubric.followups)
    training = next(s for s in chapter.learn if s.title == "Training vs. answering a request")
    assert "knowledge cutoff" not in training.body  # it has its own screen now


@pytest.mark.parametrize("chapter_id", list(CHAPTERS))
@pytest.mark.parametrize("width", (40, 120))
def test_every_chapter_runs_end_to_end(chapter_id, width):
    io = ScriptedIO(width=width)
    ctx = engine.Ctx(io=io, seed=7, chapter=CHAPTERS[chapter_id], data=BUNDLE)
    assert engine.run_chapter(ctx) == "done"
    too_wide = [line for line in io.output.splitlines() if cell_len(line) > width]
    assert not too_wide, too_wide[:3]


def test_chapter_2_is_registered_and_teaches_the_tokenizer_catch():
    chapter, rubric = CHAPTERS["2"], BUNDLE.rubrics["2"]
    assert chapter.title == "Tokens: what models read and bill"
    assert [s.title for s in chapter.learn][3] == "The rule of thumb, and its catch"
    assert "rule of thumb" in chapter.learn[3].body
    assert "pseudohypoparathyroidism" not in " ".join(f"{s.body} {s.example}" for s in chapter.learn)
    assert len(rubric.checklist) == 6
    assert rubric.question == "What's a token and why does it matter?"


def test_chapter_3_is_registered_and_says_the_newest_models_fix_temperature():
    chapter, rubric = CHAPTERS["3"], BUNDLE.rubrics["3"]
    assert chapter.title == "Temperature: how the model picks"
    assert chapter.learn[-1].title == "The newest models fix these settings"
    assert "**effort**" in chapter.learn[-1].body
    assert len(rubric.checklist) == 6
    assert rubric.question == "What does temperature do? When would you set it to 0?"


def test_chapter_4_is_registered_and_teaches_the_fixes():
    chapter, rubric = CHAPTERS["4"], BUNDLE.rubrics["4"]
    assert chapter.title == "Hallucinations: confident but wrong"
    fixes = chapter.learn[4]
    assert fixes.title == "The fix toolbox"
    assert "**Grounding**" in fixes.body
    assert "\n\nWhat doesn't work: temperature 0." in fixes.body  # set apart from the numbered fixes
    causes = chapter.learn[2]
    assert [line[:2] for line in causes.body.splitlines()] == ["• "] * 4
    assert "training data" in causes.body  # the knowledge cutoff, glossed
    assert len(rubric.checklist) == 6
    assert rubric.question == "Define hallucination. Users say it's confident but wrong. Fix it."
    assert "missing from the prompt" in rubric.checklist[2]
    assert "at least two" in rubric.checklist[4]
    assert "and why" in rubric.checklist[5]


def test_chapter_4_learn_screens_dont_give_away_the_cases():
    learn = " ".join(f"{s.body} {s.example} {s.analogy}" for s in CHAPTERS["4"].learn)
    for case in BUNDLE.hallucinations:
        assert case.prompt not in learn and case.answer not in learn, case.prompt


def test_chapter_5_is_registered_and_separates_two_kinds_of_speed():
    chapter, rubric = CHAPTERS["5"], BUNDLE.rubrics["5"]
    assert chapter.title == "Small vs. large models: how to choose"
    speed = chapter.learn[2]
    assert "**Time to first token**" in speed.body and "**Streaming speed**" in speed.body
    assert "faster streaming at a higher price" in speed.body  # fast mode is taught before its demo
    ratio = pricing.get("opus-5-5").input / pricing.get("haiku-5-5").input
    assert f"{ratio:g}×" in chapter.learn[1].body and f"{ratio:g}×" in chapter.recap[1]
    assert chapter.checks[1].screen == 4  # sorting tickets: reread the routing screen
    assert len(rubric.checklist) == 6
    assert rubric.question == "Small vs. large models: how do you choose?"
    assert "if users wait on it" in rubric.checklist[2]
    assert "how requests get sorted" in rubric.checklist[3]
    assert "human review or retries" in rubric.checklist[4]
    assert "consistent with the rest of the answer" in rubric.checklist[5]


@pytest.mark.parametrize("chapter_id", list(CHAPTERS))
def test_every_learn_title_is_shown_whole_at_40_columns(chapter_id):
    io = ScriptedIO(width=40)
    engine.run_chapter(engine.Ctx(io=io, seed=7, chapter=CHAPTERS[chapter_id], data=BUNDLE), learn_only=True)
    flat = " ".join(io.output.replace("│", " ").replace("─", " ").split())
    for screen in CHAPTERS[chapter_id].learn:
        assert screen.title in flat, screen.title


def test_chapter_6_is_registered_and_ends_on_unit_economics():
    chapter, rubric = CHAPTERS["6"], BUNDLE.rubrics["6"]
    assert chapter.title == "Cost at scale: what drives the bill"
    assert chapter.learn[-1].title == "Unit economics"
    assert "**cost of goods sold**" in chapter.learn[-1].body
    assert len(rubric.checklist) == 6
    assert rubric.question == "How do costs change as you scale?"


@pytest.mark.parametrize("chapter_id", ["6", "7"])
def test_cost_chapters_type_no_dollar_figures(chapter_id):
    # Every price comes from pricing.py at run time; the rubric is plain TOML, so it can't hold one.
    rubric = BUNDLE.rubrics[chapter_id]
    text = " ".join([rubric.hint, rubric.sample_answer, *rubric.checklist, *(f.strong for f in rubric.followups)])
    assert "$" not in text


def test_every_rubric_figure_is_computed_by_its_chapter_and_used():
    for cid, chapter in CHAPTERS.items():
        rubric = BUNDLE.rubrics[cid]
        assert rubric.figure_names() == set(chapter.figures), cid
        ctx = engine.Ctx(io=ScriptedIO(), seed=1, chapter=chapter, data=BUNDLE)
        filled = ctx.rubric
        text = " ".join([filled.hint, filled.sample_answer, *filled.checklist, *(f.strong for f in filled.followups)])
        assert "{" not in text and "}" not in text, cid


def test_chapter_7_is_registered_and_ends_on_paste_vs_fetch():
    chapter, rubric = CHAPTERS["7"], BUNDLE.rubrics["7"]
    assert chapter.title == "Context windows: what the model can see"
    assert chapter.learn[-1].title == "Paste everything vs. fetch what's relevant"
    assert "**RAG**" in chapter.learn[-1].body
    assert len(rubric.checklist) == 5
    assert rubric.question == "What's a context window? Paste everything in or fetch what's relevant?"


def test_chapter_8_recap_is_the_answer_structure():
    chapter, rubric = CHAPTERS["8"], BUNDLE.rubrics["8"]
    assert chapter.title == "Design an AI feature"
    assert rubric.question == "Design an AI feature for X."
    assert len(rubric.checklist) == 8 and chapter.checks == ()
    assert len(chapter.recap) == 9  # the nine steps of the structure
    assert len(rubric.hint.split(" · ")) == 9  # h shows the same nine steps as cues
    steps = " ".join(s.body for s in chapter.learn[1:3])
    assert [f"{n}. " in steps for n in range(1, 10)] == [True] * 9


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _strings(getattr(obj, f.name))
    elif isinstance(obj, Mapping):
        for value in obj.values():
            yield from _strings(value)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _strings(item)


def test_no_learner_facing_copy_frames_the_course_as_interview_prep():
    # The course teaches building with LLMs. Snapshots hold every rendered screen
    # (labels, follow-ups); the chapters and data files hold the rest of the copy.
    texts = [*_strings(list(CHAPTERS.values())), *_strings(BUNDLE)]
    texts += [path.read_text() for path in (Path(__file__).parent / "snapshots").glob("*.txt")]
    assert [t for t in texts if "interview" in t.lower()] == []

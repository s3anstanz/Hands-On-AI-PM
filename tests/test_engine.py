from types import SimpleNamespace

import pytest
from helpers import ScriptedIO

import data
import engine
import live
from engine import Chapter, Ctx, LearnScreen, QuickCheck
from progress import Score


def visit(name):
    def step(ctx):
        ctx.state.setdefault("visits", []).append(name)
        ctx.console.print(f"{name} rand={ctx.rng.random():.6f}")

    return step


FAKE = Chapter(
    id="T",
    title="Test chapter",
    minutes=1,
    learn=(LearnScreen("Screen one", "Body with **term** and [brackets].", "Because it matters."),),
    recap=("Point one",),
    checks=(QuickCheck("Pick two", ("one", "two"), answer=1, explanation="Two is right.", screen=1),),
    hands_on=(visit("A"), visit("B")),
)
RUBRIC = data.ChapterRubric(
    "Test question?",
    ("covers x", "covers y", "covers z"),
    (data.FollowUp("Twist?", "Strong says w."), data.FollowUp("Other?", "Strong says v.")),
    hint="x · y · z",
    sample_answer="A model answer covering x, y and z.",
)
BUNDLE = data.Bundle(prompts=[], rubrics={"T": RUBRIC}, glossary=[])


def make_ctx(io, **kwargs):
    scored = []
    ctx = Ctx(io=io, seed=1, chapter=FAKE, data=BUNDLE, on_scored=lambda s, c: scored.append((s, c)), **kwargs)
    return ctx, scored


def test_step_order_and_count():
    assert len(engine.build_steps(FAKE, learn_only=False)) == 9
    assert len(engine.build_steps(FAKE, learn_only=True)) == 4


def test_full_run_in_order():
    io = ScriptedIO()
    ctx, scored = make_ctx(io)
    assert engine.run_chapter(ctx) == "done"
    assert ctx.state["visits"] == ["A", "B"]
    out = io.output
    assert out.index("Test question?") < out.index("Screen one") < out.index("This chapter in") < out.index("Pick two")
    assert out.index("Pick two") < out.index("A rand=") < out.index("covers x")
    assert out.index("covers x") < max(out.find("Twist?"), out.find("Other?"))
    assert scored == [(Score(3, 3), None)]


def test_back_replays_the_same_numbers():
    io = ScriptedIO(overrides={"nav": ["", "", "", "", "", "b"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    a_lines = [line for line in io.output.splitlines() if line.startswith("A rand=")]
    assert len(a_lines) == 2 and a_lines[0] == a_lines[1]
    assert ctx.state["visits"] == ["A", "B", "A", "B"]


def test_quit_returns_quit():
    io = ScriptedIO(overrides={"nav": ["q"]})
    ctx, scored = make_ctx(io)
    assert engine.run_chapter(ctx) == "quit"
    assert "visits" not in ctx.state and scored == []


def test_nav_input_is_forgiving():
    io = ScriptedIO(overrides={"nav": ["x", " B ", "Q"]})
    ctx, _ = make_ctx(io)
    assert engine.run_chapter(ctx) == "quit"
    assert "Press Enter to continue" in io.output
    assert io.output.count("Test question?") == 2  # 'B' on step 1 stays put and re-renders


def test_learn_only_skips_practice_and_scoring():
    io = ScriptedIO()
    ctx, scored = make_ctx(io)
    assert engine.run_chapter(ctx, learn_only=True) == "done"
    assert "visits" not in ctx.state and scored == []


def test_wrong_quick_check_offers_reread():
    io = ScriptedIO()  # choice "1" is wrong (answer is 2); yes/no "y" rereads
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    assert "Not quite: it's 2." in io.output
    assert io.output.count("1 of 1 · Screen one") == 2


def test_learn_screen_escapes_brackets():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    assert "[brackets]" in io.output


def test_ask_choice_reprompts_until_valid():
    io = ScriptedIO(overrides={"choice": ["blue", "7", "2"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_choice("Pick", 3, key="k") == 1
    assert io.output.count("Please type a number from 1 to 3.") == 2
    assert ctx.state["k"] == 1


def test_ask_choice_keeps_previous_on_enter():
    io = ScriptedIO(overrides={"choice": [""]})
    ctx, _ = make_ctx(io)
    ctx.state["k"] = 2
    assert ctx.ask_choice("Pick", 3, key="k") == 2
    assert "(Enter keeps: 3)" in io.prompts[-1][1]


def test_ask_number_validates_range():
    io = ScriptedIO(overrides={"number": ["hot", "5", "0.7"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Temperature", key="t", low=0, high=2) == 0.7
    assert io.output.count("Please type a number from 0 to 2.") == 2


def test_yes_no_reprompts():
    io = ScriptedIO(overrides={"yesno": ["maybe", "N"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_yes_no("Sure?", default=True) is False
    assert "Please type y or n." in io.output


def test_empty_answer_can_skip_grading():
    io = ScriptedIO(overrides={"multiline": [""]})
    ctx, scored = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Grading skipped" in io.output and scored == []


def test_self_score_counts_yes_answers():
    io = ScriptedIO(overrides={"yesno": ["n", "y", "n", "y"]})  # reread? no; then 3 checklist items
    ctx, scored = make_ctx(io)
    engine.run_chapter(ctx)
    assert scored == [(Score(2, 3), None)]


def fake_live(result, error=""):
    return SimpleNamespace(grade=lambda question, checklist, answer: result, spent=0.0, last_error=error)


def test_claude_grade_recorded():
    items = tuple(live.GradeItem(c, met, "why") for c, met in zip(RUBRIC.checklist, (True, False, True), strict=True))
    io = ScriptedIO(overrides={"yesno": ["n", "y", "y", "y", "y"]})  # no reread, 3 items, grade with Claude
    ctx, scored = make_ctx(io, live=fake_live(live.GradeResult(items, "Add a number.")))
    engine.run_chapter(ctx)
    assert scored == [(Score(3, 3), Score(2, 3))]
    assert "Add a number." in io.output
    assert any("live spent $0" in prompt for kind, prompt in io.prompts if kind == "nav")


def test_claude_grade_failure_keeps_self_score():
    io = ScriptedIO(overrides={"yesno": ["n", "y", "y", "y", "y"]})
    ctx, scored = make_ctx(io, live=fake_live(None, error="rate limited; try again in a minute"))
    engine.run_chapter(ctx)
    assert "rate limited" in io.output
    assert scored == [(Score(3, 3), None)]


def test_narrow_terminal_runs():
    io = ScriptedIO(width=40)
    ctx, _ = make_ctx(io)
    assert engine.run_chapter(ctx) == "done"


def test_make_rng_is_stable_and_seed_specific():
    assert engine.make_rng(1, "T", 4).random() == engine.make_rng(1, "T", 4).random()
    assert engine.make_rng(1, "T", 4).random() != engine.make_rng(2, "T", 4).random()


def test_superscript_digit_reprompts_instead_of_crashing():
    io = ScriptedIO(overrides={"choice": ["²", "2"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_choice("Pick", 3, key="k") == 1
    assert io.output.count("Please type a number from 1 to 3.") == 1


def test_q_at_a_choice_prompt_quits_the_chapter():
    io = ScriptedIO(overrides={"choice": ["q"]})
    ctx, _ = make_ctx(io)
    assert engine.run_chapter(ctx, learn_only=True) == "quit"


def test_b_at_a_choice_prompt_goes_back_a_step():
    io = ScriptedIO(overrides={"choice": ["B", "2"]})
    ctx, _ = make_ctx(io)
    assert engine.run_chapter(ctx, learn_only=True) == "done"
    assert io.output.count("Pick two") == 2
    assert io.output.count("Point one") == 2  # the Recap step re-rendered


def test_q_at_a_number_prompt_quits_the_chapter():
    def step(ctx):
        ctx.ask_number("Temperature", key="t", low=0, high=2)

    chapter = Chapter("T", "T", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    io = ScriptedIO(overrides={"number": ["q"]})
    ctx = Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE)
    assert engine.run_chapter(ctx) == "quit"


def test_q_at_a_pause_quits_the_chapter():
    def step(ctx):
        ctx.pause("Enter for the next token")
        ctx.state["after_pause"] = True

    chapter = Chapter("T", "T", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    io = ScriptedIO(overrides={"pause": [" Q "]})
    ctx = Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE)
    assert engine.run_chapter(ctx) == "quit"
    assert "after_pause" not in ctx.state


def test_learn_only_footer_says_quit_not_menu():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    navs = [prompt for kind, prompt in io.prompts if kind == "nav"]
    assert navs and all("[q] quit" in p and "[q] menu" not in p for p in navs)


def test_short_answer_asks_for_a_full_sentence():
    io = ScriptedIO(overrides={"multiline": ["idk", "", helpers_default(), ""], "yesno": ["n", "y", "y", "y", "y"]})
    ctx, scored = make_ctx(io)  # yes/no: no reread, yes try again, 3 checklist items
    engine.run_chapter(ctx)
    assert "at least one full sentence" in io.output
    assert ctx.state["answer"] == helpers_default()
    assert scored == [(Score(3, 3), None)]


def test_short_answer_can_still_be_graded():
    io = ScriptedIO(overrides={"multiline": ["idk", ""], "yesno": ["n", "n", "y", "y", "y"]})
    ctx, scored = make_ctx(io)  # yes/no: no reread, no (grade it anyway), 3 checklist items
    engine.run_chapter(ctx)
    assert ctx.state["answer"] == "idk"
    assert scored == [(Score(3, 3), None)]


def helpers_default():
    from helpers import DEFAULT_ANSWER

    return DEFAULT_ANSWER


def test_claude_grade_prompt_shows_the_prices_checked_date():
    import pricing

    items = tuple(live.GradeItem(c, True, "why") for c in RUBRIC.checklist)
    io = ScriptedIO(overrides={"yesno": ["n", "y", "y", "y", "y"]})
    ctx, _ = make_ctx(io, live=fake_live(live.GradeResult(items, "ok")))
    engine.run_chapter(ctx)
    grade_prompt = next(p for kind, p in io.prompts if kind == "yesno" and "Claude grade" in p)
    assert f"prices checked {pricing.LAST_CHECKED}" in grade_prompt


# Feedback: f (or /feedback) at any prompt that also takes b and q.


def feedback_query(url):
    from urllib.parse import parse_qs, urlsplit

    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_f_at_the_footer_sends_feedback_then_stays_on_the_step(browser):
    io = ScriptedIO(
        overrides={"nav": ["f"], "multiline": ["The question was unclear.", ""], "choice": ["2"], "yesno": ["y", "y"]}
    )
    ctx, scored = make_ctx(io)
    assert engine.run_chapter(ctx) == "done"
    assert len(browser.opened) == 1
    q = feedback_query(browser.opened[0])
    assert q["title"] == "Confusing: The question was unclear."
    assert q["where"] == "Chapter T (Test chapter), step 1 of 9, seed 1"
    assert "Back to step 1." in io.output
    assert ctx.state["visits"] == ["A", "B"]  # the chapter carried on from the same step
    assert scored == [(Score(3, 3), None)]


def test_f_inside_a_question_sends_feedback_then_asks_again(browser):
    def step(ctx):
        ctx.state["picked"] = ctx.ask_choice("Pick", 3, key="p")

    chapter = Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    io = ScriptedIO(overrides={"choice": ["/feedback", "3", "2"], "multiline": ["Option 2 is wrong.", ""]})
    ctx = Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE)
    engine.run_chapter(ctx, learn_only=False)
    assert feedback_query(browser.opened[0])["title"] == "Idea: Option 2 is wrong."
    assert ctx.state["picked"] == 1


def test_f_at_a_pause_sends_feedback_then_waits_again(browser):
    def step(ctx):
        ctx.pause("Enter for the next token")
        ctx.state["after_pause"] = True

    chapter = Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    io = ScriptedIO(overrides={"pause": ["F", ""], "multiline": ["Too fast.", ""]})
    ctx = Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE)
    engine.run_chapter(ctx)
    assert len(browser.opened) == 1
    assert ctx.state["after_pause"] is True
    assert [kind for kind, _ in io.prompts].count("pause") == 2


def test_feedback_with_nothing_typed_sends_nothing(browser):
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": [""]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert browser.opened == []
    assert "Nothing typed, so nothing sent." in io.output


def test_feedback_declined_at_the_preview_sends_and_saves_nothing(browser):
    import feedback

    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Hmm.", ""], "yesno": ["n"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert browser.opened == []
    assert feedback.load_pending() == ([], [])
    assert "Not sent." in io.output


def test_preview_shows_everything_that_will_be_sent():
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Hmm.", ""], "yesno": ["n"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    out = io.output
    assert "Title: Bug: Hmm." in out
    assert "Where: Chapter T (Test chapter), step 1 of 9, seed 1" in out
    assert "Also sent: Commit " in out and " offline mode" in out


def test_feedback_summary_becomes_the_title(browser):
    from urllib.parse import parse_qs, urlsplit

    io = ScriptedIO(
        overrides={"nav": ["f"], "multiline": ["Hmm, long rambling note.", ""], "optional": ["  No Windows   steps "]}
    )
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Give it a short title (Enter to use the first line of your note)" in io.output
    assert "Title: Bug: No Windows steps" in io.output
    query = parse_qs(urlsplit(browser.opened[0]).query)
    assert query["title"] == ["Bug: No Windows steps"]
    assert query["feedback"] == ["Hmm, long rambling note."]


def test_feedback_says_it_is_not_sent_until_submit_is_clicked(browser):
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Nice.", ""], "yesno": ["y", "y"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Nothing is sent until you click Submit new issue" in io.output
    assert ("yesno", "Did you click Submit new issue? [Y/n]") in io.prompts


def test_feedback_that_went_through_is_not_kept(browser):
    import feedback

    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Nice.", ""], "yesno": ["y", "y"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert feedback.load_pending() == ([], [])
    assert "Thanks!" in io.output


def test_feedback_kept_for_next_time_when_the_browser_fails(browser):
    import feedback

    browser.works = False
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Nice.", ""], "yesno": ["y", "n"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    out = io.output
    assert "Couldn't open a browser" in out and f"https://github.com/{feedback.REPO}/issues/new?" in out
    went_through = [p for kind, p in io.prompts if kind == "yesno" and "Submit new issue" in p]
    assert went_through and went_through[0].endswith("[y/N]")  # no browser: Enter must not discard the note
    notes, _ = feedback.load_pending()
    assert [n.text for _, n in notes] == ["Nice."]
    assert "next time you start the tutorial" in out


def test_long_feedback_warns_that_the_link_holds_only_the_start(browser):
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["word " * 3000, ""], "yesno": ["y", "y"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Paste the rest" in io.output


def test_end_of_chapter_offers_feedback(browser):
    io = ScriptedIO(overrides={"offer": ["y"], "yesno": ["n", "y", "y", "y", "y", "y"]})
    # yes/no: no reread, 3 checklist items, then the feedback preview and "went through"
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    offers = [p for kind, p in io.prompts if kind == "offer"]
    assert offers == ["How was this chapter? Want to send feedback? [y/N]"]
    q = feedback_query(browser.opened[0])
    assert q["where"] == "End of Chapter T (Test chapter), seed 1"


def test_feedback_never_includes_the_chapter_answer(browser):
    answer = "My private answer about next-token prediction."
    io = ScriptedIO(
        overrides={
            "offer": ["y"],
            "multiline": [answer, "", "A follow-up reply.", "", "The chapter was good.", ""],
            "yesno": ["n", "y", "y", "y", "y", "y"],
        }
    )
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert ctx.state["answer"] == answer
    sent = feedback_query(browser.opened[0])
    assert sent["feedback"] == "The chapter was good."
    assert not any("private answer" in value or "follow-up reply" in value for value in sent.values())


def test_end_of_chapter_offer_is_skipped_by_default_and_in_learn_only_mode():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert [kind for kind, _ in io.prompts].count("offer") == 1
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    assert "offer" not in [kind for kind, _ in io.prompts]


def test_footer_hint_mentions_feedback():
    io = ScriptedIO(overrides={"nav": ["x"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "or f (feedback)" in io.output


def test_feedback_kind_must_be_a_listed_number(browser):
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Hmm.", ""], "choice": ["9", "x", "4"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert io.output.count("Please type a number from 1 to 4.") == 2
    assert feedback_query(browser.opened[0])["title"] == "Liked it: Hmm."


def test_unsaved_feedback_that_did_not_go_through_prints_the_link(browser, monkeypatch, tmp_path):
    import feedback

    blocker = tmp_path / "a-file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(feedback, "FEEDBACK_DIR", blocker / "feedback")
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Hmm.", ""], "yesno": ["y", "n"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Couldn't save it on this computer" in io.output
    assert io.output.count(f"https://github.com/{feedback.REPO}/issues/new?") == 1


def test_saved_copy_that_cannot_be_removed_is_reported(browser, monkeypatch):
    import feedback

    monkeypatch.setattr(feedback, "discard", lambda path: f"Couldn't remove the saved copy at {path}.")
    io = ScriptedIO(overrides={"nav": ["f"], "multiline": ["Hmm.", ""], "yesno": ["y", "y"]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    assert "Couldn't remove the saved copy at" in io.output and "Thanks!" in io.output


def test_self_grading_shows_your_answer_first():
    answer = "It predicts one token at a time from probabilities."
    io = ScriptedIO(overrides={"multiline": [answer, ""]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    out = io.output
    grading = out.index("A strong answer covers these")
    shown = out.rfind("Your answer", 0, grading)
    assert shown != -1 and answer in out[shown:grading]


def test_recap_says_what_it_recaps():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    assert 'This chapter in 1 point. It\'s also what a strong answer to "Test question?" covers.' in io.output


def test_opening_question_says_where_to_find_what_a_strong_answer_covers():
    io = ScriptedIO(width=200)
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx, learn_only=True)
    assert "The Recap at the end of the Learn section lists what a strong answer covers." in io.output


def test_h_at_the_answer_shows_the_hint_then_asks_again():
    answer = "It covers x and y and z for sure."
    io = ScriptedIO(overrides={"multiline": [" H ", "", answer, ""]})
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    out = io.output
    assert "Stuck? Type h for a hint." in out
    assert "Hint: x · y · z" in out
    assert ctx.state["answer"] == answer


def test_strong_answer_and_say_it_again_after_grading():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    engine.run_chapter(ctx)
    out = io.output
    shown = out.index("A model answer covering x, y and z.")
    assert out.index("Self-score:") < shown < out.index("Follow-up:")
    assert "Now say it out loud once more, in your own words." in out[shown:]


def test_strong_answer_shown_even_when_grading_is_skipped():
    io = ScriptedIO(overrides={"multiline": [""], "yesno": ["n", "y"]})  # no reread; yes, skip grading
    ctx, scored = make_ctx(io)
    engine.run_chapter(ctx)
    assert scored == []
    assert "A model answer covering x, y and z." in io.output


def test_h_keeps_the_answer_you_already_gave():
    earlier = "My earlier full answer about tokens and probabilities."
    io = ScriptedIO(overrides={"multiline": ["h", "", ""]})  # hint, then an empty line keeps the earlier answer
    ctx, _ = make_ctx(io)
    ctx.state["answer"] = earlier  # as if the user came back with b
    engine._answer_step(ctx)
    assert ctx.state["answer"] == earlier
    assert "That's very short" not in io.output
    assert "Your previous answer (an empty line keeps it):\nh\n" not in io.output


def number_or_skip_chapter(store):
    def step(ctx):
        store.append(ctx.ask_number_or_skip("Temperature", key="t", low=0, high=2))

    return Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))


def test_number_or_skip_returns_none_on_enter():
    got = []
    io = ScriptedIO(overrides={"optional": [""]})
    engine.run_chapter(Ctx(io=io, seed=1, chapter=number_or_skip_chapter(got), data=BUNDLE))
    assert got == [None]


def test_number_or_skip_validates_the_range():
    got = []
    io = ScriptedIO(overrides={"optional": ["3", "hot", "-1", "0.0"]})
    engine.run_chapter(Ctx(io=io, seed=1, chapter=number_or_skip_chapter(got), data=BUNDLE))
    assert got == [0.0]
    assert io.output.count("Please type a number from 0 to 2, or press Enter to move on.") == 3


def test_q_at_a_number_or_skip_prompt_quits():
    got = []
    io = ScriptedIO(overrides={"optional": ["q"]})
    assert engine.run_chapter(Ctx(io=io, seed=1, chapter=number_or_skip_chapter(got), data=BUNDLE)) == "quit"
    assert got == []


def test_scripted_number_default_stays_inside_the_range():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Tokens", key="n", low=1, high=100, integer=True) == 1
    assert ctx.ask_number("Temperature", key="t", low=0, high=2) == 0


def line_chapter(store):
    def step(ctx):
        store.append(ctx.ask_line("Your text"))

    return Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))


def test_ask_line_returns_the_line_as_typed():
    got = []
    io = ScriptedIO(overrides={"optional": ["  [b]old text "]})
    engine.run_chapter(Ctx(io=io, seed=1, chapter=line_chapter(got), data=BUNDLE))
    assert got == ["  [b]old text "]
    assert ("optional", "Your text") in io.prompts


def test_q_at_a_line_prompt_quits():
    got = []
    io = ScriptedIO(overrides={"optional": ["q"]})
    assert engine.run_chapter(Ctx(io=io, seed=1, chapter=line_chapter(got), data=BUNDLE)) == "quit"
    assert got == []


def test_f_at_a_line_prompt_sends_feedback_then_asks_again(browser):
    got = []
    io = ScriptedIO(overrides={"optional": ["f", "", "hello"], "multiline": ["Confusing.", ""]})
    engine.run_chapter(Ctx(io=io, seed=1, chapter=line_chapter(got), data=BUNDLE))
    assert len(browser.opened) == 1
    assert got == ["hello"]


def test_number_or_skip_integer_rejects_fractions():
    got = []

    def step(ctx):
        got.append(ctx.ask_number_or_skip("Line", key="l", low=1, high=5, integer=True))

    chapter = Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    io = ScriptedIO(overrides={"optional": ["1.9", "2"]})
    engine.run_chapter(Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE))
    assert got == [2.0]
    assert io.output.count("Please type a whole number from 1 to 5, or press Enter to move on.") == 1


def test_minus_zero_is_read_as_zero():
    got = []
    io = ScriptedIO(overrides={"optional": ["-0"], "number": ["-0"]})

    def step(ctx):
        got.append(ctx.ask_number_or_skip("Temperature", key="t", low=0, high=2))
        got.append(ctx.ask_number("Runs", key="n", low=0, high=20))

    chapter = Chapter("T", "Test chapter", 1, FAKE.learn, FAKE.recap, (), hands_on=(step,))
    engine.run_chapter(Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE))
    assert [f"{value:g}" for value in got] == ["0", "0"]


def test_a_ctx_built_directly_has_a_seeded_rng():
    # Step tests build Ctx without run_chapter; an unseeded default rng made them flaky (about 1 run in 100).
    first = Ctx(io=ScriptedIO(), seed=5, chapter=FAKE, data=BUNDLE)
    again = Ctx(io=ScriptedIO(), seed=5, chapter=FAKE, data=BUNDLE)
    assert first.rng.random() == again.rng.random() == engine.make_rng(5, "T", 0).random()


def test_whole_number_prompts_reject_decimals_and_words():
    io = ScriptedIO(overrides={"number": ["7.5", "seven", "-3", " 7 "]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Runs", key="n", low=0, high=20, integer=True) == 7
    assert io.output.count("Please type a whole number from 0 to 20.") == 3


@pytest.mark.parametrize(
    "value, shown", [(0, "0"), (0.5, "0.5"), (2.0, "2"), (1_000, "1,000"), (10_000_000, "10,000,000")]
)
def test_show_number(value, shown):
    assert engine.show_number(value) == shown


@pytest.mark.parametrize(
    "reply, value", [("50,000", 50_000.0), ("1,000,000", 1_000_000.0), ("0.5", 0.5), ("12", 12.0), ("-0", 0.0)]
)
def test_parse_number(reply, value):
    assert engine.parse_number(reply) == value


@pytest.mark.parametrize("reply", ["0,5", "1,00", "abc", ""])
def test_parse_number_rejects_ambiguous_or_bad_input(reply):
    assert engine.parse_number(reply) is None


def test_big_number_prompts_use_commas_not_exponents():
    io = ScriptedIO(overrides={"number": ["2,500,000"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Requests per day", key="r", low=1, high=10_000_000) == 2_500_000
    assert "[1-10,000,000]" in io.prompts[-1][1]
    io = ScriptedIO(overrides={"number": [""]})
    ctx, _ = make_ctx(io)
    ctx.state["r"] = 2_500_000.0
    assert ctx.ask_number("Requests per day", key="r", low=1, high=10_000_000) == 2_500_000
    assert "(Enter keeps: 2,500,000)" in io.prompts[-1][1]


def test_scripted_number_default_handles_comma_ranges():
    io = ScriptedIO()
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Requests per day", key="r", low=1_000, high=10_000_000) == 1_000


@pytest.mark.parametrize(
    "reply, value", [("1,000", 1_000.0), ("12", 12.0), ("7.5", None), ("1,000.5", None), ("0,5", None)]
)
def test_whole_numbers_accept_thousands_commas(reply, value):
    assert engine.parse_number(reply, integer=True) == value


def test_whole_number_prompt_with_a_big_range_uses_commas():
    io = ScriptedIO(overrides={"number": ["2.5", "25,000"]})
    ctx, _ = make_ctx(io)
    assert ctx.ask_number("Users", key="u", low=1, high=100_000, integer=True) == 25_000
    assert "Please type a whole number from 1 to 100,000." in io.output


def test_after_grade_steps_replace_the_rubric_follow_up():
    chapter = Chapter(
        "T", "Test chapter", 1, FAKE.learn, FAKE.recap, FAKE.checks, FAKE.hands_on, after_grade=(visit("X"), visit("Y"))
    )
    io = ScriptedIO()
    ctx = Ctx(io=io, seed=1, chapter=chapter, data=BUNDLE)
    assert engine.run_chapter(ctx) == "done"
    assert ctx.state["visits"] == ["A", "B", "X", "Y"]
    assert "Twist?" not in io.output and "Other?" not in io.output
    assert io.output.index("Self-score:") < io.output.index("X rand=")
    assert len(engine.build_steps(chapter, learn_only=False)) == 10
    assert len(engine.build_steps(chapter, learn_only=True)) == 4


def test_chapters_without_after_grade_keep_one_rubric_follow_up():
    assert engine.build_steps(FAKE, learn_only=False)[-1] is engine._followup_step


def page(name):
    def show(console):
        console.print(f"Page {name}")

    return show


def test_pages_enter_through_to_the_end():
    io = ScriptedIO()
    assert engine.run_pages(io, "Cheat sheet", [page("one"), page("two")]) == "done"
    assert io.output.index("Page one") < io.output.index("Page two")
    navs = [p for kind, p in io.prompts if kind == "nav"]
    assert navs[0].startswith("Cheat sheet · Page 1/2") and "[q] menu" in navs[0]


def test_pages_b_goes_back_and_q_leaves():
    io = ScriptedIO(overrides={"nav": ["", "b", "", "q"]})
    assert engine.run_pages(io, "Cheat sheet", [page("one"), page("two"), page("three")]) == "quit"
    assert io.output.count("Page one") == 2 and io.output.count("Page two") == 2
    assert "Page three" not in io.output


def test_pages_hint_on_unknown_input():
    io = ScriptedIO(overrides={"nav": ["x"]})
    engine.run_pages(io, "Cheat sheet", [page("one")])
    assert "Press Enter to continue, or type b (back), q (menu) or f (feedback)." in io.output


def test_f_on_a_page_sends_feedback_naming_the_page(browser):
    io = ScriptedIO(overrides={"nav": ["", "f"], "multiline": ["Typo here.", ""], "yesno": ["y", "y"]})
    assert engine.run_pages(io, "Cheat sheet", [page("one"), page("two")]) == "done"
    assert feedback_query(browser.opened[0])["where"] == "Cheat sheet, page 2 of 2"
    assert "Back to page 2." in io.output


def test_terminal_io_hands_the_prompt_to_input(monkeypatch):
    # The line editor can only move across a wrapped line if input() itself printed the prompt and so knows
    # where the text starts. Rich's console.input prints the prompt separately (Sean, 2026-10-14: backspace got
    # stuck once a long answer wrapped).
    import io as stdio

    from rich.console import Console

    seen = []
    monkeypatch.setattr("builtins.input", lambda prompt="": seen.append(prompt) or "typed")
    terminal = engine.TerminalIO(Console(file=stdio.StringIO()))
    assert terminal.ask("Your pick [1-3]", "choice") == "typed"
    assert seen == ["Your pick [1-3] "]


def test_terminal_io_turns_on_line_editing(monkeypatch):
    # Doesn't depend on this machine having readline: record the import TerminalIO attempts (Codex, #37).
    import io as stdio

    from rich.console import Console

    attempted = []
    monkeypatch.setattr(engine.importlib, "import_module", lambda name: attempted.append(name))
    engine.TerminalIO(Console(file=stdio.StringIO()))
    assert attempted == ["readline"]


def test_terminal_io_works_without_readline(monkeypatch):
    # Windows, and Pythons built without readline: no line editor, but asking still works.
    import io as stdio

    from rich.console import Console

    def missing(name):
        raise ImportError(name)

    monkeypatch.setattr("builtins.input", lambda prompt="": "typed")  # before the import is broken below
    monkeypatch.setattr(engine.importlib, "import_module", missing)
    assert engine.TerminalIO(Console(file=stdio.StringIO())).ask("Your pick [1-3]", "choice") == "typed"

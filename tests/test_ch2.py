import importlib.util
import random
import re

import pytest
from helpers import ScriptedIO
from rich.cells import cell_len

import costs
import data
import engine
import pricing
import tokens
from lessons import ch2_tokens as ch2

BUNDLE = data.load_all()
NO_ESTIMATE = "no reliable Claude estimate for this text (Anthropic's ratio is for English)"
MERGED = "Some emoji and scripts merge several tokens into one color."


def run_step(step, io, live=None, seed=1):
    ctx = engine.Ctx(io=io, seed=seed, chapter=ch2.CHAPTER, data=BUNDLE, live=live)
    step(ctx)
    return ctx


class FakeLive:
    def __init__(self, count=None, error="", io=None):
        self.count, self.last_error, self.io = count, error, io
        self.spent = 0.0
        self.calls = 0
        self.shown_before_call = ""

    def count_tokens(self, text, model_id):
        self.calls += 1
        self.shown_before_call = self.io.output if self.io is not None else ""
        return self.count


@pytest.fixture
def no_tokenizer(monkeypatch):
    monkeypatch.setattr(tokens, "_encoding", False)  # as if the bundled tokenizer failed to load


def row(name, *cells):
    """A table row: the name, then each cell, separated by column borders."""
    return re.compile(r"│ " + re.escape(name) + r"\s*" + "".join(rf"│\s*{re.escape(c)}\s*" for c in cells) + "│")


def test_learn_copy_numbers_still_match_the_tokenizer():
    # Learn screens 1, 2 and 5 quote measured counts; a tokenizer change must fail here, not mislead learners.
    split = " · ".join(tokens.split_for_display("antidisestablishmentarianism"))
    assert split == "ant · idis · est · ablishment · arian · ism" and split in ch2.LEARN[0].example
    assert ch2.LEARN[0].example.startswith("On OpenAI's public tokenizer,")  # screen 4 teaches tokenizers differ
    split = " · ".join(tokens.split_for_display("Zorblax"))
    assert split == "Z · or · bl · ax" and split in ch2.LEARN[1].example
    assert "on OpenAI's public tokenizer it's built from Z · or · bl · ax" in ch2.LEARN[1].example
    english = tokens.openai_count("The meeting is moved to Thursday afternoon.")[0]
    hindi = tokens.openai_count(dict(ch2.LANGUAGES)["Hindi"])[0]
    assert (english, hindi) == (8, 17)
    assert f'afternoon." is {english} tokens. The same sentence in Hindi is {hindi}.' in ch2.LEARN[4].example


def quoted_numbers():
    """The numbers the chapter teaches, worked out the way the copy should: never typed."""
    words = sum(tokens.word_count(p) for p in ch2.PARAGRAPHS)
    counted = sum(tokens.openai_count(p)[0] for p in ch2.PARAGRAPHS)
    english = tokens.openai_count(dict(ch2.LANGUAGES)["English"])[0]
    return {
        "rule": f"{round(1000 / pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN, -2):,.0f}",
        "openai": f"{round(1000 * counted / words, -2):,.0f}",
        "claude": f"{round(1000 / pricing.CLAUDE_WORDS_PER_TOKEN, -2):,.0f}",
        "japanese": f"{tokens.openai_count(dict(ch2.LANGUAGES)['Japanese'])[0] / english:.1f}×",
        "hindi": f"{tokens.openai_count(dict(ch2.LANGUAGES)['Hindi'])[0] / english:.1f}×",
    }


def test_one_defensible_number_everywhere():
    n = quoted_numbers()
    assert (n["rule"], n["openai"], n["claude"]) == ("1,300", "1,100", "1,800")  # what learners read today
    line = (
        f"By the classic ¾ rule, 1,000 words is about {n['rule']} tokens. Today's tokenizers range from about "
        f"{n['openai']} (OpenAI) to about {n['claude']} (Claude), so measure your own text."
    )
    assert line in ch2.LEARN[3].example
    assert line in ch2.RECAP[5]
    assert f"{n['openai']} to {n['claude']}" in ch2.CHECKS[0].explanation
    rubric = BUNDLE.rubrics["2"]
    for text in (rubric.checklist[5], rubric.sample_answer):
        assert all(n[key] in text for key in ("rule", "openai", "claude")), text
    assert n["japanese"] in rubric.sample_answer and n["hindi"] in rubric.sample_answer
    assert n["hindi"] in ch2.RECAP[3] and "Japanese" not in ch2.RECAP[3]  # the languages step predicts Japanese
    assert rubric.sample_answer.rstrip().endswith("before we set prices or usage limits.")  # ends with a recommendation


def test_rubric_items_are_unambiguous():
    items = BUNDLE.rubrics["2"].checklist
    assert len(items) == 6
    assert "not always a whole word" in items[0] and "not a word" not in items[0]
    assert "and says it depends on the tokenizer" in items[1]
    assert "at least two" in items[3]
    assert "roughly right" in items[5]


def test_learn_names_the_claude_tokenizer_plainly():
    body = ch2.LEARN[3].body
    assert "Anthropic's current tokenizer (Claude 4.7 and every newer model)" in body
    assert "including the 5.5 models" not in body


def test_learn_copy_ratios_still_match_pricing():
    # Learn screen 4 rounds pricing.py's ratios into words; a price-file change must fail here.
    screen = ch2.LEARN[3]
    assert f"about {pricing.CLAUDE_WORDS_PER_TOKEN:g} words per token" in screen.body


def predicted(guess, seed=3):
    io = ScriptedIO(overrides={"number": [guess]})
    ctx = run_step(ch2.predict_tokens, io, seed=seed)
    sentence = next(s for s in ch2.SENTENCES if s in io.output)
    return io, ctx, sentence, tokens.openai_count(sentence)[0]


def test_predict_reveals_the_measured_count():
    io, ctx, sentence, count = predicted("12")
    assert f"{count} tokens on" in io.output and "You guessed 12" in io.output
    assert "Each color is one token." in io.output and MERGED not in io.output
    assert ctx.state["guess_tokens"] == 12
    rule = round(tokens.word_count(sentence) / pricing.OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN)
    assert f"The ¾ rule would say about {rule}. Short common words are about one token each." in io.output


def test_predict_gives_a_verdict():
    _, _, _, count = predicted("1")
    io, _, _, _ = predicted(str(count))
    assert f"You guessed {count}: spot on." in io.output
    io, _, _, _ = predicted(str(count + 3))
    assert f"You guessed {count + 3}: off by 3." in io.output


def test_predict_takes_whole_numbers_only():
    io = ScriptedIO(overrides={"number": ["12.5", "12"]})
    run_step(ch2.predict_tokens, io, seed=3)
    assert "Please type a whole number from 1 to 100." in io.output and "You guessed 12" in io.output


def test_predict_without_the_tokenizer_says_colors_are_words(no_tokenizer):
    io = ScriptedIO()
    run_step(ch2.predict_tokens, io)
    assert "Each color is one token" not in io.output
    assert tokens.FALLBACK_LABEL in io.output and "Each color is a word, not a token" in io.output


def test_your_own_text_is_counted_until_enter():
    io = ScriptedIO(overrides={"optional": ["Zorblax is our new app", ""]})
    run_step(ch2.try_your_own, io)
    count = tokens.openai_count("Zorblax is our new app")[0]
    assert f"5 words · 22 characters · {count} tokens" in io.output
    prompts = [prompt for kind, prompt in io.prompts if kind == "optional"]
    assert len(prompts) == 2 and "one line at a time" in prompts[0]
    assert "split into many pieces" not in io.output  # about one token per word: nothing to warn about
    assert "What this shows:" in io.output.split(prompts[-1])[-1]  # the caption comes when you move on


@pytest.mark.parametrize("text", ["会議は木曜日の午後に変更されました。", "sean@example.com"])
def test_your_own_text_flags_text_that_splits_into_many_pieces(text):
    io = ScriptedIO(overrides={"optional": [text, ""]}, width=120)
    run_step(ch2.try_your_own, io)
    assert "Names, IDs and some scripts split into many pieces: that's where costs surprise you." in io.output


def test_your_own_text_has_no_word_count_without_spaces():
    io = ScriptedIO(overrides={"optional": ["会議は木曜日の午後に変更されました。", ""]}, width=120)
    run_step(ch2.try_your_own, io)
    assert "words: n/a (no spaces)" in io.output and "1 word" not in io.output


@pytest.mark.parametrize("word, move", [("q", "quit"), ("b", "back")])
def test_your_own_text_prompt_still_navigates(word, move):
    io = ScriptedIO(overrides={"optional": [word]})
    with pytest.raises(engine.LeaveStep) as left:
        run_step(ch2.try_your_own, io)
    assert left.value.move == move


def test_count_line_reads_naturally_for_one_word_and_an_exact_estimate():
    assert tokens.claude_estimate("Send it on Friday.") == (8, 8)
    assert "Claude: about 8 tokens" in ch2.count_line("Send it on Friday.")
    assert ch2.count_line("hello").startswith("1 word · ")


@pytest.mark.parametrize("text", ["sean@example.com", "会議は木曜日の午後に変更されました。", "🎉👏🏽 नमस्ते"])
def test_count_line_gives_no_claude_estimate_where_the_ratio_fails(text):
    line = ch2.count_line(text)
    assert NO_ESTIMATE in line and "Claude: about" not in line


def test_every_bills_paragraph_gets_a_reliable_claude_estimate():
    assert all(tokens.claude_estimate_reliable(p) for p in ch2.PARAGRAPHS)


@pytest.mark.parametrize("text", ["[bold]hi[/bold]", "<|endoftext|>", "🎉👏🏽 नमस्ते"])
def test_your_own_text_shows_tricky_input_literally(text):
    io = ScriptedIO(overrides={"optional": [text, ""]})
    run_step(ch2.try_your_own, io)
    assert text in io.output


@pytest.mark.parametrize("text, merged", [("🎉👏🏽 नमस्ते", True), ("Zorblax is our new app", False)])
def test_your_own_text_notes_when_one_color_holds_several_tokens(text, merged):
    io = ScriptedIO(overrides={"optional": [text, ""]})
    run_step(ch2.try_your_own, io)
    assert (MERGED in io.output) is merged


def test_long_paste_is_counted_in_full_but_drawn_short():
    text = "word " * 2000
    io = ScriptedIO(overrides={"optional": [text, ""]})
    run_step(ch2.try_your_own, io)
    assert f"{tokens.openai_count(text)[0]} tokens" in io.output
    assert "(showing the first 300 characters; the counts are for all of it)" in io.output


def test_measure_rule_shows_rule_measured_and_claude_ratios():
    io = ScriptedIO()
    run_step(ch2.measure_rule, io, seed=5)
    out = io.output
    assert "0.75" in out and f"{pricing.CLAUDE_WORDS_PER_TOKEN:g}" in out and "0.56" not in out
    used = [p for p in ch2.PARAGRAPHS if p[:40] in out]
    assert len(used) == 3
    words = sum(tokens.word_count(p) for p in used)
    counted = sum(tokens.openai_count(p)[0] for p in used)
    assert f"{words / counted:.2f}" in out and "Measured: " in out


def test_measure_rule_without_the_tokenizer_says_estimated(no_tokenizer):
    io = ScriptedIO(width=120)
    run_step(ch2.measure_rule, io, seed=5)
    assert f"Estimated: {tokens.FALLBACK_LABEL}" in io.output and "Measured" not in io.output


def shown(text):
    return " · ".join(
        piece.replace(" ", "␣") + (f"({n})" if n > 1 else "") for piece, n in tokens.split_with_counts(text)
    )


def test_gallery_measures_every_entry():
    io = ScriptedIO(width=120)
    run_step(ch2.gallery, io)
    for label, text in ch2.HARD:
        count = tokens.openai_count(text)[0]
        assert re.search(rf"│ {re.escape(label)}\s*│\s*{count} │ ", io.output), label
        assert shown(text)[:20] in io.output
    assert "! · ␣ · 🎉" in io.output  # the lone space is a token too
    assert "🏽(2)" in io.output and "🚀(2)" in io.output  # 8 pieces, 10 tokens: now countable by eye
    assert "🏽(2) is one piece holding 2 tokens" in " ".join(io.output.split())


def test_gallery_without_the_tokenizer_hides_the_pieces(no_tokenizer):
    io = ScriptedIO(width=120)
    run_step(ch2.gallery, io)
    assert "Pieces" not in io.output and "ablishment" not in io.output
    assert tokens.FALLBACK_LABEL in io.output


@pytest.mark.parametrize("step", [ch2.measure_rule, ch2.gallery])
def test_narrow_tables_wrap_instead_of_cutting_text(step):
    io = ScriptedIO(width=40)
    run_step(step, io)
    assert "…" not in io.output


def test_languages_predict_then_reveal():
    io = ScriptedIO(overrides={"choice": ["2"]}, width=120)
    run_step(ch2.languages, io)
    assert "You predicted the Japanese version." in io.output
    english = tokens.openai_count(ch2.LANGUAGES[0][1])[0]
    for name, text in ch2.LANGUAGES:
        count = tokens.openai_count(text)[0]
        assert row(name, str(count), f"{count / english:.1f}×").search(io.output), name
    assert "Japanese takes 1.5× and Hindi 2.1× the tokens of English here." in io.output


@pytest.mark.parametrize(
    "english, japanese, verdict",
    [("one two three", "one", "English takes more tokens here."), ("one two", "three four", "They take the same")],
)
def test_languages_verdict_when_japanese_is_not_longer(monkeypatch, english, japanese, verdict):
    monkeypatch.setattr(ch2, "LANGUAGES", (("English", english), ("Japanese", japanese)))
    io = ScriptedIO(width=120)
    run_step(ch2.languages, io)
    assert verdict in io.output


def test_languages_without_the_tokenizer_label_the_counts_and_skip_the_verdict(no_tokenizer):
    io = ScriptedIO(width=120)
    run_step(ch2.languages, io)
    assert tokens.FALLBACK_LABEL in io.output
    assert "takes" not in io.output and "same number" not in io.output


def test_languages_without_the_tokenizer_show_the_taught_counts_not_estimates(no_tokenizer):
    io = ScriptedIO(width=120)
    run_step(ch2.languages, io)
    assert f"English {ch2.ENGLISH_TOKENS} tokens, Hindi {ch2.HINDI_TOKENS} ({ch2.HINDI_X:.1f}×)" in io.output
    assert "× English" not in io.output  # no per-language table of estimates


def claude_rows(out, count):
    return [
        key
        for key in ch2.PRICED_MODELS
        if pricing.get(key).provider == "anthropic" and row(pricing.get(key).display_name, count).search(out)
    ]


def test_different_bills_offline_uses_the_claude_estimate():
    io = ScriptedIO(width=120)
    run_step(ch2.different_bills, io, seed=2)
    out = io.output
    text = next(p for p in ch2.PARAGRAPHS if p[:40] in out)
    low, high = tokens.claude_estimate(text)
    assert f"prices checked {pricing.LAST_CHECKED}" in out
    for key in ch2.PRICED_MODELS:
        assert pricing.get(key).display_name in out
    assert len(claude_rows(out, f"~{round((low + high) / 2)}")) == 3  # a midpoint, so marked as approximate
    assert "Claude counts are estimates" in out
    flat = " ".join(out.split())
    assert "OpenAI counts use its public GPT-4o / GPT-5 era tokenizer, an approximation for GPT-6." in flat
    assert "One request is this paragraph as the whole prompt. Input only, no answer." in flat
    for key in ch2.PRICED_MODELS:  # the price per 1M input tokens, so the cost column can be checked
        assert costs.format_usd(pricing.get(key).input) in out
    assert "So compare the cost of your real text, per language, not the price per token." in flat


def test_different_bills_explains_why_more_tokens_can_cost_less():
    io = ScriptedIO(width=120)
    run_step(ch2.different_bills, io, seed=2)
    flat = " ".join(io.output.split())
    assert re.search(
        r"Claude Haiku 5\.5 counts ~?\d+ tokens to GPT-6 Astra's \d+, yet costs less, because its price per "
        r"token is lower\.",
        flat,
    ), flat[-600:]


def test_different_bills_live_uses_the_official_count():
    io = ScriptedIO(width=120)
    live = FakeLive(count=123, io=io)
    run_step(ch2.different_bills, io, live=live, seed=2)
    assert "official count (count_tokens): 123" in io.output
    assert len(claude_rows(io.output, "123")) == 3
    assert "Claude counts are official" in io.output
    assert "Same text, different bills" in live.shown_before_call
    assert "Getting the official Claude count…" in live.shown_before_call


def test_different_bills_live_counts_once_when_you_go_back():
    io = ScriptedIO(width=120)
    live = FakeLive(count=123, io=io)
    ctx = engine.Ctx(io=io, seed=2, chapter=ch2.CHAPTER, data=BUNDLE, live=live)
    for _ in range(2):
        ctx.rng = random.Random(7)  # run_chapter reseeds each visit the same way
        ch2.different_bills(ctx)
    assert live.calls == 1
    assert io.output.count("official count (count_tokens): 123") == 2


def test_different_bills_live_failure_falls_back_to_the_estimate():
    io = ScriptedIO(width=120)
    run_step(ch2.different_bills, io, live=FakeLive(count=None, error="no network"), seed=2)
    assert "Official Claude count unavailable: no network. Using the estimate." in io.output
    assert "Claude counts are estimates" in io.output


def test_hands_on_order():
    assert ch2.CHAPTER.hands_on == (
        ch2.predict_tokens,
        ch2.try_your_own,
        ch2.measure_rule,
        ch2.gallery,
        ch2.languages,
        ch2.different_bills,
    )


def test_different_bills_without_the_tokenizer_calls_the_openai_count_rough(no_tokenizer):
    io = ScriptedIO(width=120)
    run_step(ch2.different_bills, io, seed=2)
    assert f"OpenAI counts are a {tokens.FALLBACK_LABEL}." in " ".join(io.output.split())


@pytest.mark.parametrize("name", [step.__name__ for step in ch2.CHAPTER.hands_on])
def test_every_hands_on_step_has_a_what_this_shows_caption(name):
    io = ScriptedIO(width=120)
    run_step(getattr(ch2, name), io)
    assert io.output.count("What this shows:") == 1


def test_measure_rule_fits_40_columns_without_breaking_words():
    io = ScriptedIO(width=40)
    run_step(ch2.measure_rule, io)
    assert "Words/token" in io.output  # the short header stays whole; "1,000 words" may wrap at its space
    assert re.search(r"\bGPT-4o\b", io.output) and re.search(r"\bGPT-5 era\b", io.output)
    assert "GPT-4o/GP" not in io.output


@pytest.mark.parametrize("paragraph", ch2.PARAGRAPHS, ids=range(len(ch2.PARAGRAPHS)))
@pytest.mark.parametrize("step", [ch2.different_bills, ch2.measure_rule])
def test_narrow_tables_fit_40_columns_for_every_paragraph(monkeypatch, step, paragraph):
    monkeypatch.setattr(ch2, "PARAGRAPHS", (paragraph,) * 3)
    io = ScriptedIO(width=40)
    run_step(step, io)
    too_wide = [line for line in io.output.splitlines() if cell_len(line) > 40]
    assert not too_wide and "…" not in io.output, too_wide[:2]


def test_taught_numbers_survive_the_tokenizer_fallback(monkeypatch):
    # The lesson quotes measured facts; a learner whose tokenizer fails to load must see the same ones
    # the checklist and sample answer grade against (fallback estimates would say ~1,500 and ~1.1×).
    # A separate copy of the module, imported with the fallback active; the registered chapter is untouched.
    monkeypatch.setattr(tokens, "_encoding", False)
    spec = importlib.util.spec_from_file_location("ch2_on_fallback", ch2.__file__)
    assert spec is not None and spec.loader is not None
    fallback = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fallback)
    taught = (fallback.OPENAI_1000, fallback.ENGLISH_TOKENS, fallback.HINDI_TOKENS, fallback.QUOTE_LINE)
    assert taught == (ch2.OPENAI_1000, ch2.ENGLISH_TOKENS, ch2.HINDI_TOKENS, ch2.QUOTE_LINE)


def test_taught_numbers_match_the_bundled_tokenizer():
    n = quoted_numbers()
    assert f"{ch2.OPENAI_1000:,}" == n["openai"]
    english = tokens.openai_count(dict(ch2.LANGUAGES)["English"])[0]
    hindi = tokens.openai_count(dict(ch2.LANGUAGES)["Hindi"])[0]
    assert (english, hindi) == (ch2.ENGLISH_TOKENS, ch2.HINDI_TOKENS)


def test_word_comparison_check_is_not_answerable_by_length_alone():
    check = ch2.CHECKS[1]
    counts = [tokens.openai_count(option.strip('"'))[0] for option in check.options]
    assert counts.count(max(counts)) == 1 and counts.index(max(counts)) == check.answer
    longest = max(check.options, key=lambda option: len(option.strip('"')))
    assert check.options.index(longest) != check.answer  # the longest word must not be the answer
    assert check.screen == 5


def test_measure_rule_says_the_three_rows_are_estimates_of_the_same_words():
    io = ScriptedIO(width=120)
    run_step(ch2.measure_rule, io, seed=5)
    flat = " ".join(io.output.split())
    assert "Three ways to predict the tokens in these same words, scaled to 1,000 words:" in flat
    assert re.search(r"Not the same: [\d,]+ vs [\d,]+ vs [\d,]+ tokens for the same words\.", flat), flat[-500:]


def test_different_bills_shows_the_cost_of_one_request():
    io = ScriptedIO(width=120)
    run_step(ch2.different_bills, io, seed=2)
    flat = " ".join(io.output.split())
    assert "$/1M tokens" in flat and "1 request" in flat and "$/1M in" not in flat
    opus = pricing.get("opus-5-5")
    text = next(p for p in ch2.PARAGRAPHS if p[:40] in io.output)
    low, high = tokens.claude_estimate(text)
    count = round((low + high) / 2)
    one = costs.request_cost(opus, costs.Usage(input_tokens=count, output_tokens=0)).total
    assert (
        f"One {opus.display_name} request: ~{count} tokens × {costs.format_usd(opus.input)} per million "
        f"= {ch2.per_request(one)}."
    ) in flat
    assert f"A million of them: {costs.format_usd(one * ch2.REQUESTS)}." in flat

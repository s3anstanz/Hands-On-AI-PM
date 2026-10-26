import socket

import pytest
import tiktoken.registry

import tokens


@pytest.fixture
def fresh(monkeypatch):
    """Force a real load from disk: clear our cache and tiktoken's registry."""
    monkeypatch.setattr(tokens, "_encoding", None)
    monkeypatch.setattr(tiktoken.registry, "ENCODINGS", {})
    monkeypatch.delenv("TIKTOKEN_CACHE_DIR", raising=False)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("network disabled in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_bundled_encoding_loads_offline(fresh, no_network):
    assert tokens.encoding_available(), tokens.load_error
    assert tokens.openai_count("The sky is blue.") == (5, tokens.OPENAI_LABEL)
    assert tokens.openai_count("pseudohypoparathyroidism")[0] == 8


def test_missing_bundle_falls_back(fresh, no_network, monkeypatch, tmp_path):
    monkeypatch.setattr(tokens, "TIKTOKEN_DIR", tmp_path)
    assert not tokens.encoding_available()
    assert tokens.load_error
    assert tokens.openai_count("hi")[1] == tokens.FALLBACK_LABEL


def test_special_token_text_is_treated_as_plain_text(fresh):
    count, label = tokens.openai_count("<|endoftext|>")
    assert count > 1 and label == tokens.OPENAI_LABEL


def test_split_round_trips_tricky_text(fresh):
    text = "Héllo こんにちは 👋🏽 world <|endoftext|>"
    pieces = tokens.split_for_display(text)
    assert "".join(pieces) == text
    assert all(pieces)


def test_fallback_count_rule(monkeypatch):
    monkeypatch.setattr(tokens, "_encoding", False)
    # max(ceil(4 words / 0.75) = 6, ceil(18 chars / 4) = 5)
    assert tokens.openai_count("one two three four") == (6, tokens.FALLBACK_LABEL)
    assert "".join(tokens.split_for_display("a  b\nc")) == "a  b\nc"


def test_fallback_empty_text():
    assert tokens.fallback_count("   ") == 0


def test_claude_estimate_range():
    # words: ceil(4 / 0.555) = 8; chars: ceil(16 / 2.5) = 7
    assert tokens.claude_estimate("The sky is blue.") == (7, 8)
    assert tokens.claude_estimate("") == (0, 0)


@pytest.mark.parametrize(
    "text, reliable",
    [
        ("The meeting is moved to Thursday afternoon.", True),
        ("La reunión se cambió al jueves por la tarde.", True),
        ("Send it on Friday.", True),
        ("sean@example.com", False),
        ("two words", False),
        ("会議は木曜日の午後に変更されました。", False),
        ("बैठक गुरुवार दोपहर तक स्थगित कर दी गई है।", False),
        ("🎉👏🏽 नमस्ते", False),
    ],
)
def test_claude_estimate_is_only_reliable_for_english_like_text(text, reliable):
    # Anthropic's ratio is for English: it badly undercounts emails, emoji and non-Latin scripts.
    assert tokens.claude_estimate_reliable(text) is reliable


@pytest.mark.parametrize(
    "text", ["Great job! 🎉👏🏽🚀", "会議は木曜日の午後に変更されました。", "for i in range(10)", ""]
)
def test_split_with_counts_accounts_for_every_token(text):
    pieces = tokens.split_with_counts(text)
    assert sum(n for _, n in pieces) == tokens.openai_count(text)[0]
    assert "".join(piece for piece, _ in pieces) == text
    assert [piece for piece, _ in pieces] == tokens.split_for_display(text)


def test_split_with_counts_marks_emoji_made_of_two_tokens():
    assert dict(tokens.split_with_counts("Great job! 🎉👏🏽🚀"))["🚀"] == 2

import json
from types import SimpleNamespace as NS

import pytest

import live
import pricing


class FakeMessages:
    def __init__(self, replies=(), error=None, count=None, error_after=None):
        self.calls = []
        self.replies = list(replies)
        self.error = error
        self.count = count
        self.error_after = error_after  # fail on every call after this many have succeeded

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error or (self.error_after is not None and len(self.calls) > self.error_after):
            raise self.error or StatusError(429)
        blocks = [NS(type="thinking", thinking="hmm"), NS(type="text", text=self.replies.pop(0))]
        return NS(content=blocks, usage=NS(input_tokens=20, output_tokens=2))

    def count_tokens(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return NS(input_tokens=self.count)


def session(messages):
    return live.LiveSession(live.LiveStatus(True, "test"), client=NS(messages=messages))


class StatusError(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status_code = status


class APIConnectionError(Exception):
    pass


# --- detection ---------------------------------------------------------------


def test_offline_wins(tmp_path):
    assert live.detect({"ANTHROPIC_API_KEY": "k"}, offline=True, sdk_installed=True) == live.LiveStatus(
        False, "--offline"
    )


@pytest.mark.parametrize("name", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
def test_env_credentials(name):
    assert live.detect({name: "x"}, sdk_installed=True) == live.LiveStatus(True, name)


def test_profile_env(tmp_path):
    env = {"ANTHROPIC_PROFILE": "work", "ANTHROPIC_CONFIG_DIR": str(tmp_path)}
    assert live.detect(env, sdk_installed=True) == live.LiveStatus(True, "ant profile")


def test_profile_on_disk(tmp_path):
    (tmp_path / "active_config").write_text("default", encoding="utf-8")
    assert live.detect({"ANTHROPIC_CONFIG_DIR": str(tmp_path)}, sdk_installed=True).source == "ant profile"


def test_nothing_found(tmp_path):
    status = live.detect({"ANTHROPIC_CONFIG_DIR": str(tmp_path)}, sdk_installed=True)
    assert status == live.LiveStatus(False, "no API key found")


def test_key_but_no_sdk():
    status = live.detect({"ANTHROPIC_API_KEY": "k"}, sdk_installed=False)
    assert not status.available and "requirements-live.txt" in status.source


# --- calls -------------------------------------------------------------------


def test_temperature_run_uses_extra_body():
    fake = FakeMessages(replies=[" blue\n", "clear"])
    s = session(fake)
    assert s.temperature_run("The sky is", 1.0, n=2) == ["blue", "clear"]
    for call in fake.calls:
        assert "temperature" not in call
        assert call["extra_body"] == {"temperature": 1.0}
        assert call["model"] == pricing.LIVE_TEMPERATURE_MODEL
        assert call["max_tokens"] == 5
    assert s.spent == pytest.approx(2 * (20 * 1.00 + 2 * 5.00) / 1_000_000)


def test_temperature_run_keeps_the_answers_already_paid_for_when_a_call_fails():
    fake = FakeMessages(replies=["blue", "clear", "gray"], error_after=2)
    s = session(fake)
    assert s.temperature_run("x", 1.0, n=3) == ["blue", "clear"]
    assert "rate limited" in s.last_error
    assert s.spent == pytest.approx(2 * (20 * 1.00 + 2 * 5.00) / 1_000_000)


def test_temperature_run_clears_a_stale_error_on_success():
    s = session(FakeMessages(replies=["blue"]))
    s.last_error = "old"
    assert s.temperature_run("x", 0.0, n=1) == ["blue"] and s.last_error == ""


def test_temperature_run_refuses_models_that_reject_it():
    with pytest.raises(ValueError):
        session(FakeMessages()).temperature_run("x", 0.5, 1, model_id="claude-sonnet-5-5")


def test_grade_parses_structured_output():
    payload = {
        "items": [{"item": "a", "met": True, "why": "said a"}, {"item": "b", "met": False, "why": "no b"}],
        "feedback": "Mention b.",
    }
    fake = FakeMessages(replies=[json.dumps(payload)])
    s = session(fake)
    result = s.grade("Q?", ("a", "b"), "my answer")
    assert result.met_count == 1 and result.feedback == "Mention b."
    call = fake.calls[0]
    assert call["model"] == pricing.GRADER_MODEL
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "my answer" in call["messages"][0]["content"]
    assert s.spent > 0


def test_grade_wrong_item_count_is_a_failure():
    payload = {"items": [{"item": "a", "met": True, "why": "x"}], "feedback": "f"}
    s = session(FakeMessages(replies=[json.dumps(payload)]))
    assert s.grade("Q?", ("a", "b"), "ans") is None
    assert "expected 2" in s.last_error


def test_count_tokens():
    fake = FakeMessages(count=14)
    assert session(fake).count_tokens("hello", "claude-sonnet-5-5") == 14
    assert fake.calls[0]["messages"] == [{"role": "user", "content": "hello"}]


@pytest.mark.parametrize(
    "error, phrase",
    [
        (StatusError(401), "rejected"),
        (StatusError(404), "retired"),
        (StatusError(429), "rate limited"),
        (StatusError(529), "temporary problem"),
        (APIConnectionError("down"), "no network"),
    ],
)
def test_failures_fall_back_with_a_friendly_reason(error, phrase):
    s = session(FakeMessages(error=error))
    assert s.count_tokens("x", "claude-sonnet-5-5") is None
    assert phrase in s.last_error
    assert s.temperature_run("x", 0.0, 3) == []  # nothing came back, and last_error says why
    assert s.grade("Q?", ("a",), "ans") is None


def test_live_session_satisfies_the_engine_protocol() -> None:
    import engine

    session: engine.LiveAPI = live.LiveSession(live.LiveStatus(True, "test"))  # mypy checks this line
    assert session.spent == 0.0

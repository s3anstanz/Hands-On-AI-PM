import live
import live_check
import pricing

ON = live.LiveStatus(True, "test")
GOOD = live.GradeResult(tuple(live.GradeItem(item, True, "covered") for item in live_check.SAMPLE_CHECKLIST), "Nice.")


class FakeSession:
    """Stands in for live.LiveSession; never touches the network."""

    def __init__(self, counts, grade_result=GOOD, grade_error=""):
        self.counts = counts
        self.grade_result = grade_result
        self.grade_error = grade_error
        self.counted: list[str] = []
        self.graded = 0
        self.spent = 0.0
        self.last_error = ""

    def count_tokens(self, text, model_id):
        self.counted.append(model_id)
        if model_id not in self.counts:
            self.last_error = "that model isn't available (it may have been retired)"
            return None
        return self.counts[model_id]

    def grade(self, question, checklist, answer):
        self.graded += 1
        if self.grade_result is None:
            self.last_error = self.grade_error
        else:
            self.spent += 0.006
        return self.grade_result


ALL_MODELS = {pricing.GRADER_MODEL: 12, pricing.LIVE_TEMPERATURE_MODEL: 12}


def test_without_a_credential_nothing_is_called(capsys):
    assert live_check.run(live.LiveStatus(False, "no API key found"), None, confirm=lambda prompt: True) == 1
    assert "no API key found" in capsys.readouterr().out


def test_checks_every_live_model_for_free_then_grades_after_asking(capsys):
    session = FakeSession(ALL_MODELS)
    asked = []
    assert live_check.run(ON, session, confirm=lambda prompt: asked.append(prompt) or True) == 0
    assert session.counted == [pricing.GRADER_MODEL, pricing.LIVE_TEMPERATURE_MODEL]
    assert len(asked) == 1 and pricing.GRADE_COST_HINT in asked[0]
    assert session.graded == 1
    out = capsys.readouterr().out
    assert "All live checks passed" in out and "spent" in out


def test_declining_the_paid_call_skips_grading(capsys):
    session = FakeSession(ALL_MODELS)
    assert live_check.run(ON, session, confirm=lambda prompt: False) == 0
    assert session.graded == 0
    assert "skipped" in capsys.readouterr().out


def test_a_retired_model_fails_before_any_paid_call(capsys):
    session = FakeSession({pricing.GRADER_MODEL: 12})
    asked = []
    assert live_check.run(ON, session, confirm=lambda prompt: asked.append(prompt) or True) == 1
    assert asked == [] and session.graded == 0
    out = capsys.readouterr().out
    assert pricing.LIVE_TEMPERATURE_MODEL in out and "retired" in out


def test_a_grading_failure_fails_the_check(capsys):
    session = FakeSession(ALL_MODELS, grade_result=None, grade_error="rate limited; try again in a minute")
    assert live_check.run(ON, session, confirm=lambda prompt: True) == 1
    assert "rate limited" in capsys.readouterr().out


def test_main_without_a_credential_exits_cleanly(capsys):
    assert live_check.main() == 1  # conftest strips every Anthropic credential
    assert "Live mode is off" in capsys.readouterr().out


def test_confirm_accepts_only_yes(monkeypatch):
    replies = iter(["y", " YES ", "", "nope"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert [live_check._confirm("Go?") for _ in range(4)] == [True, True, False, False]

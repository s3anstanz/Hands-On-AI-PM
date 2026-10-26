from datetime import date

import freshness
import pricing

EVENTS = (("2026-10-15", "Haiku 4.5 may retire"), ("2027-01-01", "Gemini Flash prices double"))


def test_quiet_when_prices_are_recent_and_nothing_is_due():
    assert freshness.check(date(2026, 9, 1), "2026-08-20", EVENTS, max_age_days=60) == []


def test_stale_prices_are_flagged():
    items = freshness.check(date(2026, 12, 20), "2026-10-09", (), max_age_days=60)
    assert items == ["Prices were last checked 72 days ago (2026-10-09); re-verify them (limit: 60 days)."]


def test_event_in_the_next_two_weeks_is_flagged():
    items = freshness.check(date(2026, 10, 9), "2026-10-09", EVENTS, max_age_days=60)
    assert items == ["Coming up on 2026-10-15 (in 6 days): Haiku 4.5 may retire"]


def test_event_that_passed_since_the_last_check_is_flagged():
    items = freshness.check(date(2027, 1, 2), "2026-12-15", EVENTS, max_age_days=60)
    assert items == ["Happened on 2027-01-01, after prices were last checked (2026-12-15): Gemini Flash prices double"]


def test_event_already_rechecked_after_it_passed_is_quiet():
    assert freshness.check(date(2027, 1, 5), "2027-01-02", EVENTS, max_age_days=60) == []


def test_real_watch_list_is_well_formed():
    assert pricing.PRICES_MAX_AGE_DAYS > 0
    for when, what in pricing.WATCH_DATES:
        date.fromisoformat(when)
        assert what.strip()


def test_main_prints_a_report_and_signals_attention(capsys):
    assert freshness.main(today=date.fromisoformat(pricing.LAST_CHECKED)) in (0, 1)
    stale = date(2099, 1, 1)
    assert freshness.main(today=stale) == 1
    out = capsys.readouterr().out
    assert "Prices were last checked" in out and pricing.SOURCES["anthropic"] in out


def test_main_says_all_current_when_nothing_is_due(capsys, monkeypatch):
    monkeypatch.setattr(pricing, "WATCH_DATES", ())
    assert freshness.main(today=date.fromisoformat(pricing.LAST_CHECKED)) == 0
    assert "All current" in capsys.readouterr().out

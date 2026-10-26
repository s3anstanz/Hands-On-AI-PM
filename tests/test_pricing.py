from datetime import date

import pricing


def test_last_checked_is_a_date():
    date.fromisoformat(pricing.LAST_CHECKED)


def test_every_model_has_sane_prices():
    for m in pricing.MODELS.values():
        assert m.input > 0 and m.output >= m.input, m.key
        assert 0 < m.cache_read < m.input, m.key
        assert m.provider in {"anthropic", "openai", "google"}, m.key
        assert m.size in {"small", "medium", "large"}, m.key
        assert 1 <= m.quality <= 5 and 1 <= m.speed <= 5, m.key
        assert 0.0 <= m.batch_discount < 1.0, m.key
        assert m.max_output <= m.context_window, m.key
        aboves = [t.above for t in m.tiers]
        assert aboves == sorted(aboves), m.key
        for t in m.tiers:
            assert t.input > m.input and t.output > m.output, m.key
            assert t.above < m.context_window, m.key


def test_values_verified_2026_10_09():
    assert pricing.get("sonnet-5-5").cache_read == 0.10
    assert pricing.get("opus-5-5").cache_read == 0.20
    haiku = pricing.get("haiku-5-5")
    assert (haiku.input, haiku.output, haiku.cache_read) == (0.10, 0.50, 0.01)
    tier = haiku.tiers[0]
    assert (tier.above, tier.input, tier.output, tier.cache_read) == (100_000, 0.50, 2.50, 0.05)


def test_live_models_exist_and_fit_their_role():
    assert pricing.by_api_id(pricing.LIVE_TEMPERATURE_MODEL).accepts_temperature
    assert pricing.by_api_id(pricing.GRADER_MODEL).provider == "anthropic"


def test_no_5_5_model_accepts_temperature():
    for key in ("opus-5-5", "sonnet-5-5", "haiku-5-5"):
        assert not pricing.get(key).accepts_temperature


def test_lookup_errors():
    import pytest

    with pytest.raises(KeyError):
        pricing.get("nope")
    with pytest.raises(KeyError):
        pricing.by_api_id("nope")


def test_readme_has_no_hard_coded_prices():
    import re
    from pathlib import Path

    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"\$\d", readme), "prices live in pricing.py; describe them in words in the README"


def test_every_anthropic_model_has_a_minimum_cacheable_length():
    for m in pricing.MODELS.values():
        if m.provider == "anthropic":
            assert m.min_cache_tokens and m.min_cache_tokens > 0, m.key
        else:
            assert m.min_cache_tokens is None, m.key  # no figure verified on their pricing pages

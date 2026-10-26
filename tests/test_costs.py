import pytest

import pricing
from costs import (
    Usage,
    cache_break_even_uses,
    chat_cost,
    chat_input_per_turn,
    format_usd,
    monthly_cost,
    request_cost,
    routed_monthly_cost,
)

SONNET = pricing.get("sonnet-5-5")
HAIKU = pricing.get("haiku-5-5")
ASTRA = pricing.get("gpt-6-astra")


def test_simple_request():
    cost = request_cost(SONNET, Usage(input_tokens=2000, output_tokens=500))
    assert cost.input == pytest.approx(0.004)
    assert cost.output == pytest.approx(0.005)
    assert cost.total == pytest.approx(0.009)


def test_output_is_five_times_input_per_token():
    assert SONNET.output / SONNET.input == 5


def test_thinking_tokens_billed_as_output():
    cost = request_cost(SONNET, Usage(input_tokens=0, output_tokens=100, thinking_tokens=400))
    assert cost.output == pytest.approx(500 * 10 / 1_000_000)


def test_batch_halves_the_bill():
    full = request_cost(SONNET, Usage(2000, 500)).total
    assert request_cost(SONNET, Usage(2000, 500, batch=True)).total == pytest.approx(full / 2)


def test_batch_not_modeled_for_non_anthropic():
    with pytest.raises(ValueError):
        request_cost(ASTRA, Usage(1, 1, batch=True))


def test_cache_read_and_write_5m():
    cost = request_cost(
        SONNET, Usage(input_tokens=1000, output_tokens=0, cache_read_tokens=10_000, cache_write_tokens=2_000)
    )
    assert cost.cache_read == pytest.approx(10_000 * 0.10 / 1_000_000)
    assert cost.cache_write == pytest.approx(2_000 * 2.50 / 1_000_000)


def test_cache_write_1h():
    cost = request_cost(SONNET, Usage(0, 0, cache_write_tokens=1_000_000, cache_ttl="1h"))
    assert cost.cache_write == pytest.approx(4.00)


def test_cache_write_needs_a_price():
    with pytest.raises(ValueError):
        request_cost(ASTRA, Usage(0, 0, cache_write_tokens=10))


def test_bad_ttl_rejected():
    with pytest.raises(ValueError):
        request_cost(SONNET, Usage(0, 0, cache_ttl="2h"))


def test_haiku_tier_boundary():
    at_limit = request_cost(HAIKU, Usage(input_tokens=100_000, output_tokens=0))
    over = request_cost(HAIKU, Usage(input_tokens=100_001, output_tokens=0))
    assert at_limit.input == pytest.approx(100_000 * 0.10 / 1_000_000)
    assert over.input == pytest.approx(100_001 * 0.50 / 1_000_000)


def test_tier_counts_cached_tokens_too():
    cost = request_cost(HAIKU, Usage(input_tokens=50_000, output_tokens=1_000, cache_read_tokens=60_000))
    assert cost.input == pytest.approx(50_000 * 0.50 / 1_000_000)
    assert cost.output == pytest.approx(1_000 * 2.50 / 1_000_000)
    assert cost.cache_read == pytest.approx(60_000 * 0.05 / 1_000_000)


def test_monthly_cost():
    assert monthly_cost(SONNET, Usage(2000, 500), requests_per_day=1000) == pytest.approx(270.0)


def test_chat_history_resent_every_turn():
    assert chat_input_per_turn(turns=3, system_tokens=100, message_tokens=50) == [150, 250, 350]


def test_long_chat_costs_more_than_its_length():
    ratio = chat_cost(SONNET, 10, 500, 200) / chat_cost(SONNET, 1, 500, 200)
    assert ratio == pytest.approx(0.07 / 0.0034)
    assert ratio > 10


def test_cache_break_even():
    assert cache_break_even_uses(SONNET) == 2
    assert cache_break_even_uses(SONNET, "1h") == 3
    with pytest.raises(ValueError):
        cache_break_even_uses(ASTRA)


def test_routing_blends_costs():
    usage = Usage(2000, 500)
    blended = routed_monthly_cost(HAIKU, SONNET, usage, 1000, share_small=0.8)
    expected = 0.8 * monthly_cost(HAIKU, usage, 1000) + 0.2 * monthly_cost(SONNET, usage, 1000)
    assert blended == pytest.approx(expected)
    assert blended < monthly_cost(SONNET, usage, 1000)
    with pytest.raises(ValueError):
        routed_monthly_cost(HAIKU, SONNET, usage, 1000, share_small=1.5)


@pytest.mark.parametrize("amount, text", [(0, "$0"), (0.0042, "$0.0042"), (1234.5, "$1,234.50"), (0.5, "$0.50")])
def test_format_usd(amount, text):
    assert format_usd(amount) == text

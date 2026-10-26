"""Cost math. Every rate comes from pricing.py; nothing here hard-codes a price."""

import dataclasses
from dataclasses import dataclass

from pricing import Model

PER_MILLION = 1_000_000
DAYS_PER_MONTH = 30


@dataclass(frozen=True)
class Usage:
    input_tokens: int  # uncached input: system prompt, history, documents, question
    output_tokens: int  # visible answer
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cache_ttl: str = "5m"  # "5m" | "1h"
    thinking_tokens: int = 0  # billed at the output rate
    batch: bool = False

    @property
    def prompt_tokens(self) -> int:
        """What tiered pricing looks at: all input, cached or not."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class Cost:
    input: float
    output: float
    cache_read: float
    cache_write: float

    @property
    def total(self) -> float:
        return self.input + self.output + self.cache_read + self.cache_write


@dataclass(frozen=True)
class Rates:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float | None
    cache_write_1h: float | None


def rates_for(model: Model, prompt_tokens: int) -> Rates:
    """Base rates, replaced by the highest tier whose threshold the prompt exceeds."""
    rates = Rates(model.input, model.output, model.cache_read, model.cache_write_5m, model.cache_write_1h)
    for tier in model.tiers:
        if prompt_tokens > tier.above:
            rates = Rates(tier.input, tier.output, tier.cache_read, tier.cache_write_5m, tier.cache_write_1h)
    return rates


def supports_batch(model: Model) -> bool:
    return model.batch_discount > 0


def supports_cache_write(model: Model) -> bool:
    return model.cache_write_5m is not None


def request_cost(model: Model, usage: Usage) -> Cost:
    if usage.cache_ttl not in ("5m", "1h"):
        raise ValueError(f"cache_ttl must be '5m' or '1h', not {usage.cache_ttl!r}")
    if usage.batch and not supports_batch(model):
        raise ValueError(f"Batch pricing isn't modeled for {model.display_name}")
    rates = rates_for(model, usage.prompt_tokens)
    write_rate = rates.cache_write_5m if usage.cache_ttl == "5m" else rates.cache_write_1h
    if usage.cache_write_tokens and write_rate is None:
        raise ValueError(f"{model.display_name} has no cache-write price in pricing.py")
    scale = (1 - model.batch_discount) if usage.batch else 1.0

    def priced(tokens: int, rate: float) -> float:
        return tokens * rate / PER_MILLION * scale

    return Cost(
        input=priced(usage.input_tokens, rates.input),
        output=priced(usage.output_tokens + usage.thinking_tokens, rates.output),
        cache_read=priced(usage.cache_read_tokens, rates.cache_read),
        cache_write=priced(usage.cache_write_tokens, write_rate or 0.0),
    )


def apply_cache_minimum(model: Model, usage: Usage) -> Usage:
    """Bill cache reads as regular input when the cached part is under the model's minimum cacheable length."""
    if model.min_cache_tokens is None or usage.cache_read_tokens >= model.min_cache_tokens:
        return usage
    return dataclasses.replace(usage, input_tokens=usage.input_tokens + usage.cache_read_tokens, cache_read_tokens=0)


def monthly_cost(model: Model, usage: Usage, requests_per_day: int) -> float:
    return request_cost(model, usage).total * requests_per_day * DAYS_PER_MONTH


def chat_input_per_turn(turns: int, system_tokens: int, message_tokens: int) -> list[int]:
    """Input tokens sent on each turn when the app re-sends the whole history.

    Turn k sends the system prompt, k user messages and k-1 assistant replies,
    each `message_tokens` long.
    """
    return [system_tokens + (2 * k - 1) * message_tokens for k in range(1, turns + 1)]


def chat_cost(model: Model, turns: int, system_tokens: int, message_tokens: int) -> float:
    return sum(
        request_cost(model, Usage(input_tokens=sent, output_tokens=message_tokens)).total
        for sent in chat_input_per_turn(turns, system_tokens, message_tokens)
    )


def cache_break_even_uses(model: Model, ttl: str = "5m") -> int:
    """Fewest uses of the same prefix at which caching beats not caching.

    Without a cache, n uses cost n x input. With one, they cost one write plus
    (n - 1) reads.
    """
    write = model.cache_write_5m if ttl == "5m" else model.cache_write_1h
    if write is None:
        raise ValueError(f"{model.display_name} has no cache-write price in pricing.py")
    uses = 1
    while uses * model.input <= write + (uses - 1) * model.cache_read:
        uses += 1
    return uses


def routed_monthly_cost(small: Model, large: Model, usage: Usage, requests_per_day: int, share_small: float) -> float:
    if not 0 <= share_small <= 1:
        raise ValueError("share_small must be between 0 and 1")
    return share_small * monthly_cost(small, usage, requests_per_day) + (1 - share_small) * monthly_cost(
        large, usage, requests_per_day
    )


def format_usd(amount: float) -> str:
    if amount == 0:
        return "$0"
    if abs(amount) < 0.01:
        return f"${amount:.4f}"
    return f"${amount:,.2f}"

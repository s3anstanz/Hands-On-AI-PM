"""Every price and tokenizer ratio in the tutorial lives in this file.

Prices are USD per 1M tokens, standard tier, verified on the official
pricing pages on LAST_CHECKED. Re-verify before editing and bump the date.
"""

from dataclasses import dataclass

LAST_CHECKED = "2026-10-09"

# Minimum cacheable prompt lengths (min_cache_tokens), checked 2026-10-14:
# https://platform.claude.com/docs/en/build-with-claude/prompt-caching#cache-limitations
SOURCES = {
    "anthropic": "https://platform.claude.com/docs/en/about-claude/pricing",
    "anthropic_fast_mode": "https://platform.claude.com/docs/en/build-with-claude/fast-mode",
    "openai": "https://developers.openai.com/api/docs/pricing",
    "google": "https://ai.google.dev/gemini-api/docs/pricing",
}

# freshness.py (run monthly in CI) opens an issue when prices are older than this,
# or when a date below is near or has passed since LAST_CHECKED.
PRICES_MAX_AGE_DAYS = 60
WATCH_DATES = (
    (
        "2026-12-13",
        "Earliest possible retirement of Claude Haiku 4.5 (LIVE_TEMPERATURE_MODEL): still active, not deprecated, "
        "on 2026-10-14, and retirements get 60+ days' notice. Re-check Anthropic's model deprecations page and move "
        "this date forward; the live temperature demo needs a model that accepts temperature.",
    ),
    ("2027-01-01", "Gemini 3.8 Flash prices double (to $1.50 / $7.50 per 1M tokens). Update its entry below."),
)

# Anthropic's documented ratio for the current Claude tokenizer (Claude 4.7+):
# 1M tokens ≈ 555K words ≈ 2.5M characters (models overview footnote).
CLAUDE_WORDS_PER_TOKEN = 0.555
CLAUDE_CHARS_PER_TOKEN = 2.5

# OpenAI's long-standing rule of thumb (a token ≈ ¾ of an English word). Its newest public
# tokenizer measures closer to 0.9 on plain English; Chapter 2 shows both.
OPENAI_RULE_OF_THUMB_WORDS_PER_TOKEN = 0.75

# Opus 5.5 fast mode (research preview): 2x price for up to 2.5x output tokens/sec.
OPUS_FAST_MODE_INPUT = 8.00
OPUS_FAST_MODE_OUTPUT = 40.00
OPUS_FAST_MODE_SPEEDUP = 2.5

# Illustrative, not from a pricing page: the loaded cost of one hour of expert review
# (salary plus overhead). Used only by Chapter 5's full-cost example, labeled as illustrative there.
REVIEW_HOURLY_USD = 60.00

# The 5.5 models reject custom temperature, so the live demo uses a legacy model.
LIVE_TEMPERATURE_MODEL = "claude-haiku-4-5"
GRADER_MODEL = "claude-sonnet-5-5"
GRADE_COST_HINT = "$0.01"  # shown before each Claude grading call (~1.5K in + 300 out on Sonnet 5.5)


@dataclass(frozen=True)
class Tier:
    """Rates that replace the base rates when a request's prompt exceeds `above` tokens."""

    above: int
    input: float
    output: float
    cache_read: float
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None


@dataclass(frozen=True)
class Model:
    key: str
    provider: str  # "anthropic" | "openai" | "google"
    display_name: str
    api_id: str
    input: float
    output: float
    cache_read: float
    cache_write_5m: float | None
    cache_write_1h: float | None
    context_window: int
    max_output: int
    batch_discount: float  # 0.5 = 50% off; 0.0 = batch pricing not modeled
    accepts_temperature: bool  # only meaningful for Anthropic models we call live
    size: str  # "small" | "medium" | "large"
    quality: int  # illustrative 1-5, labeled as such on screen
    speed: int  # illustrative 1-5, labeled as such on screen
    tiers: tuple[Tier, ...] = ()
    note: str = ""
    # Shortest prompt prefix that can be cached; below it the cache discount doesn't apply.
    # None = not modeled (OpenAI's and Google's pricing pages state no figure).
    min_cache_tokens: int | None = None


MODELS: dict[str, Model] = {
    m.key: m
    for m in (
        Model(
            key="opus-5-5",
            provider="anthropic",
            display_name="Claude Opus 5.5",
            api_id="claude-opus-5-5",
            input=4.00,
            output=20.00,
            cache_read=0.20,
            cache_write_5m=5.00,
            cache_write_1h=8.00,
            context_window=1_000_000,
            max_output=128_000,
            batch_discount=0.5,
            accepts_temperature=False,
            size="large",
            quality=5,
            speed=2,
            min_cache_tokens=512,
        ),
        Model(
            key="sonnet-5-5",
            provider="anthropic",
            display_name="Claude Sonnet 5.5",
            api_id="claude-sonnet-5-5",
            input=2.00,
            output=10.00,
            cache_read=0.10,
            cache_write_5m=2.50,
            cache_write_1h=4.00,
            context_window=1_000_000,
            max_output=128_000,
            batch_discount=0.5,
            accepts_temperature=False,
            size="medium",
            quality=4,
            speed=3,
            min_cache_tokens=512,
        ),
        Model(
            key="haiku-5-5",
            provider="anthropic",
            display_name="Claude Haiku 5.5",
            api_id="claude-haiku-5-5",
            input=0.10,
            output=0.50,
            cache_read=0.01,
            cache_write_5m=0.125,
            cache_write_1h=0.20,
            context_window=1_000_000,
            max_output=128_000,
            batch_discount=0.5,
            accepts_temperature=False,
            size="small",
            quality=3,
            speed=5,
            tiers=(
                Tier(
                    above=100_000, input=0.50, output=2.50, cache_read=0.05, cache_write_5m=0.625, cache_write_1h=1.00
                ),
            ),
            note="Prompts over 100K tokens cost 5× as much per token, for the whole request.",
            min_cache_tokens=512,
        ),
        Model(
            key="haiku-4-5",
            provider="anthropic",
            display_name="Claude Haiku 4.5",
            api_id="claude-haiku-4-5",
            input=1.00,
            output=5.00,
            cache_read=0.10,
            cache_write_5m=1.25,
            cache_write_1h=2.00,
            context_window=200_000,
            max_output=64_000,
            batch_discount=0.5,
            accepts_temperature=True,
            size="small",
            quality=2,
            speed=5,
            note="Legacy model, used only for the live temperature demo.",
            min_cache_tokens=4096,
        ),
        Model(
            key="gpt-6-astra",
            provider="openai",
            display_name="GPT-6 Astra",
            api_id="gpt-6-astra",
            input=10.00,
            output=50.00,
            cache_read=1.00,
            cache_write_5m=None,
            cache_write_1h=None,
            context_window=1_050_000,
            max_output=128_000,
            batch_discount=0.0,
            accepts_temperature=False,
            size="large",
            quality=5,
            speed=2,
            tiers=(Tier(above=272_000, input=20.00, output=75.00, cache_read=2.00),),
        ),
        Model(
            key="gpt-6-luna",
            provider="openai",
            display_name="GPT-6 Luna",
            api_id="gpt-6-luna",
            input=0.10,
            output=0.50,
            cache_read=0.01,
            cache_write_5m=None,
            cache_write_1h=None,
            context_window=1_050_000,
            max_output=128_000,
            batch_discount=0.0,
            accepts_temperature=False,
            size="small",
            quality=3,
            speed=5,
            tiers=(Tier(above=272_000, input=0.20, output=0.75, cache_read=0.02),),
        ),
        Model(
            key="gemini-3-1-pro",
            provider="google",
            display_name="Gemini 3.1 Pro (Preview)",
            api_id="gemini-3.1-pro-preview",
            input=2.00,
            output=12.00,
            cache_read=0.20,
            cache_write_5m=None,
            cache_write_1h=None,
            context_window=1_048_576,
            max_output=65_536,
            batch_discount=0.0,
            accepts_temperature=False,
            size="large",
            quality=5,
            speed=3,
            tiers=(Tier(above=200_000, input=4.00, output=18.00, cache_read=0.40),),
            note="Preview model. Cache storage is billed separately ($4.50 per 1M tokens per hour).",
        ),
        Model(
            key="gemini-3-8-flash",
            provider="google",
            display_name="Gemini 3.8 Flash",
            api_id="gemini-3.8-flash",
            input=0.75,
            output=3.75,
            cache_read=0.075,
            cache_write_5m=None,
            cache_write_1h=None,
            context_window=1_048_576,
            max_output=65_536,
            batch_discount=0.0,
            accepts_temperature=False,
            size="medium",
            quality=4,
            speed=4,
            # Cache storage is billed separately: $0.50 per 1M tokens per hour (spec §8.1).
            note="Prices double on 2027-01-01 (to $1.50 / $7.50).",
        ),
    )
}


def get(key: str) -> Model:
    return MODELS[key]


def by_api_id(api_id: str) -> Model:
    for model in MODELS.values():
        if model.api_id == api_id:
            return model
    raise KeyError(api_id)

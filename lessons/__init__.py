"""Chapter registry, in menu order. Part 2 adds chapters as they're built."""

from engine import Chapter
from lessons import (
    ch1_generation,
    ch2_tokens,
    ch3_temperature,
    ch4_hallucination,
    ch5_model_choice,
    ch6_cost,
    ch7_context,
    ch8_design_feature,
)

CHAPTERS: dict[str, Chapter] = {
    chapter.id: chapter
    for chapter in (
        ch1_generation.CHAPTER,
        ch2_tokens.CHAPTER,
        ch3_temperature.CHAPTER,
        ch4_hallucination.CHAPTER,
        ch5_model_choice.CHAPTER,
        ch6_cost.CHAPTER,
        ch7_context.CHAPTER,
        ch8_design_feature.CHAPTER,
    )
}

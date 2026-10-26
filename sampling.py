"""Turn next-token weights into probabilities and pick from them.

This is the same math a real model runs at its last step: softmax with
temperature, optional top-k / top-p filtering, then a weighted random pick.
Filtered-out words stay in the dict with probability 0.0 so the UI can show
them grayed out.
"""

import math
import random
from collections.abc import Mapping


def normalize(weights: Mapping[str, float]) -> dict[str, float]:
    if not weights:
        raise ValueError("need at least one candidate")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights can't be negative")
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return {word: w / total for word, w in weights.items()}


def top_word(probs: dict[str, float]) -> str:
    return max(probs, key=lambda word: probs[word])


def apply_temperature(probs: dict[str, float], temperature: float) -> dict[str, float]:
    if temperature < 0:
        raise ValueError("temperature must be 0 or more")
    probs = normalize(probs)
    if temperature == 0:
        top = top_word(probs)
        return {word: (1.0 if word == top else 0.0) for word in probs}
    logits = {word: math.log(p) / temperature for word, p in probs.items() if p > 0}
    if not all(math.isfinite(logit) for logit in logits.values()):
        return apply_temperature(probs, 0)  # too close to 0 to compute (log(p) / t overflows): same as 0
    peak = max(logits.values())
    return normalize({word: (math.exp(logits[word] - peak) if word in logits else 0.0) for word in probs})


def top_k(probs: dict[str, float], k: int) -> dict[str, float]:
    if k < 1:
        raise ValueError("k must be at least 1")
    probs = normalize(probs)
    keep = set(sorted(probs, key=lambda word: probs[word], reverse=True)[:k])
    return normalize({word: (p if word in keep else 0.0) for word, p in probs.items()})


def top_p(probs: dict[str, float], p: float) -> dict[str, float]:
    if not 0 < p <= 1:
        raise ValueError("p must be more than 0 and at most 1")
    probs = normalize(probs)
    keep: set[str] = set()
    running = 0.0
    for word in sorted(probs, key=lambda word: probs[word], reverse=True):
        keep.add(word)
        running += probs[word]
        if running >= p - 1e-9:
            break
    return normalize({word: (q if word in keep else 0.0) for word, q in probs.items()})


def sample(probs: dict[str, float], rng: random.Random) -> str:
    words = [word for word, p in probs.items() if p > 0]
    return rng.choices(words, weights=[probs[word] for word in words])[0]


def sample_many(probs: dict[str, float], n: int, rng: random.Random) -> dict[str, int]:
    counts = {word: 0 for word in probs}
    for _ in range(n):
        counts[sample(probs, rng)] += 1
    return counts


def nudge(weights: dict[str, float], rng: random.Random, sigma: float = 0.15) -> dict[str, float]:
    """Wiggle each weight a little so the odds differ between runs."""
    return normalize({word: w * math.exp(rng.gauss(0.0, sigma)) for word, w in weights.items()})


def entropy(probs: dict[str, float]) -> float:
    return -sum(p * math.log(p) for p in probs.values() if p > 0)

import random

import pytest

import sampling

SKY = {"blue": 62, "clear": 18, "dark": 12, "gray": 6, "ugly": 2}


def test_normalize_sums_to_one():
    probs = sampling.normalize(SKY)
    assert sum(probs.values()) == pytest.approx(1.0)
    assert probs["blue"] == pytest.approx(0.62)


@pytest.mark.parametrize("bad", [{}, {"a": -1, "b": 2}, {"a": 0, "b": 0}])
def test_normalize_rejects_bad_weights(bad):
    with pytest.raises(ValueError):
        sampling.normalize(bad)


def test_temperature_one_is_unchanged():
    assert sampling.apply_temperature(SKY, 1.0) == pytest.approx(sampling.normalize(SKY))


def test_temperature_zero_always_picks_top():
    probs = sampling.apply_temperature(SKY, 0)
    assert probs["blue"] == 1.0
    assert sum(probs.values()) == 1.0


def test_low_temperature_sharpens_high_flattens():
    low = sampling.apply_temperature(SKY, 0.5)
    high = sampling.apply_temperature(SKY, 1.5)
    assert low["blue"] > 0.62 > high["blue"]
    assert sampling.entropy(low) < sampling.entropy(sampling.normalize(SKY)) < sampling.entropy(high)


def test_tiny_temperature_does_not_crash():
    assert sampling.apply_temperature(SKY, 0.01)["blue"] == pytest.approx(1.0)


def test_negative_temperature_rejected():
    with pytest.raises(ValueError):
        sampling.apply_temperature(SKY, -0.1)


def test_temperature_keeps_zero_entries_at_zero():
    trimmed = sampling.top_k(SKY, 2)
    assert sampling.apply_temperature(trimmed, 1.5)["ugly"] == 0.0


def test_top_k_keeps_the_k_best():
    probs = sampling.top_k(SKY, 2)
    assert {w for w, p in probs.items() if p > 0} == {"blue", "clear"}
    assert probs["blue"] == pytest.approx(62 / 80)
    assert set(probs) == set(SKY)


def test_top_p_keeps_smallest_set_reaching_p():
    assert {w for w, p in sampling.top_p(SKY, 0.9).items() if p > 0} == {"blue", "clear", "dark"}
    assert {w for w, p in sampling.top_p(SKY, 0.5).items() if p > 0} == {"blue"}
    assert all(p > 0 for p in sampling.top_p(SKY, 1.0).values())


@pytest.mark.parametrize("bad", [0, 1.5])
def test_top_p_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        sampling.top_p(SKY, bad)


def test_top_k_rejects_zero():
    with pytest.raises(ValueError):
        sampling.top_k(SKY, 0)


def test_same_seed_same_samples():
    probs = sampling.normalize(SKY)
    first = [sampling.sample(probs, rng) for rng in [random.Random(7)] for _ in range(50)]
    rng = random.Random(7)
    second = [sampling.sample(probs, rng) for _ in range(50)]
    assert first == second


def test_sample_never_picks_zero_probability():
    probs = sampling.top_k(SKY, 1)
    rng = random.Random(1)
    assert {sampling.sample(probs, rng) for _ in range(100)} == {"blue"}


def test_sample_many_counts():
    counts = sampling.sample_many(sampling.apply_temperature(SKY, 0), 20, random.Random(3))
    assert counts == {"blue": 20, "clear": 0, "dark": 0, "gray": 0, "ugly": 0}


def test_nudge_moves_odds_but_keeps_shape():
    base = sampling.normalize(SKY)
    nudged = sampling.nudge(SKY, random.Random(5))
    assert set(nudged) == set(SKY)
    assert sum(nudged.values()) == pytest.approx(1.0)
    assert nudged != pytest.approx(base)
    assert sampling.nudge(SKY, random.Random(5)) == nudged


def test_nudge_keeps_a_clear_leader_on_top():
    for seed in range(200):
        assert sampling.top_word(sampling.nudge(SKY, random.Random(seed))) == "blue"


@pytest.mark.parametrize("t", [1e-310, 5e-324])
def test_a_temperature_too_small_to_compute_acts_as_zero(t):
    # log(p) / t overflows to -inf for subnormal t; the pick must still be the top word, not NaN.
    probs = sampling.normalize({"blue": 62, "clear": 18, "dark": 20})
    assert sampling.apply_temperature(probs, t) == sampling.apply_temperature(probs, 0)

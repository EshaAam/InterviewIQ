"""GeminiKeyPool — round-robin + per-key cooldown, tested with a fake clock."""

from __future__ import annotations

import pytest

from app.providers.gemini import GeminiKeyPool


def _pool(keys, *, cooldown=60.0, clock=None):
    return GeminiKeyPool(keys, cooldown=cooldown, clock=clock or (lambda: 0.0))


def test_requires_at_least_one_key() -> None:
    with pytest.raises(ValueError):
        GeminiKeyPool([], cooldown=1.0)


def test_round_robins_across_keys() -> None:
    pool = _pool(["a", "b", "c"])
    picks = [pool.acquire()[1] for _ in range(6)]
    assert picks == ["a", "b", "c", "a", "b", "c"]


def test_penalized_key_is_skipped_until_cooldown_expires() -> None:
    now = {"t": 0.0}
    pool = _pool(["a", "b"], cooldown=10.0, clock=lambda: now["t"])

    idx, key = pool.acquire()  # -> a (index 0)
    assert key == "a"
    pool.penalize(idx)  # bench "a" until t=10

    # Next acquisitions skip "a" and keep returning "b".
    assert pool.acquire()[1] == "b"
    assert pool.acquire()[1] == "b"

    # After cooldown, "a" is back in rotation.
    now["t"] = 10.0
    assert pool.acquire()[1] == "a"


def test_returns_none_when_all_keys_benched() -> None:
    pool = _pool(["a", "b"], cooldown=10.0)
    i0, _ = pool.acquire()
    pool.penalize(i0)
    i1, _ = pool.acquire()
    pool.penalize(i1)
    assert pool.acquire() is None  # nothing available -> caller raises transient


def test_config_merges_and_dedupes_keys() -> None:
    from app.core.config import Settings

    s = Settings(GEMINI_API_KEY="k1", GEMINI_API_KEYS="k2, k3 ,k1,")
    assert s.gemini_keys == ["k1", "k2", "k3"]

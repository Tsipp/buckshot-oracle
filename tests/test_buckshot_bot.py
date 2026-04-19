"""Smoke tests for the offline Buckshot bot.

These tests only aim to ensure the game engine and the bot's decision
logic terminate correctly on a wide range of seeds. They are intentionally
lightweight so they run in well under a second.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# Make the repo root importable without requiring a package install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buckshot_bot  # noqa: E402


def _play_silent_bot_vs_bot(seed: int) -> int:
    rng = random.Random(seed)
    state = buckshot_bot.start_round(
        "A", "B", buckshot_bot.DEFAULT_MAX_HP, rng, True, True
    )
    return buckshot_bot.play_round(state, human_idx=None, log=lambda _m: None)


def test_bot_vs_bot_terminates_across_seeds():
    for seed in range(200):
        winner = _play_silent_bot_vs_bot(seed)
        assert winner in (0, 1), f"seed={seed} returned {winner}"


def test_simulate_returns_balanced_counts():
    rng = random.Random(1234)
    stats = buckshot_bot.simulate(200, rng)
    total = sum(stats.values())
    assert total == 200
    # Neither bot should be wiped out — a symmetric match-up should be
    # somewhere near 50/50. Allow a generous margin to keep the test
    # stable.
    for _, wins in stats.items():
        assert 40 <= wins <= 160


def test_new_loadout_always_has_both_kinds():
    rng = random.Random(0)
    for _ in range(500):
        shells = buckshot_bot.new_loadout(rng)
        assert 2 <= len(shells) <= 8
        assert any(shells)      # at least one live
        assert not all(shells)  # at least one blank


def test_player_hp_and_items():
    p = buckshot_bot.Player("x", hp=2, max_hp=4)
    assert p.alive()
    p.hp = 0
    assert not p.alive()

    p2 = buckshot_bot.Player("y", hp=2, max_hp=4)
    assert p2.add_item("cigarettes")
    assert p2.remove_item("cigarettes")
    assert not p2.remove_item("cigarettes")

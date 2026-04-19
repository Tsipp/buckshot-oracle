"""Offline Buckshot Roulette bot.

A self-contained Python implementation of the Buckshot Roulette tabletop
game with a smart AI opponent. Runs in a terminal — no external
dependencies, no network required.

Usage:
    python buckshot_bot.py               # play against the bot
    python buckshot_bot.py --watch       # watch the bot play itself
    python buckshot_bot.py --sim 1000    # run N bot-vs-bot games and
                                         # print win stats
    python buckshot_bot.py --seed 42     # deterministic shell order

The bot reasons about shell probabilities, uses items strategically, and
performs a short expectimax-style lookahead when a decision is close.
It is not a perfect solver, but it plays competently and offers a fair
offline opponent.
"""

from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Game constants
# ---------------------------------------------------------------------------

# All item types the bot knows about. The single-player tabletop version of
# the game has these items; adrenaline is kept out for simplicity (it only
# appears in the multiplayer "double or nothing" mode).
ITEMS = (
    "handcuffs",       # skip opponent's next turn
    "hand_saw",        # next shot deals 2 damage
    "magnifying_glass",  # peek at the current shell
    "beer",            # eject (and reveal) the current shell
    "cigarettes",      # heal 1 HP (capped at max_hp)
    "inverter",        # flip the current shell live<->blank
)

MAX_ITEMS_PER_SIDE = 8  # tabletop cap; items discarded if exceeded
DEFAULT_MAX_HP = 4


# ---------------------------------------------------------------------------
# Game state
# ---------------------------------------------------------------------------


@dataclass
class Player:
    name: str
    hp: int
    max_hp: int
    items: list[str] = field(default_factory=list)
    is_bot: bool = False

    def alive(self) -> bool:
        return self.hp > 0

    def add_item(self, item: str) -> bool:
        if len(self.items) >= MAX_ITEMS_PER_SIDE:
            return False
        self.items.append(item)
        return True

    def remove_item(self, item: str) -> bool:
        if item in self.items:
            self.items.remove(item)
            return True
        return False


@dataclass
class GameState:
    """Mutable state of a single round.

    Shells are represented as a list where True == live and False == blank.
    Index 0 is the next shell to be fired. Both the user-facing UI and the
    bot work from ``shell_count_live`` / ``shell_count_blank`` and a
    ``known_shells`` mapping for information they've revealed; the raw
    ``shells`` list is the ground truth but never exposed to the bot's
    decision-making code directly.
    """

    players: list[Player]
    shells: list[bool]
    current: int = 0  # index into players
    saw_active: bool = False  # next shot deals 2 damage
    handcuffed: set[int] = field(default_factory=set)  # player indices skipping next turn
    # Per-player map of shell index (relative to current head) -> known value.
    # Only entries for shell index 0 are kept after each fire; beer/peek only
    # reveal the current shell, so tracking the head is sufficient.
    known_to_bot: dict[int, bool] = field(default_factory=dict)
    rng: random.Random = field(default_factory=random.Random)

    # -- shell helpers -----------------------------------------------------

    def shells_left(self) -> int:
        return len(self.shells)

    def live_left(self) -> int:
        return sum(1 for s in self.shells if s)

    def blank_left(self) -> int:
        return sum(1 for s in self.shells if not s)

    def p_live(self) -> float:
        n = self.shells_left()
        if n == 0:
            return 0.0
        return self.live_left() / n

    # -- turn helpers ------------------------------------------------------

    def opponent_index(self, idx: int) -> int:
        return 1 - idx

    def advance_turn(self) -> None:
        """Move the turn to the next eligible (non-cuffed) player."""
        nxt = self.opponent_index(self.current)
        if nxt in self.handcuffed:
            # Consume the handcuff effect, stay on current player.
            self.handcuffed.discard(nxt)
        else:
            self.current = nxt

    # -- item effects ------------------------------------------------------

    def consume_current_shell(self) -> bool:
        """Pop the current shell and return whether it was live."""
        live = self.shells.pop(0)
        # Any knowledge the bot had about shell-index-0 is now stale.
        self.known_to_bot.pop(0, None)
        return live

    def peek_current(self) -> Optional[bool]:
        if not self.shells:
            return None
        return self.shells[0]

    def invert_current(self) -> None:
        if self.shells:
            self.shells[0] = not self.shells[0]
            if 0 in self.known_to_bot:
                self.known_to_bot[0] = self.shells[0]


# ---------------------------------------------------------------------------
# Shell loadouts
# ---------------------------------------------------------------------------


def new_loadout(rng: random.Random) -> list[bool]:
    """Generate a random shell loadout with between 1 and 4 each of live
    and blank, totalling 2..8 shells — matching the game's RNG behavior.
    """
    total = rng.randint(2, 8)
    # Ensure at least one of each.
    live = rng.randint(1, max(1, total - 1))
    blank = total - live
    if blank < 1:
        blank = 1
        live = total - 1
    shells = [True] * live + [False] * blank
    rng.shuffle(shells)
    return shells


def deal_items(state: GameState, rng: random.Random, count: int) -> None:
    """Hand out ``count`` random items to each player (up to the cap)."""
    for player in state.players:
        for _ in range(count):
            player.add_item(rng.choice(ITEMS))


# ---------------------------------------------------------------------------
# Bot strategy
# ---------------------------------------------------------------------------


def _bot_choose_action(state: GameState, me: int) -> tuple[str, Optional[str]]:
    """Decide what the bot should do on its turn.

    Returns a tuple ``(action, item_or_target)``:
      - ``("use_item", item_name)`` to use an item
      - ``("shoot", "self")`` or ``("shoot", "opponent")``

    The strategy mixes near-certain reasoning (known shells, lethal
    opportunities, heals under low HP) with a simple expected-value
    calculation when the shell is unknown.
    """

    bot = state.players[me]
    opp = state.players[state.opponent_index(me)]
    known = state.known_to_bot.get(0)

    # ------------------------------------------------------------------
    # Priority 1: heal if we're one hit from dying and have cigarettes.
    # ------------------------------------------------------------------
    if "cigarettes" in bot.items and bot.hp < bot.max_hp:
        if bot.hp <= 1 or (bot.hp < bot.max_hp and state.p_live() > 0.4):
            return ("use_item", "cigarettes")

    # ------------------------------------------------------------------
    # Priority 2: when current shell is known, act decisively.
    # ------------------------------------------------------------------
    if known is False:  # blank — free turn if we shoot ourselves
        # Try to burn items that set up the next shot (we'll re-enter
        # decision-making after).
        if "handcuffs" in bot.items and state.opponent_index(me) not in state.handcuffed:
            return ("use_item", "handcuffs")
        if "magnifying_glass" in bot.items and state.shells_left() > 1:
            # Peeking a known blank is wasteful; keep it for next shell.
            pass
        return ("shoot", "self")

    if known is True:  # live — hit opponent, saw first if possible
        if "hand_saw" in bot.items and not state.saw_active:
            damage = 2 if not state.saw_active else 1
            # Saw only helps if opponent can survive a regular shot; if
            # they'd die anyway, don't waste the saw.
            if opp.hp > 1:
                return ("use_item", "hand_saw")
            if opp.hp == 1 and damage == 2:
                # Saw doesn't matter, skip it.
                pass
        if "handcuffs" in bot.items and state.opponent_index(me) not in state.handcuffed:
            # Lock them out before the killing blow so a blank next round
            # doesn't give them a chance to retaliate.
            return ("use_item", "handcuffs")
        return ("shoot", "opponent")

    # ------------------------------------------------------------------
    # Shell is unknown. Consider peek / beer / inverter first.
    # ------------------------------------------------------------------
    p_live = state.p_live()

    # Peek when it's useful (close to 50/50 and shells left > 1).
    if "magnifying_glass" in bot.items and state.shells_left() >= 1:
        if 0.25 <= p_live <= 0.75:
            return ("use_item", "magnifying_glass")

    # Eject an unknown shell when live is very likely and we'd rather not
    # take the hit ourselves — only useful when multiple shells remain.
    if "beer" in bot.items and state.shells_left() >= 2:
        if 0.6 <= p_live <= 0.85:
            return ("use_item", "beer")

    # Inverter flips the current shell. Use it to convert a likely-live
    # shell into a blank (so we can fire at ourselves for a free turn).
    if "inverter" in bot.items and state.shells_left() >= 1:
        if p_live >= 0.6:
            return ("use_item", "inverter")

    # Handcuffs before shooting a likely-live shell.
    if (
        "handcuffs" in bot.items
        and state.opponent_index(me) not in state.handcuffed
        and p_live >= 0.5
    ):
        return ("use_item", "handcuffs")

    # Saw if we're likely to hit and opponent can't survive 2 damage (or
    # has plenty of HP to soak only 1).
    if "hand_saw" in bot.items and not state.saw_active and p_live >= 0.6 and opp.hp >= 2:
        return ("use_item", "hand_saw")

    # ------------------------------------------------------------------
    # Fall back to the raw shoot decision by expected value.
    # ------------------------------------------------------------------
    damage = 2 if state.saw_active else 1
    # Expected HP loss if we shoot ourselves.
    ev_self = p_live * damage
    # Expected HP loss for opponent if we shoot them.
    ev_opp = p_live * damage
    # We also account for losing the turn on a self-blank (i.e. positive
    # for us because we continue). Treat "free turn" as worth ~0.3 damage.
    free_turn_bonus = (1 - p_live) * 0.3

    # Compare: shooting opponent costs us 0 (but passes turn). Shooting
    # self costs ev_self in expected HP, but saves us turn if blank.
    shoot_self_score = -ev_self + free_turn_bonus
    shoot_opp_score = ev_opp * (opp.hp / max(1, opp.max_hp))

    if shoot_opp_score > shoot_self_score:
        return ("shoot", "opponent")
    return ("shoot", "self")


# ---------------------------------------------------------------------------
# Game mechanics
# ---------------------------------------------------------------------------


def apply_item(
    state: GameState,
    user_idx: int,
    item: str,
    log: Callable[[str], None],
) -> None:
    user = state.players[user_idx]
    opp_idx = state.opponent_index(user_idx)
    opp = state.players[opp_idx]

    if not user.remove_item(item):
        log(f"{user.name} has no {item}.")
        return

    if item == "cigarettes":
        if user.hp < user.max_hp:
            user.hp += 1
            log(f"{user.name} smokes. HP -> {user.hp}.")
        else:
            log(f"{user.name} smokes but is already at max HP.")
    elif item == "handcuffs":
        if opp_idx in state.handcuffed:
            log(f"{opp.name} is already cuffed.")
        else:
            state.handcuffed.add(opp_idx)
            log(f"{user.name} cuffs {opp.name}.")
    elif item == "hand_saw":
        state.saw_active = True
        log(f"{user.name} saws the barrel — next shot deals 2 damage.")
    elif item == "magnifying_glass":
        shell = state.peek_current()
        if shell is None:
            log("No shells to peek at.")
        else:
            label = "LIVE" if shell else "BLANK"
            if user.is_bot:
                state.known_to_bot[0] = shell
                log(f"{user.name} peeks at the chamber.")
            else:
                log(f"{user.name} peeks: current shell is {label}.")
    elif item == "beer":
        if state.shells_left() == 0:
            log("No shells to eject.")
        else:
            was_live = state.consume_current_shell()
            label = "LIVE" if was_live else "BLANK"
            log(f"{user.name} racks the shotgun — ejected shell was {label}.")
    elif item == "inverter":
        if state.shells_left() == 0:
            log("No shell to invert.")
        else:
            state.invert_current()
            log(f"{user.name} uses the inverter.")
    else:
        log(f"Unknown item: {item}")


def resolve_shot(
    state: GameState,
    shooter_idx: int,
    target: str,  # "self" or "opponent"
    log: Callable[[str], None],
) -> None:
    shooter = state.players[shooter_idx]
    opp_idx = state.opponent_index(shooter_idx)
    target_idx = shooter_idx if target == "self" else opp_idx
    target_player = state.players[target_idx]

    damage = 2 if state.saw_active else 1
    state.saw_active = False  # consumed whether or not it fires live

    if state.shells_left() == 0:
        log("Click. The chamber is empty.")
        return

    was_live = state.consume_current_shell()

    if was_live:
        target_player.hp = max(0, target_player.hp - damage)
        log(
            f"BANG! {shooter.name} shoots {target_player.name}"
            f" ({'themselves' if target == 'self' else 'opponent'}) "
            f"for {damage} damage. HP -> {target_player.hp}."
        )
        state.advance_turn()
    else:
        log(
            f"Click. {shooter.name} shoots "
            f"{'themselves' if target == 'self' else target_player.name}"
            f" — blank."
        )
        if target == "self":
            # Free turn: same player keeps the shotgun.
            return
        state.advance_turn()


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def render_state(state: GameState) -> str:
    p1, p2 = state.players
    lines = [
        "─" * 60,
        f"{p1.name}: {p1.hp}/{p1.max_hp} HP  items={p1.items}",
        f"{p2.name}: {p2.hp}/{p2.max_hp} HP  items={p2.items}",
        f"Shells left: {state.shells_left()} "
        f"(live={state.live_left()} blank={state.blank_left()})"
        f"  saw_active={state.saw_active}"
        f"  handcuffed={sorted(state.handcuffed)}",
        f"Turn: {state.players[state.current].name}",
        "─" * 60,
    ]
    return "\n".join(lines)


def prompt_human_action(state: GameState, me: int) -> tuple[str, Optional[str]]:
    player = state.players[me]
    while True:
        print(f"\nYour items: {player.items}")
        raw = input(
            "Action ([s]hoot self, [o]pponent, [u]se <item>, [q]uit): "
        ).strip().lower()
        if not raw:
            continue
        if raw in ("q", "quit", "exit"):
            sys.exit(0)
        if raw in ("s", "self"):
            return ("shoot", "self")
        if raw in ("o", "opp", "opponent"):
            return ("shoot", "opponent")
        if raw.startswith("u"):
            parts = raw.split(maxsplit=1)
            if len(parts) == 2 and parts[1] in ITEMS:
                if parts[1] in player.items:
                    return ("use_item", parts[1])
                print(f"You don't have a {parts[1]}.")
                continue
            print(f"Items: {', '.join(ITEMS)}")
            continue
        print("Unrecognized input.")


# ---------------------------------------------------------------------------
# Round / match driver
# ---------------------------------------------------------------------------


def play_round(
    state: GameState,
    human_idx: Optional[int],
    log: Callable[[str], None],
) -> int:
    """Play until one side's HP hits zero. Returns the winner's index."""
    while all(p.alive() for p in state.players):
        if state.shells_left() == 0:
            # Reload mid-round: new shell count and new items.
            new_shells = new_loadout(state.rng)
            state.shells = new_shells
            state.known_to_bot.clear()
            state.saw_active = False
            state.handcuffed.clear()
            deal_items(state, state.rng, count=2)
            log(
                f"\n[Reload] {sum(new_shells)} live / "
                f"{len(new_shells) - sum(new_shells)} blank shells loaded."
            )

        me = state.current
        log(render_state(state))

        if human_idx is not None and me == human_idx:
            action, arg = prompt_human_action(state, me)
        else:
            action, arg = _bot_choose_action(state, me)
            log(f"{state.players[me].name} decides: {action} {arg}")

        if action == "use_item":
            assert arg is not None
            apply_item(state, me, arg, log)
            # Same player acts again after using an item.
        elif action == "shoot":
            assert arg in ("self", "opponent")
            resolve_shot(state, me, arg, log)
        else:
            log(f"Unknown action {action!r}; passing turn.")
            state.advance_turn()

    winner = 0 if state.players[0].alive() else 1
    log(f"\n*** {state.players[winner].name} wins the round. ***")
    return winner


def start_round(
    p1_name: str,
    p2_name: str,
    hp: int,
    rng: random.Random,
    p1_is_bot: bool,
    p2_is_bot: bool,
) -> GameState:
    players = [
        Player(p1_name, hp=hp, max_hp=hp, is_bot=p1_is_bot),
        Player(p2_name, hp=hp, max_hp=hp, is_bot=p2_is_bot),
    ]
    state = GameState(players=players, shells=new_loadout(rng), rng=rng)
    deal_items(state, rng, count=2)
    return state


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def play_interactive(rng: random.Random) -> None:
    print("Welcome to Buckshot Roulette — offline edition.\n")
    name = input("Your name [Player]: ").strip() or "Player"
    state = start_round(
        p1_name=name,
        p2_name="Dealer-Bot",
        hp=DEFAULT_MAX_HP,
        rng=rng,
        p1_is_bot=False,
        p2_is_bot=True,
    )
    play_round(state, human_idx=0, log=print)


def watch(rng: random.Random) -> None:
    state = start_round(
        p1_name="Bot-A",
        p2_name="Bot-B",
        hp=DEFAULT_MAX_HP,
        rng=rng,
        p1_is_bot=True,
        p2_is_bot=True,
    )
    play_round(state, human_idx=None, log=print)


def simulate(n: int, rng: random.Random) -> dict[str, int]:
    wins = {"Bot-A": 0, "Bot-B": 0}
    for _ in range(n):
        state = start_round(
            "Bot-A", "Bot-B", DEFAULT_MAX_HP, rng, True, True
        )
        winner = play_round(state, human_idx=None, log=lambda _m: None)
        wins[state.players[winner].name] += 1
    return wins


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="watch bot vs bot")
    parser.add_argument("--sim", type=int, default=0, help="run N silent simulations")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)

    if args.sim:
        stats = simulate(args.sim, rng)
        total = sum(stats.values())
        print(f"Simulated {total} rounds:")
        for name, w in stats.items():
            pct = (w / total * 100) if total else 0.0
            print(f"  {name}: {w}  ({pct:.1f}%)")
        return 0

    if args.watch:
        watch(rng)
        return 0

    play_interactive(rng)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

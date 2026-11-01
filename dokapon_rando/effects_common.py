"""Who gets which effect: the logic shared by the weapon and shield effect engines.

Three tiers (the same for every kind of equipment):
  unchanged: each item keeps the effect it started with. If the equipment shuffler has moved items between slots, the effect
             follows the item (its name), because the exe keys effects on the slot's id.
  shuffle:   the same effects, as many copies of each as the game had, on different items.
  random:    every item rolls whether it gets an effect and which one (optionally weighted).
Items can be pinned: they keep what the unchanged tier gave them whatever the mode.
"""
import random
from dataclasses import dataclass, field


ALWAYS = 101      # chance byte value that always procs (a roll is 0..100 and procs when it is below the chance)


@dataclass
class TierSettings:
    mode: str = "unchanged"                  # "unchanged", "shuffle" or "random"
    pinned: frozenset[int] = frozenset()     # slot ids that keep their unchanged-tier effect
    effect_weights: dict[int, float] = field(default_factory=dict)   # random mode: weight per effect (default 1 each)
    effect_rate: float | None = None         # random mode: chance an item gets any effect (default: the share that had one)
    always_proc: bool = False                # every effect with a roll procs every time
    effect_odds: dict[int, int] = field(default_factory=dict)        # percent per effect; beats the default, loses to always_proc
    odds_range: tuple[int, int] | None = None                        # each item with a roll gets random odds in this range (percent)


def follow_base(vanilla: dict[int, int], names_now: list[str], original_names: list[str] | None, none: int) -> dict[int, int]:
    """The unchanged tier. vanilla: slot id -> effect in the base game (ids start at 1); names_now: the name in each slot now.
    `original_names` are the names before any shuffle; without them every slot keeps its own effect."""
    if original_names is None:
        return dict(vanilla)
    out = {}
    for i, name in enumerate(names_now, 1):
        origin = original_names.index(name) + 1 if name in original_names else None
        out[i] = vanilla[origin] if origin is not None else none
    return out


def assign(base: dict[int, int], effects: list[int], s: TierSettings, rng: random.Random, none: int) -> dict[int, int]:
    """Apply the tier to `base` (slot id -> effect, `none` for nothing). `effects` are all the effect ids that can be dealt."""
    result = dict(base)
    free = [slot for slot in sorted(base) if slot not in s.pinned]
    if s.mode == "unchanged":
        return result
    if s.mode == "shuffle":
        carried = [base[slot] for slot in free if base[slot] != none]    # as many copies as there were
        homes = rng.sample(free, len(carried))
        for slot in free:
            result[slot] = none
        for slot, eff in zip(homes, carried):
            result[slot] = eff
    elif s.mode == "random":
        weights = [max(0.0, s.effect_weights.get(e, 1.0)) for e in effects]
        had = sum(1 for slot in free if base[slot] != none)
        rate = s.effect_rate if s.effect_rate is not None else (had / len(free) if free else 0.0)
        for slot in free:
            gets = rng.random() < rate and sum(weights) > 0
            result[slot] = rng.choices(effects, weights)[0] if gets else none
    else:
        raise ValueError(f"unknown effect mode {s.mode!r}")
    return result


def chance_for(effect: int, none: int, vanilla_pct: int, rolls: bool, s: TierSettings, rng: random.Random | None = None) -> int:
    """The chance byte for one item: 0 for none, ALWAYS for effects without a roll.
    Precedence: always_proc, then the per-effect percentage, then odds_range (needs an rng), then the effect's own odds."""
    if effect == none:
        return 0
    if not rolls or s.always_proc:
        return ALWAYS
    if effect in s.effect_odds:
        pct = s.effect_odds[effect]
    elif s.odds_range is not None and rng is not None:
        pct = rng.randint(*s.odds_range)
    else:
        pct = vanilla_pct
    return ALWAYS if pct >= 100 else max(0, pct)

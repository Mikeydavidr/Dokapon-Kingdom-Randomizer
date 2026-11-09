"""One list of effects across weapons, shields and accessories (the data model for mixed pools; see docs/randomizer-design.md).

An effect is identified by (kind, native id): the kind of equipment that carries it in the base game and the id the exe's code
switches on there. This module only describes effects; it does not patch anything. It joins the weapon and shield registries with
the accessory sites found so far, and records for each one the hook it fires from and whether it is safe to move to another kind.
"""
from dataclasses import dataclass
from enum import Enum

from . import shield_effects, weapon_effects


class Kind(Enum):
    WEAPON = "weapon"
    SHIELD = "shield"
    ACCESSORY = "accessory"


class Hook(Enum):
    ATTACK = "attack"          # the wielder hits (weapon effect function)
    DEFEND = "defend"          # the wielder is attacked or defends (shield dispatcher)
    TURN_START = "turn start"  # start of the wearer's turn (event picker)
    PASSIVE = "passive"        # read at scattered sites (stats, movement, Wanted ...)


class ChanceSource(Enum):
    RECORD = "record"          # the item record's chance byte (+0x139 in memory)
    LITERAL = "literal"        # a constant compiled into code
    GAME_STATE = "game state"  # an int in the game state
    NONE = "none"              # always on / no roll


@dataclass(frozen=True)
class Effect:
    kind: Kind                 # the kind that carries it in the base game
    native_id: int             # weapon: case 0-21; shield: the vanilla shield id; accessory: the accessory id
    name: str
    hook: Hook
    vanilla_odds: int          # percent; 100 when it never rolls
    chance_source: ChanceSource  # where the odds come from in the UNPATCHED exe
    site: int | None           # VA of the code that makes the effect happen / roll, if known
    verified: bool             # seen in play
    movable: bool              # safe to give to another kind of item (False until a cross-kind test has passed)

    @property
    def key(self) -> tuple[Kind, int]:
        return (self.kind, self.native_id)


# Accessory sites found so far (docs/item-records-and-effects.md, section 5). Names are the effect, not the accessory.
# They are fixed code at each site, so none is movable yet.
_ACCESSORIES: tuple[tuple[int, str, Hook, int, ChanceSource, int, bool], ...] = (
    (0x0D, "Squid Ring", Hook.PASSIVE, 100, ChanceSource.RECORD, 0x1401BA1B9, False),
    (0x12, "Wind Bracelet", Hook.PASSIVE, 100, ChanceSource.NONE, 0x14017A62A, False),
    (0x13, "Crystal Choker", Hook.TURN_START, 10, ChanceSource.GAME_STATE, 0x1401B1F96, True),
    (0x14, "Mirror Necklace", Hook.DEFEND, 100, ChanceSource.RECORD, 0x140201442, False),
    (0x15, "Dodge Necklace", Hook.DEFEND, 100, ChanceSource.RECORD, 0x1400EB5EA, False),
    (0x16, "Angel Choker", Hook.PASSIVE, 100, ChanceSource.RECORD, 0x1400E6AB4, False),
    (0x1E, "Wallace Badge", Hook.TURN_START, 10, ChanceSource.GAME_STATE, 0x1401B1FA5, False),
    (0x1F, "Criminal Studs", Hook.PASSIVE, 100, ChanceSource.NONE, 0x1401F1547, False),
)


def all_effects() -> list[Effect]:
    out: list[Effect] = []
    for e in weapon_effects.EFFECTS.values():
        rolls = e.roll_va is not None
        out.append(Effect(Kind.WEAPON, e.case, e.full, Hook.ATTACK, e.vanilla_odds,
                          ChanceSource.LITERAL if rolls else ChanceSource.NONE, e.roll_va, False, False))
    for e in shield_effects.EFFECTS.values():
        rolls = e.roll_va is not None
        out.append(Effect(Kind.SHIELD, e.id, e.full, Hook.DEFEND, e.vanilla_odds,
                          ChanceSource.LITERAL if rolls else ChanceSource.NONE, e.roll_va, e.verified, False))
    for ident, name, hook, odds, src, site, verified in _ACCESSORIES:
        out.append(Effect(Kind.ACCESSORY, ident, name, hook, odds, src, site, verified, False))
    return out


def by_key() -> dict[tuple[Kind, int], Effect]:
    return {e.key: e for e in all_effects()}


def candidates_for(kind: Kind, effects: list[Effect] | None = None, allow_cross: bool = False) -> list[Effect]:
    """Effects an item of `kind` may be given. Without `allow_cross` that is its own kind; with it, every `movable` effect too."""
    pool = effects if effects is not None else all_effects()
    return [e for e in pool if e.kind == kind or (allow_cross and e.movable)]

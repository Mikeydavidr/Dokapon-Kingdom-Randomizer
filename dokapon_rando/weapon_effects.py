"""Weapon effects: move which weapon carries which special effect, and control how often each procs.

How the game does it (see docs/item-records-and-effects.md): the attacker's weapon-effect function picks a case with a switch on the
weapon's id (ids 13-67 in the base game), and each case rolls its proc against a number compiled into the code. The patch built here
  1. widens the switch to all 67 weapons and moves the id -> case byte table to free space at the end of .text;
  2. makes each effect's first roll compare against the weapon record's chance byte (tail byte 2, in memory at the weapon struct
     +0x139), so every weapon can have its own odds. Follow-up rolls (made only after the first one procs) keep their constants.
Effects are called "cases" 0-21 here, numbered in the order of the weapon each belongs to in the base game; case 22 is no effect.
"""
import random
import struct
from dataclasses import dataclass, field

from .effects_common import ALWAYS, TierSettings, assign, chance_for, follow_base
from .exe import Exe, HexMod, foff, rva_to_va
from .gamefile import GameFile
from .tables import TableSpec, read_table, write_table

WEAPON_COUNT = 67
NO_EFFECT = 22


@dataclass(frozen=True)
class WeaponEffect:
    case: int
    source_weapon: int      # the weapon id that has this effect in the base game
    full: str               # shop text, first line ("defender" is the one being attacked, "attacker" the wielder)
    short: str              # for small description slots
    vanilla_odds: int       # percent; 100 for the effect that never rolls
    spell: int              # position in the offensive magic table of the spell the effect casts, or -1
    roll_va: int | None     # VA of the first roll's "cmp cx, imm8", None if it never rolls (case 11, Soul Eater)


EFFECTS: dict[int, WeaponEffect] = {e.case: e for e in (
    WeaponEffect(0, 13, "Put defender to sleep", "Sleep", 12, -1, 0x140178EDA),
    WeaponEffect(1, 18, "Curse defender", "Curse", 12, -1, 0x140178F3F),
    WeaponEffect(2, 23, "Light damage to defender", "Light damage", 12, 4, 0x14017927D),
    WeaponEffect(3, 24, "Poison defender", "Poison", 12, -1, 0x140178FA4),
    WeaponEffect(4, 26, "Reduce defender's attack", "Attack down", 12, -1, 0x140179218),
    WeaponEffect(5, 33, "Fire damage to defender", "Fire damage", 12, 1, 0x1401795B9),
    WeaponEffect(6, 34, "Seal one defender battle command", "Seal command", 12, -1, 0x1401790D3),
    WeaponEffect(7, 37, "Light damage to defender", "Light damage", 25, 4, 0x1401793B7),
    WeaponEffect(8, 43, "Wind damage to defender", "Wind damage", 12, 11, 0x1401797C4),
    WeaponEffect(9, 50, "Instantly kill defender", "Instant kill", 8, -1, 0x140178E7B),
    WeaponEffect(10, 53, "Reduce all defender's stats", "All stats down", 12, -1, 0x1401791B3),
    WeaponEffect(11, 56, "Drain 2x attacker's level", "Drain 2x level", 100, -1, None),
    WeaponEffect(12, 57, "Raise all attacker's stats 25%", "Own stats +25%", 12, -1, 0x140178DF2),
    WeaponEffect(13, 58, "Blind defender", "Blind", 12, -1, 0x140179009),
    WeaponEffect(14, 59, "Reduce defender's speed", "Speed down", 12, -1, 0x14017914E),
    WeaponEffect(15, 60, "Lightning damage to defender", "Lightning", 25, 4, 0x1401794B8),
    WeaponEffect(16, 61, "Light damage to defender", "Light damage", 12, 14, 0x1401798C5),
    WeaponEffect(17, 62, "Destroy defender's battle magic", "Destroy magic", 12, -1, 0x14017906E),
    WeaponEffect(18, 63, "Fire damage to defender", "Fire damage", 12, 2, 0x1401796BA),
    WeaponEffect(19, 64, "Drain 1/10 attacker's HP", "Drain 1/10 HP", 25, -1, 0x140178D5B),
    WeaponEffect(20, 66, "Wind damage to defender", "Wind damage", 25, 11, 0x1401799C6),
    WeaponEffect(21, 67, "Fire damage to defender", "Fire damage", 50, 2, 0x140179AC7),
)}

# Where the patch puts things (the end of .text; the shield patch starts at 0x44C4A0)
OLD_TABLE_RVA = 0x179E38     # ids 13..67, one case byte each
TABLE_RVA = 0x44C420         # 67 bytes, index = weapon id - 1
HELPER_RVA = 0x44C470
CAVE_END = 0x44C490
# The switch head: add eax,-0xd / cmp eax,0x36 / movzx eax, byte [r12 + rax + table]
ADD_VA, CMP_VA, MOVZX_VA = 0x140178CB5, 0x140178CB8, 0x140178CD2
# sub ecx, eax / mov rax, [rsi + 0x18] (the attacker's weapon struct) / movzx eax, byte [rax + 0x139] (its chance byte) / cmp cx, ax / ret
HELPER = bytes.fromhex("29 C1" "48 8B 46 18" "0F B6 80 39 01 00 00" "66 39 C1" "C3")


class WeaponEffectSettings(TierSettings):
    """mode, pinned, effect_weights, effect_rate, always_proc, effect_odds, odds_range: see effects_common.TierSettings
    (ids are weapon ids for `pinned` and effect cases 0-21 for `effect_weights` and `effect_odds`)."""


@dataclass
class WeaponEffectResult:
    assignment: dict[int, int]              # weapon id -> effect case (22 = none), all 67
    odds: dict[int, int]                    # weapon id -> chance byte (meaningful for effects that roll)
    described: int = 0
    log: list[str] = field(default_factory=list)


def vanilla_assignment() -> dict[int, int]:
    out = {wid: NO_EFFECT for wid in range(1, WEAPON_COUNT + 1)}
    for e in EFFECTS.values():
        out[e.source_weapon] = e.case
    return out


def odds_for(case: int, settings: WeaponEffectSettings, rng: random.Random | None = None) -> int:
    eff = EFFECTS.get(case)
    return chance_for(case, NO_EFFECT, eff.vanilla_odds if eff else 0, bool(eff and eff.roll_va), settings, rng)


def weapon_spec(game: GameFile) -> TableSpec:
    return TableSpec("WEAPON", game.build.weapons, 0x58, 1, "SII", "IIII" + "S" * 16, 4)


# -- the exe patch -----------------------------------------------------------------------------------------------------

def patch_weapon_effects(exe: Exe, mod: HexMod, cases: dict[int, int]) -> None:
    """Add the weapon effect patch to `mod`. cases: weapon id -> effect case for all 67 weapons."""
    assert sorted(cases) == list(range(1, WEAPON_COUNT + 1))
    exe.check_cave_empty(TABLE_RVA, CAVE_END)
    # the base game's table must agree with the effect data above
    old = exe.data[foff(rva_to_va(OLD_TABLE_RVA)):foff(rva_to_va(OLD_TABLE_RVA)) + 55]
    expected = vanilla_assignment()
    assert [expected[w] for w in range(13, 68)] == list(old), "the effect data doesn't match this exe's weapon table"
    mod.add(*exe.map_slack_edit())
    mod.add(foff(rva_to_va(TABLE_RVA)), bytes(cases[w] for w in range(1, WEAPON_COUNT + 1)))
    mod.add(foff(rva_to_va(HELPER_RVA)), HELPER)

    # switch head: index by id - 1, up to id 67, through the new table
    exe.expect(ADD_VA, bytes.fromhex("83 C0 F3"))
    mod.add(foff(ADD_VA), bytes.fromhex("83 C0 FF"))
    exe.expect(CMP_VA, bytes.fromhex("83 F8 36"))
    mod.add(foff(CMP_VA), bytes.fromhex("83 F8 42"))
    exe.expect(MOVZX_VA, bytes.fromhex("41 0F B6 84 04") + struct.pack("<I", OLD_TABLE_RVA))
    mod.add(foff(MOVZX_VA) + 5, struct.pack("<I", TABLE_RVA))

    # first rolls read the chance byte: "sub ecx, eax; cmp cx, imm8" -> call helper; nop
    for e in EFFECTS.values():
        if e.roll_va is None:
            continue
        start = e.roll_va - 2
        o = exe.expect(start, bytes.fromhex("2B C8 66 83 F9"))
        assert exe.data[o + 5] == e.vanilla_odds, (e.case, exe.data[o + 5])
        mod.add(foff(start), b"\xE8" + struct.pack("<i", rva_to_va(HELPER_RVA) - (start + 5)) + b"\x90")


# -- the data file: chance bytes and descriptions ----------------------------------------------------------------------

def write_chances(game: GameFile, odds: dict[int, int]) -> None:
    """Weapon record tail byte 2 is the chance the patched roll reads. Pass only the weapons to change."""
    table = read_table(game.data, weapon_spec(game))
    if table is None or len(table.records) != WEAPON_COUNT:
        raise ValueError("couldn't recognize the weapon table")
    for rec in table.records:
        if rec.id in odds:
            rec.tail = rec.tail[:2] + bytes([odds[rec.id]]) + rec.tail[3:]
    write_table(game.data, table)


def description_slots(data: bytes | bytearray) -> list[tuple[int, int]]:
    """(position, size) of the 67 weapon descriptions: null-terminated strings in id order, each padded to 4 bytes."""
    raw = bytes(data)
    pos = raw.find(b"A regular ol' knife.")
    if pos < 0:
        raise ValueError("couldn't find the weapon descriptions")
    out = []
    for _ in range(WEAPON_COUNT):
        end = raw.index(b"\0", pos)
        nxt = end
        while raw[nxt] == 0:
            nxt += 1
        out.append((pos, nxt - pos))
        pos = nxt
    if not raw[out[-1][0]:].startswith(b"A sword found hidden"):
        raise ValueError("the weapon descriptions aren't where expected")
    return out


def effect_text(case: int, chance: int, size: int, spell_names: list[str]) -> str:
    if case == NO_EFFECT:
        return "No special effect."
    e = EFFECTS[case]
    rolls = e.roll_va is not None
    casts = 0 <= e.spell < len(spell_names)
    line = "Cast " + spell_names[e.spell] if casts else e.full
    when = ("Always on" if chance >= 100 else f"{chance}% chance") if rolls else "Always on"
    text = line + "\\n" + when
    if len(text) >= size:   # short form for the small slots
        text = line if casts else e.short
        if rolls and chance < 100:
            text += f" {chance}%"
    return text


def write_descriptions(game: GameFile, slots: list[tuple[int, int]], assignment: dict[int, int], odds: dict[int, int],
                       vanilla: dict[int, int], vanilla_odds: dict[int, int], spell_names: list[str]) -> int:
    """Rewrite the description of every weapon whose effect or odds aren't its own anymore, inside the space it has.
    The game walks the strings one after another, so the rest of a slot is filled with spaces and ends in one terminator."""
    count = 0
    for wid in range(1, WEAPON_COUNT + 1):
        if assignment[wid] == vanilla[wid] and odds[wid] == vanilla_odds[wid]:
            continue
        pos, size = slots[wid - 1]
        text = effect_text(assignment[wid], odds[wid], size, spell_names)
        if len(text) >= size:
            continue
        game.data[pos:pos + size] = text.ljust(size - 1).encode("ascii") + b"\0"
        count += 1
    return count


def spell_names(game: GameFile) -> list[str]:
    spec = TableSpec("OFFENSE MAGIC", game.build.magic_offense, 0x70, 1, "SII", "SSSSSSISIIII", 0)
    table = read_table(game.data, spec)
    return [r.name for r in table.records] if table else []


# -- everything together -----------------------------------------------------------------------------------------------

def apply_weapon_effects(game: GameFile, exe: Exe, mod: HexMod, settings: WeaponEffectSettings, seed: int,
                         original_names: list[str] | None = None) -> WeaponEffectResult:
    """Decide who gets what, patch the data file (chances, descriptions) and add the exe patch to `mod`.
    original_names: the weapon names before any equipment shuffle, so the unchanged tier can follow each weapon."""
    rng = random.Random(seed + 3)
    names_now = [r.name for r in read_table(game.data, weapon_spec(game)).records]
    base = follow_base(vanilla_assignment(), names_now, original_names, NO_EFFECT)
    assignment = assign(base, list(EFFECTS), settings, rng, NO_EFFECT)
    odds = {wid: odds_for(case, settings, rng) for wid, case in assignment.items()}
    vanilla = vanilla_assignment()   # what the unpatched game does (and what the descriptions say)
    vanilla_odds = {wid: odds_for(case, WeaponEffectSettings()) for wid, case in vanilla.items()}
    result = WeaponEffectResult(assignment, odds)
    if assignment == vanilla and odds == vanilla_odds:
        result.log.append("Weapon effects: unchanged.")
        return result

    slots = description_slots(game.data)
    names = spell_names(game)
    patch_weapon_effects(exe, mod, assignment)
    # effects without a roll ignore the chance byte, so leave those records alone
    write_chances(game, {wid: odds[wid] for wid, case in assignment.items() if case != NO_EFFECT and EFFECTS[case].roll_va is not None})
    result.described = write_descriptions(game, slots, assignment, odds, vanilla, vanilla_odds, names)
    for wid in range(1, WEAPON_COUNT + 1):
        if assignment[wid] != vanilla[wid] or odds[wid] != vanilla_odds[wid]:
            e = EFFECTS.get(assignment[wid])
            when = "always" if odds[wid] >= 100 or (e and e.roll_va is None) else f"{odds[wid]}%"
            origin = original_names[e.source_weapon - 1] if e and original_names else f"weapon {e.source_weapon}" if e else ""
            result.log.append(f"{names_now[wid - 1]}: " + (f"{origin}'s effect ({when})" if e else "no effect"))
    return result

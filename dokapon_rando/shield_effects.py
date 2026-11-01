"""Shield effects: move which shield carries which ability, and control how often each procs.

How the game does it (see docs/item-records-and-effects.md): one function switches on the equipped shield's id (15..39) and each
case rolls its proc against a number compiled into the code. The records' chance bytes are never read. The patch built here
  1. sends every read of the shield id through a byte table (id -> effect), so shield N can carry the effect of shield E,
     including the animation and text, which the battle scripts pick by the same id;
  2. makes each effect's roll compare against the wielder's own shield record chance byte (like the weapon effects patch),
     so every shield can have its own odds.
A roll is 0..100 and procs when below the chance, so a chance of 101 means "always". Athena's and Dark have no roll.
"""
import random
import struct
from dataclasses import dataclass, field

from .exe import BASE, Exe, HexMod, foff, rva_to_va
from .gamefile import GameFile
from .tables import TableSpec, read_table, write_table

ALWAYS = 101      # chance byte value that always procs
NO_EFFECT = 0


@dataclass(frozen=True)
class ShieldEffect:
    id: int                 # the vanilla shield id whose behaviour this is (the dispatcher's case)
    name: str
    full: str               # shop text, first line
    short: str              # for small description slots
    vanilla_odds: int       # percent; 100 for the effects with no roll
    roll_va: int | None     # VA of the roll's "cmp cx, imm8", None if the effect never rolls
    verified: bool          # watched in play (otherwise worded from the community wiki)


# Cases that have a roll come in two shapes (see _odds_helper): "sub ecx,eax; cmp cx,imm" (A) or with a "mov eax,r9d" between (B)
EFFECTS: dict[int, ShieldEffect] = {e.id: e for e in (
    ShieldEffect(15, "Warrior", "Block status ailments", "Block ailments", 25, 0x14017891E, False),
    ShieldEffect(20, "Mirror", "Reflect battle magic", "Reflect magic", 12, 0x140178A57, True),
    ShieldEffect(21, "Binder", "Reflect an attack's damage", "Reflect attack", 25, 0x140178983, True),
    ShieldEffect(30, "Metal Guard", "Reflect an attack's damage", "Reflect attack", 12, 0x1401789EB, True),
    ShieldEffect(31, "Sun", "Fully heal when defending", "Heal on defend", 12, 0x14017883C, True),
    ShieldEffect(32, "Cursed", "Damages the wielder", "Hurts wielder", 25, 0x140178795, False),
    ShieldEffect(36, "Athena's", "Halve battle magic damage", "Half magic dmg", 100, None, False),
    ShieldEffect(38, "Dark", "Damages wielder, 2x level", "Hurts wielder", 100, None, False),
    ShieldEffect(39, "Dokapon", "Reduce opponent's damage", "Reduce damage", 12, 0x1401788B0, False),
)}
SHIELD_COUNT = 40
_SHAPE_B = {20, 21, 30}   # Mirror, Binder, Metal Guard have a "mov eax, r9d" before the compare

# Where the patch puts things: the end of .text (the weapon effects patch uses RVAs up to 0x44C487)
TABLE_RVA = 0x44C4A0      # 48 bytes, index = shield id
ID_HELPER_A, ID_HELPER_B, ID_HELPER_C = 0x44C4D0, 0x44C4F0, 0x44C510
ODDS_HELPER_A, ODDS_HELPER_B = 0x44C540, 0x44C560
CAVE_END = 0x44C580
# The three reads of the shield id: the effect function, the second half of the Dokapon Shield, the battle-script value fetch
ID_SITE_A, ID_OLD_A = 0x1401786E6, bytes.fromhex("0F B6 80 48 01 00 00")     # movzx eax, byte [rax + 0x148]
ID_SITE_B, ID_OLD_B = 0x140175405, bytes.fromhex("80 B8 48 01 00 00 27")     # cmp byte [rax + 0x148], 0x27
ID_SITE_C, ID_OLD_C = 0x1401717D6, bytes.fromhex("44 0F B6 88 48 01 00 00")  # movzx r9d, byte [rax + 0x148]


@dataclass
class ShieldEffectSettings:
    mode: str = "unchanged"                 # "unchanged", "shuffle" (same effects, other shields), "random" (each shield rolls)
    pinned: frozenset[int] = frozenset()    # shield ids that keep their own effect whatever the mode
    effect_weights: dict[int, float] = field(default_factory=dict)   # random mode: weight per effect id (default 1 each)
    effect_rate: float | None = None        # random mode: chance a shield gets any effect (default: the original share, 9 of 40)
    always_proc: bool = False               # "effectful": every effect with a roll procs every time
    effect_odds: dict[int, int] = field(default_factory=dict)        # percent per effect id; beats the default, loses to always_proc


@dataclass
class ShieldEffectResult:
    assignment: dict[int, int]              # shield id -> effect id (0 = none), all 40
    odds: dict[int, int]                    # shield id -> chance byte written
    described: int = 0
    log: list[str] = field(default_factory=list)


# -- who gets what -----------------------------------------------------------------------------------------------------

def vanilla_assignment() -> dict[int, int]:
    return {sid: (sid if sid in EFFECTS else NO_EFFECT) for sid in range(1, SHIELD_COUNT + 1)}


def assign_effects(settings: ShieldEffectSettings, rng: random.Random) -> dict[int, int]:
    result = vanilla_assignment()
    free = [sid for sid in range(1, SHIELD_COUNT + 1) if sid not in settings.pinned]
    if settings.mode == "unchanged":
        return result
    if settings.mode == "shuffle":
        effects = [result[sid] for sid in free if result[sid] != NO_EFFECT]   # as many copies as the game had
        homes = rng.sample(free, len(effects))
        for sid in free:
            result[sid] = NO_EFFECT
        for sid, eff in zip(homes, effects):
            result[sid] = eff
    elif settings.mode == "random":
        ids = list(EFFECTS)
        weights = [max(0.0, settings.effect_weights.get(e, 1.0)) for e in ids]
        rate = settings.effect_rate if settings.effect_rate is not None else len(EFFECTS) / SHIELD_COUNT
        for sid in free:
            result[sid] = rng.choices(ids, weights)[0] if rng.random() < rate and sum(weights) > 0 else NO_EFFECT
    else:
        raise ValueError(f"unknown shield effect mode {settings.mode!r}")
    return result


def odds_for(effect_id: int, settings: ShieldEffectSettings) -> int:
    """The chance byte for an effect: 0 for none, ALWAYS for effects without a roll, else the setting."""
    if effect_id == NO_EFFECT:
        return 0
    eff = EFFECTS[effect_id]
    if eff.roll_va is None:
        return ALWAYS
    if settings.always_proc:
        return ALWAYS
    pct = settings.effect_odds.get(effect_id, eff.vanilla_odds)
    return ALWAYS if pct >= 100 else max(0, pct)


# -- the exe patch -----------------------------------------------------------------------------------------------------

def _id_helper(rva: int, tail: bytes = b"") -> bytes:
    """rax = shield struct -> eax = table[id]; r11 kept; then `tail` (a replaced instruction's follow-up) and ret."""
    head = bytes.fromhex("0F B6 80 48 01 00 00" "41 53")       # movzx eax, byte [rax+0x148] ; push r11
    lea = bytes.fromhex("4C 8D 1D") + struct.pack("<i", TABLE_RVA - (rva + len(head) + 7))   # lea r11, [rip+table]
    return head + lea + bytes.fromhex("41 0F B6 04 03" "41 5B") + tail + b"\xC3"   # movzx eax,[r11+rax] ; pop r11 ; tail ; ret


def _id_helper_c(rva: int) -> bytes:
    """rax = shield struct -> r9d = table[id]; every other register (rax too) kept."""
    head = bytes.fromhex("50" "44 0F B6 88 48 01 00 00")      # push rax ; movzx r9d, byte [rax+0x148]
    lea = bytes.fromhex("48 8D 05") + struct.pack("<i", TABLE_RVA - (rva + len(head) + 7))   # lea rax, [rip+table]
    return head + lea + bytes.fromhex("46 0F B6 0C 08" "58 C3")   # movzx r9d,[rax+r9] ; pop rax ; ret


_CHANCE = bytes.fromhex("52"                       # push rdx
                        "49 8B 90 98 00 00 00"     # mov rdx, [r8 + 0x98]        (r8 = the battle action, +0x98 = defender's shield struct)
                        "0F B6 92 39 01 00 00")    # movzx edx, byte [rdx + 0x139]   (the record's chance byte)
_COMPARE = bytes.fromhex("66 39 D1" "5A" "C3")     # cmp cx, dx ; pop rdx ; ret   (flags survive the pop and ret)


def _odds_helper(shape_b: bool) -> bytes:
    """Replaces "sub ecx,eax; cmp cx,imm8" (shape A) or "mov eax,r9d; cmp cx,imm8" (shape B) with a compare against the chance byte."""
    if shape_b:
        return _CHANCE + bytes.fromhex("41 8B C1") + _COMPARE                         # mov eax, r9d
    return bytes.fromhex("2B C8") + _CHANCE + _COMPARE                                # sub ecx, eax


def patch_shield_effects(exe: Exe, mod: HexMod, id_table: dict[int, int], per_item_odds: bool = True) -> None:
    """Add the shield effect patch to `mod`. id_table: shield id -> effect id (0 = none); unlisted ids keep their own."""
    exe.check_cave_empty(TABLE_RVA, CAVE_END)
    mod.add(*exe.map_slack_edit())
    table = bytearray(range(48))
    for sid, eff in id_table.items():
        table[sid] = eff
    mod.add(foff(rva_to_va(TABLE_RVA)), bytes(table))

    helpers = {ID_HELPER_A: _id_helper(ID_HELPER_A), ID_HELPER_B: _id_helper(ID_HELPER_B, bytes.fromhex("3C 27")),   # cmp al, 0x27
               ID_HELPER_C: _id_helper_c(ID_HELPER_C)}
    for rva, code in helpers.items():
        assert len(code) <= 0x20, hex(rva)
        mod.add(foff(rva_to_va(rva)), code)
    for site, old, rva in ((ID_SITE_A, ID_OLD_A, ID_HELPER_A), (ID_SITE_B, ID_OLD_B, ID_HELPER_B), (ID_SITE_C, ID_OLD_C, ID_HELPER_C)):
        exe.expect(site, old)
        nop = b"\x66\x90" if len(old) == 7 else b"\x0F\x1F\x00"
        mod.add(foff(site), b"\xE8" + struct.pack("<i", rva_to_va(rva) - (site + 5)) + nop)

    if not per_item_odds:
        return
    for rva, code in ((ODDS_HELPER_A, _odds_helper(False)), (ODDS_HELPER_B, _odds_helper(True))):
        assert len(code) <= 0x20, hex(rva)
        mod.add(foff(rva_to_va(rva)), code)
    for eff in EFFECTS.values():
        if eff.roll_va is None:
            continue
        shape_b = eff.id in _SHAPE_B
        start = eff.roll_va - (3 if shape_b else 2)
        old = (bytes.fromhex("41 8B C1") if shape_b else bytes.fromhex("2B C8")) + bytes.fromhex("66 83 F9")
        o = exe.expect(start, old)
        assert exe.data[o + len(old)] == eff.vanilla_odds, (eff.name, exe.data[o + len(old)])   # the literal this replaces
        helper = ODDS_HELPER_B if shape_b else ODDS_HELPER_A
        mod.add(foff(start), b"\xE8" + struct.pack("<i", rva_to_va(helper) - (start + 5)) + (b"\x66\x90" if shape_b else b"\x90"))


# -- the data file: chance bytes and descriptions ----------------------------------------------------------------------

def shield_spec(game: GameFile) -> TableSpec:
    return TableSpec("SHIELD", game.build.shields, 0x5E, 1, "SII", "IIII" + "S" * 16, 4)


def write_chances(game: GameFile, odds: dict[int, int]) -> None:
    """Shield record tail byte 0 is the chance the patched roll reads. Pass only the shields to change."""
    table = read_table(game.data, shield_spec(game))
    if table is None or len(table.records) != SHIELD_COUNT:
        raise ValueError("couldn't recognize the shield table")
    for rec in table.records:
        if rec.id in odds:
            rec.tail = bytes([odds[rec.id]]) + rec.tail[1:]
    write_table(game.data, table)


def description_slots(data: bytes | bytearray) -> list[tuple[int, int]]:
    """(position, size) of the 40 shield descriptions: null-terminated strings in id order, each padded to 4 bytes.
    Anchored on the second one so that an already edited file still works."""
    pos = bytes(data).find(b"A very lightweight shield")
    if pos < 0:
        raise ValueError("couldn't find the shield descriptions")
    while data[pos - 1] == 0:
        pos -= 1
    while data[pos - 1] != 0:
        pos -= 1
    out = []
    for _ in range(SHIELD_COUNT):
        end = bytes(data).index(b"\0", pos)
        nxt = end
        while data[nxt] == 0:
            nxt += 1
        out.append((pos, nxt - pos))
        pos = nxt
    if not bytes(data[out[-1][0]:]).startswith(b"An evil shield said t"):
        raise ValueError("the shield descriptions aren't where expected")
    return out


def effect_text(effect_id: int, chance: int, size: int) -> str:
    if effect_id == NO_EFFECT:
        return "No special effect."
    eff = EFFECTS[effect_id]
    text = eff.full + "\\n" + ("Always on" if chance >= 100 else f"{chance}% chance")
    if len(text) >= size:   # short form for the small slots
        text = eff.short + ("" if chance >= 100 else f" {chance}%")
    return text


def write_descriptions(game: GameFile, slots: list[tuple[int, int]], assignment: dict[int, int], odds: dict[int, int],
                       vanilla: dict[int, int], vanilla_odds: dict[int, int]) -> int:
    """Rewrite the description of every shield whose effect or odds aren't its own anymore, inside the space it has.
    The game walks the strings one after another, so the rest of a slot is filled with spaces and ends in one terminator.
    `slots` come from description_slots, read before anything is written (a rewrite can remove its own anchor)."""
    count = 0
    for sid in range(1, SHIELD_COUNT + 1):
        if assignment[sid] == vanilla[sid] and odds[sid] == vanilla_odds[sid]:
            continue
        pos, size = slots[sid - 1]
        text = effect_text(assignment[sid], odds[sid], size)
        if len(text) >= size:
            continue
        game.data[pos:pos + size] = text.ljust(size - 1).encode("ascii") + b"\0"
        count += 1
    return count


# -- everything together -----------------------------------------------------------------------------------------------

def apply_shield_effects(game: GameFile, exe: Exe, mod: HexMod, settings: ShieldEffectSettings, seed: int) -> ShieldEffectResult:
    """Decide who gets what, patch the data file (chances, descriptions) and add the exe patch to `mod`."""
    rng = random.Random(seed + 0x5B1E)
    assignment = assign_effects(settings, rng)
    odds = {sid: odds_for(eff, settings) for sid, eff in assignment.items()}
    vanilla = vanilla_assignment()
    vanilla_odds = {sid: odds_for(eff, ShieldEffectSettings()) for sid, eff in vanilla.items()}
    result = ShieldEffectResult(assignment, odds)
    if assignment == vanilla and odds == vanilla_odds:
        result.log.append("Shield effects: unchanged.")
        return result
    slots = description_slots(game.data)
    patch_shield_effects(exe, mod, {sid: eff for sid, eff in assignment.items() if eff != vanilla[sid]})
    # effects without a roll ignore the chance byte, so leave those records alone
    write_chances(game, {sid: odds[sid] for sid, eff in assignment.items() if eff == NO_EFFECT or EFFECTS[eff].roll_va is not None})
    result.described = write_descriptions(game, slots, assignment, odds, vanilla, vanilla_odds)
    names = {r.id: r.name for r in read_table(game.data, shield_spec(game)).records}
    for sid in range(1, SHIELD_COUNT + 1):
        if assignment[sid] != vanilla[sid] or odds[sid] != vanilla_odds[sid]:
            eff = EFFECTS.get(assignment[sid])
            when = "always" if odds[sid] >= 100 else f"{odds[sid]}%"
            result.log.append(f"{names[sid]}: " + (f"{eff.name} ({when})" if eff else "no effect"))
    return result

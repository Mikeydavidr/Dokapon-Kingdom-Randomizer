"""Shield effects. The assignment logic needs no game files. The patch and data checks need an UNMODIFIED DkkStm.exe
(DKK_EXE) and stageBase_EN.DAT (DKK_STAGEBASE); they are skipped otherwise."""
import os
import random
import struct
from pathlib import Path

import pytest

from dokapon_rando import shield_effects as se
from dokapon_rando.exe import Exe, HexMod, foff, rva_to_va
from dokapon_rando.gamefile import GameFile
from dokapon_rando.tables import read_table

EXE, DAT = os.environ.get("DKK_EXE"), os.environ.get("DKK_STAGEBASE")
needs_exe = pytest.mark.skipif(not EXE or not Path(EXE).exists(), reason="set DKK_EXE to an unmodified DkkStm.exe")
needs_dat = pytest.mark.skipif(not DAT or not Path(DAT).exists(), reason="set DKK_STAGEBASE to an unmodified stageBase_EN.DAT")


# -- who gets what -----------------------------------------------------------------------------------------------------

def test_unchanged_is_vanilla():
    assert se.assign_effects(se.ShieldEffectSettings(), random.Random(1)) == se.vanilla_assignment()


def test_shuffle_keeps_the_number_of_copies_and_moves_them():
    s = se.ShieldEffectSettings(mode="shuffle")
    moved = False
    for seed in range(20):
        a = se.assign_effects(s, random.Random(seed))
        assert sorted(e for e in a.values() if e) == sorted(se.EFFECTS)
        moved |= a != se.vanilla_assignment()
    assert moved


def test_pinned_shields_keep_their_effect_and_never_receive_others():
    pinned = frozenset({32, 38})   # Cursed, Dark
    for mode in ("shuffle", "random"):
        for seed in range(20):
            a = se.assign_effects(se.ShieldEffectSettings(mode=mode, pinned=pinned), random.Random(seed))
            assert a[32] == 32 and a[38] == 38
            if mode == "shuffle":   # the pinned effects stay put, so nobody else may carry them
                assert sorted(e for e in a.values() if e) == sorted(se.EFFECTS)


def test_random_rate_and_weights():
    everyone = se.ShieldEffectSettings(mode="random", effect_rate=1.0)
    assert all(se.assign_effects(everyone, random.Random(3)).values())
    nobody = se.ShieldEffectSettings(mode="random", effect_rate=0.0)
    assert not any(se.assign_effects(nobody, random.Random(3)).values())
    only_sun = se.ShieldEffectSettings(mode="random", effect_rate=1.0, effect_weights={e: (1 if e == 31 else 0) for e in se.EFFECTS})
    assert set(se.assign_effects(only_sun, random.Random(3)).values()) == {31}


def test_stat_only_shields_can_receive_effects():
    s = se.ShieldEffectSettings(mode="random", effect_rate=1.0)
    a = se.assign_effects(s, random.Random(2))
    assert a[1] != 0   # the Wooden Shield, which has no ability of its own


def test_odds_resolution():
    s = se.ShieldEffectSettings()
    assert se.odds_for(0, s) == 0
    assert se.odds_for(31, s) == 12 and se.odds_for(32, s) == 25
    assert se.odds_for(36, s) == se.ALWAYS                       # Athena's never rolls
    assert se.odds_for(31, se.ShieldEffectSettings(effect_odds={31: 100})) == se.ALWAYS
    assert se.odds_for(32, se.ShieldEffectSettings(effect_odds={32: 10})) == 10
    assert se.odds_for(32, se.ShieldEffectSettings(always_proc=True, effect_odds={32: 10})) == se.ALWAYS


# -- the exe patch -----------------------------------------------------------------------------------------------------

@needs_exe
def test_patch_sites_and_helpers():
    capstone = pytest.importorskip("capstone")
    exe = Exe(Path(EXE).read_bytes())
    mod = HexMod()
    se.patch_shield_effects(exe, mod, {1: 20, 15: 31, 20: 0})
    patched = bytes(mod.apply(exe.data))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

    def dis(va, n):
        """The instructions up to and including the first ret."""
        o, out = foff(va), []
        for i in md.disasm(patched[o:o + n], va):
            out.append((i.mnemonic + " " + i.op_str).strip())
            if i.mnemonic == "ret":
                break
        return out

    # every patched site calls the right helper
    def call_target(va):
        o = foff(va)
        assert patched[o] == 0xE8
        return va + 5 + struct.unpack_from("<i", patched, o + 1)[0]
    assert call_target(se.ID_SITE_A) == rva_to_va(se.ID_HELPER_A)
    assert call_target(se.ID_SITE_B) == rva_to_va(se.ID_HELPER_B)
    assert call_target(se.ID_SITE_C) == rva_to_va(se.ID_HELPER_C)
    for eff in se.EFFECTS.values():
        if eff.roll_va:
            shape_b = eff.id in se._SHAPE_B
            assert call_target(eff.roll_va - (3 if shape_b else 2)) == rva_to_va(se.ODDS_HELPER_B if shape_b else se.ODDS_HELPER_A)

    # the id table
    table = patched[foff(rva_to_va(se.TABLE_RVA)):foff(rva_to_va(se.TABLE_RVA)) + 48]
    assert table[1] == 20 and table[15] == 31 and table[20] == 0 and table[21] == 21 and table[39] == 39

    # the helpers say what they should
    a = dis(rva_to_va(se.ID_HELPER_A), 0x20)
    assert a[:2] == ["movzx eax, byte ptr [rax + 0x148]", "push r11"] and a[2].startswith("lea r11, [rip")
    assert a[3:] == ["movzx eax, byte ptr [r11 + rax]", "pop r11", "ret"]
    oa = dis(rva_to_va(se.ODDS_HELPER_A), 0x20)
    assert oa == ["sub ecx, eax", "push rdx", "mov rdx, qword ptr [r8 + 0x98]", "movzx edx, byte ptr [rdx + 0x139]", "cmp cx, dx", "pop rdx", "ret"]
    ob = dis(rva_to_va(se.ODDS_HELPER_B), 0x20)
    assert ob == ["push rdx", "mov rdx, qword ptr [r8 + 0x98]", "movzx edx, byte ptr [rdx + 0x139]", "mov eax, r9d", "cmp cx, dx", "pop rdx", "ret"]
    c = dis(rva_to_va(se.ID_HELPER_C), 0x20)
    assert c[0] == "push rax" and c[-2:] == ["pop rax", "ret"] and "movzx r9d, byte ptr [rax + r9]" in c


@needs_exe
def test_patch_only_touches_the_expected_places():
    exe = Exe(Path(EXE).read_bytes())
    mod = HexMod()
    se.patch_shield_effects(exe, mod, {1: 20})
    patched = mod.apply(exe.data)
    changed = [i for i in range(len(exe.data)) if patched[i] != exe.data[i]]
    text_slack = range(foff(rva_to_va(se.TABLE_RVA)), foff(rva_to_va(se.CAVE_END)))
    sites = [foff(se.ID_SITE_A) + k for k in range(7)] + [foff(se.ID_SITE_B) + k for k in range(7)] + [foff(se.ID_SITE_C) + k for k in range(8)]
    for e in se.EFFECTS.values():
        if e.roll_va:
            sites += [foff(e.roll_va) - 3 + k for k in range(7)]
    allowed = set(text_slack) | set(sites) | {exe.text_header + 8 + k for k in range(4)}
    assert set(changed) <= allowed


# -- the data file -----------------------------------------------------------------------------------------------------

@needs_exe
@needs_dat
def test_end_to_end_shuffle_writes_chances_and_descriptions():
    game = GameFile(DAT)
    before = bytes(game.data)
    slots = se.description_slots(game.data)
    exe, mod = Exe(Path(EXE).read_bytes()), HexMod()
    settings = se.ShieldEffectSettings(mode="shuffle", always_proc=True)
    res = se.apply_shield_effects(game, exe, mod, settings, seed=42)

    assert len(game.data) == len(before)
    # every description kept its slot: the bytes outside the rewritten ones are untouched and each rewritten one still ends in one terminator
    for sid, (pos, size) in enumerate(slots, 1):
        if res.assignment[sid] == sid or (res.assignment[sid] == 0 and sid not in se.EFFECTS):
            if bytes(game.data[pos:pos + size]) != before[pos:pos + size]:
                assert res.odds[sid] != se.EFFECTS.get(sid, se.ShieldEffect(0, "", "", "", 0, None, False)).vanilla_odds
        assert game.data[pos + size - 1] == 0 and (size < 2 or game.data[pos + size - 2] != 0 or before[pos + size - 2] == 0)
    records = {r.id: r for r in read_table(game.data, se.shield_spec(game)).records}
    assert len(records) == 40
    for sid, eff in res.assignment.items():
        if eff and se.EFFECTS[eff].roll_va:
            assert records[sid].tail[0] == se.ALWAYS
        if eff == 0:
            assert records[sid].tail[0] == 0
    # stats and prices stay put
    old = {r.id: r for r in read_table(before, se.shield_spec(game)).records}
    for sid, r in records.items():
        assert r.tail[4:] == old[sid].tail[4:] and r.name == old[sid].name
    assert res.described > 0 and mod.edits


@needs_exe
@needs_dat
def test_unchanged_makes_no_patch():
    game = GameFile(DAT)
    before = bytes(game.data)
    mod = HexMod()
    res = se.apply_shield_effects(game, Exe(Path(EXE).read_bytes()), mod, se.ShieldEffectSettings(), seed=1)
    assert not mod.edits and bytes(game.data) == before and res.log == ["Shield effects: unchanged."]

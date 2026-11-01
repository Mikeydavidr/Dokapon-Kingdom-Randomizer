"""Weapon effects. The assignment checks need no game files; the patch and data checks need an UNMODIFIED DkkStm.exe (DKK_EXE) and
stageBase_EN.DAT (DKK_STAGEBASE) and are skipped otherwise."""
import os
import random
import sys
from pathlib import Path

import pytest

from dokapon_rando import effects_common as ec
from dokapon_rando import weapon_effects as we
from dokapon_rando.exe import Exe, HexMod
from dokapon_rando.gamefile import GameFile
from dokapon_rando.tables import read_table

EXE, DAT = os.environ.get("DKK_EXE"), os.environ.get("DKK_STAGEBASE")
needs_exe = pytest.mark.skipif(not EXE or not Path(EXE).exists(), reason="set DKK_EXE to an unmodified DkkStm.exe")
needs_dat = pytest.mark.skipif(not DAT or not Path(DAT).exists(), reason="set DKK_STAGEBASE to an unmodified stageBase_EN.DAT")


def test_vanilla_has_22_effects_on_22_weapons():
    v = we.vanilla_assignment()
    assert len(v) == 67 and sum(1 for c in v.values() if c != we.NO_EFFECT) == 22
    assert v[13] == 0 and v[67] == 21 and v[1] == we.NO_EFFECT


def test_shuffle_keeps_every_effect_and_moves_some():
    s = we.WeaponEffectSettings(mode="shuffle")
    moved = False
    for seed in range(10):
        a = ec.assign(we.vanilla_assignment(), list(we.EFFECTS), s, random.Random(seed), we.NO_EFFECT)
        assert sorted(c for c in a.values() if c != we.NO_EFFECT) == sorted(we.EFFECTS)
        moved |= a != we.vanilla_assignment()
    assert moved


def test_random_default_rate_is_the_original_share():
    s = we.WeaponEffectSettings(mode="random")
    counts = [sum(1 for c in ec.assign(we.vanilla_assignment(), list(we.EFFECTS), s, random.Random(i), we.NO_EFFECT).values()
                  if c != we.NO_EFFECT) for i in range(200)]
    assert abs(sum(counts) / len(counts) - 22) < 2


def test_follow_base_moves_effects_with_the_item():
    vanilla = {1: 10, 2: 0, 3: 0}
    now = ["B", "A", "C"]            # A and B swapped slots
    base = ec.follow_base(vanilla, now, ["A", "B", "C"], 0)
    assert base == {1: 0, 2: 10, 3: 0}
    assert ec.follow_base(vanilla, now, None, 0) == vanilla


def test_chance_precedence():
    s = we.WeaponEffectSettings
    assert we.odds_for(0, s()) == 12 and we.odds_for(11, s()) == ec.ALWAYS and we.odds_for(we.NO_EFFECT, s()) == 0
    assert we.odds_for(0, s(effect_odds={0: 40})) == 40
    assert we.odds_for(0, s(effect_odds={0: 40}, always_proc=True)) == ec.ALWAYS
    r = random.Random(1)
    got = {we.odds_for(0, s(odds_range=(5, 50)), r) for _ in range(50)}
    assert min(got) >= 5 and max(got) <= 50 and len(got) > 5
    assert we.odds_for(0, s(odds_range=(5, 50), effect_odds={0: 9}), random.Random(1)) == 9


@needs_exe
def test_patch_matches_the_verified_script_byte_for_byte():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "testpatch"))
    import patch_exe
    vanilla = Path(EXE).read_bytes()
    cases = we.vanilla_assignment()
    cases.update({1: 5, 2: 21, 40: 0, 67: we.NO_EFFECT})   # a few weapons moved
    reference = patch_exe.patch(bytearray(vanilla), [cases[w] for w in range(1, 68)])
    mod = HexMod()
    we.patch_weapon_effects(Exe(vanilla), mod, cases)
    assert bytes(mod.apply(vanilla)) == bytes(reference)


@needs_exe
def test_weapon_and_shield_patches_do_not_collide():
    from dokapon_rando import shield_effects as se
    exe = Exe(Path(EXE).read_bytes())
    mod = HexMod()
    we.patch_weapon_effects(exe, mod, we.vanilla_assignment())
    se.patch_shield_effects(exe, mod, {1: 20})     # raises if any edit overlaps another
    assert we.CAVE_END <= se.TABLE_RVA


@needs_exe
@needs_dat
def test_end_to_end_random_with_always_proc():
    game = GameFile(DAT)
    before = bytes(game.data)
    slots = we.description_slots(game.data)
    mod = HexMod()
    res = we.apply_weapon_effects(game, Exe(Path(EXE).read_bytes()), mod,
                                  we.WeaponEffectSettings(mode="random", always_proc=True, effect_rate=1.0), seed=3)
    assert len(game.data) == len(before) and mod.edits
    records = {r.id: r for r in read_table(game.data, we.weapon_spec(game)).records}
    old = {r.id: r for r in read_table(before, we.weapon_spec(game)).records}
    for wid, case in res.assignment.items():
        assert case != we.NO_EFFECT                        # rate 1.0: every weapon has one
        if we.EFFECTS[case].roll_va:
            assert records[wid].tail[2] == ec.ALWAYS
        # price, stats and names stay
        assert records[wid].name == old[wid].name and records[wid].tail[4:] == old[wid].tail[4:]
    for pos, size in slots:                                # every description keeps its slot and one terminator
        assert game.data[pos + size - 1] == 0
    assert res.described > 40


@needs_exe
@needs_dat
def test_unchanged_makes_no_patch():
    game = GameFile(DAT)
    before = bytes(game.data)
    mod = HexMod()
    res = we.apply_weapon_effects(game, Exe(Path(EXE).read_bytes()), mod, we.WeaponEffectSettings(), seed=1)
    assert not mod.edits and bytes(game.data) == before and res.log == ["Weapon effects: unchanged."]


@needs_exe
@needs_dat
def test_unchanged_after_an_equipment_shuffle_follows_the_weapon():
    from dokapon_rando.shuffle import shuffle_equipment
    game = GameFile(DAT)
    names0 = [r.name for r in read_table(game.data, we.weapon_spec(game)).records]
    shuffle_equipment(game, seed=11)
    mod = HexMod()
    res = we.apply_weapon_effects(game, Exe(Path(EXE).read_bytes()), mod, we.WeaponEffectSettings(), seed=1, original_names=names0)
    now = [r.name for r in read_table(game.data, we.weapon_spec(game)).records]
    v = we.vanilla_assignment()
    for slot, name in enumerate(now, 1):
        assert res.assignment[slot] == v[names0.index(name) + 1]
    assert mod.edits      # the slots changed owners, so the table must too

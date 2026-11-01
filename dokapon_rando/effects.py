"""Equipment effects as one step: weapons and shields, one hex mod.

The equipment shuffler (shuffle.py) moves item identities between slots; the effects step runs after it and, in its unchanged tier,
makes each effect follow its item. So pass the names as they were before the shuffle.
"""
from dataclasses import dataclass, field

from .exe import Exe, HexMod
from .gamefile import GameFile
from .shield_effects import ShieldEffectResult, ShieldEffectSettings, apply_shield_effects, shield_spec
from .tables import read_table
from .weapon_effects import WeaponEffectResult, WeaponEffectSettings, apply_weapon_effects, weapon_spec


@dataclass
class EffectsResult:
    mod: HexMod
    weapons: WeaponEffectResult | None = None
    shields: ShieldEffectResult | None = None

    @property
    def log(self) -> list[str]:
        return (self.weapons.log if self.weapons else []) + (self.shields.log if self.shields else [])


def equipment_names(game: GameFile) -> tuple[list[str], list[str]]:
    """(weapon names, shield names) in slot order: call before the equipment shuffle and keep the result."""
    return ([r.name for r in read_table(game.data, weapon_spec(game)).records],
            [r.name for r in read_table(game.data, shield_spec(game)).records])


def apply_effects(game: GameFile, exe_data: bytes, seed: int, weapons: WeaponEffectSettings | None = None,
                  shields: ShieldEffectSettings | None = None,
                  original_names: tuple[list[str], list[str]] | None = None) -> EffectsResult:
    """Run the weapon and shield effects. `weapons`/`shields` of None leave that kind alone (no patch for it)."""
    exe = Exe(exe_data)
    result = EffectsResult(HexMod())
    original_weapons, original_shields = original_names or (None, None)
    if weapons is not None:
        result.weapons = apply_weapon_effects(game, exe, result.mod, weapons, seed, original_weapons)
    if shields is not None:
        result.shields = apply_shield_effects(game, exe, result.mod, shields, seed, original_shields)
    return result

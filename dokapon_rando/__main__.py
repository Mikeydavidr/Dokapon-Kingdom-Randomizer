"""Command line: python -m dokapon_rando effects --dat stageBase_EN.DAT --exe DkkStm.exe --out Mods/MyMod [options]

Reads the UNMODIFIED data file and exe, and writes a ConnectModInstaller mod folder:
    <out>/Assets/stageBase_EN.DAT
    <out>/Hex/effects.hex          (only if an effect option needs the exe patched)
Each of --weapons and --shields takes a tier: unchanged, shuffle or random (see effects_common.py). Leave one out to not touch it.
"""
import argparse
from pathlib import Path

from .effects import apply_effects, equipment_names
from .effects_common import TierSettings
from .gamefile import FILE_NAME, GameFile
from .shield_effects import ShieldEffectSettings
from .shuffle import shuffle_equipment
from .weapon_effects import WeaponEffectSettings


def _ids(text: str) -> frozenset[int]:
    return frozenset(int(x) for x in text.split(",") if x)


def _pairs(text: str) -> dict[int, int]:
    return {int(k): int(v) for k, v in (p.split("=") for p in text.split(",") if p)}


def _range(text: str) -> tuple[int, int] | None:
    return tuple(int(x) for x in text.split("-")) if text else None   # type: ignore[return-value]


def add_kind_options(ap: argparse.ArgumentParser, kind: str, ids: str, effects: str) -> None:
    g = ap.add_argument_group(kind)
    g.add_argument(f"--{kind}", choices=["unchanged", "shuffle", "random"], default=None, help=f"tier for {kind} effects")
    g.add_argument(f"--{kind}-pin", default="", help=f"{kind} ids that keep their effect, e.g. {ids}")
    g.add_argument(f"--{kind}-odds", default="", help=f"percent per effect, e.g. {effects}")
    g.add_argument(f"--{kind}-rate", type=float, default=None, help="random tier: chance an item gets any effect")
    g.add_argument(f"--{kind}-always-proc", action="store_true", help="every effect with a roll procs every time")
    g.add_argument(f"--{kind}-odds-range", default="", help="random odds per item, e.g. 5-50")


def settings_for(args: argparse.Namespace, kind: str, cls: type[TierSettings]) -> TierSettings | None:
    mode = getattr(args, kind)
    if mode is None:
        return None
    k = kind
    return cls(mode=mode, pinned=_ids(getattr(args, f"{k}_pin")), effect_odds=_pairs(getattr(args, f"{k}_odds")),
               effect_rate=getattr(args, f"{k}_rate"), always_proc=getattr(args, f"{k}_always_proc"),
               odds_range=_range(getattr(args, f"{k}_odds_range")))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dokapon_rando")
    sub = ap.add_subparsers(dest="command", required=True)
    ef = sub.add_parser("effects", help="move weapon and shield effects around and set their odds")
    ef.add_argument("--dat", required=True, help="an unmodified stageBase_EN.DAT")
    ef.add_argument("--exe", required=True, help="an unmodified DkkStm.exe")
    ef.add_argument("--out", required=True, help="the mod folder to write")
    ef.add_argument("--seed", type=int, default=0)
    ef.add_argument("--shuffle-equipment", action="store_true", help="also shuffle which weapon/shield/accessory sits in which slot first")
    add_kind_options(ef, "weapons", "13,67", "0=100,9=2")
    add_kind_options(ef, "shields", "32,38", "31=100,32=10")
    args = ap.parse_args(argv)

    game = GameFile(args.dat)
    original = equipment_names(game)
    if args.shuffle_equipment:
        shuffle_equipment(game, args.seed)
    result = apply_effects(game, Path(args.exe).read_bytes(), args.seed,
                           settings_for(args, "weapons", WeaponEffectSettings), settings_for(args, "shields", ShieldEffectSettings), original)
    for line in result.log:
        print(line)

    out = Path(args.out)
    (out / "Assets").mkdir(parents=True, exist_ok=True)
    game.save(out / "Assets" / FILE_NAME)
    if result.mod.edits:
        print("wrote", result.mod.write(out / "Hex" / "effects.hex"))
    print(f"rewrote {(result.weapons.described if result.weapons else 0)} weapon and "
          f"{(result.shields.described if result.shields else 0)} shield descriptions")


if __name__ == "__main__":
    main()

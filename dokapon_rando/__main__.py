"""Command line: python -m dokapon_rando shield-effects --dat stageBase_EN.DAT --exe DkkStm.exe --out Mods/MyMod [options]

Reads the UNMODIFIED data file and exe, and writes a ConnectModInstaller mod folder:
    <out>/Assets/stageBase_EN.DAT
    <out>/Hex/shield_effects.hex
"""
import argparse
from pathlib import Path

from .exe import Exe, HexMod
from .gamefile import FILE_NAME, GameFile
from .shield_effects import ShieldEffectSettings, apply_shield_effects


def _ids(text: str) -> frozenset[int]:
    return frozenset(int(x) for x in text.split(",") if x)


def _pairs(text: str) -> dict[int, int]:
    return {int(k): int(v) for k, v in (p.split("=") for p in text.split(",") if p)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="dokapon_rando")
    sub = ap.add_subparsers(dest="command", required=True)
    sh = sub.add_parser("shield-effects", help="move shield effects and set their odds")
    sh.add_argument("--dat", required=True, help="an unmodified stageBase_EN.DAT")
    sh.add_argument("--exe", required=True, help="an unmodified DkkStm.exe")
    sh.add_argument("--out", required=True, help="the mod folder to write")
    sh.add_argument("--mode", choices=["unchanged", "shuffle", "random"], default="shuffle")
    sh.add_argument("--seed", type=int, default=0)
    sh.add_argument("--pin", default="", help="shield ids that keep their own effect, e.g. 32,38")
    sh.add_argument("--odds", default="", help="percent per effect id, e.g. 31=100,32=10")
    sh.add_argument("--rate", type=float, default=None, help="random mode: chance a shield gets any effect")
    sh.add_argument("--always-proc", action="store_true", help="every effect with a roll procs every time")
    args = ap.parse_args(argv)

    out = Path(args.out)
    game = GameFile(args.dat)
    settings = ShieldEffectSettings(mode=args.mode, pinned=_ids(args.pin), effect_odds=_pairs(args.odds),
                                    effect_rate=args.rate, always_proc=args.always_proc)
    mod = HexMod()
    result = apply_shield_effects(game, Exe(Path(args.exe).read_bytes()), mod, settings, args.seed)
    for line in result.log:
        print(line)
    (out / "Assets").mkdir(parents=True, exist_ok=True)
    game.save(out / "Assets" / FILE_NAME)
    if mod.edits:
        print("wrote", mod.write(out / "Hex" / "shield_effects.hex"))
    print(f"rewrote {result.described} shield descriptions")


if __name__ == "__main__":
    main()

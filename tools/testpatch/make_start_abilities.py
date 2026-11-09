"""Build a hex mod that starts every human player with Rust (battle magic) and Waterfall (skill), to test how equipment breaks.

usage: python make_start_abilities.py <mod folder> [vanilla DkkStm.exe] [--spell ID] [--skill ID] [--no-spell] [--no-skill]
Writes <mod>/Hex/start_abilities.hex. Defaults: Rust (23), Waterfall (38). Install with Connect Mod Installer like the other hex mods.
Untested in play; see dokapon_rando/start_abilities.py for what it assumes.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dokapon_rando.exe import Exe, HexMod
from dokapon_rando.start_abilities import RUST, WATERFALL, apply_start_abilities

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("exe", nargs="?", default=r"G:\Programming\Dokapon-Workspace\ActualGame\DkkStm.exe")
ap.add_argument("--spell", type=int, default=RUST)
ap.add_argument("--skill", type=int, default=WATERFALL)
ap.add_argument("--no-spell", action="store_true")
ap.add_argument("--no-skill", action="store_true")
a = ap.parse_args()
mod = HexMod()
apply_start_abilities(Exe(Path(a.exe).read_bytes()), mod, None if a.no_spell else a.spell, None if a.no_skill else a.skill)
out = mod.write(Path(a.mod) / "Hex" / "start_abilities.hex")
print(f"wrote {out} ({len(mod.edits)} edits)")

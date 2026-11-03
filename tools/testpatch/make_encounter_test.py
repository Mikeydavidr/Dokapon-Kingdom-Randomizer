"""Encounter test: every empty space of one area of board 0 meets one monster from its first table and another from its second,
to see in game that the space's tables pick the monsters (sea spaces included) and when the game uses the second table.

usage: python make_encounter_test.py <mod folder> [--area A] [--first NAME] [--second NAME] [--base <mod Assets>] [--assets <folder>]
  Tables 0x70 and 0x71 (placeholders no space uses) become one-monster tables, and every empty space (plain, forest, ocean,
  ...) of area A (0 = the starting area) points at 0x70 first and 0x71 second.
  --near SPACE: instead, the empty spaces within --steps links of SPACE use table 0x72 for both, a long list (--long-copies
  of each --long monster, in that order) too big for the lists' own space, so it goes past the old end of the data: seeing
  the last monster in game means the game read all of it.
  Writes stageBase_EN.DAT and stg000_EN.DAT to <mod>/Assets (read from --base if given, so they can go on top of another mod)
  and <mod>/encounter_log.txt.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from boardlib import load_board
from encounters import KINDS, Encounters

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("--area", type=int, default=0)
ap.add_argument("--first", default="Skeleton")
ap.add_argument("--second", default="Bat")
ap.add_argument("--near", type=int, default=None)
ap.add_argument("--steps", type=int, default=3)
ap.add_argument("--long", default="Zombie,Gremlin")
ap.add_argument("--long-copies", type=int, default=100)
ap.add_argument("--base", default=None)
ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
args = ap.parse_args()
mod = Path(args.mod)
FIRST, SECOND, LONG = 0x70, 0x71, 0x72

enc = Encounters(Path(args.assets), Path(args.base) if args.base else None)
first, second = enc.monster_id(args.first), enc.monster_id(args.second)
enc.tables[FIRST], enc.tables[SECOND] = [first], [second]
log = [f"table 0x{FIRST:02x} = {enc.label[first]}, table 0x{SECOND:02x} = {enc.label[second]}"]
near = set()
if args.near is not None:
    links = load_board(Path(args.assets), 0)[1]
    near, edge = {args.near}, {args.near}
    for _ in range(args.steps):
        edge = {b for a in edge for b in links[a]} - near
        near |= edge
    longs = [enc.monster_id(m) for m in args.long.split(",")]
    enc.tables[LONG] = [m for m in longs for _ in range(args.long_copies)]
    log.append(f"table 0x{LONG:02x} = " + ", then ".join(f"{enc.label[m]} x{args.long_copies}" for m in longs)
               + f" ({len(enc.tables[LONG]) + 1} bytes)")
for s in enc.spaces[0]:
    if s["id"] in near:
        old = enc.space_tables(0, s)
        enc.set_space_tables(0, s["id"], LONG, LONG)
        log.append(f"space {s['id']} ({KINDS[s['kind']]}): tables 0x{old[0]:02x} / 0x{old[1]:02x} -> 0x{LONG:02x} / 0x{LONG:02x}")
    elif s["area"] == args.area:
        old = enc.space_tables(0, s)
        enc.set_space_tables(0, s["id"], FIRST, SECOND)
        log.append(f"space {s['id']} ({KINDS[s['kind']]}): tables 0x{old[0]:02x} / 0x{old[1]:02x} -> 0x{FIRST:02x} / 0x{SECOND:02x}")
for p in enc.save(mod / "Assets"):
    log.append(f"wrote {p}")
(mod / "encounter_log.txt").write_text("\n".join(log) + "\n")
print("\n".join(log))

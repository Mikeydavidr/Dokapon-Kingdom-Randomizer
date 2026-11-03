"""Swap stores and castles completely: the space records, their signs, and the whole art unit (building, shadow, decor).

usage: python make_unit_swap.py <mod folder> <a>-<b>[,<c>-<d>...] [assets folder]
Writes <mod>/Assets/stg000_EN.DAT and the F00_*.model files the moves touch. Both spaces of a pair must be units in
tools/boardview/board0_buildings.json. Each unit moves by the difference between the two spaces' positions, so it keeps its
own offset from its space and lands on the target's ground height.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from boardlib import load_board
from stage import Stage
from units import Art, load_units

mod = Path(sys.argv[1])
pairs = [tuple(int(v) for v in p.split("-")) for p in sys.argv[2].split(",")]
assets = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("G:/Programming/Dokapon-Workspace/assets")
spaces, _ = load_board(assets, 0)
byid = {s["id"]: s for s in spaces}
units = load_units()
art, stage = Art(assets), Stage(assets)
stage.move({x: y for a, b in pairs for x, y in ((a, b), (b, a))})
for a, b in pairs:
    for x, y in ((a, b), (b, a)):
        offset = tuple(byid[y]["pos"][k] - byid[x]["pos"][k] for k in range(3))
        print(f"{units[x]['kind']} {x} -> space {y}, offset {tuple(round(v) for v in offset)}")
        for line in art.move(units[x], offset, label=str(x)):
            print("   ", line)
out = mod / "Assets"
stage.save(out)
for path in art.save(out):
    print("wrote", path.name)

"""Art hide probe: shrinks transform matrices to nothing so the objects they place disappear, to find which matrix is which building.

usage: python make_art_hide.py <mod folder> [assets folder]
Hides the F00_M and F00_N matrices whose translation lands within 30 units of a store, town or castle space (N matrix 35 is
skipped, it is the grass patch found earlier). The translation is kept; only the 3x3 part is zeroed.
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel
from boardlib import load_board

mod = Path(sys.argv[1])
assets = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("G:/Programming/Dokapon-Workspace/assets")
spaces, _ = load_board(assets, 0)
special = [s for s in spaces if s["type"][0] in (0x14, 0x15, 0x16, 0x17, 0x18)]
(mod / "Assets").mkdir(parents=True, exist_ok=True)

for kind, skip in (("M", set()), ("N", {35})):
    src = assets / "CommonData" / "dataField" / "F00" / f"F00_{kind}.model"
    m = igbmodel.load(src)
    data = bytearray(m.data)
    base, _ = m.chunk("MTRX")
    for i, mat in enumerate(m.matrices()):
        near = min(special, key=lambda s: math.dist((mat[12], mat[14]), (s["pos"][0], s["pos"][2])))
        d = math.dist((mat[12], mat[14]), (near["pos"][0], near["pos"][2]))
        if d < 30 and i not in skip:
            struct.pack_into("<12f", data, base + 64 * i, *([0.0] * 12))
            print(f"F00_{kind} matrix {i} hidden: at ({mat[12]:.0f}, {mat[14]:.0f}), space {near['id']} ({near['type'][0]:#x}) {d:.0f} away")
    (mod / "Assets" / src.name).write_bytes(data)

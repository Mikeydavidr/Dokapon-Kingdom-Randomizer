"""Art probe: lifts a few transform matrices in the board 0 art files so the game shows which objects they move.

usage: python make_art_probe.py <mod folder> [assets folder]
Writes <mod>/Assets/F00_N.model, F00_M.model and F00_A.model (flat names, the installer matches them inside the CPK).
Each probe adds LIFT to the y translation of one matrix, chosen because its translation lands next to a town or shop node:
  F00_N matrix 35  next to town space 325 (dist 11)
  F00_M matrix 44  next to Magic Store space 268 (dist 25)
  F00_A matrix 7   next to town space 89 (dist 1)
Anything that floats 60 units above the board after this is what the matrix places.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

LIFT = 60.0
PROBES = {"N": [35], "M": [44], "A": [7]}

mod = Path(sys.argv[1])
assets = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("G:/Programming/Dokapon-Workspace/assets")
(mod / "Assets").mkdir(parents=True, exist_ok=True)

for kind, indices in PROBES.items():
    src = assets / "CommonData" / "dataField" / "F00" / f"F00_{kind}.model"
    m = igbmodel.load(src)
    data = bytearray(m.data)
    base, _ = m.chunk("MTRX")
    for i in indices:
        o = base + 64 * i + 48 + 4            # row 4 of the matrix is the translation; +4 is its y
        y = struct.unpack_from("<f", data, o)[0]
        struct.pack_into("<f", data, o, y + LIFT)
        print(f"F00_{kind} matrix {i}: y {y:.1f} -> {y + LIFT:.1f}")
    (mod / "Assets" / src.name).write_bytes(data)

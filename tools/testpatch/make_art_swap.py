"""Art swap: moves buildings between spaces by rewriting the translation of their transform matrices in F00_M or F00_N.

usage: python make_art_swap.py <mod folder> <M|N> <matrix:space>-<matrix:space>[,...] [assets folder]
Each pair names a building by its matrix and the space it belongs to; the two buildings trade places. A building keeps its
own offset from its space (so it lands on the target's ground height), rotation and scale.
Matrix to building (found with make_art_hide.py): F00_M 24 castle 170, 43 magic 87, 5 magic 152, 44 magic 268, 20 item 122,
2 item 218, 45 item 237;  F00_N 1 castle 76, 37 castle 311, 46 item 18, 14 item 59, 32 magic 287, 33 item 314.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel
from boardlib import load_board

mod, kind = Path(sys.argv[1]), sys.argv[2]
pairs = [tuple(tuple(int(v) for v in side.split(":")) for side in p.split("-")) for p in sys.argv[3].split(",")]
assets = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("G:/Programming/Dokapon-Workspace/assets")
spaces, _ = load_board(assets, 0)
node = {s["id"]: s["pos"] for s in spaces}
src = assets / "CommonData" / "dataField" / "F00" / f"F00_{kind}.model"
m = igbmodel.load(src)
data = bytearray(m.data)
base, _ = m.chunk("MTRX")


def put(matrix: int, space_from: int, space_to: int) -> None:
    o = base + 64 * matrix + 48
    t = struct.unpack_from("<3f", data, o)
    offset = [t[i] - node[space_from][i] for i in range(3)]
    new = [node[space_to][i] + offset[i] for i in range(3)]
    struct.pack_into("<3f", data, o, *new)
    print(f"F00_{kind} matrix {matrix}: space {space_from} -> {space_to}, offset {tuple(round(v) for v in offset)}, "
          f"at {tuple(round(v) for v in new)}")


for (ma, sa), (mb, sb) in pairs:
    put(ma, sa, sb)
    put(mb, sb, sa)
(mod / "Assets").mkdir(parents=True, exist_ok=True)
(mod / "Assets" / src.name).write_bytes(data)

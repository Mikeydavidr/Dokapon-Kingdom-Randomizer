"""Shift every vertex of chosen mesh pieces of a board model file, to find which piece draws which object.

usage: python make_mesh_shift.py <mod folder> <M|N|A|...> <mesh>:<dx>,<dy>,<dz> [<mesh>:<dx>,<dy>,<dz> ...] [--from <folder>]
Reads the file from <mod folder>/Assets if it is already there (so shifts add up across calls), else from the game assets,
and writes <mod folder>/Assets/F00_<kind>.model.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

mod, kind = Path(sys.argv[1]), sys.argv[2]
edits = [a for a in sys.argv[3:] if ":" in a]
staged = mod / "Assets" / f"F00_{kind}.model"
src = staged if staged.exists() else Path("G:/Programming/Dokapon-Workspace/assets/CommonData/dataField/F00") / f"F00_{kind}.model"
m = igbmodel.load(src)
data = bytearray(m.data)
vo, _ = m.chunk("VERT")
for e in edits:
    gi, shift = e.split(":")
    dx, dy, dz = (float(v) for v in shift.split(","))
    g = m.geoms[int(gi)]
    for i in range(g.verts):
        o = vo + g.vert_offset + i * g.stride
        x, y, z = struct.unpack_from("<3f", data, o)
        struct.pack_into("<3f", data, o, x + dx, y + dy, z + dz)
    print(f"F00_{kind} mesh {gi}: shifted {g.verts} vertices by ({dx}, {dy}, {dz})")
(mod / "Assets").mkdir(parents=True, exist_ok=True)
staged.write_bytes(data)

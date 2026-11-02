"""Shadow probe: hides chosen matrices (and flat world pieces) to find which ones are the baked shadows.

usage: python make_shadow_probe.py <mod folder> [--a=0,109] [--m=24] [--n=...] [--geom=A:18] [--assets=folder]
  --a / --m / --n   matrix indices (or all) to zero (translation kept) in F00_A / F00_M / F00_N
  --geom=A:18       (A:all = every piece) collapse a world-positioned piece to a point (for pieces with baked positions)
Reads F00_M from <mod folder>/Assets if it is there (so building swaps made earlier are kept), else from the game assets.
Matrices tried so far: F00_A 57 shadow of 268, 142 of 76, 191 of 246, 47/60 of 260, 133/138/193 near 69, geom 18 of 218;
0 (near 152), 109/173 (near 59) and 56 (near 87) are not confirmed.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

mod = Path(sys.argv[1])
opts = {a.split("=")[0][2:]: a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--")}
assets = Path(opts.get("assets", "G:/Programming/Dokapon-Workspace/assets"))
(mod / "Assets").mkdir(parents=True, exist_ok=True)

for kind in "AMN":
    staged = mod / "Assets" / f"F00_{kind}.model"
    m = igbmodel.load(staged if staged.exists() else assets / "CommonData" / "dataField" / "F00" / f"F00_{kind}.model")
    if opts.get(kind.lower()) == "all":                 # --a=all: every matrix
        hide = list(range(len(m.matrices())))
    else:
        hide = [int(v) for v in opts.get(kind.lower(), "").split(",") if v]
    collapse = [int(g.split(":")[1]) for g in opts.get("geom", "").split(",") if g.startswith(kind + ":") and g[2:] != "all"]
    if f"{kind}:all" in opts.get("geom", ""):           # --geom=A:all: every piece (also the world-positioned ones)
        collapse = list(range(len(m.geoms)))
    if not hide and not collapse:
        continue
    data = bytearray(m.data)
    base, _ = m.chunk("MTRX")
    for i in hide:
        struct.pack_into("<12f", data, base + 64 * i, *([0.0] * 12))
        pass
    vo, _ = m.chunk("VERT")
    for gi in collapse:
        g = m.geoms[gi]
        first = struct.unpack_from("<3f", data, vo + g.vert_offset)
        for i in range(g.verts):
            struct.pack_into("<3f", data, vo + g.vert_offset + g.stride * i, *first)
        print(f"F00_{kind} geom {gi} collapsed")
    staged.write_bytes(data)
    print(f"F00_{kind}: {len(hide)} matrices hidden, {len(collapse)} pieces collapsed")

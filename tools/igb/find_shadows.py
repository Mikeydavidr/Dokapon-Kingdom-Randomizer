"""List flat vertex clusters (shadow candidates) near each known building of board 0.

usage: python find_shadows.py [radius]
A building is a (file, matrix) pair whose translation is where the building stands. A cluster is a set of vertices connected by
triangles in one mesh piece; it counts as shadow-like when its height range is under 10 units (shadows lie on sloped ground). Clusters are listed by distance.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel as im
from boardlib import load_board

ASSETS = Path("G:/Programming/Dokapon-Workspace/assets")
radius = float(sys.argv[1]) if len(sys.argv) > 1 else 28
BUILDINGS = {   # space: (file, matrix)  from the hide tests
    170: ("M", 24), 87: ("M", 43), 152: ("M", 5), 268: ("M", 44), 122: ("M", 20), 218: ("M", 2), 237: ("M", 45),
    76: ("N", 1), 311: ("N", 37), 18: ("N", 46), 59: ("N", 14), 287: ("N", 32), 314: ("N", 33), 69: ("N", 15),
    "69b": ("N", 27), 260: ("A", 47), "260b": ("A", 60), 246: ("A", 191), 123: ("A", 142),
}
models = {k: im.load(ASSETS / "CommonData" / "dataField" / "F00" / f"F00_{k}.model") for k in ("A", "M", "N", "wood", "Anim1", "Anim2")}


def clusters(m, g):
    pos, tris = im.mesh(m, g)
    parent = list(range(len(pos)))

    def root(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for t in tris:
        for v in t[1:]:
            parent[root(v)] = root(t[0])
    groups = {}
    for i in range(len(pos)):
        groups.setdefault(root(i), []).append(i)
    for vs in groups.values():
        xs, ys, zs = [pos[i][0] for i in vs], [pos[i][1] for i in vs], [pos[i][2] for i in vs]
        yield vs, ((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2), max(xs) - min(xs), max(zs) - min(zs), max(ys) - min(ys)


index = []   # every flat world-positioned cluster of every file, computed once
for kind, m in models.items():
    for gi, g in enumerate(m.geoms):
        for vs, c, w, d, h in clusters(m, g):
            if h < 10 and 6 < max(w, d) < 90 and len(vs) <= 40 and abs(c[0]) + abs(c[1]) > 60:
                index.append((kind, gi, len(vs), c, w, d, h, vs[0]))
print(f"{len(index)} flat clusters in total")
for sid, (kind, mi) in BUILDINGS.items():
    t = models[kind].matrices()[mi]
    where = (t[12], t[14])
    cands = sorted(((math.dist(c, where), k, gi, n, c, w, d) for k, gi, n, c, w, d, h, v0 in index if math.dist(c, where) <= radius))
    print(f"space {sid} building {kind}{mi} at ({where[0]:.0f}, {where[1]:.0f}):")
    for dist, k, gi, n, c, w, d in cands[:5]:
        print(f"    {k} mesh {gi} cluster of {n} vertices at ({c[0]:.0f}, {c[1]:.0f}) {w:.0f}x{d:.0f}, {dist:.0f} away")

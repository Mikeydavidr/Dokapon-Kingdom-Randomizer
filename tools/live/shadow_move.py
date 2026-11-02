"""Move ONE connected cluster of vertices of a mesh piece in the RUNNING game (for example a single shadow in a shared batch).

usage: python shadow_move.py <pid> <F00_X.model as the game loaded it> <geom index> <x> <z> <dx> <dz> [dy] [--weld] [--radius R] [--minh H] [--dry] [--at DX,DY,DZ]
  --radius R moves EVERY cluster whose centre is within R of (x, z) instead of the nearest one (a building is several clusters); --minh H skips clusters lower than H, such as the shadow.
  --weld joins vertices that share a position, for buildings whose faces each carry their own copy of the vertices (shadows do not need it). dy lifts the cluster.
(x, z) are ORIGINAL coordinates, as in the model file, even for a cluster that was moved earlier. The cluster is the set of vertices connected through triangles whose bounding box is centred nearest to (x, z). The shift (dx, dy, dz) is
measured from the ORIGINAL positions in the file, so repeating a call does not add up and a shift of 0 0 0 puts the cluster back exactly. --dry only
shows which vertices would be picked. --at DX,DY,DZ says what shift is applied to the cluster right now (default 0,0,0): it is needed to find a mesh whose
selected vertices were all moved, since the search matches on the mesh as it currently is in memory.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

pid, path, gi = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
VALUE_FLAGS = ("--radius", "--minh", "--at")
args_, skip = [], False
for a in sys.argv[4:]:                          # positional numbers: x z dx dz [dy]; flags and their values are skipped
    if skip:
        skip = False
    elif a in VALUE_FLAGS:
        skip = True
    elif not a.startswith("--"):
        args_.append(a)
weld_on = "--weld" in sys.argv
radius = float(sys.argv[sys.argv.index("--radius") + 1]) if "--radius" in sys.argv else None
minh = float(sys.argv[sys.argv.index("--minh") + 1]) if "--minh" in sys.argv else 0.0
cx, cz, dx, dz = (float(v) for v in args_[:4])
dy = float(args_[4]) if len(args_) > 4 else 0.0
m = igbmodel.load(path)
g = m.geoms[gi]
pos, tris = igbmodel.mesh(m, g)
parent = list(range(len(pos)))


def root(x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


weld = list(range(len(pos)))
if weld_on:
    seen = {}
    weld = [seen.setdefault((round(p[0], 1), round(p[1], 1), round(p[2], 1)), i) for i, p in enumerate(pos)]
for t in tris:
    for v in t:
        parent[root(v)] = root(weld[v])
    for v in t[1:]:
        parent[root(v)] = root(t[0])
groups: dict[int, list[int]] = {}
for i in range(len(pos)):
    groups.setdefault(root(i), []).append(i)


def centre(vs):
    xs, zs = [pos[i][0] for i in vs], [pos[i][2] for i in vs]
    return (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2


if radius is None:
    best = min(groups.values(), key=lambda vs: (centre(vs)[0] - cx) ** 2 + (centre(vs)[1] - cz) ** 2)
else:
    chosen = [vs for vs in groups.values()
              if ((centre(vs)[0] - cx) ** 2 + (centre(vs)[1] - cz) ** 2) ** 0.5 <= radius
              and max(pos[i][1] for i in vs) - min(pos[i][1] for i in vs) >= minh]
    best = sorted(i for vs in chosen for i in vs)
    print(f"{len(chosen)} clusters")
print(f"cluster of {len(best)} vertices centred at {tuple(round(v) for v in centre(best))}, vertices {best[:12]}{'...' if len(best) > 12 else ''}")
if "--dry" in sys.argv:
    sys.exit()

vo, _ = m.chunk("VERT")
block = bytes(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])
at = tuple(float(v) for v in sys.argv[sys.argv.index("--at") + 1].split(",")) if "--at" in sys.argv else (0.0, 0.0, 0.0)
current = bytearray(block)                          # the mesh as it is in memory now
for i in best:
    x, y, z = struct.unpack_from("<3f", block, i * g.stride)
    struct.pack_into("<3f", current, i * g.stride, x + at[0], y + at[1], z + at[2])
current = bytes(current)
# The mesh is located by short runs of vertices spread over the whole mesh; at least two runs must agree on where it starts, so a
# cluster moved earlier (which spoils only the runs it touches) does not hide the mesh.
RUN = 4
spots = list(range(0, max(1, g.verts - RUN + 1), max(1, (g.verts - RUN) // 8 or 1)))[:9]
needles = {current[lo * g.stride:(lo + RUN) * g.stride]: lo for lo in spots if lo + RUN <= g.verts}
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0438, False, pid)
a, mbi, votes = 0, MBI(), {}
need = min(len(nd) for nd in needles)
while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
    b, s = mbi.Base or 0, mbi.Size
    if mbi.State == 0x1000 and mbi.Protect & 0x04 and s >= need:
        buf = ctypes.create_string_buffer(s)
        n = ctypes.c_size_t()
        k.ReadProcessMemory(h, ctypes.c_void_p(b), buf, s, ctypes.byref(n))
        d = buf.raw[:n.value]
        for nd, lo in needles.items():
            p = 0
            while (p := d.find(nd, p)) != -1:
                votes[b + p - lo * g.stride] = votes.get(b + p - lo * g.stride, 0) + 1
                p += 1
    a = b + s
    if a <= b:
        break
found = [addr for addr, v in votes.items() if v >= min(2, len(needles))]
print(f"mesh found {len(found)}x in memory")
for base in found:
    for i in best:
        x, y, z = struct.unpack_from("<3f", block, i * g.stride)       # the original position, so repeated calls do not add up
        k.WriteProcessMemory(h, ctypes.c_void_p(base + i * g.stride), struct.pack("<3f", x + dx, y + dy, z + dz), 12, ctypes.byref(ctypes.c_size_t()))
print(f"shifted by ({dx}, {dy}, {dz}) from the original")

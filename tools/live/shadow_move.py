"""Move ONE connected cluster of vertices of a mesh piece in the RUNNING game (for example a single shadow in a shared batch).

usage: python shadow_move.py <pid> <F00_X.model as the game loaded it> <geom index> <x> <z> <dx> <dz>
(x, z) are ORIGINAL coordinates, as in the model file, even for a cluster that was moved earlier. The cluster is the set of vertices connected through triangles whose bounding box is centred nearest to (x, z). Its positions are
shifted by (dx, dz) in memory; use dx = dz = 0 to just see which cluster would be picked. Moves add to what is in memory now, so the opposite shift undoes a move.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

pid, path, gi = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
cx, cz, dx, dz = (float(v) for v in sys.argv[4:8])
m = igbmodel.load(path)
g = m.geoms[gi]
pos, tris = igbmodel.mesh(m, g)
parent = list(range(len(pos)))


def root(x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


for t in tris:
    for v in t[1:]:
        parent[root(v)] = root(t[0])
groups: dict[int, list[int]] = {}
for i in range(len(pos)):
    groups.setdefault(root(i), []).append(i)


def centre(vs):
    xs, zs = [pos[i][0] for i in vs], [pos[i][2] for i in vs]
    return (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2


best = min(groups.values(), key=lambda vs: (centre(vs)[0] - cx) ** 2 + (centre(vs)[1] - cz) ** 2)
print(f"cluster of {len(best)} vertices centred at {tuple(round(v) for v in centre(best))}, vertices {best}")
if dx == 0 and dz == 0:
    sys.exit()

vo, _ = m.chunk("VERT")
block = bytes(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])
# the mesh is located by several short runs of vertices outside the cluster: an earlier move of another cluster in the same mesh then
# only spoils the runs it touches
inside = set(best)
needles: dict[bytes, int] = {}
free = [lo for lo in range(0, g.verts - 12, 6) if not any(v in inside for v in range(lo, lo + 12))]
for lo in free[:: max(1, len(free) // 6)][:6]:                 # at most six runs, spread over the mesh
    needles[block[lo * g.stride:(lo + 12) * g.stride]] = lo
if not needles:                                   # a small mesh: search for the whole block, as it is, or as it would be if this very move undoes an earlier one
    needles[block] = 0
    shifted = bytearray(block)
    for i in best:
        x, y, z = struct.unpack_from("<3f", block, i * g.stride)
        struct.pack_into("<3f", shifted, i * g.stride, x - dx, y, z - dz)
    needles[bytes(shifted)] = 0
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
while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
    b, s = mbi.Base or 0, mbi.Size
    if mbi.State == 0x1000 and mbi.Protect & 0x04 and s >= min(len(nd) for nd in needles):
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
found = [addr for addr, v in votes.items() if v >= (1 if len(needles) <= 2 else 2)]       # two independent runs agree on where the mesh starts
print(f"mesh found {len(found)}x in memory")
for base in found:
    for i in best:
        addr = base + i * g.stride
        cur = ctypes.create_string_buffer(12)
        k.ReadProcessMemory(h, ctypes.c_void_p(addr), cur, 12, ctypes.byref(ctypes.c_size_t()))
        x, y, z = struct.unpack("<3f", cur.raw)
        k.WriteProcessMemory(h, ctypes.c_void_p(addr), struct.pack("<3f", x + dx, y, z + dz), 12, ctypes.byref(ctypes.c_size_t()))
print(f"moved by ({dx}, {dz})")

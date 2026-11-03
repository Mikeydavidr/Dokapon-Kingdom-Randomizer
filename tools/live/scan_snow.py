"""Find the falling snow over the snowy island in the RUNNING game: the flakes are positions that drop between two looks.

usage: python scan_snow.py <pid> [--box x0,z0,x1,z1] [--wait seconds]
Read-only. Have the game on the board with the snowy island (Sermitsiaq, Strom Castle) on screen. Every float triple (x, y, z)
with x/z inside the box (default: the island, vanilla and spread out) and y 0-400 is noted, then read again after the wait;
the ones whose x and z stay put while y drops are flakes. Prints how many, the area they cover (min/max x, z, y), where they
sit in memory (first address and spacing) and the 256 bytes before the first one (an emitter header may hold the centre).
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import struct
import time

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("pid", type=int)
ap.add_argument("--box", default="-80,100,320,460")
ap.add_argument("--wait", type=float, default=0.3)
args = ap.parse_args()
x0, z0, x1, z1 = (float(v) for v in args.box.split(","))

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0410, False, args.pid)          # query + read only


def read(addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    k.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value]


def candidates(d: bytes) -> np.ndarray:
    """Float indices i where (f[i], f[i+1], f[i+2]) could be a flake."""
    f = np.frombuffer(d[:len(d) // 4 * 4], dtype="<f4")
    if len(f) < 3:
        return np.zeros(0, int)
    x, y, z = f[:-2], f[1:-1], f[2:]
    with np.errstate(invalid="ignore"):
        ok = (x > x0) & (x < x1) & (z > z0) & (z < z1) & (y > 0) & (y < 400) & (np.abs(x) > 0.5) & (np.abs(z) > 0.5)
    return np.nonzero(ok)[0]


regions, a, mbi = [], 0, MBI()
while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
    b, s = mbi.Base or 0, mbi.Size
    if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and s < 1 << 30:      # committed, read-write
        regions.append((b, s))
    a = b + s
    if a <= b:
        break

flakes = []
for b, s in regions:
    first = read(b, s)
    idx = candidates(first)
    if not len(idx):
        continue
    time.sleep(args.wait)
    second = read(b, s)
    f1 = np.frombuffer(first[:len(first) // 4 * 4], dtype="<f4")
    f2 = np.frombuffer(second[:len(second) // 4 * 4], dtype="<f4")
    if len(f2) != len(f1):
        continue
    dx, dy, dz = f2[idx] - f1[idx], f2[idx + 1] - f1[idx + 1], f2[idx + 2] - f1[idx + 2]
    keep = idx[(np.abs(dx) < 3) & (np.abs(dz) < 3) & (dy < -0.05) & (dy > -60)]
    flakes += [(b + 4 * int(i), *f2[i:i + 3]) for i in keep]

print(f"{len(flakes)} falling points in {len(regions)} regions")
if flakes:
    arr = np.array([f[1:] for f in flakes])
    print("x %.1f .. %.1f   z %.1f .. %.1f   y %.1f .. %.1f" % (arr[:, 0].min(), arr[:, 0].max(), arr[:, 2].min(), arr[:, 2].max(),
                                                            arr[:, 1].min(), arr[:, 1].max()))
    print("centre x %.1f z %.1f" % ((arr[:, 0].min() + arr[:, 0].max()) / 2, (arr[:, 2].min() + arr[:, 2].max()) / 2))
    addrs = sorted(f[0] for f in flakes)
    gaps = np.diff(addrs)
    print("first", hex(addrs[0]), "last", hex(addrs[-1]), "most common spacing", np.bincount(gaps).argmax() if len(gaps) else None)
    head = read(addrs[0] - 256, 256)
    for o in range(0, 256, 16):
        print(hex(addrs[0] - 256 + o), head[o:o + 16].hex(" "), [round(v, 2) for v in struct.unpack_from("<4f", head, o)])

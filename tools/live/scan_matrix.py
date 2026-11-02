"""Look for a board model's transform matrix inside the running game's memory.

usage: python scan_matrix.py <pid> <F00_X.model> <matrix index>
Prints every place the matrix's 64 bytes (and its translation row on its own) appear. Read-only.
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

pid, path, idx = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
m = igbmodel.load(path)
base, _ = m.chunk("MTRX")
raw = bytes(m.data[base + 64 * idx: base + 64 * idx + 64])
needles = {"matrix": raw, "translation row": raw[48:64]}

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0410, False, pid)          # query + read only
a, mbi, hits = 0, MBI(), {n: [] for n in needles}
while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
    b, s = mbi.Base or 0, mbi.Size
    if mbi.State == 0x1000 and not (mbi.Protect & 0x101):
        buf = ctypes.create_string_buffer(s)
        n = ctypes.c_size_t()
        k.ReadProcessMemory(h, ctypes.c_void_p(b), buf, s, ctypes.byref(n))
        d = buf.raw[:n.value]
        for name, nd in needles.items():
            p = d.find(nd)
            while p != -1:
                hits[name].append(b + p)
                p = d.find(nd, p + 1)
    a = b + s
    if a <= b:
        break
for name, v in hits.items():
    print(f"{name}: {len(v)} hits", [hex(x) for x in v[:12]])
print("translation", struct.unpack("<4f", raw[48:64]))

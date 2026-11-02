"""Hide (or restore) every board matrix within a radius of a space, in the RUNNING game, in one memory pass.

usage: python hide_near.py <pid> <space id> <radius> [--dir <folder with the model files the game loaded>] [--restore]
Matrices of F00_M, F00_N and F00_A whose translation is within `radius` units of the space are zeroed (the 3x3 part). The
originals are kept in hide_near_state.json so --restore can put them back. Meshes are not touched.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel
from boardlib import load_board

ASSETS = Path("G:/Programming/Dokapon-Workspace/assets")
STATE = Path(__file__).with_name("hide_near_state.json")
ap = argparse.ArgumentParser()
ap.add_argument("pid", type=int)
ap.add_argument("space", type=int)
ap.add_argument("radius", type=float)
ap.add_argument("--dir", default=None)
ap.add_argument("--restore", action="store_true")
args = ap.parse_args()

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
h = k.OpenProcess(0x0438, False, args.pid)


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


def write(addr: int, data: bytes) -> None:
    k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(ctypes.c_size_t()))


state = json.loads(STATE.read_text()) if STATE.exists() else {}
key = f"{args.pid}"
if args.restore:
    for addr, raw in state.pop(key, {}).items():
        write(int(addr, 16), bytes.fromhex(raw))
    STATE.write_text(json.dumps(state))
    sys.exit("restored")

spaces, _ = load_board(ASSETS, 0)
centre = next(s["pos"] for s in spaces if s["id"] == args.space)
folder = Path(args.dir) if args.dir else None
needles: dict[bytes, str] = {}
for kind in "MNA":
    name = f"F00_{kind}.model"
    m = igbmodel.load(folder / name if folder and (folder / name).exists() else ASSETS / "CommonData" / "dataField" / "F00" / name)
    base, _ = m.chunk("MTRX")
    for i in range(len(m.matrices())):
        raw = bytes(m.data[base + 64 * i: base + 64 * i + 64])
        t = struct.unpack_from("<3f", raw, 48)
        if math.dist((t[0], t[2]), (centre[0], centre[2])) <= args.radius and any(struct.unpack_from("<12f", raw)):
            needles[raw] = f"{kind} {i}"
print(f"{len(needles)} matrices within {args.radius:g} of space {args.space}: {sorted(needles.values())}")
first_words = {struct.unpack_from("<I", raw, 48)[0] for raw in needles}
saved = state.get(key, {})
hidden = 0
a, mbi = 0, MBI()
while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
    b, s = mbi.Base or 0, mbi.Size
    if mbi.State == 0x1000 and mbi.Protect == 0x04 and s >= 64:
        buf = ctypes.create_string_buffer(s)
        n = ctypes.c_size_t()
        k.ReadProcessMemory(h, ctypes.c_void_p(b), buf, s, ctypes.byref(n))
        d = buf.raw[:n.value]
        arr = np.frombuffer(d[: len(d) // 4 * 4], dtype="<u4")
        for i in np.nonzero(np.isin(arr, list(first_words)))[0]:
            pos = int(i) * 4 - 48
            if pos >= 0 and d[pos:pos + 64] in needles:
                raw = d[pos:pos + 64]
                saved.setdefault(hex(b + pos), raw.hex())
                mat = list(struct.unpack("<16f", raw))
                mat[:12] = [0.0] * 12
                write(b + pos, struct.pack("<16f", *mat))
                hidden += 1
    a = b + s
    if a <= b:
        break
state[key] = saved
STATE.write_text(json.dumps(state))
print(f"hid {hidden} copies")

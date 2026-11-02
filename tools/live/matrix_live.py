"""Step through the board's transform matrices in the RUNNING game and hide or lift each one, to see what it places.

usage: python matrix_live.py [--dir <folder with the F00_*.model files the game loaded>] [--pid N] [--mod back|lb|rb|lbrb|none] [--keep]

Needs the game open on the board. The matrices of F00_M, F00_N and F00_A are found in memory in one pass (the files in --dir,
default: the extracted originals; use the installed mod's Assets folder if the installed models differ from the originals).
Hold the modifier (default: the Back button; on the keyboard, Ctrl) and press:
    d-pad right / left   next / previous matrix        (arrow keys with Ctrl)
    d-pad up             hide the selected matrix, press again to bring it back   (up arrow)
    d-pad down           lift it 40 units, press again to put it back, handy to spot where it is   (down arrow)
    Y                    switch between the M, N and A files        (key F)
    X                    restore everything                          (key R)
Everything is restored when this script exits, unless --keep is given. Edits live only in the game's memory.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import math
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel
from boardlib import load_board

ASSETS = Path("G:/Programming/Dokapon-Workspace/assets")
KINDS = {0x14: "town", 0x15: "castle", 0x16: "weapon store", 0x17: "item store", 0x18: "magic store", 0x1B: "casino", 0x1C: "coliseum"}
LIFT = 40.0

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=None)
ap.add_argument("--pid", type=int, default=None)
ap.add_argument("--mod", default="back", choices=["back", "lb", "rb", "lbrb", "none"])
ap.add_argument("--keep", action="store_true")
args = ap.parse_args()

pid = args.pid
if pid is None:
    out = subprocess.check_output(["tasklist", "/FI", "IMAGENAME eq DkkStm.exe", "/FO", "CSV", "/NH"]).decode()
    pid = int(out.split(",")[1].strip('"'))

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
h = k.OpenProcess(0x0438, False, pid)
if not h:
    sys.exit(f"cannot open process {pid}: {ctypes.get_last_error()}")


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


# ---- the matrices of every file, keyed by their bytes ------------------------------------------------------------------
folder = Path(args.dir) if args.dir else None
spaces, _ = load_board(ASSETS, 0)
nodes = [(s["id"], KINDS.get(s["type"][0]), s["pos"]) for s in spaces]
needles: dict[bytes, tuple[str, int]] = {}
dupes: set[bytes] = set()
entries: dict[tuple[str, int], dict] = {}
for kind in "MNA":
    name = f"F00_{kind}.model"
    path = folder / name if folder and (folder / name).exists() else ASSETS / "CommonData" / "dataField" / "F00" / name
    m = igbmodel.load(path)
    base, _ = m.chunk("MTRX")
    for i in range(len(m.matrices())):
        raw = bytes(m.data[base + 64 * i: base + 64 * i + 64])
        if raw in needles:
            dupes.add(raw)
        needles[raw] = (kind, i)
        mat = struct.unpack("<16f", raw)
        near = min(((math.dist((mat[12], mat[14]), (p[0], p[2])), sid, kd) for sid, kd, p in nodes if kd), default=(0, 0, ""))
        entries[(kind, i)] = {"raw": raw, "addrs": [], "mode": None, "pos": (mat[12], mat[13], mat[14]), "near": near}
for raw in dupes:
    entries.pop(needles[raw], None)             # identical matrices cannot be told apart: leave them out
    needles.pop(raw)

# ---- find them -----------------------------------------------------------------------------------------------------------
first_words = {struct.unpack_from("<I", raw, 48)[0] for raw in needles}
t0 = time.time()
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
            if pos >= 0 and (key := needles.get(d[pos:pos + 64])):
                entries[key]["addrs"].append(b + pos)
    a = b + s
    if a <= b:
        break
order = [key for key in sorted(entries, key=lambda kk: ("MNA".index(kk[0]), kk[1])) if entries[key]["addrs"]]
print(f"process {pid}: found {len(order)} of {len(entries)} matrices in {time.time() - t0:.1f}s")
if not order:
    sys.exit("none found: is the game on the board, and does --dir hold the models it loaded?")


def write(addr: int, data: bytes) -> None:
    k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(ctypes.c_size_t()))


def apply(key: tuple[str, int], mode: str | None) -> None:
    e = entries[key]
    mat = list(struct.unpack("<16f", e["raw"]))
    if mode == "hide":
        mat[:12] = [0.0] * 12
    elif mode == "lift":
        mat[13] += LIFT
    for addr in e["addrs"]:
        write(addr, struct.pack("<16f", *mat))
    e["mode"] = mode


def restore_all() -> None:
    for key in order:
        if entries[key]["mode"]:
            apply(key, None)


def show(key: tuple[str, int]) -> None:
    e = entries[key]
    d, sid, kd = e["near"]
    print(f"\r[{key[0]} {key[1]:3d}] at ({e['pos'][0]:.0f}, {e['pos'][2]:.0f}) nearest {kd} space {sid} ({d:.0f} away)  "
          f"state: {e['mode'] or 'normal'}   ({order.index(key) + 1}/{len(order)})            ", end="", flush=True)


# ---- input: XInput pad, with the keyboard as a fallback ---------------------------------------------------------------
class Gamepad(ctypes.Structure):
    _fields_ = [("buttons", wt.WORD), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte), ("lx", ctypes.c_short), ("ly", ctypes.c_short),
                ("rx", ctypes.c_short), ("ry", ctypes.c_short)]


class XState(ctypes.Structure):
    _fields_ = [("packet", wt.DWORD), ("pad", Gamepad)]


try:
    xinput = ctypes.WinDLL("xinput1_4")
except OSError:
    xinput = None
user32 = ctypes.WinDLL("user32")
BTN = {"up": 0x1, "down": 0x2, "left": 0x4, "right": 0x8, "back": 0x20, "lb": 0x100, "rb": 0x200, "a": 0x1000, "x": 0x4000, "y": 0x8000}
MODIFIER = {"back": BTN["back"], "lb": BTN["lb"], "rb": BTN["rb"], "lbrb": BTN["lb"] | BTN["rb"], "none": 0}[args.mod]
VK = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "ctrl": 0x11, "y": 0x46, "x": 0x52}


def pressed() -> set[str]:
    out: set[str] = set()
    if xinput:
        st = XState()
        if xinput.XInputGetState(0, ctypes.byref(st)) == 0:
            b = st.pad.buttons
            if (b & MODIFIER) == MODIFIER:
                out |= {n for n in ("up", "down", "left", "right", "y", "x") if b & BTN[n]}
    if user32.GetAsyncKeyState(VK["ctrl"]) & 0x8000:
        out |= {n for n in ("up", "down", "left", "right", "y", "x") if user32.GetAsyncKeyState(VK[n]) & 0x8000}
    return out


file_cycle = "MNA"
pos = 0
print(__doc__.split("Hold the modifier")[1].split("Everything is restored")[0].strip().replace("\n    ", "\n  "))
print(f"(modifier: {args.mod}; Ctrl on the keyboard)\n")
show(order[pos])
last: set[str] = set()
try:
    while True:
        now = pressed()
        for press in now - last:
            key = order[pos]
            if press in ("right", "left"):
                pos = (pos + (1 if press == "right" else -1)) % len(order)
            elif press == "up":
                apply(key, None if entries[key]["mode"] == "hide" else "hide")
            elif press == "down":
                apply(key, None if entries[key]["mode"] == "lift" else "lift")
            elif press == "y":
                i = (file_cycle.index(order[pos][0]) + 1) % 3
                pos = next((n for n, kk in enumerate(order) if kk[0] == file_cycle[i]), pos)
            elif press == "x":
                restore_all()
            show(order[pos])
        last = now
        time.sleep(0.03)
except KeyboardInterrupt:
    pass
finally:
    if not args.keep:
        restore_all()
        print("\nrestored every matrix")

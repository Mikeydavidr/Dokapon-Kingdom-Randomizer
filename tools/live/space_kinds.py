"""Find and change the kind of board spaces in the RUNNING game (no reinstall), to see if the game picks up a new kind live.

usage: python space_kinds.py <pid> scan [--board N] [--assets <folder>] [--stg <stgNNN_EN.DAT the game loaded>]
       python space_kinds.py <pid> set SPACE:KIND[:PARAM[:SKIN]][,...] [same options]      (hex, e.g. 36:03:0d)
       python space_kinds.py <pid> restore
scan is read-only: it looks through writable memory for the board's space kinds laid out with any stride from 1 to 1024
bytes (the raw 16-byte stgNNN records, or whatever per-space struct the game builds from them), and prints each layout
found with the bytes of the first spaces, so the struct can be read. The skin (second type byte) and param are found next
to the kind by matching the board file (pass the installed one with --stg if the mod changed params). set writes the new
kind, and optionally the param's first u16 (a loot space's loot table: a kind change without it can crash on landing) and
the skin, into every layout found, and keeps the old bytes in space_kinds_state.json next to this script for restore.
Needs the game to be on the board.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from boardlib import load_board

STATE = Path(__file__).with_name("space_kinds_state.json")
ap = argparse.ArgumentParser()
ap.add_argument("pid", type=int)
ap.add_argument("action", choices=["scan", "set", "restore"])
ap.add_argument("changes", nargs="?", default="")
ap.add_argument("--board", type=int, default=0)
ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
ap.add_argument("--stg", default=None)
ap.add_argument("--min-match", type=float, default=0.9)
args = ap.parse_args()

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0410 if args.action == "scan" else 0x0438, False, args.pid)
state = json.loads(STATE.read_text()) if STATE.exists() else {}


def read(addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    k.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value]


def write(addr: int, data: bytes) -> None:
    n = ctypes.c_size_t()
    if not k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n)):
        raise OSError(f"write at {addr:#x} failed: {ctypes.get_last_error()}")


def regions():
    a, mbi = 0, MBI()
    while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        b, s = mbi.Base or 0, mbi.Size
        if mbi.State == 0x1000 and not (mbi.Protect & 0x101) and mbi.Protect & 0x44 and s < 1 << 30:      # committed, read-write
            yield b, s, mbi.Type
        a = b + s
        if a <= b:
            break


def scan(kinds: np.ndarray) -> list[dict]:
    """Every (address of space 0's kind, stride) where at least --min-match of the spaces' kinds sit."""
    n = len(kinds)
    sample = np.unique(np.linspace(0, n - 1, 24).astype(int))
    hits = []
    for b, size, typ in regions():
        a = np.frombuffer(read(b, size), dtype=np.uint8)
        if len(a) < n:
            continue
        hist = np.bincount(a, minlength=256)
        j = int(sample[np.argmin(hist[kinds[sample]])])          # the sampled space whose kind is rarest here
        at = np.nonzero(a == kinds[j])[0]
        for stride in range(1, min(1024, (len(a) - 1) // (n - 1)) + 1):
            base = at - j * stride
            base = base[(base >= 0) & (base + (n - 1) * stride < len(a))]
            for i in sample:
                if not len(base):
                    break
                base = base[a[base + i * stride] == kinds[i]]
            for p in base:
                match = float(np.mean(a[p + np.arange(n) * stride] == kinds))
                if match >= args.min_match:
                    hits.append({"addr": b + int(p), "stride": stride, "match": match, "image": typ == 0x1000000})
    return hits


if args.action == "restore":
    for addr, old in state.pop(str(args.pid), {}).items():
        write(int(addr, 16), bytes.fromhex(old))
        print("restored", addr)
    STATE.write_text(json.dumps(state))
    sys.exit()

def locate(hit: dict, values: list[bytes]) -> int | None:
    """Offset from the kind (within 16 bytes) where most spaces hold their value of another field, e.g. the param."""
    s, w = hit["stride"], len(values[0])
    d = read(hit["addr"] - 16, s * (len(values) - 1) + 33 + w)
    best = max((sum(d[16 + off + i * s: 16 + off + i * s + w] == v for i, v in enumerate(values)), off)
               for off in range(-16, 18 - w) if not -w < off <= 0)
    return best[1] if best[0] >= 0.7 * len(values) else None


assets = Path(args.assets)
spaces = load_board(assets, args.board)[0]
stg = Path(args.stg).read_bytes() if args.stg else None
rec = [stg[s["offset"] + 8: s["offset"] + 16] if stg else bytes([*s["type"], s["grp"], 0, *s["param"]]) for s in spaces]
kinds = np.array([r[0] for r in rec], dtype=np.uint8)
hits = scan(kinds)
# a short stride that only matches because the kinds repeat (e.g. stride 1 inside a bigger struct) is still listed: read
# the dump to tell them apart
if not hits:
    sys.exit("space kinds not found in memory (is the game on the board, and is --stg the file it loaded?)")
for hit in hits:
    hit["skin"] = locate(hit, [r[1:2] for r in rec])
    hit["param"] = locate(hit, [r[4:8] for r in rec])

if args.action == "scan":
    for hit in hits:
        a, s = hit["addr"], hit["stride"]
        print(f"{a:#x} stride {s} ({hit['match']:.0%} of {len(kinds)} kinds match{', in the exe image' if hit['image'] else ''}),"
              f" skin at {hit['skin']}, param at {hit['param']} (bytes from the kind)")
        show = min(max(s, 16), 128)
        pre = min(show // 2, 64)
        print(f"  (dumps start {pre} bytes before the kind)")
        for i in range(4):
            print(f"  space {i} (kind {kinds[i]:02x}):", read(a + i * s - pre, show).hex(" "))
        mism = [i for i in range(len(kinds)) if read(a + i * s, 1)[0] != kinds[i]]
        if mism:
            print("  differs at spaces", mism[:20], "now", [f"{read(a + i * s, 1)[0]:02x}" for i in mism[:20]])
else:
    saved = state.setdefault(str(args.pid), {})
    for item in args.changes.split(","):
        sp, *vals = item.split(":")
        sp = int(sp)
        fields = [("kind", 0, bytes([int(vals[0], 16)]))]
        if len(vals) > 1:
            fields.append(("param", "param", struct.pack("<HH", int(vals[1], 16), 0)))
        if len(vals) > 2:
            fields.append(("skin", "skin", bytes([int(vals[2], 16)])))
        for hit in hits:
            for name, where, data in fields:
                off = hit[where] if isinstance(where, str) else where
                if off is None:
                    print(f"space {sp}: no {name} field found in the stride-{hit['stride']} layout, left alone")
                    continue
                addr = hit["addr"] + sp * hit["stride"] + off
                saved.setdefault(hex(addr), read(addr, len(data)).hex())
                write(addr, data)
                print(f"space {sp}: {name} {read(addr, len(data)).hex()} at {addr:#x} (stride {hit['stride']})")
    STATE.write_text(json.dumps(state))

"""Find a game value (week, day, gold...) by snapshots of the RUNNING game's writable memory taken at known values.

usage: python memscan.py snap <pid> <dir> <name>
       python memscan.py find <dir> <name>=<value> [<name>=<value> ...] [--width 1|2|4] [--pid PID]
snap saves every committed read-write region (not the GPU upload buffers) to <dir>/<name>.bin with an index <dir>/<name>.json
(about 450 MB a snapshot: keep <dir> out of the repo). find lists the addresses whose value (unsigned, little-endian, aligned to
the width) equals the given value in every named snapshot, among the regions present at the same place in all of them.
A value of * means "anything". With --pid it also prints what each address holds now. Read-only.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys
from pathlib import Path

import numpy as np

ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("snap")
s.add_argument("pid", type=int)
s.add_argument("dir")
s.add_argument("name")
f = sub.add_parser("find")
f.add_argument("dir")
f.add_argument("conds", nargs="+")
f.add_argument("--width", type=int, default=1, choices=[1, 2, 4])
f.add_argument("--pid", type=int, default=None)
f.add_argument("--max", type=int, default=60)
args = ap.parse_args()

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


def open_process(pid: int):
    return k.OpenProcess(0x0410, False, pid)          # query + read only


def read(h, addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    k.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value]


if args.cmd == "snap":
    h = open_process(args.pid)
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    index, a, mbi = [], 0, MBI()
    with open(out / f"{args.name}.bin", "wb") as fh:
        while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            b, size = mbi.Base or 0, mbi.Size
            if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and size < 1 << 30:      # committed, read-write, not write-combined
                d = read(h, b, size)
                index.append({"base": b, "size": len(d), "offset": fh.tell(), "image": mbi.Type == 0x1000000})
                fh.write(d)
            a = b + size
            if a <= b:
                break
    (out / f"{args.name}.json").write_text(json.dumps(index))
    print(f"saved {sum(r['size'] for r in index) / 2 ** 20:.0f} MB in {len(index)} regions to {out / args.name}.bin")
    sys.exit()

snaps = []
for c in args.conds:
    name, val = c.split("=")
    idx = json.loads((Path(args.dir) / f"{name}.json").read_text())
    snaps.append((name, None if val == "*" else int(val, 0), {(r["base"], r["size"]): r for r in idx}, Path(args.dir) / f"{name}.bin"))
dtype = {1: "<u1", 2: "<u2", 4: "<u4"}[args.width]
common = set(snaps[0][2])
for _, _, regions, _ in snaps[1:]:
    common &= set(regions)
hits = []
maps = [np.memmap(path, dtype=np.uint8, mode="r") for *_, path in snaps]
for base, size in sorted(common):
    n = size // args.width
    mask = None
    for (name, val, regions, _), mm in zip(snaps, maps):
        if val is None:
            continue
        r = regions[(base, size)]
        arr = np.frombuffer(mm[r["offset"]: r["offset"] + n * args.width], dtype=dtype)
        m = arr == val
        mask = m if mask is None else mask & m
        if not mask.any():
            break
    if mask is not None and mask.any():
        image = snaps[0][2][(base, size)]["image"]
        hits += [(base + int(i) * args.width, image) for i in np.nonzero(mask)[0]]
print(f"{len(hits)} addresses match")
h = open_process(args.pid) if args.pid else None
for addr, image in hits[:args.max]:
    vals = []
    for (name, _, regions, _), mm in zip(snaps, maps):
        r = next(r for (b, sz), r in regions.items() if b <= addr < b + sz)
        o = r["offset"] + addr - r["base"]
        vals.append(f"{name}={int.from_bytes(bytes(mm[o:o + args.width]), 'little')}")
    now = f" now={int.from_bytes(read(h, addr, args.width), 'little')}" if h else ""
    print(f"  {addr:#x}{' (exe/dll image)' if image else ''} {' '.join(vals)}{now}")

"""Collapse (hide) or restore one mesh piece of a board model in the RUNNING game, if the game draws from its RAM copy.

usage: python mesh_poke.py <pid> <F00_X.model as the game loaded it> <geom index> <collapse|restore|show>
  show: for a piece the INSTALLED mod collapsed. Pass the ORIGINAL model; the collapsed bytes are found in memory and the original written over them.
Finds the piece's vertex block (stride x vertex count bytes) in memory; collapse sets every vertex position to the first one's,
restore writes the original positions back (kept in mesh_poke_state.json). Meshes may live on the GPU only, in which case this
changes nothing on screen.
"""
import ctypes
import ctypes.wintypes as wt
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

STATE = Path(__file__).with_name("mesh_poke_state.json")
pid, path, gi, action = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
m = igbmodel.load(path)
g = m.geoms[gi]
vo, _ = m.chunk("VERT")
block = bytes(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0438, False, pid)
state = json.loads(STATE.read_text()) if STATE.exists() else {}
key = f"{pid}:{Path(path).name}:{gi}"


def write(addr: int, data: bytes) -> None:
    k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(ctypes.c_size_t()))


if action == "restore":
    for addr, hexbytes in state.pop(key, {}).items():
        write(int(addr, 16), bytes.fromhex(hexbytes))
        print("restored", addr)
else:
    if action == "show":
        first = block[:12]
        search = b"".join(first + block[i * g.stride + 12:(i + 1) * g.stride] for i in range(g.verts))
    else:
        search = block
    found, a, mbi = [], 0, MBI()
    while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        b, s = mbi.Base or 0, mbi.Size
        if mbi.State == 0x1000 and mbi.Protect & 0x04 and s >= len(search):
            buf = ctypes.create_string_buffer(s)
            n = ctypes.c_size_t()
            k.ReadProcessMemory(h, ctypes.c_void_p(b), buf, s, ctypes.byref(n))
            d, p = buf.raw[:n.value], 0
            while (p := d.find(search, p)) != -1:
                found.append(b + p)
                p += 1
        a = b + s
        if a <= b:
            break
    print(f"vertex block ({len(search)} bytes) found at {[hex(x) for x in found]}")
    first = block[:12]
    flat = b"".join(first + block[i * g.stride + 12:(i + 1) * g.stride] for i in range(g.verts))
    saved = state.get(key, {})
    for addr in found:
        if action == "show":
            write(addr, block)
            print("shown", hex(addr))
        else:
            saved.setdefault(hex(addr), block.hex())
            write(addr, flat)
    state[key] = saved
STATE.write_text(json.dumps(state))

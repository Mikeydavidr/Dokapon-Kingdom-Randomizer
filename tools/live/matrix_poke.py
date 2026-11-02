"""Change board model matrices in the RUNNING game (no reinstall): lift, hide or restore a building.

usage: python matrix_poke.py <pid> <F00_X.model> <matrix index> <lift|hide|restore> [amount]
The matrix is found by its 64 bytes from the model file, so pass the same file the game loaded (the installed one if it was
modified, else the extracted original). Every copy found is edited and the original bytes are kept in matrix_poke_state.json
next to this script so `restore` can put them back, even from a later run. Needs the game to be on the board.
"""
import ctypes
import ctypes.wintypes as wt
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

STATE = Path(__file__).with_name("matrix_poke_state.json")
pid, path, idx, action = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
amount = float(sys.argv[5]) if len(sys.argv) > 5 else 40.0
m = igbmodel.load(path)
base, _ = m.chunk("MTRX")
raw = bytes(m.data[base + 64 * idx: base + 64 * idx + 64])

k = ctypes.WinDLL("kernel32", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0438, False, pid)          # query, read, write, operation
state = json.loads(STATE.read_text()) if STATE.exists() else {}
key = f"{pid}:{Path(path).name}:{idx}"


def find(needle: bytes) -> list[int]:
    out, a, mbi = [], 0, MBI()
    while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        b, s = mbi.Base or 0, mbi.Size
        if mbi.State == 0x1000 and not (mbi.Protect & 0x101) and mbi.Protect & 0x04:      # committed, readable, writable
            buf = ctypes.create_string_buffer(s)
            n = ctypes.c_size_t()
            k.ReadProcessMemory(h, ctypes.c_void_p(b), buf, s, ctypes.byref(n))
            d, p = buf.raw[:n.value], 0
            while (p := d.find(needle, p)) != -1:
                out.append(b + p)
                p += 1
        a = b + s
        if a <= b:
            break
    return out


def write(addr: int, data: bytes) -> None:
    n = ctypes.c_size_t()
    if not k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n)):
        raise OSError(f"write at {addr:#x} failed: {ctypes.get_last_error()}")


if action == "restore":
    for addr, hexbytes in state.pop(key, {}).items():
        write(int(addr, 16), bytes.fromhex(hexbytes))
        print("restored", addr)
else:
    saved = state.get(key, {})
    needle = raw if not saved else None
    addrs = [int(a, 16) for a in saved] if saved else find(raw)
    if not addrs:
        sys.exit("matrix not found in memory (is the board loaded, and is this the file the game loaded?)")
    for a in addrs:
        saved.setdefault(hex(a), raw.hex())
        mat = list(struct.unpack("<16f", raw))
        if action == "lift":
            mat[13] += amount
        elif action == "hide":
            mat[:12] = [0.0] * 12
        write(a, struct.pack("<16f", *mat))
        print(action, hex(a))
    state[key] = saved
STATE.write_text(json.dumps(state))

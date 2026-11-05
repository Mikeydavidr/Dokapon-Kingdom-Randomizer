"""Read the calendar and give accessories (or change their proc chance) in the RUNNING game, no reinstall.

usage: python players.py <pid> show
       python players.py <pid> equip PLAYER ACCESSORY_ID [--chance PERCENT]      (accessory id 0 = take it off)
       python players.py <pid> chance ACCESSORY_ID PERCENT
show prints the week and weekday (exe global RVA 0x8A8408 -> state + 0x20, week u16 at +0x1C, weekday u16 at +0x1E, Sun 0), the
players (game state base B + 0x24A0, stride 0x508: control byte +0x70, weapon/shield/accessory ids at +0xBE/+0xBF/+0xC0) and the
accessory structs (B + 0x35598, stride 0x148, id +0x140, chance +0x139) that hold an id. B is not fixed: it is found by the
"Wooden Shield" name at B + 0x31A80 + 0x150 + 0x14. equip writes the player's accessory id (and with --chance also that
accessory's chance byte, which the data-driven rolls such as the Mirror Necklace read). See docs/item-records-and-effects.md.
Needs the game to be past the title screen (a board loaded) to find B.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import struct

ap = argparse.ArgumentParser()
ap.add_argument("pid", type=int)
ap.add_argument("action", choices=["show", "equip", "chance"])
ap.add_argument("a", nargs="?", type=lambda s: int(s, 0))
ap.add_argument("b", nargs="?", type=lambda s: int(s, 0))
ap.add_argument("--chance", type=int, default=None)
args = ap.parse_args()

PLAYERS, PLAYER_STRIDE, ACCS, ACC_STRIDE, ACC_SLOTS = 0x24A0, 0x508, 0x35598, 0x148, 40
NAME_AT = 0x31A80 + 0x150 + 0x14
RVA_STATE = 0x8A8408

k = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k.OpenProcess.restype = wt.HANDLE
k.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
psapi.EnumProcessModules.argtypes = [wt.HANDLE, ctypes.POINTER(wt.HMODULE), wt.DWORD, ctypes.POINTER(wt.DWORD)]


class MBI(ctypes.Structure):
    _fields_ = [("Base", ctypes.c_void_p), ("AllocBase", ctypes.c_void_p), ("AllocProt", wt.DWORD), ("pad", wt.DWORD), ("Size", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("pad2", wt.DWORD)]


h = k.OpenProcess(0x0410 if args.action == "show" else 0x0438, False, args.pid)
if not h:
    raise SystemExit(f"cannot open process {args.pid}")


def read(addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    k.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n))
    return buf.raw[:n.value]


def write(addr: int, data: bytes) -> None:
    n = ctypes.c_size_t()
    if not k.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n)):
        raise SystemExit(f"write at {addr:#x} failed")


def exe_base() -> int:
    mods = (wt.HMODULE * 1)()
    need = wt.DWORD()
    psapi.EnumProcessModules(h, mods, ctypes.sizeof(mods), ctypes.byref(need))
    return mods[0]


def calendar() -> tuple[int, int] | None:
    ptr = struct.unpack("<Q", read(exe_base() + RVA_STATE, 8).ljust(8, b"\0"))[0]
    blk = read(ptr, 0x20) if ptr else b""
    return struct.unpack_from("<HH", blk, 0x1C) if len(blk) == 0x20 else None


def find_base() -> int:
    needle, a, mbi = b"Wooden Shield\0", 0, MBI()
    while a < 0x7FFFFFFFFFFF and k.VirtualQueryEx(h, ctypes.c_void_p(a), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        b, size = mbi.Base or 0, mbi.Size
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and mbi.Type != 0x1000000 and size < 1 << 30:
            d, i = read(b, size), -1
            while (i := d.find(needle, i + 1)) >= 0:
                base = b + i - NAME_AT
                if i >= NAME_AT and read(base + 0x31A80 + 0x150 + 0x148, 1) == b"\x01":       # the Wooden Shield is id 1, in slot 1
                    return base
        a = b + size
        if a <= b:
            break
    raise SystemExit("game state not found: is a board loaded?")


def player_addr(base: int, n: int) -> int:
    return base + PLAYERS + n * PLAYER_STRIDE


def acc_slots(base: int) -> dict[int, int]:
    """accessory id -> address of its struct, for the slots that hold an id."""
    out = {}
    for s in range(ACC_SLOTS):
        addr = base + ACCS + s * ACC_STRIDE
        aid = read(addr + 0x140, 1)
        if aid and aid[0] and aid[0] not in out:
            out[aid[0]] = addr
    return out


cal = calendar()
print("calendar:", f"week {cal[0]}, weekday {cal[1]} (Sun 0)" if cal else "state block not readable")
base = find_base()
print(f"state base B = {base:#x}")
accs = acc_slots(base)

if args.action == "show":
    for n in range(8):
        p = read(player_addr(base, n), PLAYER_STRIDE)
        if len(p) < PLAYER_STRIDE:
            break
        who = "human" if struct.unpack_from("<I", p, 0x70)[0] == 0 else "cpu"
        print(f"player {n}: {who:5s} weapon {p[0xBE]:#04x} shield {p[0xBF]:#04x} accessory {p[0xC0]:#04x}")
    for aid, addr in sorted(accs.items()):
        name = read(addr + 0x14, 24).split(b"\0")[0].decode("ascii", "replace")
        print(f"accessory {aid:#04x}: chance {read(addr + 0x139, 1)[0]:3d}  {name!r}")
    raise SystemExit

if args.action == "equip":
    player, aid = args.a, args.b
    write(player_addr(base, player) + 0xC0, bytes([aid]))
    print(f"player {player} now wears accessory {aid:#x}")
    chance_for = aid if args.chance is not None else None
else:
    chance_for = args.a
    args.chance = args.b
if chance_for:
    if chance_for not in accs:
        raise SystemExit(f"accessory {chance_for:#x} has no struct")
    write(accs[chance_for] + 0x139, bytes([args.chance]))
    print(f"accessory {chance_for:#x} chance = {args.chance}")

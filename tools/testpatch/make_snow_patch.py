"""Move, resize or turn off the falling snow of board 0 (normally over the snowy island of Sermitsiaq and Strom Castle).

usage: python make_snow_patch.py <mod folder> [--centre X,Z] [--half-width W] [--height H] [--off] [--exe <DkkStm.exe>]
Writes <mod>/Hex/snow.hex for ConnectModInstaller (it patches a fresh copy of the backup exe on every install, so leaving the
file out of a later install undoes it). Prints the area the snow will cover.

The snow is one emitter set up by the game code, not by any data file (found by watching the flakes in the running game):
  file 0x213D2A  mov dword [rdi], X        mov dword [rdi+4], 10       mov qword [rdi+8], Z      (board 0: X 120, Z 250)
  file 0x213D14  movss xmm1, [height]      (175: flakes fall from y 175 to 0)
  file 0x213D1E  movss xmm2, [half-width]  (125: flakes cover centre +- 125 in x and z)
The centre is an immediate, so any value works (the function clears the emitter with memset first, so a negative z is stored
with a 4-byte move instead of the sign-extending 8-byte one). The height and the half-width are read from shared constants in .rdata, which
other code uses too, so the load is pointed at another constant that already holds the wanted value (the closest whole number
found there is used). --off puts the centre far off the board.
"""
import argparse
import struct
from pathlib import Path

INSTALLER_EXE = "C:/Users/Mikey/AppData/Local/Temp/claude/g--Programming-Dokapon-Kingdom-Randomizer-main/5415d715-a1e2-4534-81c5-9bc9ba5e492e/scratchpad/inst_actual/Backup/DkkStm.exe"
TEXT_VA, TEXT_RAW = 0x1000, 0x400
RDATA_VA, RDATA_RAW, RDATA_SIZE = 0x44D000, 0x44BA00, 681984
CENTRE = 0x213D2A                     # c7 07 imm32 | c7 47 04 imm32 | 48 c7 47 08 imm32
LOADS = {"height": 0x213D14, "half-width": 0x213D1E}   # f3 0f 10 xx disp32 (8 bytes)
ORIGINAL = bytes.fromhex("c7070000f042c747040000204148c74708 00007a43".replace(" ", ""))

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("--centre", default=None)
ap.add_argument("--half-width", type=float, default=None)
ap.add_argument("--height", type=float, default=None)
ap.add_argument("--off", action="store_true")
ap.add_argument("--exe", default=INSTALLER_EXE)
args = ap.parse_args()
exe = Path(args.exe).read_bytes()
assert exe[CENTRE:CENTRE + len(ORIGINAL)] == ORIGINAL, "this exe's snow code is not the one this patch was made for"

edits = []                             # (file offset, bytes)


def target(load: int) -> int:
    """File offset of the constant a movss [rip+disp32] at file offset `load` reads."""
    disp = struct.unpack_from("<i", exe, load + 4)[0]
    return load - TEXT_RAW + TEXT_VA + 8 + disp - RDATA_VA + RDATA_RAW


def retarget(name: str, value: float) -> float:
    load = LOADS[name]
    consts = {}
    for o in range(RDATA_RAW, RDATA_RAW + RDATA_SIZE, 4):
        v = struct.unpack_from("<f", exe, o)[0]
        if 0 < v < 1e6 and v == int(v):
            consts.setdefault(v, o)
    v = min(consts, key=lambda c: abs(c - value))
    disp = consts[v] + RDATA_VA - RDATA_RAW - (load - TEXT_RAW + TEXT_VA + 8)
    edits.append((load + 4, struct.pack("<i", disp)))
    return v


x, z = struct.unpack_from("<f", exe, CENTRE + 2)[0], struct.unpack_from("<f", exe, CENTRE + 17)[0]
if args.off:
    x, z = 20000.0, 20000.0
elif args.centre:
    x, z = (float(v) for v in args.centre.split(","))
edits.append((CENTRE + 2, struct.pack("<f", x)))
edits.append((CENTRE + 17, struct.pack("<f", z)))
if z < 0:
    # the z store writes 8 bytes and sign-extends its 4-byte value, so a negative z would fill the word after it with ones;
    # nop the REX.W prefix (48 -> 90) to store 4 bytes only (the emitter was zeroed just before)
    edits.append((CENTRE + 13, b"\x90"))
half = retarget("half-width", args.half_width) if args.half_width else struct.unpack_from("<f", exe, target(LOADS["half-width"]))[0]
height = retarget("height", args.height) if args.height else struct.unpack_from("<f", exe, target(LOADS["height"]))[0]

hexdir = Path(args.mod) / "Hex"
hexdir.mkdir(parents=True, exist_ok=True)
blob = b"".join(struct.pack(">qq", o, len(b)) + b for o, b in sorted(edits))
(hexdir / "snow.hex").write_bytes(blob)
print(f"snow: centre ({x:g}, {z:g}), x {x - half:g} .. {x + half:g}, z {z - half:g} .. {z + half:g}, falling from y {height:g}")
print("wrote", hexdir / "snow.hex", f"({len(edits)} edits)")

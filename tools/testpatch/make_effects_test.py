"""Effects test round (PC version). Takes a randomizer run (mode 3: a random effect on every weapon) and makes it easy to test:
  - every weapon's chance byte becomes 101 (the effect procs on every attack)
  - every weapon costs 50G, so the first weapon shop can be bought out and sold back over and over
  - the Dokapon Castle area on the overworld gets Weapon spaces: spaces 36 and 39 (the castle's two neighbours) and space 49
    (the lone Dark Space) are changed to the tutorial island's Weapon space (kind 07, param 0x15)

usage: python make_effects_test.py <randomizer Mods/<name> folder> [assets folder]
Edits the randomizer's stageBase_EN.DAT in place and adds stg000_EN.DAT next to it. Original files are only read.
"""
import struct
import sys
from pathlib import Path

mod = Path(sys.argv[1])
workspace = Path(__file__).resolve().parents[3] / "Dokapon-Workspace"
assets = Path(sys.argv[2]) if len(sys.argv) > 2 else workspace / "assets"
if assets.resolve() in mod.resolve().parents or mod.resolve() == assets.resolve():
    sys.exit("refusing to write inside the assets folder")

sbp = mod / "Assets" / "stageBase_EN.DAT"
sb = bytearray(sbp.read_bytes())
start = sb.find(b"\x58\x00\x00\x00\x01\x00", 0x8000)
o, n = start, 0
while sb[o:o + 4] == b"\x58\x00\x00\x00":
    p = o + 8
    while sb[p] != 0:
        p += 1
    p += 1
    while (p - o) % 4:
        p += 1
    sb[p + 2] = 101
    sb[p + 4:p + 8] = (50).to_bytes(4, "little")
    o, n = p + 20, n + 1
assert n == 67, n
sbp.write_bytes(bytes(sb))
print(f"{n} weapons: chance 101, price 50")

sg = bytearray((assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT").read_bytes())
s0 = next(i for i in range(len(sg) - 16) if sg[i:i + 8] == b"\x33\x00\x00\x00\x00\x00\x00\x00")
for space, was in ((36, 0x1E), (39, 0x01), (49, 0x11)):
    r = s0 + 16 * space
    assert struct.unpack_from("<I", sg, r + 4)[0] == space and sg[r + 8] == was, (space, sg[r + 8])
    sg[r + 8:r + 10] = b"\x07\xff"
    sg[r + 12:r + 16] = (0x15).to_bytes(4, "little")
    print(f"space {space}: kind {was:02X} -> Weapon (07)")
(mod / "Assets" / "stg000_EN.DAT").write_bytes(bytes(sg))

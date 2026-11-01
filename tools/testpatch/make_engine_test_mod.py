"""Test setup on top of a mod written by `python -m dokapon_rando shield-effects`: makes shields cheap and tanky and puts a known
set of shields into shop 1 and the starting loadout, so the effects can be tried quickly in a new game.

usage: python make_engine_test_mod.py <mod folder> <start shield id> <shop 1 shield ids, 4 of them, comma separated> [start weapon id]
  every shield: price 50 and +3000 HP; the player starts with the given shield and weapon (default 13, the Sleep Bow).
"""
import struct
import sys
from pathlib import Path

mod = Path(sys.argv[1])
start_shield = int(sys.argv[2])
shop = [int(x) for x in sys.argv[3].split(",")]
assert len(shop) == 4
start_weapon = int(sys.argv[4]) if len(sys.argv) > 4 else 13

path = mod / "Assets" / "stageBase_EN.DAT"
sb = bytearray(path.read_bytes())

# starting equipment table: six (threshold, weapon, shield) entries; the first is what a level 1 player gets
t = sb.find(bytes.fromhex("090101130605 1d0a07".replace(" ", "")))
assert t >= 0
sb[t + 1], sb[t + 2] = start_weapon, start_shield

# shop 1 stock: [weapon ids] 00 [shield ids] 00 per shop, the count per shop is fixed
o = 0x5054
while sb[o]:
    o += 1
o += 1
q = o
while sb[q]:
    q += 1
assert q - o == 4, q - o
sb[o:q] = bytes(shop)

# every shield: 50G, +3000 HP (tail bytes 4-7 price, 16-17 HP)
o, n = sb.find(b"\x5e\x00\x00\x00\x01\x00", 0x8000), 0
while sb[o:o + 4] == b"\x5e\x00\x00\x00":
    p = o + 8
    while sb[p]:
        p += 1
    p += 1
    while (p - o) % 4:
        p += 1
    struct.pack_into("<I", sb, p + 4, 50)
    struct.pack_into("<H", sb, p + 16, struct.unpack_from("<H", sb, p + 16)[0] + 3000)
    o, n = p + 20, n + 1
assert n == 40
path.write_bytes(sb)
print(f"start with weapon {start_weapon} + shield {start_shield}; shop 1 shields {shop}; {n} shields at 50G, +3000 HP")

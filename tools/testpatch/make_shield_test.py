"""Shield test round (PC version): makes the shields cheap and certain so each ability can be tested.
  - every shield costs 50G
  - the shields with an ability (chance byte != 0) get chance 100, so a proc that reads the record happens on every try

usage: python make_shield_test.py <stageBase_EN.DAT>      (edited in place; point it at a copy inside a randomizer Mods/<name>/Assets)
"""
import sys
from pathlib import Path

path = Path(sys.argv[1])
sb = bytearray(path.read_bytes())
o, n = sb.find(b"\x5e\x00\x00\x00\x01\x00", 0x8000), 0
while sb[o:o + 4] == b"\x5e\x00\x00\x00":
    p = o + 8
    while sb[p] != 0:
        p += 1
    p += 1
    while (p - o) % 4:
        p += 1
    name = sb[o + 8:p].split(b"\0")[0].decode()
    if sb[p]:
        print(f"  {sb[o + 4]:>2} {name}: chance {sb[p]} -> 100")
        sb[p] = 100
    sb[p + 4:p + 8] = (50).to_bytes(4, "little")
    o, n = p + 20, n + 1
assert n == 40, n
print(f"{n} shields: price 50")

# the ability shields go into the first shops' stock (deep shops are slow to reach): shop lists start at 0x5054 as
# [weapon ids] 00 [shield ids] 00 per shop; the stock size is fixed, so the ids are replaced in place
STOCK = [[15, 20, 21, 30], [31, 32, 36], [38, 39, 1]]  # Warrior Mirror Binder MetalGuard | Sun Cursed Athena | Dark Dokapon Wooden
o = 0x5054
for shop, ids in enumerate(STOCK):
    while sb[o]:
        o += 1
    o += 1
    q = o
    while sb[q]:
        q += 1
    assert q - o == len(ids), (shop, q - o)
    print(f"shop {shop + 1} shields {list(sb[o:q])} -> {ids}")
    sb[o:q] = bytes(ids)
    o = q + 1
path.write_bytes(bytes(sb))

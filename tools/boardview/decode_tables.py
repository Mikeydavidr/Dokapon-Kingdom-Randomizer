"""Read-only: print the space-kind names and the town/castle table from stageBase_EN.DAT (PC layout).

usage: python decode_tables.py <path to stageBase_EN.DAT>
Kind table: records  87 00 00 00 | kind u32 | name (null-terminated, padded to 4)
Town table: records  6D 00 00 00 | id u8, continent u8, u8, 00 | name (padded to 4) | 12 byte tail (u32, price u32, u32)
"""
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8")  # the game uses full-width placeholder names
data = open(sys.argv[1], "rb").read()


def records(marker, start_filter, tail=0):
    m = struct.pack("<I", marker)
    pos = data.find(m, start_filter)
    while pos >= 0 and data[pos:pos + 4] == m:
        p = pos + 8
        while data[p] != 0:
            p += 1
        name = data[pos + 8:p].decode("utf-8", "replace")
        p += 1
        while (p - pos) % 4:
            p += 1
        yield pos, name, p
        pos = p + tail
        if data[pos:pos + 4] != m:
            return


print("== space kinds (first byte of a space's type)")
for pos, name, p in records(0x87, 0x400):
    print(f"  {struct.unpack_from('<I', data, pos + 4)[0]:02X}  {name or '(blank)'}")

print("\n== towns and castles (a Town space's param[0] is the town id; sign image = NamePlate_EN.texpack entry (position in this list) + 3)")
for pos, name, p in records(0x6D, 0xE00, tail=12):
    tid, cont, b2 = data[pos + 4], data[pos + 5], data[pos + 6]
    a, price, c = struct.unpack_from("<III", data, p)
    print(f"  id {tid:02X}  continent {cont}  name '{name}' (field {p - pos - 8} bytes)  values {a} / price {price} / {c}  @0x{pos:X}")

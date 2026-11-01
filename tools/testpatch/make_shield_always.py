"""Test patch: every ability shield procs on every attack (the roll compares against 101 instead of its hard-coded odds).
The odds are literals in the shield effect function at 0x1401786E0 (see docs/item-records-and-effects.md), not data.

usage: python make_shield_always.py <vanilla DkkStm.exe> <out.hex>      (ConnectModInstaller hex mod)
"""
import struct
import sys

# shield -> (VA of its "cmp cx, imm8", vanilla imm8)
SITES = {"Cursed": (0x140178795, 0x19), "Sun": (0x14017883C, 0xC), "Dokapon": (0x1401788B0, 0xC), "Warrior": (0x14017891E, 0x19),
         "Binder": (0x140178983, 0x19), "Metal Guard": (0x1401789EB, 0xC), "Mirror": (0x140178A57, 0xC)}

exe = open(sys.argv[1], "rb").read()
out = b""
for name, (va, vanilla) in SITES.items():
    o = va - 0x140000000 - 0x1000 + 0x400
    assert exe[o:o + 4] == bytes([0x66, 0x83, 0xF9, vanilla]), (name, exe[o:o + 4].hex())
    out += struct.pack(">qq", o + 3, 1) + bytes([101])
open(sys.argv[2], "wb").write(out)
print(f"wrote {sys.argv[2]}: {len(SITES)} edits")

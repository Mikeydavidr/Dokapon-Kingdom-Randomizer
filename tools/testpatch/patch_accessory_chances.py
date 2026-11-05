"""Accessory proc-chance patch for the current (post Oct 2025) DkkStm.exe: sets the turn-start proc chance of the accessories whose
roll reads a game-state field instead of the accessory record's chance byte.

The turn-start event picker (entry VA 0x1401B1690, see docs/item-records-and-effects.md) rolls `rand % 100 < chance` for the worn
accessory, and the chance is a 32-bit field of the game state (the block the calendar pointer at RVA 0x8A8408 points to):
  Crystal Choker (id 0x13) reads state + 0x746F8 (default 10) at VA 0x1401B200C, "mov r9d, [r10 + 0x746F8]"
  Wallace Badge  (id 0x1E) reads state + 0x746FC (default 10) at VA 0x1401B1FA4, "mov r9d, [r10 + 0x746FC]"
Each load becomes "mov r9d, <percent>" + nop (same length, no cave). The Mirror Necklace and Squid Ring already read the record's
chance byte, so they need no patch. The per-class turn-start rolls (state + 0x746E8..0x746F4) are not touched.

usage: python patch_accessory_chances.py --hex <out.hex> <vanilla DkkStm.exe> [choker=PCT] [wallace=PCT]
Unlisted accessories keep the vanilla 10. Writes a ConnectModInstaller hex mod (repeated [u64 big-endian offset][u64 big-endian length][bytes]).
"""
import struct
import sys

BASE = 0x140000000
TEXT_RVA, TEXT_RAW = 0x1000, 0x400
SITES = {
    "choker": (0x1401B200C, bytes.fromhex("45 8B 8A F8 46 07 00")),    # mov r9d, [r10 + 0x746F8]
    "wallace": (0x1401B1FA4, bytes.fromhex("45 8B 8A FC 46 07 00")),   # mov r9d, [r10 + 0x746FC]
}


def foff(va):
    return va - BASE - TEXT_RVA + TEXT_RAW


def patch(exe, chances):
    for name, pct in chances.items():
        assert 0 <= pct <= 100, (name, pct)
        site, old = SITES[name]
        o = foff(site)
        assert exe[o:o + len(old)] == old, (name, hex(site), exe[o:o + len(old)].hex())
        exe[o:o + len(old)] = b"\x41\xB9" + struct.pack("<I", pct) + b"\x90"   # mov r9d, imm32 ; nop
    return exe


def hex_mod(vanilla, patched):
    runs, i = [], 0
    while i < len(vanilla):
        if vanilla[i] != patched[i]:
            j = i
            while j < len(vanilla) and (vanilla[j] != patched[j] or any(vanilla[k] != patched[k] for k in range(j + 1, min(j + 8, len(vanilla))))):
                j += 1
            runs.append((i, bytes(patched[i:j])))
            i = j
        else:
            i += 1
    return b"".join(struct.pack(">qq", off, len(data)) + data for off, data in runs), len(runs)


if __name__ == "__main__":
    args = sys.argv[1:]
    assert args[0] == "--hex"
    out_path, exe_path = args[1], args[2]
    chances = {a.split("=")[0]: int(a.split("=")[1]) for a in args[3:]}
    vanilla = open(exe_path, "rb").read()
    exe = patch(bytearray(vanilla), chances)
    data, n = hex_mod(vanilla, exe)
    open(out_path, "wb").write(data)
    print(f"wrote {out_path}: {n} edits; chances {chances or 'vanilla'}")

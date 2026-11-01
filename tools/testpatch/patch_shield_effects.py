"""Shield-effect patch for the current (post Oct 2025) DkkStm.exe: lets any shield carry any ability shield's effect.

The shield effect function (entry VA 0x1401786D0, see docs/item-records-and-effects.md) switches on the equipped shield's id
(15..39). This patch sends the id through a byte table first, so shield N behaves like the shield whose id the table gives for N.
Three places read the id and all go through the table:
  1. the effect function itself (VA 0x1401786E6, "movzx eax, byte [rax + 0x148]")
  2. the second half of the Dokapon Shield's effect (VA 0x140175405, "cmp byte [rax + 0x148], 0x27")
  3. the battle-script value fetch (VA 0x1401717D6, "movzx r9d, byte [rax + 0x148]"): the animation/message scripts ask for the
     defender's shield id this way, so with it remapped the effect's own animation and text play too
Odds are literals inside each effect's case (not the record's chance byte), so an effect keeps its own odds wherever it goes.
Other readers of the shield id (shop code, AI) still see the real id.

usage: python patch_shield_effects.py --hex <out.hex> <vanilla DkkStm.exe> [shield_id=effect_id ...]
  effect_id is the id of the vanilla shield whose effect to use (15 Warrior, 20 Mirror, 21 Binder, 30 Metal Guard, 31 Sun,
  32 Cursed, 36 Athena's, 38 Dark, 39 Dokapon; 0 = no effect). Unlisted shields keep their own id (vanilla behaviour).
Writes a ConnectModInstaller hex mod (repeated [u64 big-endian offset][u64 big-endian length][bytes]).
"""
import struct
import sys

BASE = 0x140000000
TEXT_RVA, TEXT_RAW = 0x1000, 0x400
TABLE_RVA = 0x44C4A0   # 48 bytes, index = shield id (cave at the end of .text; the weapon patch uses up to 0x44C487)
HELPER_A_RVA = 0x44C4D0
HELPER_B_RVA = 0x44C4F0
HELPER_C_RVA = 0x44C510
SITE_A, OLD_A = 0x1401786E6, bytes.fromhex("0F B6 80 48 01 00 00")   # movzx eax, byte [rax + 0x148]
SITE_B, OLD_B = 0x140175405, bytes.fromhex("80 B8 48 01 00 00 27")   # cmp byte [rax + 0x148], 0x27
SITE_C, OLD_C = 0x1401717D6, bytes.fromhex("44 0F B6 88 48 01 00 00")   # movzx r9d, byte [rax + 0x148]


def foff(va):
    return va - BASE - TEXT_RVA + TEXT_RAW


def helper(rva, tail):
    """rax = shield struct -> eax = table[id]; r11 is preserved; then `tail` (the replaced instruction's follow-up) and ret."""
    head = bytes.fromhex("0F B6 80 48 01 00 00"   # movzx eax, byte [rax + 0x148]
                         "41 53")                 # push r11
    lea_end = rva + len(head) + 7
    lea = bytes.fromhex("4C 8D 1D") + struct.pack("<i", (TABLE_RVA) - lea_end)   # lea r11, [rip + table]
    return head + lea + bytes.fromhex("41 0F B6 04 03"   # movzx eax, byte [r11 + rax]
                                      "41 5B") + tail + b"\xC3"   # pop r11 ; tail ; ret


def helper_c(rva):
    """rax = shield struct -> r9d = table[id]; every other register (rax included) is preserved."""
    head = bytes.fromhex("50"                      # push rax
                         "44 0F B6 88 48 01 00 00")  # movzx r9d, byte [rax + 0x148]
    lea_end = rva + len(head) + 7
    lea = bytes.fromhex("48 8D 05") + struct.pack("<i", TABLE_RVA - lea_end)   # lea rax, [rip + table]
    return head + lea + bytes.fromhex("46 0F B6 0C 08"   # movzx r9d, byte [rax + r9]
                                      "58 C3")           # pop rax ; ret


def patch(exe, mapping):
    sec = next(h for h in (struct.unpack_from("<I", exe, 0x3C)[0] + 24 + struct.unpack_from("<H", exe, struct.unpack_from("<I", exe, 0x3C)[0] + 20)[0] + 40 * i
                           for i in range(struct.unpack_from("<H", exe, struct.unpack_from("<I", exe, 0x3C)[0] + 6)[0]))
               if exe[h:h + 8].rstrip(b"\0") == b".text")
    vsize, rawsize = struct.unpack_from("<I", exe, sec + 8)[0], struct.unpack_from("<I", exe, sec + 16)[0]
    assert (vsize, rawsize) == (0x44B410, 0x44B600), "not the expected exe build"
    struct.pack_into("<I", exe, sec + 8, rawsize)  # map the slack (the weapon patch does the same; the edit is identical)
    table = bytearray(range(48))
    for sid, eff in mapping.items():
        assert 1 <= sid < 48 and 0 <= eff < 48, (sid, eff)
        table[sid] = eff
    assert not any(exe[foff(BASE + TABLE_RVA):foff(BASE + HELPER_C_RVA) + 0x20]), "cave is not empty"
    exe[foff(BASE + TABLE_RVA):foff(BASE + TABLE_RVA) + 48] = table
    a = helper(HELPER_A_RVA, b"")
    b = helper(HELPER_B_RVA, bytes.fromhex("3C 27"))   # cmp al, 0x27 (flags survive pop/ret)
    c = helper_c(HELPER_C_RVA)
    assert len(a) <= 0x20 and len(b) <= 0x20 and len(c) <= 0x20, (len(a), len(b), len(c))
    exe[foff(BASE + HELPER_A_RVA):foff(BASE + HELPER_A_RVA) + len(a)] = a
    exe[foff(BASE + HELPER_B_RVA):foff(BASE + HELPER_B_RVA) + len(b)] = b
    exe[foff(BASE + HELPER_C_RVA):foff(BASE + HELPER_C_RVA) + len(c)] = c
    for site, old, rva in ((SITE_A, OLD_A, HELPER_A_RVA), (SITE_B, OLD_B, HELPER_B_RVA), (SITE_C, OLD_C, HELPER_C_RVA)):
        o = foff(site)
        assert exe[o:o + len(old)] == old, (hex(site), exe[o:o + len(old)].hex())
        nop = {7: b"\x66\x90", 8: b"\x0F\x1F\x00"}[len(old)]   # pad to the replaced length with a 2- or 3-byte nop
        exe[o:o + len(old)] = b"\xE8" + struct.pack("<i", (BASE + rva) - (site + 5)) + nop   # call helper
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
    mapping = {int(a.split("=")[0]): int(a.split("=")[1]) for a in args[3:]}
    vanilla = open(exe_path, "rb").read()
    exe = patch(bytearray(vanilla), mapping)
    data, n = hex_mod(vanilla, exe)
    open(out_path, "wb").write(data)
    print(f"wrote {out_path}: {n} edits; mapping {mapping or 'identity'}")

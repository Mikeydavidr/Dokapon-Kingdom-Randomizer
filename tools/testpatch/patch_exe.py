"""Weapon-effect patch for the current (post Oct 2025) DkkStm.exe. Patches a COPY of the exe in place.

What it changes (all inside the attacker weapon-effect function at VA 0x140178C50):
  1. The effect switch covers weapon ids 1..67 instead of 13..67. The byte table that picks a case for each weapon id moves
     to unused space at the end of .text (the section's VirtualSize grows to its raw size so that space is mapped).
  2. Each effect's first proc roll (roll 0..100, proc when roll < chance) compares against the weapon's own chance byte
     (record tail byte 2, in memory at weapon struct +0x139) instead of a constant compiled into the code. Second rolls
     (follow-ups that only happen after the first one procs) keep their constants.

usage: python patch_exe.py <DkkStm.exe copy> [id=case ...]
       python patch_exe.py --hex <out.hex> <vanilla DkkStm.exe> [id=case ...]
  id=case assigns effect case 0..22 to weapon id 1..67 (22 = no effect); unspecified ids keep the vanilla case.
  --hex leaves the exe alone and writes the changes as a ConnectModInstaller hex mod (Mods/<mod>/Hex/*.hex):
  repeated [u64 big-endian file offset][u64 big-endian length][bytes].
"""
import struct
import sys

BASE = 0x140000000
TEXT_RVA, TEXT_RAW = 0x1000, 0x400
CASE_NONE = 22


def foff(va):
    return va - BASE - TEXT_RVA + TEXT_RAW


# vanilla table: index = weapon id - 13, ids 13..67
OLD_TABLE_RVA = 0x179E38
# switch head: add eax, -0xd / cmp eax, 0x36 / movzx eax, byte ptr [r12 + rax + 0x179e38]
ADD_VA, CMP_VA, MOVZX_VA = 0x140178CB5, 0x140178CB8, 0x140178CD2
# first proc roll of every case that has one: "sub ecx, eax; cmp cx, imm8" (case -> VA of the cmp)
FIRST_ROLL = {0: 0x140178EDA, 1: 0x140178F3F, 2: 0x14017927D, 3: 0x140178FA4, 4: 0x140179218, 5: 0x1401795B9,
              6: 0x1401790D3, 7: 0x1401793B7, 8: 0x1401797C4, 9: 0x140178E7B, 10: 0x1401791B3, 12: 0x140178DF2,
              13: 0x140179009, 14: 0x14017914E, 15: 0x1401794B8, 16: 0x1401798C5, 17: 0x14017906E, 18: 0x1401796BA,
              19: 0x140178D5B, 20: 0x1401799C6, 21: 0x140179AC7}  # case 11 (Soul Eater) has no roll: always on
# the constant each case used, so the data side can keep vanilla odds: case -> chance
VANILLA_CHANCE = {0: 12, 1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 25, 8: 12, 9: 8, 10: 12, 12: 12, 13: 12, 14: 12,
                  15: 25, 16: 12, 17: 12, 18: 12, 19: 25, 20: 25, 21: 50}

# cave at the end of .text (raw data past VirtualSize, zero in the file)
NEW_TABLE_RVA = 0x44C420  # 67 bytes, index = weapon id - 1
HELPER_RVA = 0x44C470
HELPER = bytes.fromhex(
    "29 C1"                 # sub ecx, eax              (the instruction the call replaced)
    "48 8B 46 18"           # mov rax, [rsi + 0x18]     (rsi = battle character, +0x18 = its weapon struct)
    "0F B6 80 39 01 00 00"  # movzx eax, byte [rax + 0x139]   (the record's chance byte)
    "66 39 C1"              # cmp cx, ax                (roll vs chance; the caller's jae skips the effect)
    "C3")                   # ret                       (flags survive the ret)


def vanilla_table(exe):
    old = exe[foff(BASE + OLD_TABLE_RVA):foff(BASE + OLD_TABLE_RVA) + 55]
    return [CASE_NONE] * 12 + list(old)  # ids 1..67


def text_header(exe):
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    nsec = struct.unpack_from("<H", exe, pe + 6)[0]
    opt = struct.unpack_from("<H", exe, pe + 20)[0]
    sec = pe + 24 + opt
    for i in range(nsec):
        h = sec + 40 * i
        if exe[h:h + 8].rstrip(b"\0") == b".text":
            return h
    raise SystemExit("no .text section")


def patch(exe, cases):
    """exe: bytearray of the vanilla current-build exe; cases: list of 67 case numbers (index = weapon id - 1)."""
    assert len(cases) == 67 and all(0 <= c <= CASE_NONE for c in cases)
    h = text_header(exe)
    vsize, rva, rawsize = struct.unpack_from("<III", exe, h + 8)[0], struct.unpack_from("<I", exe, h + 12)[0], struct.unpack_from("<I", exe, h + 16)[0]
    assert (vsize, rva, rawsize) == (0x44B410, 0x1000, 0x44B600), "not the expected exe build"
    cave = foff(BASE + NEW_TABLE_RVA), foff(BASE + HELPER_RVA) + len(HELPER)
    assert not any(exe[foff(BASE + 0x1000 + vsize):TEXT_RAW + rawsize]), "end of .text is not empty"

    # 1. map the slack and put the new table there
    struct.pack_into("<I", exe, h + 8, rawsize)
    exe[cave[0]:cave[0] + 67] = bytes(cases)
    exe[foff(BASE + HELPER_RVA):cave[1]] = HELPER

    # switch head: ids 1..67
    def expect_and_put(va, old, new):
        o = foff(va)
        assert exe[o:o + len(old)] == old, (hex(va), exe[o:o + len(old)].hex())
        exe[o:o + len(new)] = new
    expect_and_put(ADD_VA, bytes.fromhex("83 C0 F3"), bytes.fromhex("83 C0 FF"))
    expect_and_put(CMP_VA, bytes.fromhex("83 F8 36"), bytes.fromhex("83 F8 42"))
    expect_and_put(MOVZX_VA, bytes.fromhex("41 0F B6 84 04") + struct.pack("<I", OLD_TABLE_RVA),
                   bytes.fromhex("41 0F B6 84 04") + struct.pack("<I", NEW_TABLE_RVA))

    # 2. first rolls read the record's chance byte
    for case, cmp_va in FIRST_ROLL.items():
        call_va = cmp_va - 2  # the "sub ecx, eax" before the cmp
        o = foff(call_va)
        assert exe[o:o + 5] == bytes.fromhex("2B C8 66 83 F9"), (case, hex(cmp_va), exe[o:o + 6].hex())
        assert exe[o + 5] == VANILLA_CHANCE[case], (case, exe[o + 5])
        rel = (BASE + HELPER_RVA) - (call_va + 5)
        exe[o:o + 6] = b"\xE8" + struct.pack("<i", rel) + b"\x90"
    return exe


def hex_mod(vanilla, patched):
    """The differences as a ConnectModInstaller .hex file (runs closer than 8 bytes are merged)."""
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
    hex_out = None
    if args[0] == "--hex":
        hex_out, args = args[1], args[2:]
    path = args[0]
    if hex_out is None and "steamapps" in path.lower():
        sys.exit("refusing to patch the Steam install")
    vanilla = open(path, "rb").read()
    exe = bytearray(vanilla)
    cases = vanilla_table(exe)
    for arg in args[1:]:
        wid, case = (int(x) for x in arg.split("="))
        cases[wid - 1] = case
    patch(exe, cases)
    if hex_out:
        data, n = hex_mod(vanilla, exe)
        open(hex_out, "wb").write(data)
        print(f"wrote {hex_out}: {n} edits")
    else:
        open(path, "wb").write(exe)
        print("patched", path)
    print("  effect table (id:case, non-empty):", {i + 1: c for i, c in enumerate(cases) if c != CASE_NONE})

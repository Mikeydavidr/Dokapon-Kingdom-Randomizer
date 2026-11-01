"""Appends a new executable section to DkkStm.exe as a ConnectModInstaller hex mod. Needs an installer that lets a hex edit
reach past the end of the exe (the stock one refuses).

The PE edits are the same ones DKCedit makes, but computed from the exe instead of hard-coded: section count + 1, SizeOfImage,
one more section header (the header table has room for exactly one), and the section's bytes appended at the end of the file.
Code in the section is reached by direct calls/jumps from patched spots in .text (an indirect call would have to pass Control
Flow Guard, which only knows the original sections).

usage: python add_section.py --hex <out.hex> <vanilla DkkStm.exe> [--proto | --proto-int3 | --loadout WEAPON,SHIELD,ACCESSORY]
  --proto       the entry point goes through a stub in the new section (nop; jmp original entry): boots only if the section works
  --proto-int3  same with an int3 first, so a debugger sees it run (the game crashes without a debugger)
  --loadout     the human player starts a new game with these weapon, shield and accessory ids (accessory 0 = none) instead of
                Knife / Wooden Shield / nothing. Custom code in the new section, called from the game's own new-character setup.
"""
import struct
import sys

NAME = b".dkmod\0\0"
CHARACTERISTICS = 0x60000020  # code, executable, readable


def align(v, a):
    return (v + a - 1) // a * a


class Exe:
    def __init__(self, data):
        self.d = data
        self.pe = struct.unpack_from("<I", data, 0x3C)[0]
        self.nsec = struct.unpack_from("<H", data, self.pe + 6)[0]
        self.opt = self.pe + 24
        self.sec_align, self.file_align = struct.unpack_from("<II", data, self.opt + 32)
        self.table = self.opt + struct.unpack_from("<H", data, self.pe + 20)[0]
        last_rva_end, last_raw_end, first_raw = 0, 0, 1 << 62
        for i in range(self.nsec):
            h = self.table + 40 * i
            vs, rva, rs, ro = struct.unpack_from("<IIII", data, h + 8)
            last_rva_end = max(last_rva_end, rva + vs)
            last_raw_end = max(last_raw_end, ro + rs)
            first_raw = min(first_raw, ro)
        self.new_rva = align(last_rva_end, self.sec_align)
        self.new_raw = align(max(last_raw_end, len(data)), self.file_align)
        self.entry = struct.unpack_from("<I", data, self.opt + 16)[0]
        self.new_header = self.table + 40 * self.nsec
        assert self.new_header + 40 <= first_raw, "no room for another section header"
        assert len(data) == last_raw_end, "data after the last section (certificate/overlay): not handled"


def build(vanilla, content):
    """-> (patched exe bytes, new section's RVA). content: bytes, or a function of the section's RVA."""
    e = Exe(vanilla)
    code = content(e.new_rva) if callable(content) else content
    raw_size = align(len(code), e.file_align)
    virt_size = len(code)
    out = bytearray(vanilla)
    out += b"\0" * (e.new_raw - len(out))
    out += code + b"\0" * (raw_size - len(code))
    struct.pack_into("<H", out, e.pe + 6, e.nsec + 1)
    struct.pack_into("<I", out, e.opt + 56, align(e.new_rva + virt_size, e.sec_align))  # SizeOfImage
    out[e.new_header:e.new_header + 40] = NAME + struct.pack("<IIIIIIHHI", virt_size, e.new_rva, raw_size, e.new_raw, 0, 0, 0, 0, CHARACTERISTICS)
    return out, e.new_rva


def hex_edits(vanilla, patched):
    """Differences as a ConnectModInstaller .hex (runs closer than 8 bytes merge); the appended bytes are one explicit run."""
    n = len(vanilla)
    runs, i = [], 0
    while i < n:
        if vanilla[i] != patched[i]:
            j = i
            while j < n and (vanilla[j] != patched[j] or any(vanilla[k] != patched[k] for k in range(j + 1, min(j + 8, n)))):
                j += 1
            runs.append((i, bytes(patched[i:j])))
            i = j
        else:
            i += 1
    if len(patched) > n:
        runs.append((n, bytes(patched[n:])))
    return b"".join(struct.pack(">qq", off, len(data)) + data for off, data in runs), len(runs)


def proto(vanilla, int3):
    """Entry point -> stub in the new section -> original entry point."""
    e = Exe(vanilla)

    def code(rva):
        stub = (b"\xcc" if int3 else b"\x90") + b"\xe9"
        return stub + struct.pack("<i", e.entry - (rva + len(stub) + 4))
    patched, rva = build(vanilla, code)
    struct.pack_into("<I", patched, e.opt + 16, rva)
    return patched


BASE = 0x140000000
# new-character setup (function 0x14010FC60): "if the weapon / shield slot is empty, give the default"; each default is one
#   mov byte ptr [rbx + 0xbe / 0xbf], 1      (7 bytes) - replaced by a call into the new section + a 2-byte nop.
# rbx = the player struct; [rbx + 0x70] == 0 marks the human player (the code right after sets the "new item" UI flag only then).
WEAPON_SITE, SHIELD_SITE = 0x14011055F, 0x140110597
WEAPON_OLD = bytes.fromhex("C6 83 BE 00 00 00 01")
SHIELD_OLD = bytes.fromhex("C6 83 BF 00 00 00 01")


def loadout(vanilla, weapon, shield, accessory):
    """The two stubs: do the game's default, then for the human player replace it. Returns the patched exe."""
    e = Exe(vanilla)

    def stub(slot, value, extra=b""):
        return (bytes.fromhex("C6 83") + struct.pack("<IB", slot, 1)      # mov byte [rbx + slot], 1   (the game's default)
                + bytes.fromhex("83 7B 70 00")                              # cmp dword [rbx + 0x70], 0
                + bytes([0x75, 7 + len(extra)])                             # jne done
                + bytes.fromhex("C6 83") + struct.pack("<IB", slot, value)  # mov byte [rbx + slot], value
                + extra
                + bytes([0xC3]))                                            # done: ret

    acc = bytes.fromhex("C6 83") + struct.pack("<IB", 0xC0, accessory) if accessory else b""
    w_stub, s_stub = stub(0xBE, weapon, acc), stub(0xBF, shield)

    def code(rva):
        return w_stub + s_stub
    patched, rva = build(vanilla, code)
    for site, old, target in ((WEAPON_SITE, WEAPON_OLD, rva), (SHIELD_SITE, SHIELD_OLD, rva + len(w_stub))):
        o = site - BASE - 0x1000 + 0x400
        assert patched[o:o + 7] == old, hex(site)
        patched[o:o + 7] = bytes([0xE8]) + struct.pack("<i", (BASE + target) - (site + 5)) + bytes([0x66, 0x90])  # call stub; 2-byte nop
    return patched


if __name__ == "__main__":
    args = sys.argv[1:]
    assert args[0] == "--hex"
    out_path, exe_path, mode = args[1], args[2], args[3]
    vanilla = open(exe_path, "rb").read()
    if mode == "--loadout":
        patched = loadout(vanilla, *(int(x) for x in args[4].split(",")))
    else:
        patched = proto(vanilla, mode == "--proto-int3")
    data, n = hex_edits(vanilla, patched)
    open(out_path, "wb").write(data)
    print(f"wrote {out_path}: {n} edits, exe grows {len(vanilla)} -> {len(patched)} bytes")

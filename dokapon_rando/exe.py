"""DkkStm.exe (current build) and the hex mods that patch it.

The randomizer never rewrites the exe itself: it writes ConnectModInstaller hex mods (Mods/<name>/Hex/*.hex), a list of
[u64 big-endian file offset][u64 big-endian length][bytes], which the installer applies to a fresh copy of the vanilla exe.
Code is added in the unused end of the .text section (the slack between its VirtualSize and its raw size).
"""
import struct
from pathlib import Path

BASE = 0x140000000
TEXT_RVA, TEXT_RAW = 0x1000, 0x400
TEXT_VIRTUAL_SIZE, TEXT_RAW_SIZE = 0x44B410, 0x44B600   # of the current build's .text; the slack in between is zero


def foff(va: int) -> int:
    """File offset of a virtual address inside .text."""
    return va - BASE - TEXT_RVA + TEXT_RAW


def rva_to_va(rva: int) -> int:
    return BASE + rva


class HexMod:
    """A set of byte edits to the vanilla exe, written as a .hex file."""

    def __init__(self) -> None:
        self.edits: dict[int, bytes] = {}

    def add(self, offset: int, data: bytes) -> None:
        if self.edits.get(offset) == bytes(data):
            return   # the same edit twice (e.g. the weapon and shield patches both map the slack) is fine
        for o, d in self.edits.items():
            if offset < o + len(d) and o < offset + len(data):
                raise ValueError(f"edit at {offset:#x} overlaps the one at {o:#x}")
        self.edits[offset] = bytes(data)

    def to_bytes(self) -> bytes:
        return b"".join(struct.pack(">qq", o, len(d)) + d for o, d in sorted(self.edits.items()))

    def write(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.to_bytes())
        return p

    def apply(self, exe: bytes | bytearray) -> bytearray:
        """What the installer does: the edits laid over a copy of the vanilla exe."""
        out = bytearray(exe)
        for o, d in self.edits.items():
            out[o:o + len(d)] = d
        return out


class Exe:
    """The vanilla exe, checked to be the build the patches were written for."""

    def __init__(self, data: bytes | bytearray):
        self.data = bytes(data)
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        nsec = struct.unpack_from("<H", self.data, pe + 6)[0]
        opt = struct.unpack_from("<H", self.data, pe + 20)[0]
        sec = pe + 24 + opt
        for i in range(nsec):
            h = sec + 40 * i
            if self.data[h:h + 8].rstrip(b"\0") == b".text":
                self.text_header = h
                break
        else:
            raise ValueError("no .text section")
        vsize, rva, rawsize = struct.unpack_from("<III", self.data, self.text_header + 8)[0], \
            struct.unpack_from("<I", self.data, self.text_header + 12)[0], struct.unpack_from("<I", self.data, self.text_header + 16)[0]
        if (vsize, rva, rawsize) != (TEXT_VIRTUAL_SIZE, TEXT_RVA, TEXT_RAW_SIZE):
            raise ValueError("this DkkStm.exe isn't the current (October 2025) build the patches were written for")

    def expect(self, va: int, old: bytes) -> int:
        """File offset of `va`, checking the vanilla bytes there are `old`."""
        o = foff(va)
        if self.data[o:o + len(old)] != old:
            raise ValueError(f"unexpected bytes at {va:#x}: {self.data[o:o + len(old)].hex(' ')}")
        return o

    def check_cave_empty(self, rva_start: int, rva_end: int) -> None:
        if any(self.data[foff(rva_to_va(rva_start)):foff(rva_to_va(rva_end))]):
            raise ValueError("the free space at the end of .text isn't empty")

    def map_slack_edit(self) -> tuple[int, bytes]:
        """Make the zero padding after .text's VirtualSize part of the mapped section, so code placed there runs."""
        return self.text_header + 8, struct.pack("<I", TEXT_RAW_SIZE)

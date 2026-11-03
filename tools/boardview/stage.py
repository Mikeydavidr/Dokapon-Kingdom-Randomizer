"""Edit the space records of board 0 (stg000_EN.DAT): move records between spaces, and the signs (nameplates) with them.

A space record is 16 bytes: 33 00 00 00 | index u32 | type 2 bytes | group | 00 | param 4 bytes. Moving a record moves the
8 bytes after the index (what the space is). The nameplates are a list near the end of the file, entries of
u32 0x92, u16 space, u16 plate; right after it, the signs' placement: entries of u32 0x91, u32 space, u16 height?, u16 depth?
(item stores 30/22, magic stores 32/12, castles 35/10 or 32-35/20: a castle's sign stands higher and further forward than a
store's). A moved record takes its plate and its sign placement along.
"""
import struct
from pathlib import Path

from boardlib import load_board


class Stage:
    def __init__(self, assets: Path):
        self.path = assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT"
        self.data = bytearray(self.path.read_bytes())
        spaces, _ = load_board(assets, 0)
        self.offset = {s["id"]: s["offset"] for s in spaces}
        self.plaque_start = self.find_plaques(bytes(self.data))
        assert self.plaque_start > 0, "nameplate list not found"

    @staticmethod
    def find_plaques(d: bytes, run: int = 40) -> int:
        """Offset of the nameplate list: the first 0x92 entry followed by `run` more (its first entry changes when records move)."""
        o = d.find(b"\x92\x00\x00\x00")
        while o >= 0:
            if all(d[o + 8 * i: o + 8 * i + 4] == b"\x92\x00\x00\x00" for i in range(run)):
                return o
            o = d.find(b"\x92\x00\x00\x00", o + 1)
        return -1

    def plaques(self) -> dict[int, int]:
        """space -> file offset of its nameplate entry."""
        o, out = self.plaque_start, {}
        while struct.unpack_from("<I", self.data, o)[0] == 0x92:
            out[struct.unpack_from("<H", self.data, o + 4)[0]] = o
            o += 8
        return out

    def sign_placements(self) -> dict[int, int]:
        """space -> file offset of its sign placement entry (u32 0x91, u32 space, u16, u16)."""
        o = self.plaque_start
        while struct.unpack_from("<I", self.data, o)[0] == 0x92:
            o += 8
        o = bytes(self.data).find(b"\x91\x00\x00\x00", o)
        out = {}
        while o >= 0 and o + 12 <= len(self.data) and struct.unpack_from("<I", self.data, o)[0] == 0x91:
            out[struct.unpack_from("<I", self.data, o + 4)[0]] = o
            o += 12
        return out

    def move(self, dest: dict[int, int]) -> None:
        """Move the record, sign and sign placement of every space s in dest to space dest[s]; dest must be a permutation of
        its keys."""
        assert sorted(dest) == sorted(dest.values()), "records can only trade places"
        old = {s: bytes(self.data[self.offset[s] + 8: self.offset[s] + 16]) for s in dest}
        for s, t in dest.items():
            self.data[self.offset[t] + 8: self.offset[t] + 16] = old[s]
        plaques, placements = self.plaques(), self.sign_placements()
        for s, t in dest.items():
            if s in plaques:
                struct.pack_into("<H", self.data, plaques[s] + 4, t)
            if s in placements:
                struct.pack_into("<I", self.data, placements[s] + 4, t)

    def save(self, out: Path) -> Path:
        out.mkdir(parents=True, exist_ok=True)
        path = out / self.path.name
        path.write_bytes(self.data)
        return path

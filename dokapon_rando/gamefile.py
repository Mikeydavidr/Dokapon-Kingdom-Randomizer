"""The game's data file (stageBase_EN.DAT) and the two PC builds it comes in.

The October 2025 update re-encoded some text as UTF-8, so every offset after the first few KB moved. The two builds are told
apart by file size. Offsets are listed per build: index 0 = before the update (the Chinese language patch), 1 = current.
"""
from dataclasses import dataclass
from pathlib import Path

FILE_NAME = "stageBase_EN.DAT"


@dataclass(frozen=True)
class Build:
    index: int
    size: int
    label: str
    # where each table's records begin (approximately: the table reader searches around it for the first record)
    weapons: int
    shields: int
    accessories: int
    magic_offense: int


BUILDS = (
    Build(0, 725136, "before the October 2025 update", 0x83CC, 0xAB48, 0xBDAC, 0x14C4C),
    Build(1, 725600, "current (October 2025 update)", 0x83F0, 0xAB7C, 0xBDE4, 0x14C94),
)


def detect_build(data: bytes) -> Build | None:
    for b in BUILDS:
        if len(data) == b.size:
            return b
    return None


class GameFile:
    """The file's bytes plus which build they are. `data` is a bytearray the modes edit in place."""

    def __init__(self, path: str | Path, data: bytes | None = None, build: Build | None = None):
        self.path = Path(path)
        raw = data if data is not None else self.path.read_bytes()
        self.data = bytearray(raw)
        self.build = build or detect_build(raw)
        if self.build is None:
            raise ValueError(f"{self.path.name} is {len(raw)} bytes, which matches neither known build of the game")

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self.path
        target.write_bytes(bytes(self.data))
        return target

    def backup(self) -> Path:
        """Copy the file next to itself as <name>.backup, unless one is already there."""
        dest = self.path.with_name(self.path.name + ".backup")
        if not dest.exists():
            dest.write_bytes(self.path.read_bytes())
        return dest

"""Tables of equipment/item records inside stageBase_EN.DAT.

Every record is laid out as
    [marker 4][id 1] [3 prefix bytes] [name, null-terminated and padded to 4] [tail]
(weapons, shields, accessories; see docs/item-records-and-effects.md). A table is a run of records whose ids count up from
`first_id`. The shufflers move an item's *identity* between slots and keep the slot's own price, stats and id: a mask string says,
byte by byte, what stays with the slot ('S') and what moves with the identity ('I'). The name always moves.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    label: str
    start: int           # approximate file offset; the reader searches +-0x100 around it
    marker: int          # first byte of the 4-byte marker (the other three are zero)
    first_id: int
    prefix_mask: str     # one letter per prefix byte
    tail_mask: str       # one letter per tail byte; its length is the tail length
    price_offset: int    # where the u32 price sits in the tail, -1 if the table has none


@dataclass
class Record:
    name: str
    head: bytes          # marker + id
    prefix: bytes
    name_field: bytes    # the name with its terminator and padding
    tail: bytes

    def serialize(self) -> bytes:
        return self.head + self.prefix + self.name_field + self.tail

    @property
    def id(self) -> int:
        return self.head[4]

    def price(self, spec: TableSpec) -> int:
        return int.from_bytes(self.tail[spec.price_offset:spec.price_offset + 4], "little")


@dataclass
class Table:
    spec: TableSpec
    start: int
    end: int
    records: list[Record]

    def serialize(self) -> bytes:
        return b"".join(r.serialize() for r in self.records)


def read_table(data: bytes | bytearray, spec: TableSpec) -> Table | None:
    """Read a table into records, or None if the layout isn't what's expected (so the caller can leave the file alone)."""
    marker = spec.marker.to_bytes(4, "little")
    n = len(data)
    o = -1
    for s in range(max(0, spec.start - 0x100), min(spec.start + 0x100, n - 8)):
        if data[s:s + 4] == marker and data[s + 4] == spec.first_id:
            o = s
            break
    if o < 0:
        return None
    start = o
    records: list[Record] = []
    while o + 8 <= n and data[o:o + 4] == marker and data[o + 4] == spec.first_id + len(records):
        p = o + 8
        while p < n and data[p] != 0:
            p += 1
        if p >= n:
            return None
        name = bytes(data[o + 8:p]).decode("utf-8", errors="replace")
        p += 1
        while (p - o) % 4:
            p += 1
        end = p + len(spec.tail_mask)
        if end > n:
            return None
        records.append(Record(name, bytes(data[o:o + 5]), bytes(data[o + 5:o + 8]), bytes(data[o + 8:p]), bytes(data[p:end])))
        o = end
    return Table(spec, start, o, records) if records else None


def write_table(data: bytearray, table: Table) -> None:
    """Write a table back where it was read. Refuses a table whose size changed (names pad to 4, so shuffles never change it)."""
    blob = table.serialize()
    if len(blob) != table.end - table.start:
        raise ValueError(f"the {table.spec.label.lower()} table changed size")
    data[table.start:table.end] = blob

"""Board 0 test mod: swap store spaces and a town, cut one link, add one, so the game shows what follows the data.

usage: python make_board_test.py <mod folder> [assets folder]
Writes <mod>/Assets/stg000_EN.DAT and <mod>/Assets/CHAIN_000.DAT (Assets is flat, files are matched by name).
Reads the originals from the extracted assets folder (default G:/Programming/Dokapon-Workspace/assets) and never writes there.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from boardlib import load_board

mod = Path(sys.argv[1])
assets = Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else Path("G:/Programming/Dokapon-Workspace/assets")
spaces, links = load_board(assets, 0)
stg = bytearray((assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT").read_bytes())
chain = bytearray((assets / "CommonData" / "fieldChain" / "CHAIN_000.DAT").read_bytes())
byid = {s["id"]: s for s in spaces}

SWAPS = [(18, 24),   # Item Store <-> Weapon Store, near the start (works in game)
         (21, 20),   # Balle (town id 5, blocked by a monster) <-> town id 6: does the blocker follow the id or the space?
         (2, 5)]     # Magic Store <-> a plain space
for arg in sys.argv:                      # --swap=268-122,87-170 adds more record swaps
    if arg.startswith("--swap="):
        SWAPS += [tuple(int(v) for v in pair.split("-")) for pair in arg[7:].split(",")]
CUT = (14, 6)        # the castle's link towards the start
ADD = (3, 21)        # Coliseum <-> the space that now holds the Magic Store


def swap(a: int, b: int) -> None:
    oa, ob = byid[a]["offset"] + 8, byid[b]["offset"] + 8      # type, group, param: everything after the index
    stg[oa:oa + 8], stg[ob:ob + 8] = bytes(stg[ob:ob + 8]), bytes(stg[oa:oa + 8])
    move_plaques(a, b)


PLAQUE_START = bytes(stg).find(bytes.fromhex("9200000012000100"))   # looked up in the unmodified file: item store 18, plate 1
assert PLAQUE_START > 0, "plaque list not found"


def plaque_entries() -> list[int]:
    """File offsets of the nameplate placement list at the end of stg000: 92 entries of u32 0x92, u16 space, u16 plate."""
    o = PLAQUE_START
    found = []
    while struct.unpack_from("<I", stg, o)[0] == 0x92:
        found.append(o)
        o += 8
    return found


def move_plaques(a: int, b: int) -> None:
    """The plate that sat on space a now sits on b and vice versa (plates follow the records)."""
    at = {struct.unpack_from("<H", stg, o + 4)[0]: o for o in plaque_entries()}
    if a in at:
        struct.pack_into("<H", stg, at[a] + 4, b)
    if b in at:
        struct.pack_into("<H", stg, at[b] + 4, a)


def slots(i: int) -> int:
    o = 2 + 10 * i
    assert struct.unpack_from("<H", chain, o)[0] == i
    return o + 2


def unlink(a: int, b: int) -> None:
    for x, y in ((a, b), (b, a)):
        o = slots(x)
        vals = list(struct.unpack_from("<4H", chain, o))
        vals[vals.index(y)] = 0xFFFF
        struct.pack_into("<4H", chain, o, *vals)


DIRECTIONS = {(0, 1): 0, (1, 0): 1, (0, -1): 2, (-1, 0): 3}   # slot = direction: 0 +z, 1 +x, 2 -z, 3 -x (every link in the game)


def slot_towards(a: int, b: int) -> int:
    dx, dz = byid[b]["pos"][0] - byid[a]["pos"][0], byid[b]["pos"][2] - byid[a]["pos"][2]
    assert min(abs(dx), abs(dz)) < 1.5, f"{a} and {b} are not on one axis (dx {dx:.0f}, dz {dz:.0f}); roads are always axis-aligned"
    return DIRECTIONS[(0, 1 if dz > 0 else -1)] if abs(dz) > abs(dx) else DIRECTIONS[(1 if dx > 0 else -1, 0)]


def link(a: int, b: int) -> None:
    for x, y in ((a, b), (b, a)):
        o = slots(x)
        vals = list(struct.unpack_from("<4H", chain, o))
        k = slot_towards(x, y)
        assert vals[k] == 0xFFFF, f"space {x} already has a neighbour in direction slot {k}"
        vals[k] = y
        struct.pack_into("<4H", chain, o, *vals)


def reachable(start: int) -> int:
    seen, todo = set(), [start]
    while todo:
        x = todo.pop()
        if x in seen:
            continue
        seen.add(x)
        base = slots(x)
        todo.extend(v for v in struct.unpack_from("<4H", chain, base) if v != 0xFFFF)
    return len(seen)


before = reachable(0)
for a, b in SWAPS:
    swap(a, b)
unlink(*CUT)
if "--no-link" not in sys.argv:
    link(*ADD)
for arg in sys.argv:                      # --links 235-241,109-149 adds more links
    if arg.startswith("--links="):
        for pair in arg[8:].split(","):
            link(*(int(v) for v in pair.split("-")))
after = reachable(0)
print(f"spaces reachable from the start: {before} before, {after} after (the cut must not strand any)")
assert before == after, "the cut split the board; pick another link"

(mod / "Assets").mkdir(parents=True, exist_ok=True)
(mod / "Assets" / "stg000_EN.DAT").write_bytes(stg)
(mod / "Assets" / "CHAIN_000.DAT").write_bytes(chain)
print("swapped", SWAPS, "| cut", CUT, "| added", None if "--no-link" in sys.argv else ADD, "->", mod / "Assets")

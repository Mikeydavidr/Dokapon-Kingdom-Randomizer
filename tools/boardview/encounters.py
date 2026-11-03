"""Monster encounters: which monsters each space can meet. Read them out to a JSON file, edit it, build them back in.

usage: python encounters.py dump <file.json> [--assets <folder>] [--base <mod Assets>] [--map <file.png>]
       python encounters.py build <file.json> <mod folder> [--assets <folder>] [--base <mod Assets>] [--allow-special]
  dump writes every encounter table (monster -> copies, the copies are the odds) and every empty space of every board with
  the two tables it uses; --map also draws board 0 from above with each empty space marked by its first table.
  build writes stageBase_EN.DAT and the changed stgNNN_EN.DAT to <mod>/Assets. --base reads the game files from a mod's
  Assets folder instead (to add encounter edits to a mod), falling back to the extracted game for files it does not have.
  Monsters are named as in the dump ("Skeleton", or "Skeleton #131" for a second monster of that name) or given by id.
  Special monsters (bosses, Rico Jr. and the others whose stats scale with the player) are refused unless --allow-special.

Where it lives (PC, from the data; see SpaceTypes.md "Monster encounters"):
  stageBase_EN.DAT  monsters: records 50 00 00 00 | id u8 | u8 | level u8 | 00 | name (null-terminated, padded to 4) | 10 u16
                    stats (hp, attack, defence, speed, magic, ...; bit 0x8000 = scales with the player), from 0x1B0B0.
                    tables: 160 u32 pointers at 0x25060 (a 0x4F record at 0x24D3C points at them), list i at pointer +
                    0x8350 (the start of the @CHR chunk): monster ids (u8) ending in FF. The lists fill 0x252E4-0x259CC,
                    then the next record starts; lists that no longer fit there go at the end of the chunk (not yet
                    tested in game).
  stgNNN_EN.DAT     an empty space (kinds 0C, 0D, 1E-25) has param = [first table u16][second table u16].
"""
import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

from boardlib import load_board

MONSTERS = 0x1B0B0
INDEX, COUNT, BASE = 0x25060, 160, 0x8350
KINDS = {0x0C: "Poison Swamp", 0x0D: "Snowfield", 0x1E: "Plain", 0x1F: "Forest", 0x20: "Mountain", 0x21: "Desert",
         0x22: "Ocean", 0x23: "Swamp", 0x24: "Cave", 0x25: "Lava"}
BOARDS = range(23)
STAGE = Path("Data_eng") / "dataSeq_EN"


class Encounters:
    def __init__(self, assets: Path, base: Path | None = None):
        self.assets, self.base = assets, base
        self.data = bytearray(self.read("stageBase_EN.DAT"))
        d = self.data

        # monsters
        self.monsters, o = {}, MONSTERS
        while d[o:o + 4] == b"P\x00\x00\x00":
            e = d.index(0, o + 8)
            q = e + 1 + (-(e + 1 - o) % 4)
            stats = struct.unpack_from("<10H", d, q)
            self.monsters[d[o + 4]] = {"name": d[o + 8:e].decode("ascii"), "level": d[o + 6],
                                       "special": any(s & 0x8000 for s in stats[:5])}
            o = q + 20
        seen = Counter()
        self.label = {}
        for i, m in self.monsters.items():
            seen[m["name"]] += 1
            self.label[i] = m["name"] if seen[m["name"]] == 1 else f"{m['name']} #{i}"
        self.by_label = {v: k for k, v in self.label.items()}

        # tables
        self.pointers = list(struct.unpack_from(f"<{COUNT}I", d, INDEX))
        starts = [p + BASE for p in self.pointers]
        self.tables = [list(d[s:d.index(0xFF, s)]) for s in starts]
        self.start = min(starts)
        end = max(d.index(0xFF, s) for s in starts) + 1
        self.end = end + (-end % 4)
        self.original = [t[:] for t in self.tables]

        # empty spaces: board -> list of {id, kind, area, offset}; the tables are read from / written to self.stages
        self.stages, self.spaces = {}, {}
        for n in BOARDS:
            name = f"stg{n:03d}_EN.DAT"
            if not (assets / STAGE / name).exists():
                continue
            spaces, _ = load_board(assets, n)
            self.stages[n] = bytearray(self.read(name))
            self.spaces[n] = [{"id": s["id"], "kind": s["type"][0], "area": s["grp"], "offset": s["offset"], "pos": s["pos"]}
                              for s in spaces if s["type"][0] in KINDS]
        self.changed = set()

    def read(self, name: str) -> bytes:
        if self.base and (self.base / name).exists():
            return (self.base / name).read_bytes()
        return (self.assets / STAGE / name).read_bytes()

    def space_tables(self, board: int, space: dict) -> tuple[int, int]:
        return struct.unpack_from("<HH", self.stages[board], space["offset"] + 12)

    def set_space_tables(self, board: int, space_id: int, first: int, second: int) -> None:
        space = next(s for s in self.spaces[board] if s["id"] == space_id)
        if (first, second) != self.space_tables(board, space):
            struct.pack_into("<HH", self.stages[board], space["offset"] + 12, first, second)
            self.changed.add(board)

    def users(self) -> dict[int, Counter]:
        """table -> Counter of (board, 'first'/'second', kind name, area): which spaces look at it."""
        out = {t: Counter() for t in range(COUNT)}
        for n, spaces in self.spaces.items():
            for s in spaces:
                for slot, t in zip(("first", "second"), self.space_tables(n, s)):
                    if t < COUNT:
                        out[t][(n, slot, KINDS[s["kind"]], s["area"])] += 1
        return out

    def pack(self) -> bytes:
        """The pointer index and the lists. Unchanged lists keep the game's layout (some identical lists are stored twice, a
        few tables share one list); if that does not fit, every distinct list is stored once; if that does not fit either,
        the changed lists that do not fit go after the last record of the @CHR chunk, which grows to hold them (see
        `overflow`)."""
        d = bytearray(self.data)
        room = self.end - self.start
        for merge in (False, True):
            where, blob, keys = {}, bytearray(), []
            for i, t in enumerate(self.tables):
                key = bytes(t) if merge or t != self.original[i] else self.pointers[i]
                keys.append(key)
                if key not in where:
                    where[key] = len(blob)
                    blob += bytes(t) + b"\xff"
            if len(blob) <= room:
                d[self.start:self.end] = bytes(blob) + bytes(room - len(blob))
                for i, key in enumerate(keys):
                    struct.pack_into("<I", d, INDEX + 4 * i, self.start + where[key] - BASE)
                return bytes(d)
        return self.overflow()

    def overflow(self) -> bytes:
        """Unchanged lists in their place, changed ones in what room is left and the rest at the end of the @CHR chunk.

        stageBase is a script of tagged records the game runs at load; data blocks in it are skipped by a jump record
        (03 00 00 00 | target - 0x8350), e.g. the one before the encounter tables jumps to 0x259CC. The chunk's last record
        ends the script (else the game would run past the end), so lists placed after it are never run as records. The
        chunk header (@CHR at 0x8350, u32 size) grows by the added bytes; the file stays padded to 16 bytes."""
        d = bytearray(self.data)
        chunk = d.find(b"@CHR")
        assert chunk == BASE, "the @CHR chunk is not where the pointers count from"
        chr_end = chunk + struct.unpack_from("<I", d, chunk + 4)[0]
        room = self.end - self.start
        where, blob, extra = {}, bytearray(), bytearray()
        for i, t in enumerate(self.tables):                   # unchanged lists first: they fit, as they did
            if t == self.original[i] and self.pointers[i] not in where:
                where[self.pointers[i]] = self.start + len(blob)
                blob += bytes(t) + b"\xff"
        for i, t in enumerate(self.tables):
            if t != self.original[i] and bytes(t) not in where:
                if len(blob) + len(t) + 1 <= room:
                    where[bytes(t)] = self.start + len(blob)
                    blob += bytes(t) + b"\xff"
                else:
                    where[bytes(t)] = chr_end + len(extra)
                    extra += bytes(t) + b"\xff"
        d[self.start:self.end] = bytes(blob) + bytes(room - len(blob))
        for i, t in enumerate(self.tables):
            key = self.pointers[i] if t == self.original[i] else bytes(t)
            struct.pack_into("<I", d, INDEX + 4 * i, where[key] - BASE)
        extra += bytes(-len(extra) % 4)
        struct.pack_into("<I", d, chunk + 4, chr_end + len(extra) - chunk)
        out = d[:chr_end] + extra
        return bytes(out + bytes(-len(out) % 16))

    def save(self, out: Path) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / "stageBase_EN.DAT"]
        paths[0].write_bytes(self.pack())
        for n in sorted(self.changed):
            paths.append(out / f"stg{n:03d}_EN.DAT")
            paths[-1].write_bytes(self.stages[n])
        return paths

    # ---- the JSON file ------------------------------------------------------------------------------------------------------
    def to_json(self) -> str:
        users = self.users()
        lines = ["{",
                 ' "about": "tables: monster -> copies (the odds). spaces: board -> space -> [first table, second table]. '
                 'kind/area/used_by are notes, only monsters and tables are read back.",',
                 ' "monsters": {']
        mons = [f'  {json.dumps(self.label[i])}: "id {i}, level {m["level"]}{", special" if m["special"] else ""}"'
                for i, m in self.monsters.items()]
        lines += [",\n".join(mons), " },", ' "tables": {']
        rows = []
        for i, t in enumerate(self.tables):
            used = "; ".join(f"board {n} {slot}: {c} {kind} (area {a})" for (n, slot, kind, a), c in sorted(users[i].items()))
            mons = {self.label[m]: c for m, c in sorted(Counter(t).items())}
            rows.append(f'  "0x{i:02x}": {{"used_by": {json.dumps(used or "no board space")}, "monsters": {json.dumps(mons)}}}')
        lines += [",\n".join(rows), " },", ' "spaces": {']
        boards = []
        for n, spaces in self.spaces.items():
            if not spaces:
                continue
            rows = [f'   "{s["id"]}": {{"kind": "{KINDS[s["kind"]]}", "area": {s["area"]}, "tables": '
                    f'{json.dumps([f"0x{t:02x}" for t in self.space_tables(n, s)])}}}' for s in spaces]
            boards.append(f'  "{n}": {{\n' + ",\n".join(rows) + "\n  }")
        lines += [",\n".join(boards), " }", "}"]
        return "\n".join(lines) + "\n"

    def monster_id(self, key) -> int:
        if isinstance(key, int) or str(key).isdigit():
            return int(key)
        if key not in self.by_label:
            raise SystemExit(f"unknown monster {key!r}")
        return self.by_label[key]

    def from_json(self, doc: dict, allow_special: bool = False) -> list[str]:
        """Apply a dump's tables and spaces; return what changed."""
        log = []
        for key, entry in doc.get("tables", {}).items():
            i = int(key, 16)
            want = Counter()
            for m, c in entry["monsters"].items():
                mid = self.monster_id(m)
                if mid not in self.monsters:
                    raise SystemExit(f"table {key}: no monster with id {mid}")
                if self.monsters[mid]["special"] and not allow_special and mid not in self.original[i]:
                    raise SystemExit(f"table {key}: {self.label[mid]} is a special monster (use --allow-special)")
                want[mid] += int(c)
            if want == Counter(self.original[i]):
                self.tables[i] = self.original[i][:]          # unchanged: keep the game's order
                continue
            assert 0 < sum(want.values()) < 255, f"table {key}: needs 1-254 monsters"
            self.tables[i] = [m for m in sorted(want) for _ in range(want[m])]
            log.append(f"table {key}: " + ", ".join(f"{self.label[m]} x{c}" for m, c in sorted(want.items())))
        for n, spaces in doc.get("spaces", {}).items():
            for sid, entry in spaces.items():
                first, second = (int(t, 16) if isinstance(t, str) else t for t in entry["tables"])
                assert first < COUNT and second < COUNT, f"board {n} space {sid}: no table {max(first, second):#x}"
                space = next(s for s in self.spaces[int(n)] if s["id"] == int(sid))
                if (first, second) != self.space_tables(int(n), space):
                    self.set_space_tables(int(n), int(sid), first, second)
                    log.append(f"board {n} space {sid}: tables 0x{first:02x} / 0x{second:02x}")
        return log


def draw_map(enc: Encounters, path: Path) -> None:
    """Board 0 from above, each empty space ringed in its first table's colour and labelled with it."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
    import render_top
    from PIL import Image, ImageDraw
    box, scale = (-700, -780, 700, 480), 1.2
    render_top.render(path, None, scale, box, render_top.FILES, False, None)
    img = Image.open(path)
    dr = ImageDraw.Draw(img)
    for s in enc.spaces[0]:
        first, second = enc.space_tables(0, s)
        x, y = (box[2] - s["pos"][0]) * scale, (box[3] - s["pos"][2]) * scale
        h = (first * 47) % 360
        colour = f"hsl({h}, 90%, 60%)"
        dr.ellipse([x - 9, y - 9, x + 9, y + 9], outline=colour, width=4)
        dr.text((x - 7, y - 6), f"{first:02x}", fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    img.save(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["dump", "build"])
    ap.add_argument("json")
    ap.add_argument("mod", nargs="?")
    ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
    ap.add_argument("--base", default=None)
    ap.add_argument("--map", default=None)
    ap.add_argument("--allow-special", action="store_true")
    args = ap.parse_args()
    enc = Encounters(Path(args.assets), Path(args.base) if args.base else None)
    if args.command == "dump":
        Path(args.json).write_text(enc.to_json(), encoding="utf-8")
        print("wrote", args.json)
        if args.map:
            draw_map(enc, Path(args.map))
            print("wrote", args.map)
        return
    assert args.mod, "build needs a mod folder"
    log = enc.from_json(json.loads(Path(args.json).read_text(encoding="utf-8")), args.allow_special)
    for p in enc.save(Path(args.mod) / "Assets"):
        print("wrote", p)
    print("\n".join(log) or "no changes")


if __name__ == "__main__":
    main()

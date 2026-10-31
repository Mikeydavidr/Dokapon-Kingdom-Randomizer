"""One-off test patch (PC version). Reads the original files, writes modified COPIES to an output folder.

  1. Town and castle names: first-continent towns trade names with the Hallstatt towns (text + the board's sign images)
  2. Weapons: the Knife slot and the Aura Knuckle slot trade identities; the Knife slot's proc byte becomes 0x64 (100%)
  3. Spaces next to the Dokapon Castle: three swaps with spaces elsewhere on the overworld (distribution unchanged)

usage: python make_test_patch.py [assets folder] [output folder]
"""
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
assets = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "assets"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "TestMod"
if assets.resolve() in out.resolve().parents or out.resolve() == assets.resolve():
    sys.exit("refusing to write inside the assets folder")
(out / "Assets").mkdir(parents=True, exist_ok=True)

STAGEBASE = assets / "Data_eng" / "dataSeq_EN" / "stageBase_EN.DAT"
STG000 = assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT"
TEXPACK = assets / "CommonData" / "map" / "NamePlate_EN.texpack"

log = []


def say(line=""):
    log.append(line)
    print(line)


def read_records(data, start, marker, tail_size):
    """Records: [marker 4][id 1][3 bytes][name, null-terminated, padded to 4][tail]."""
    recs, o = [], start
    while data[o:o + 4] == marker:
        p = o + 8
        while data[p] != 0:
            p += 1
        name = data[o + 8:p].decode("utf-8")
        p += 1
        while (p - o) % 4:
            p += 1
        recs.append({"start": o, "head": data[o:o + 5], "prefix": data[o + 5:o + 8], "namefield": data[o + 8:p],
                     "tail": data[p:p + tail_size], "name": name})
        o = p + tail_size
    return recs, o


# ------------------------------------------------------------------ stageBase: weapons and town names
sb = bytearray(STAGEBASE.read_bytes())

# --- 2. weapons: the whole-weapon test ---------------------------------------------------------------------------
# Earlier rounds moved a weapon's identity into the Knife slot; the name, class/animation, description and model followed,
# but the special effect did not (so it is probably keyed by weapon id). Here the Sleep Bow keeps its own id and record
# and is simply sold in the first town's weapon shop in place of the Knife.
wstart = sb.find(b"\x58\x00\x00\x00\x01\x00", 0x8000)
weapons, wend = read_records(bytes(sb), wstart, b"\x58\x00\x00\x00", 20)
assert len(weapons) == 67, len(weapons)
# Weapon effects live in the exe. patch_exe.py extends the effect table to ids 1..67 and makes each effect's first proc roll
# read the weapon record's chance byte (tail byte 2). This round: the Knife (id 1) gets the Sleep Bow's effect (case 0, given
# on the patch_exe.py command line) with chance 101, i.e. every attack. The roll is 0..100 and procs when roll < chance.
k = weapons[0]
assert k["name"] == "Knife" and k["head"][4] == 1
ktail = k["start"] + 8 + len(k["namefield"])
sb[ktail + 2] = 101
sb[ktail + 4:ktail + 8] = (100).to_bytes(4, "little")
sb[ktail + 8:ktail + 16] = b"".join(v.to_bytes(2, "little") for v in (4, 300, 300, 300))  # ATK 4, DEF/MAG/SPD 300
# with the exe reading the records, three records disagree with the constants the code used; keep the vanilla odds
VANILLA = {"Nihilist Sword": 25, "Chevalier": 25, "Punisher": 50}
say("WEAPONS")
for w in weapons:
    if w["name"] in VANILLA:
        t = w["start"] + 8 + len(w["namefield"])
        say(f"  {w['name']}: chance byte {sb[t + 2]} -> {VANILLA[w['name']]} (the value the game's code used)")
        sb[t + 2] = VANILLA[w["name"]]
say("  Knife (id 1, first weapon shop as usual): chance byte 0 -> 101 (always), price 100G, ATK 4, DEF/MAG/SPD -> 300; the exe patch gives it case 0 (sleep)")

# --- 1a. town names ---------------------------------------------------------------------------------------------
tstart = sb.find(b"\x6d\x00\x00\x00\x00\x00", 0xE00)
towns, tend = read_records(bytes(sb), tstart, b"\x6d\x00\x00\x00", 12)
assert len(towns) == 55, len(towns)
pos = {t["name"]: i for i, t in enumerate(towns)}
continent = {t["name"]: t["head"][4:5] and sb[t["start"] + 5] for t in towns}

# same-size name fields only, so every record stays at its original offset
PAIRS = [("Bukhan", "Garonne"), ("Jurong", "Aniene"), ("Ussuri", "Balle"), ("Volga", "Danube"), ("Ural", "Groat"),
         ("Moriah", "Pfennig"), ("Uvs Nuur", "Athenaeum"), ("Tiphrates", "Sterling"), ("Khan's Castle", "Rhine Castle")]
say()
say("TOWN NAMES (stageBase_EN.DAT)")
for a, b in PAIRS:
    ta, tb = towns[pos[a]], towns[pos[b]]
    assert len(ta["namefield"]) == len(tb["namefield"]), (a, b)
    assert continent[a] == 0 and continent[b] == 1, (a, b, continent[a], continent[b])
    off_a, off_b = ta["start"] + 8, tb["start"] + 8
    sb[off_a:off_a + len(ta["namefield"])] = tb["namefield"]
    sb[off_b:off_b + len(tb["namefield"])] = ta["namefield"]
    say(f"  {a:<14} (continent 0, id {sb[ta['start'] + 4]:02X})  <->  {b:<10} (continent 1, id {sb[tb['start'] + 4]:02X})")

(out / "Assets" / "stageBase_EN.DAT").write_bytes(bytes(sb))

# ------------------------------------------------------------------ NamePlate_EN.texpack: swap the sign images too
tp = TEXPACK.read_bytes()
count = struct.unpack_from("<I", tp, 0)[0]
table = [struct.unpack_from("<4sI", tp, 0x10 + 8 * i) for i in range(count)]
p = 0x10 + 8 * count
entries = []  # [name field 16 bytes, png bytes]
for tag, size in table:
    entries.append([tp[p:p + 16], tp[p + 16:p + 16 + size]])
    p = (p + 16 + size + 15) & ~15


def pack(entries):
    head = tp[:0x10]
    # tag = 07 09 <padding bytes after this entry> cc; the game steps through the pack with it, so it must follow the size
    tbl = b"".join(struct.pack("<4sI", table[i][0][:2] + bytes([-(len(e[0]) + len(e[1])) % 16]) + table[i][0][3:], len(e[1]))
                   for i, e in enumerate(entries))
    body = b""
    for name, png in entries:
        blob = name + png
        body += blob + b"\x00" * (-len(blob) % 16)
    return head + tbl + body


assert pack(entries) == tp, "texpack repack is not byte-identical to the original"
say()
say("SIGNS (NamePlate_EN.texpack): repack of the unmodified file is byte-identical; swapping the same pairs")
for a, b in PAIRS:
    ia, ib = pos[a] + 3, pos[b] + 3  # sign number = position in the town table + 3
    entries[ia][1], entries[ib][1] = entries[ib][1], entries[ia][1]
    say(f"  sign {ia:>2}.png <-> sign {ib:>2}.png   ({a} / {b})")
(out / "Assets" / "NamePlate_EN.texpack").write_bytes(pack(entries))

# ------------------------------------------------------------------ 3. spaces around the Dokapon Castle (board 0)
sg = bytearray(STG000.read_bytes())
sstart = next(i for i in range(len(sg) - 16) if sg[i:i + 8] == b"\x33\x00\x00\x00\x00\x00\x00\x00")
NAME = {0x01: "Item", 0x02: "Magic", 0x03: "Red Loot", 0x0A: "Bank", 0x1E: "Plain", 0x22: "Ocean"}


def rec(i):
    o = sstart + 16 * i
    assert sg[o:o + 4] == b"\x33\x00\x00\x00" and struct.unpack_from("<I", sg, o + 4)[0] == i
    return o


# (space next to / near the castle, expected kind byte, space elsewhere, expected kind byte)
SWAPS = [(36, 0x1E, 67, 0x03), (39, 0x01, 22, 0x0A), (55, 0x1E, 12, 0x01)]
assert sg[rec(35) + 8] == 0x1D  # the Dokapon Castle itself
say()
say("SPACES (stg000_EN.DAT, overworld). The castle is space 35; its only neighbours are 36 and 39.")
for near, kn, far, kf in SWAPS:
    on, of = rec(near), rec(far)
    assert sg[on + 8] == kn and sg[of + 8] == kf, (near, far)
    a_ty, a_pa = bytes(sg[on + 8:on + 10]), bytes(sg[on + 12:on + 16])
    b_ty, b_pa = bytes(sg[of + 8:of + 10]), bytes(sg[of + 12:of + 16])
    sg[on + 8:on + 10], sg[on + 12:on + 16] = b_ty, b_pa
    sg[of + 8:of + 10], sg[of + 12:of + 16] = a_ty, a_pa
    say(f"  space {near:<3} {NAME[kn]:<9} -> {NAME[kf]:<9}   (and space {far} {NAME[kf]} -> {NAME[kn]})")
(out / "Assets" / "stg000_EN.DAT").write_bytes(bytes(sg))

(out / "CHANGES.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
say()
say(f"written to {out / 'Assets'}")

"""Void board probe: board 0 with its scenery stripped to a flat grass floor, every road drawn from scratch, the spaces flattened
(and optionally spread out), to find out whether a board can be laid out freely.

usage: python make_void_board.py <mod folder> [--scale S] [--y Y] [--assets <folder>]
  Every F00 piece is hidden (collapsed to one degenerate triangle) except the sky, the buildings (town_01 / block_01 pieces
  smaller than 70 units across: stores, castles, caves, temples; the Lava Cave and its smoke; and the castles that share a big
  piece with other art, cut out of it by their "area" in board0_buildings.json) and two pieces reused: one green_01 piece becomes a flat floor
  of tiled grass under the whole board, one road_01 piece holds every road (dirt strip and junction tiles for each link).
  Spaces move to height Y and, with --scale, their x and z are multiplied by S (the link directions stay the same, so CHAIN
  does not change). Each building, each town model (TW_LOC.position, one point per town) and each W point of MASU00 moves by
  the move of the space nearest to it. The camera limits (stg000) grow with the board, keeping the game's margins.
Writes F00_*.model, MASU00.position, TW_LOC.position and stg000_EN.DAT to <mod>/Assets and <mod>/void_map.png (the board from
above).
"""
import argparse
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel
import render_top
from boardlib import load_board
from roads import CLEAR, DIRT_TILE, DIRT_V, STEPS, Roads, road_uv
from units import centre, clusters, load_units

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("--scale", type=float, default=1.0)
ap.add_argument("--y", type=float, default=10.0)
ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
args = ap.parse_args()
assets, mod = Path(args.assets), Path(args.mod)
out = mod / "Assets"
out.mkdir(parents=True, exist_ok=True)
F00 = assets / "CommonData" / "dataField" / "F00"
POS = assets / "CommonData" / "fieldPosition"
FILES = ["A", "M", "N", "Anim1", "Anim2", "wood"]
ROAD_Y, FLOOR_Y = args.y - 0.6, args.y - 1.0          # vanilla: spaces at 10, roads at 9.4, grass a little below
FLOOR_PIECE, ROAD_PIECE = ("N", 39), ("A", 9)          # a world-placed grass piece (test.tga) and road piece (fieldC.tga)
FLOOR_BOX, FLOOR_STEP, GRASS_UV = (-900, -1000, 900, 700), 50.0, 1 / 60   # the grass texture repeats every 60 units
BUILDING_LAYERS, BUILDING_SIZE = {"town_01", "block_01"}, 70.0
KEEP_LAYERS = {"sky_01"}
EXTRA_BUILDINGS = {("Anim2", 9): 140}                  # the Lava Cave's smoke: its space
# animated pieces the game turns about their own origin: they move by the matrix that places them, not by their vertices
# (Daunting Mountain and its cloud rings, the Sunken Shrine whirlpool, which also has to rise from sea level onto the grass)
PIVOTED = {**{("Anim1", gi): (221, None) for gi in range(3, 9)}, ("Anim2", 0): (180, FLOOR_Y + 0.15), ("Anim2", 1): (180, FLOOR_Y + 0.2)}
AREAS = {("N", 59): [{"centre": [-541, 240], "radius": 28, "space": 3}],   # the Coliseum
         ("A", 25): [{"centre": [413, 66], "radius": 30, "space": 140}]}    # the Lava Cave (the piece also has the mesas by 124)
for unit in load_units().values():                     # buildings in a big piece with other art (castles 123 and 199, magic
    for part in unit["parts"]:                         # store 2): keep only their part
        if part["role"] == "building" and "area" in part:
            AREAS.setdefault(tuple(part["area"]), []).append(part)

# ---- where everything goes -------------------------------------------------------------------------------------------------
spaces, links = load_board(assets, 0)
old = {s["id"]: s["pos"] for s in spaces}
new = {n: (p[0] * args.scale, args.y, p[2] * args.scale) for n, p in old.items()}
delta = {n: tuple(new[n][k] - old[n][k] for k in range(3)) for n in old}


def nearest(x: float, z: float, ids=None) -> int:
    return min(ids or old, key=lambda n: (old[n][0] - x) ** 2 + (old[n][2] - z) ** 2)


def position_file(name: str, ids=None) -> bytes:
    """A .position file with every point moved: Z#### to its space's new place, the others by the move of the nearest space."""
    b = bytearray((POS / name).read_bytes())
    count, base = struct.unpack_from("<II", b, 0)
    q = 8
    for i in range(count):
        e = b.index(0, q)
        nm, q = b[q:e].decode("ascii"), e + 1
        p = struct.unpack_from("<3f", b, base + 12 * i)
        if nm.startswith("Z") and nm[1:].isdigit():
            p2 = new[int(nm[1:])]
        else:
            d = delta[nearest(p[0], p[2], ids)]
            p2 = tuple(p[k] + d[k] for k in range(3))
        struct.pack_into("<3f", b, base + 12 * i, *p2)
    return bytes(b)


towns = [s["id"] for s in spaces if s["type"][0] == 0x14]
(out / "MASU00.position").write_bytes(position_file("MASU00.position"))
(out / "TW_LOC.position").write_bytes(position_file("TW_LOC.position", towns))


def extent(pos) -> tuple:
    xs, zs = [p[0] for p in pos], [p[2] for p in pos]
    return max(xs), max(zs), min(xs), min(zs)


# ---- camera limits: stg000 record 13 00 00 00 | x max, z max, x min, z min (s16), seen in game: the camera stops there -------
stg = bytearray((assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT").read_bytes())
cam = next(o for o in range(0, len(stg) - 28, 4) if stg[o:o + 4] == b"\x13\x00\x00\x00"
           and stg[o + 12:o + 16] == b"\x12\x00\x00\x00" and stg[o + 20:o + 24] == b"\x11\x00\x00\x00")
limits = struct.unpack_from("<4h", stg, cam + 4)
margin = [l - e for l, e in zip(limits, extent(old.values()))]      # keep the game's room around the outermost spaces
new_limits = [round(e + m) for e, m in zip(extent(new.values()), margin)]
struct.pack_into("<4h", stg, cam + 4, *new_limits)
(out / "stg000_EN.DAT").write_bytes(stg)

# ---- roads: every link and junction tile drawn again on the flat board -------------------------------------------------------
roads = Roads(assets)
roads.node = dict(new)
road = roads.meshes[ROAD_PIECE]
proto = next(i for t in road["tris"] for i in t if road_uv(*road["verts"][i].uv))
road["tris"] = [[proto] * 3]                           # emit copies its vertex layout from a road triangle: keep one, flat
road["changed"] = True
style = "dirt"                                         # all grass: the game draws dirt between two grass spaces
for a in sorted(links):
    for b in links[a]:
        if a > b:
            continue
        d = STEPS[roads.slot(a, b)]
        ca, cb = roads.centre(a), roads.centre(b)
        length = math.dist(ca, cb)
        span = length - 2 * CLEAR
        if span <= 0.5:
            continue                                   # the two tiles touch
        n = max(1, round(span / 10.0))
        rows = []
        for s in range(n + 1):
            t = CLEAR + span * s / n
            x, z = ca[0] + (cb[0] - ca[0]) * t / length, ca[1] + (cb[1] - ca[1]) * t / length
            ph = (span * s / n / DIRT_TILE) % 2        # the dirt strip, mirrored every repeat so the seams match
            v = DIRT_V[0] + (DIRT_V[1] - DIRT_V[0]) * (ph if ph <= 1 else 2 - ph)
            rows.append(roads.band((x, z), d, 0.0, 0.0, ROAD_Y, v, v)[:2])
        roads.emit(ROAD_PIECE, [[*rows[s], *rows[s + 1][::-1]] for s in range(n)])
for a in sorted(links):
    roads.build_tile(a, {roads.slot(a, b): style for b in links[a]}, ROAD_PIECE, ROAD_Y)

# ---- the model files ---------------------------------------------------------------------------------------------------------
specials = [s["id"] for s in spaces if 0x14 <= s["type"][0] <= 0x1D or s["type"][0] >= 0x26]
log = [f"void board: scale {args.scale}, spaces at y {args.y}", f"camera limits (x max, z max, x min, z min): {limits} -> {tuple(new_limits)}"]
for f in FILES:
    m = igbmodel.load(F00 / f"F00_{f}.model")
    vo = m.chunk("VERT")[0]
    replace, mdata, moved = {}, bytearray(m.data), set()
    recs, parent = m.tree()
    for gi, nd in enumerate(m.mesh_nodes()):
        g = m.geoms[gi]
        raw = bytearray(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])
        _, tris = igbmodel.mesh(m, g)
        M = m.placement(gi)
        world = [igbmodel.apply(M, struct.unpack_from("<3f", raw, g.stride * i)) for i in range(g.verts)]
        xs, zs = [p[0] for p in world], [p[2] for p in world]
        if (f, gi) == ROAD_PIECE:
            continue                                   # written below through Roads
        if (f, gi) == FLOOR_PIECE:
            best = max(range(g.verts), key=lambda i: raw[g.stride * i + 0x18: g.stride * i + 0x1c] == b"\xff\xff\xff\xff")
            grass = bytes(raw[g.stride * best: g.stride * (best + 1)])
            x0, z0, x1, z1 = FLOOR_BOX
            nx, nz = int((x1 - x0) / FLOOR_STEP), int((z1 - z0) / FLOOR_STEP)
            inv = igbmodel.inverse(M)                  # the piece sits under a matrix that scales it by 1.5
            vb = bytearray()
            for j in range(nz + 1):
                for i in range(nx + 1):
                    x, z = x0 + i * FLOOR_STEP, z0 + j * FLOOR_STEP
                    vb += (struct.pack("<6f", *igbmodel.apply(inv, (x, FLOOR_Y, z)), 0.0, 1.0, 0.0) + grass[0x18:0x1c]
                           + struct.pack("<2f", x * GRASS_UV, z * GRASS_UV) + grass[0x24:])
            idx = []
            for j in range(nz):
                for i in range(nx):
                    a, b, c, d = j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i
                    for t in ((a, b, c), (a, c, d)):   # same facing as the game's terrain (negative xz winding)
                        (ax, az), (bx, bz), (cx, cz) = [(x0 + (q % (nx + 1)) * FLOOR_STEP, z0 + (q // (nx + 1)) * FLOOR_STEP) for q in t]
                        idx += list(t) if (bx - ax) * (cz - az) - (cx - ax) * (bz - az) < 0 else [t[0], t[2], t[1]]
            replace[gi] = (bytes(vb), idx)
            log.append(f"F00_{f} piece {gi}: grass floor {nx}x{nz} squares at y {FLOOR_Y}")
            continue
        if nd["name"] in KEEP_LAYERS:
            continue
        if (f, gi) in PIVOTED:
            n, y = PIVOTED[(f, gi)]
            i = nd["node"]
            while recs[i][0] < 0:
                i = parent[i]
            mi = recs[i][0] // 64
            if mi not in moved:
                moved.add(mi)
                o = m.chunk("MTRX")[0] + 64 * mi + 48          # the translation row
                t = struct.unpack_from("<3f", mdata, o)
                t2 = (t[0] + delta[n][0], t[1] + delta[n][1] if y is None else t[1] + y - min(p[1] for p in world), t[2] + delta[n][2])
                struct.pack_into("<3f", mdata, o, *t2)
                log.append(f"F00_{f} matrix {mi} (piece {gi}, {nd['name']}): space {n}, ({t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f}) -> "
                           f"({t2[0]:.1f}, {t2[1]:.1f}, {t2[2]:.1f})")
            continue
        if (f, gi) in EXTRA_BUILDINGS or (nd["name"] in BUILDING_LAYERS
                                         and max(max(xs) - min(xs), max(zs) - min(zs)) < BUILDING_SIZE):
            n = EXTRA_BUILDINGS.get((f, gi)) or nearest((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2, specials)
            d = delta[n]
            if any(abs(c) > 1e-6 for c in d):
                inv = igbmodel.inverse(M)
                for i, p in enumerate(world):
                    struct.pack_into("<3f", raw, g.stride * i, *igbmodel.apply(inv, tuple(p[k] + d[k] for k in range(3))))
                replace[gi] = (bytes(raw), [i for t in tris for i in t])
            log.append(f"F00_{f} piece {gi} ({nd['name']}): building of space {n}, moved by ({d[0]:.1f}, {d[1]:.1f}, {d[2]:.1f})")
            continue
        if (f, gi) in AREAS:
            inv, keep = igbmodel.inverse(M), set()
            for part in AREAS[(f, gi)]:
                vs = {i for c in clusters(world, tris, weld=True) if math.dist(centre(world, c), part["centre"]) <= part["radius"]
                      for i in c}
                n = part.get("space") or nearest(*centre(world, sorted(vs)), specials)
                d = delta[n]
                for i in vs:
                    struct.pack_into("<3f", raw, g.stride * i, *igbmodel.apply(inv, tuple(world[i][k] + d[k] for k in range(3))))
                keep |= vs
                log.append(f"F00_{f} piece {gi} ({nd['name']}): {len(vs)} vertices kept, building of space {n}, "
                           f"moved by ({d[0]:.1f}, {d[1]:.1f}, {d[2]:.1f})")
            replace[gi] = (bytes(raw), [i for t in tris if all(v in keep for v in t) for i in t])
            continue
        replace[gi] = (bytes(raw[:g.stride]), [0, 0, 0])   # hidden: one degenerate triangle
    if f == ROAD_PIECE[0]:
        ms = roads.meshes[ROAD_PIECE]
        used = sorted({i for t in ms["tris"] for i in t})
        remap = {o: k for k, o in enumerate(used)}
        inv = ms["inverse"]
        verts = [ms["verts"][i] for i in used]
        vb = b"".join(type(v)(igbmodel.apply(inv, v.pos), v.nrm, v.col, v.uv, v.rest).pack() for v in verts)
        replace[ROAD_PIECE[1]] = (vb, [remap[i] for t in ms["tris"] for i in t])
        log.append(f"F00_{f} piece {ROAD_PIECE[1]}: {len(ms['tris'])} road triangles")
    hidden = sum(1 for gi, (vb, idx) in replace.items() if idx == [0, 0, 0])
    log.append(f"F00_{f}: {hidden} pieces hidden")
    (out / f"F00_{f}.model").write_bytes(igbmodel.rebuild(m, replace, bytes(mdata)))

(mod / "void_log.txt").write_text("\n".join(log) + "\n")
print("\n".join(log))

# ---- picture --------------------------------------------------------------------------------------------------------------------
s = max(1.0, args.scale)
box = (-700 * s, -780 * s, 700 * s, 480 * s)
render_top.render(mod / "void_map.png", out, 0.9 / s, box, render_top.FILES, False, None)
from PIL import Image, ImageDraw
img = Image.open(mod / "void_map.png")
dr = ImageDraw.Draw(img)
px = lambda p: ((box[2] - p[0]) * 0.9 / s, (box[3] - p[2]) * 0.9 / s)
for n, p in new.items():
    x, y = px(p)
    dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 0, 0), width=2)
    dr.text((x + 5, y - 5), str(n), fill=(255, 255, 255))
img.save(mod / "void_map.png")
print("wrote", mod / "void_map.png")

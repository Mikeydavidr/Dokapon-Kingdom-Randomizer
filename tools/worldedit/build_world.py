"""Build a board mod from a world file (world.py): its ground drawn from the terrain grid, its spaces where the file puts
them, every road drawn again for its links, and the game's buildings moved along with their spaces.

usage: python build_world.py <world.json> <mod folder> [--assets <folder>] [--no-picture]
Writes F00_*.model, MASU00.position, TW_LOC.position, stg000_EN.DAT and CHAIN_000.DAT to <mod>/Assets, <mod>/world_log.txt
and <mod>/world_map.png (the board from above, drawn from the written files). A dungeon's world file (board 1-22) is built
by dungeon.py instead: its spaces, links and paths, on the dungeon's own art.

What is drawn: the terrain meshes of terrain.meshes(), each in a piece of the game's own that has the right texture and
shader (so no texture or material is added); the trees, mountains, hills and decorations of the world's props and a
bridge wherever a road crosses a river (props.py); the sea plane of F00_Anim1; the sky; the buildings (the pieces the void
board keeps, see tools/testpatch/make_void_board.py), moved by the move of their space; the roads, the blue sea routes
and the one-way roads' arrows; the game's sea lanes, moved with their links. Every other piece (the game's own ground,
coasts, shadows) is hidden. Spaces sit at y 10, as on flat parts of the game's board.
"""
import argparse
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "boardview"))
sys.path.insert(0, str(HERE.parent / "igb"))
import dungeon
import igbmodel
import props
import render_top
import terrain
import world as worldfile
from boardlib import load_board
from roads import CLEAR, DIRT_TILE, DIRT_V, STEPS, LINE_V, Roads, road_uv
from units import centre, clusters, load_units

FILES = ["A", "M", "N", "Anim1", "Anim2", "wood"]
SPACE_Y = 10.0
ROAD_Y = SPACE_Y - 0.6
ROAD_PIECE = ("A", 9)
SEA_PIECE = ("Anim1", 9)                               # the sea plane: drawn again whole (terrain.sea)
KEEP = {SEA_PIECE}
KEEP_LAYERS = {"sky_01"}
BUILDING_LAYERS, BUILDING_SIZE = {"town_01", "block_01"}, 70.0
EXTRA_BUILDINGS = {("Anim2", 9): 140}                  # the Lava Cave's smoke: its space
PIVOTED = {**{("Anim1", gi): (221, None) for gi in range(3, 9)}, ("Anim2", 0): (180, terrain.BASE_Y - 0.3),
           ("Anim2", 1): (180, terrain.BASE_Y - 0.25)}  # Daunting Mountain and clouds; the whirlpool (moved by matrix)
AREAS = {("N", 59): [{"centre": [-541, 240], "radius": 28, "space": 3}],   # the Coliseum
         ("A", 25): [{"centre": [413, 66], "radius": 30, "space": 140}]}    # the Lava Cave
for _unit in load_units().values():
    for _part in _unit["parts"]:
        if _part["role"] == "building" and "area" in _part:
            AREAS.setdefault(tuple(_part["area"]), []).append(_part)
# which pieces each terrain mesh may go into: (layer, texture); the pieces are ones the board would hide anyway
CHANNELS = {"base": ("green_01", "test.tga"), "beach": ("road_side_sea", "fieldC.tga"), "edge": ("road_side", "fieldC.tga"),
            "s": ("town_01", "objes.tga"), "p": ("town_01", "objes.tga"), "m": ("town_01", "objes.tga"),
            "w": ("road_01", "fieldC.tga"), "d": ("jimem_01", "jimem.tga"),
            "cliff": ("town_01", "objes.tga"), "moat": ("sea_01", "water_test.tga")}
# the grass edges are _Fog_Water pieces, which hide what is drawn after them under their clear parts: they go into a piece
# drawn after the sea and the surf (a road_shadow piece, the same material and atlas), so shore edges over water show it
LATE = {"edge": [("Anim2", 14)]}
# the scrolling arrows of the one-way roads (it_OP pieces, it_002.tga): their links get no road strip, and the arrows follow
# their spaces. They all go into Anim2:16: a _Fog_Water piece, and A:216 is drawn before the ground, which it would hide
ARROWS = {("A", 216): [(285, 286), (286, 287)], ("Anim2", 16): [(223, 226), (226, 227)]}
ARROW_PIECE = ("Anim2", 16)
# the light lanes along the sea routes (wave_01 pieces, see_st.tga, scrolling): along the links with an Ocean space; they
# follow those links' spaces, and a lane whose link is gone is left out
LANES = [("Anim2", 5), ("Anim2", 10)]
MAX_VERTS = 60000                                      # indices are u16
OCEAN = 0x22                                           # links between two Ocean spaces are water paths the game draws
WATER_V = (0.53, 0.62)                                 # a road into the sea: the line turning blue (atlas rows)
SEA_LINE_Y = 6.5                                       # the blue line between two Ocean spaces (over the lane, y 6)
BRIDGE_LENGTH, BRIDGE_WATER = 22.0, 60.0               # the game's bridge; water up to this wide gets bridges end to end
BRIDGE_SPAN = 20.0                                     # one bridge does for water this much longer than it (the game's
                                                       # bridges cross up to about 40 units of grid water each)


def texture_names(m: igbmodel.Model) -> list[str]:
    o, n = m.chunk("TEXT")
    return [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("mod")
    ap.add_argument("--assets", default=str(worldfile.ASSETS))
    ap.add_argument("--no-picture", action="store_true")
    args = ap.parse_args()
    assets, mod = Path(args.assets), Path(args.mod)
    out = mod / "Assets"
    out.mkdir(parents=True, exist_ok=True)
    F00 = assets / "CommonData" / "dataField" / "F00"
    POS = assets / "CommonData" / "fieldPosition"
    w = worldfile.load(Path(args.world))
    if w["board"] != 0:
        log = [f"world {args.world}: board {w['board']}, {len(w['spaces'])} spaces, {len(w['links'])} links"]
        dungeon.build(w, assets, out, log)
        (mod / "world_log.txt").write_text("\n".join(log) + "\n")
        print("\n".join(log))
        if not args.no_picture:
            render_top.render(mod / "world_map.png", out, 1.2, render_top.board_box(w["board"]), render_top.board_files(w["board"]),
                              True, None, w["board"])
            print("wrote", mod / "world_map.png")
        return
    grid = worldfile.grid(w)
    log = [f"world {args.world}: {len(w['spaces'])} spaces, {len(w['links'])} links, terrain {grid.w}x{grid.h} cells of {grid.cell}"]

    # ---- where everything goes ---------------------------------------------------------------------------------------------
    spaces, game_links = load_board(assets, 0)
    old = {s["id"]: s["pos"] for s in spaces}
    by_id = {s["id"]: s for s in w["spaces"]}
    if set(by_id) != set(old):
        sys.exit("the world must keep every space of the board (adding or removing spaces is not supported yet)")
    # roads climb plateaus by slopes: where one would climb too steeply (up a cliff), the cells around it become a slope
    on_land = [(a, b) for a, b in w["links"] if by_id[a]["kind"] != OCEAN and by_id[b]["kind"] != OCEAN]
    ramps = terrain.ramp_roads(grid, [((by_id[a]["x"], by_id[a]["z"]), (by_id[b]["x"], by_id[b]["z"])) for a, b in on_land])
    log.append(f"terrain: {ramps} slopes widened where roads climbed onto a plateau too steeply")
    # a space on the sea stays on it (the grid lifts water like the nearest land, for the cliffs' sake)
    space_lift = lambda x, z: 0.0 if grid.code_at(x, z) == "." else grid.lift(x, z)
    new = {n: (by_id[n]["x"], SPACE_Y + space_lift(by_id[n]["x"], by_id[n]["z"]), by_id[n]["z"]) for n in old}
    delta = {n: tuple(new[n][k] - old[n][k] for k in range(3)) for n in old}

    def nearest(x: float, z: float, ids=None) -> int:
        return min(ids or old, key=lambda n: (old[n][0] - x) ** 2 + (old[n][2] - z) ** 2)

    def position_file(name: str, ids=None) -> bytes:
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

    # ---- links: CHAIN slots are directions (0 +z, 1 +x, 2 -z, 3 -x) ------------------------------------------------------
    roads = Roads(assets)
    roads.node = dict(new)
    links = {n: [] for n in old}
    for a, b in w["links"]:
        links[a].append(b)
        links[b].append(a)
    problems = []
    chain = bytearray(roads.chain)
    for n in old:
        slots = [0xFFFF] * 4
        for m in links[n]:
            dx, dz = new[m][0] - new[n][0], new[m][2] - new[n][2]
            if min(abs(dx), abs(dz)) >= 1.5:
                problems.append(f"link {n}-{m} is not straight (dx {dx:.0f}, dz {dz:.0f})")
            s = roads.slot(n, m)
            if slots[s] != 0xFFFF:
                problems.append(f"space {n}: links to {slots[s]} and {m} leave in the same direction")
            slots[s] = m
        o = 2 + 10 * n
        assert struct.unpack_from("<H", chain, o)[0] == n
        struct.pack_into("<4H", chain, o + 2, *slots)
    if problems:
        sys.exit("cannot build:\n  " + "\n  ".join(sorted(set(problems))))
    roads.chain = chain
    roads.links = links
    (out / "CHAIN_000.DAT").write_bytes(bytes(chain))
    changed = sum(1 for n in old if sorted(links[n]) != sorted(game_links.get(n, [])))
    log.append(f"links: {changed} spaces have links other than the game's")

    # ---- camera limits (stg000 record 13 00 00 00: x max, z max, x min, z min) ---------------------------------------------
    stg = bytearray((assets / "Data_eng" / "dataSeq_EN" / "stg000_EN.DAT").read_bytes())
    cam = next(o for o in range(0, len(stg) - 28, 4) if stg[o:o + 4] == b"\x13\x00\x00\x00"
               and stg[o + 12:o + 16] == b"\x12\x00\x00\x00" and stg[o + 20:o + 24] == b"\x11\x00\x00\x00")
    limits = struct.unpack_from("<4h", stg, cam + 4)
    ext = lambda pos: (max(p[0] for p in pos), max(p[2] for p in pos), min(p[0] for p in pos), min(p[2] for p in pos))
    margin = [l - e for l, e in zip(limits, ext(old.values()))]
    new_limits = [round(e + m) for e, m in zip(ext(new.values()), margin)]
    struct.pack_into("<4h", stg, cam + 4, *new_limits)
    (out / "stg000_EN.DAT").write_bytes(stg)
    log.append(f"camera limits (x max, z max, x min, z min): {limits} -> {tuple(new_limits)}")

    # ---- terrain ----------------------------------------------------------------------------------------------------------
    shores = []
    meshes = terrain.meshes(grid, shores)
    for k, ms in meshes.items():
        log.append(f"terrain {k}: {len(ms)} vertices, {len(ms.tris)} triangles")

    def shore(x: float, z: float) -> str:
        return min(shores, key=lambda s: (s[0] - x) ** 2 + (s[1] - z) ** 2)[2]

    # ---- roads ------------------------------------------------------------------------------------------------------------
    road = roads.meshes[ROAD_PIECE]
    proto = next(i for t in road["tris"] for i in t if road_uv(*road["verts"][i].uv))
    road["tris"] = [[proto] * 3]
    road["changed"] = True
    ground = lambda n: grid.code_at(*roads.centre(n))
    ocean = lambda n: by_id[n]["kind"] == OCEAN
    # a space out on the open sea that is no Ocean space (the whirlpool): reached by the sea lane alone, no line or tile
    adrift = lambda n: not ocean(n) and all(grid.code_at(roads.centre(n)[0] + dx, roads.centre(n)[1] + dz) == "."
                                            for dx in (-12, 0, 12) for dz in (-12, 0, 12))
    arrowed = {tuple(sorted(l)) for ls in ARROWS.values() for l in ls}
    styles, bridges = {}, []
    for a in sorted(links):
        for b in links[a]:
            if a > b:
                continue
            if (a, b) in arrowed:
                styles[(a, b)] = styles[(b, a)] = "arrow"     # the arrows are the road (_arrows())
                continue
            if adrift(a) or adrift(b):
                styles[(a, b)] = styles[(b, a)] = "lane"
                continue
            if ocean(a) and ocean(b):
                styles[(a, b)] = styles[(b, a)] = "water"     # the blue line, on the sea lane (_sea_route())
                roads.emit(ROAD_PIECE, _sea_route(roads, a, b))
                continue
            if ocean(a) or ocean(b):
                styles[(a, b)] = styles[(b, a)] = "line"
                land, sea = (b, a) if ocean(a) else (a, b)
                roads.emit(ROAD_PIECE, _to_water(roads, grid, land, sea))
                continue
            style = "dirt" if ground(a) in "gf" and ground(b) in "gf" else "line"
            styles[(a, b)] = styles[(b, a)] = style
            d = STEPS[roads.slot(a, b)]
            ca, cb = roads.centre(a), roads.centre(b)
            length = math.dist(ca, cb)
            if length - 2 * CLEAR <= 0.5:
                continue
            at = lambda t: (ca[0] + (cb[0] - ca[0]) * t / length, ca[1] + (cb[1] - ca[1]) * t / length)
            # rivers the road crosses get a bridge (the bridge is the road there); wider water, and water between two
            # open shores (a strait between islands), keeps the strip
            gaps, open_water, t, run = [], [], CLEAR, None
            while t <= length - CLEAR:
                wet = grid.code_at(*at(t)) == "."
                if wet and run is None:
                    run = t
                if run is not None and (not wet or t + 1 > length - CLEAR):
                    if t - run > BRIDGE_WATER or shore(*at(run)) == shore(*at(t)) == "sea":
                        open_water.append((run, t))                  # the plain line across, as the game draws it
                    else:
                        k = max(1, math.ceil((t - run - BRIDGE_SPAN) / BRIDGE_LENGTH))
                        mid = (run + t) / 2
                        gaps.append((mid - k * BRIDGE_LENGTH / 2, mid + k * BRIDGE_LENGTH / 2))
                        # between two snowy banks the game's bridge has snow on it (it has one only along x)
                        snowy = d[0] and all(grid.code_at(*at(s)) == "w" for s in (run - 5, t + 5))
                        kind = "bridge:" + ("x" if d[0] else "z") + (":snow" if snowy else "")
                        for i in range(k):
                            x, z = at(mid + (i - (k - 1) / 2) * BRIDGE_LENGTH)
                            bridges.append({"t": "bridge", "v": kind, "x": round(x, 2), "z": round(z, 2)})
                        log.append(f"bridge: link {a}-{b}, water {t - run:.0f} across, {k} bridge(s) at {at(mid)[0]:.0f}, {at(mid)[1]:.0f}"
                                   + (" (snowy)" if snowy else ""))
                    run = None
                t += 1.0
            pieces_t, start = [], CLEAR
            for g0, g1 in sorted(gaps):
                if g0 - start > 0.5:
                    pieces_t.append((start, g0))
                start = max(start, g1)
            if length - CLEAR - start > 0.5:
                pieces_t.append((start, length - CLEAR))
            cuts, split = [c for span in open_water for c in span], []
            for t0, t1 in pieces_t:                              # dirt on land, the line over open water
                cs = sorted({t0, t1, *(c for c in cuts if t0 < c < t1)})
                split += [(c0, c1) for c0, c1 in zip(cs, cs[1:]) if c1 - c0 > 0.5]
            pieces_t = split
            for t0, t1 in pieces_t:
                n = max(1, round((t1 - t0) / 10.0))
                rows = []
                dry = not any(w0 <= (t0 + t1) / 2 <= w1 for w0, w1 in open_water)
                for s_ in range(n + 1):
                    t = t0 + (t1 - t0) * s_ / n
                    if style == "dirt" and dry:
                        v = DIRT_V[0] + (DIRT_V[1] - DIRT_V[0]) * terrain.mirror(t - CLEAR, DIRT_TILE)
                    else:
                        v = LINE_V
                    rows.append(roads.band(at(t), d, 0.0, 0.0, ROAD_Y, v, v)[:2])
                roads.emit(ROAD_PIECE, [[*rows[q], *rows[q + 1][::-1]] for q in range(n)])
    for a in sorted(links):
        arms = [b for b in links[a] if styles[(a, b)] not in ("arrow", "lane")]
        if ocean(a):                                     # its tile: the blue line from the centre towards each link
            roads.emit(ROAD_PIECE, [_blue(roads.band(roads.centre(a), STEPS[roads.slot(a, b)], 0.0, CLEAR, SEA_LINE_Y,
                                                     WATER_V[1], WATER_V[1])) for b in arms])
        elif not adrift(a):
            roads.build_tile(a, {roads.slot(a, b): styles[(a, b)] for b in arms}, ROAD_PIECE, ROAD_Y)
    count = lambda st: sum(1 for k, s in styles.items() if k[0] < k[1] and s == st)
    log.append(f"roads: {len(bridges)} bridges over rivers")
    log.append(f"roads: {sum(1 for k in styles if k[0] < k[1])} links, {count('dirt')} with dirt, "
               f"{count('water')} sea routes, {count('arrow')} with arrows, {count('lane')} by the sea lane alone")

    # ---- trees and mountains ----------------------------------------------------------------------------------------------
    prop_pieces = props.pieces(F00)

    # ---- the model files ----------------------------------------------------------------------------------------------------
    specials = [s["id"] for s in spaces if 0x14 <= s["type"][0] <= 0x1D or s["type"][0] >= 0x26]
    models = {f: igbmodel.load(F00 / f"F00_{f}.model") for f in FILES}
    plan = {}                                          # (file, piece) -> 'hide' | 'keep' | 'building' | 'area' | 'pivot' | channel
    free = {}                                          # (layer, texture) -> pieces that are hidden and can take terrain
    for f, m in models.items():
        tex = texture_names(m)
        for gi, nd in enumerate(m.mesh_nodes()):
            g = m.geoms[gi]
            pos, _ = igbmodel.mesh(m, g)
            M = m.placement(gi)
            world_pos = [igbmodel.apply(M, p) for p in pos]
            xs, zs = [p[0] for p in world_pos], [p[2] for p in world_pos]
            key = (f, gi)
            if key == ROAD_PIECE or key in KEEP or nd["name"] in KEEP_LAYERS:
                plan[key] = "keep"
            elif key in ARROWS:
                plan[key] = "arrow"
            elif key in LANES:
                plan[key] = "lane"
            elif key in prop_pieces:
                plan[key] = "props"
            elif key in PIVOTED:
                plan[key] = "pivot"
            elif key in EXTRA_BUILDINGS or (nd["name"] in BUILDING_LAYERS and max(max(xs) - min(xs), max(zs) - min(zs)) < BUILDING_SIZE):
                plan[key] = "building"
            elif key in AREAS:
                plan[key] = "area"
            else:
                plan[key] = "hide"
                kind = (nd["name"], tex[nd["texture"]] if nd["texture"] >= 0 else "")
                free.setdefault(kind, []).append(key)
    # the shadows (props of type shade) of pieces the build keeps as they are (a building's own) are still there: only the
    # ones in pieces it hides or rewrites are drawn again
    templates = props.templates(F00)
    own = [p for p in w.get("props", []) if p["t"] == "shade" and plan.get(templates[p["v"]]["piece"]) in ("keep", "building", "area", "pivot")]
    placed = [p for p in w.get("props", []) if p not in own]
    prop_parts = props.build({f: igbmodel.load(F00 / f"F00_{f}.model") for f in FILES}, placed + bridges,
                             terrain.BASE_Y, F00, shadow_y=terrain.OVERLAY_Y + 0.12, lift=grid.lift)
    log.append(f"props: {len(placed)} ({sum(1 for p in placed if p['t'] == 'tree')} trees, "
               f"{sum(1 for p in placed if p['t'] == 'shade')} shadows) in {len(prop_parts)} pieces")
    assign = {}                                        # (file, piece) -> list of (channel, Mesh) parts
    used = set()
    for ch, ms in meshes.items():
        if ch == "sea":
            assign[SEA_PIECE] = (ch, ms)
            continue
        if not len(ms):
            continue
        parts = _split(ms, MAX_VERTS)
        pool = LATE.get(ch) or sorted(free.get(CHANNELS[ch], []), key=lambda k: -models[k[0]].geoms[k[1]].verts)
        pool = [k for k in pool if k not in used and plan[k] == "hide"]
        if len(pool) < len(parts):
            sys.exit(f"terrain {ch}: {len(parts)} pieces needed, only {len(pool)} free pieces of {CHANNELS[ch]}")
        for part, key in zip(parts, pool):
            assign[key] = (ch, part)
            used.add(key)
            log.append(f"terrain {ch}: {len(part)} vertices into F00_{key[0]} piece {key[1]}")

    present = {tuple(sorted(l)) for l in w["links"]}
    arrows = _arrows(models, present, old, delta, log)
    game_ocean = {s["id"] for s in spaces if s["type"][0] == OCEAN}
    sea_links = sorted({tuple(sorted((a, b))) for a, bs in game_links.items() for b in bs if a in game_ocean or b in game_ocean})
    log.append(f"sea lanes: {sum(1 for l in sea_links if l in present)} of the game's {len(sea_links)} links with an Ocean "
               f"space are in the world; links with one that the game has not get no lane: "
               f"{sorted(l for l in present if (l[0] in game_ocean or l[1] in game_ocean) and l not in sea_links) or 'none'}")
    for f, m in models.items():
        vo = m.chunk("VERT")[0]
        replace, mdata, moved = {}, bytearray(m.data), set()
        recs, parent = m.tree()
        for gi, nd in enumerate(m.mesh_nodes()):
            key = (f, gi)
            g = m.geoms[gi]
            raw = bytearray(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])
            _, tris = igbmodel.mesh(m, g)
            M = m.placement(gi)
            world_pos = [igbmodel.apply(M, struct.unpack_from("<3f", raw, g.stride * i)) for i in range(g.verts)]
            xs, zs = [p[0] for p in world_pos], [p[2] for p in world_pos]
            what = plan[key]
            if key in assign:
                ch, part = assign[key]
                replace[gi] = _pack(part, raw[:g.stride], g.stride, M)
            elif key in prop_parts:
                replace[gi] = prop_parts[key]
            elif what == "keep":
                continue
            elif what == "arrow":
                replace[gi] = arrows if key == ARROW_PIECE and arrows[1] else (bytes(raw[:g.stride]), [0, 0, 0])
            elif what == "lane":
                lane = _along(m, gi, sea_links, present, old, delta, g.stride)
                replace[gi] = lane if lane[1] else (bytes(raw[:g.stride]), [0, 0, 0])
            elif what == "pivot":
                n, y = PIVOTED[key]
                i = nd["node"]
                while recs[i][0] < 0:
                    i = parent[i]
                mi = recs[i][0] // 64
                if mi not in moved:
                    moved.add(mi)
                    o = m.chunk("MTRX")[0] + 64 * mi + 48
                    t = struct.unpack_from("<3f", mdata, o)
                    t2 = (t[0] + delta[n][0], t[1] + delta[n][1] if y is None else t[1] + y - min(p[1] for p in world_pos),
                          t[2] + delta[n][2])
                    struct.pack_into("<3f", mdata, o, *t2)
            elif what == "building":
                n = EXTRA_BUILDINGS.get(key) or nearest((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2, specials)
                d = delta[n]
                if any(abs(c) > 1e-6 for c in d):
                    inv = igbmodel.inverse(M)
                    for i, p in enumerate(world_pos):
                        struct.pack_into("<3f", raw, g.stride * i, *igbmodel.apply(inv, tuple(p[k] + d[k] for k in range(3))))
                    replace[gi] = (bytes(raw), [i for t in tris for i in t])
            elif what == "area":
                inv, keep = igbmodel.inverse(M), set()
                for part in AREAS[key]:
                    vs = {i for c in clusters(world_pos, tris, weld=True) if math.dist(centre(world_pos, c), part["centre"]) <= part["radius"]
                          for i in c}
                    n = part.get("space") or nearest(*centre(world_pos, sorted(vs)), specials)
                    d = delta[n]
                    for i in vs:
                        struct.pack_into("<3f", raw, g.stride * i, *igbmodel.apply(inv, tuple(world_pos[i][k] + d[k] for k in range(3))))
                    keep |= vs
                replace[gi] = (bytes(raw), [i for t in tris if all(v in keep for v in t) for i in t])
            else:
                replace[gi] = (bytes(raw[:g.stride]), [0, 0, 0])     # hidden: one degenerate triangle
        if f == ROAD_PIECE[0]:
            ms = roads.meshes[ROAD_PIECE]
            used_v = sorted({i for t in ms["tris"] for i in t})
            remap = {o: k for k, o in enumerate(used_v)}
            # the roads were laid at ROAD_Y: raised here onto plateaus and up slopes; out on the sea (not on a land space's
            # tile) they stay down, as the Ocean spaces do
            tiles = [roads.centre(n) for n in old if not ocean(n)]
            on_tile = lambda x, z: any(abs(x - cx) <= CLEAR + 0.5 and abs(z - cz) <= CLEAR + 0.5 for cx, cz in tiles)
            road_lift = lambda x, z: grid.lift(x, z) if grid.code_at(x, z) != "." or on_tile(x, z) else 0.0
            up = lambda p: (p[0], p[1] + road_lift(p[0], p[2]), p[2])
            vb = b"".join(type(v)(igbmodel.apply(ms["inverse"], up(v.pos)), v.nrm, v.col, v.uv, v.rest).pack()
                          for v in (ms["verts"][i] for i in used_v))
            replace[ROAD_PIECE[1]] = (vb, [remap[i] for t in ms["tris"] for i in t])
        (out / f"F00_{f}.model").write_bytes(igbmodel.rebuild(m, replace, bytes(mdata)))
    (mod / "world_log.txt").write_text("\n".join(log) + "\n")
    print("\n".join(log))

    if not args.no_picture:
        g = grid
        box = (g.x0, g.z0, g.x0 + g.w * g.cell, g.z0 + g.h * g.cell)
        render_top.render(mod / "world_map.png", out, 0.7, box, render_top.FILES, False, None)
        print("wrote", mod / "world_map.png")


def _blue(band: list) -> list:
    """A band of the line (roads.band) in the blue line instead: the atlas column right of the line's."""
    return [(p, (u + 0.25, v)) for p, (u, v) in band]


def _sea_route(roads: Roads, a: int, b: int) -> list[list[tuple]]:
    """The road between two Ocean spaces' tiles, as the game draws it: the blue line (atlas row WATER_V[1]), a little above
    the sea lane under it (SEA_LINE_Y)."""
    ca, cb = roads.centre(a), roads.centre(b)
    d = STEPS[roads.slot(a, b)]
    length = math.dist(ca, cb)
    if length - 2 * CLEAR <= 0.5:
        return []
    v = WATER_V[1]
    n = max(1, round((length - 2 * CLEAR) / 10.0))
    rows = [_blue(roads.band(ca, d, CLEAR + (length - 2 * CLEAR) * k / n, 0.0, SEA_LINE_Y, v, v)[:2]) for k in range(n + 1)]
    return [[*rows[k], *rows[k + 1][::-1]] for k in range(n)]


def _to_water(roads: Roads, grid: terrain.Grid, land: int, sea: int) -> list[list[tuple]]:
    """The road from a land space's tile to an Ocean space's, as the game draws it (link 39-38): the line alone, turning
    from orange to blue (atlas rows WATER_V, the column right of the dirt strip) where it leaves the land, and coming down
    from the road's height to the blue line's (SEA_LINE_Y) over the water."""
    ca, cb = roads.centre(land), roads.centre(sea)
    d = STEPS[roads.slot(land, sea)]
    length = math.dist(ca, cb)
    end = length - CLEAR
    if end - CLEAR <= 0.5:
        return []
    at = lambda t: (ca[0] + (cb[0] - ca[0]) * t / length, ca[1] + (cb[1] - ca[1]) * t / length)
    shore = next((t for t in range(int(CLEAR), int(end)) if grid.code_at(*at(t)) == "."), end - 6.0)
    ramp = (max(shore - 6.0, CLEAR), min(shore + 3.0, end))   # where the orange turns blue
    ts = sorted({CLEAR, end, *(t for t in ramp if CLEAR < t < end),
                 *(CLEAR + k * 10.0 for k in range(1, int((end - CLEAR) / 10.0)))})
    rows = []
    for t in ts:
        f = min(max((t - ramp[0]) / (ramp[1] - ramp[0]), 0.0), 1.0)
        v = WATER_V[0] + (WATER_V[1] - WATER_V[0]) * f
        y = ROAD_Y + (SEA_LINE_Y - ROAD_Y) * min(max((t - shore) / max(end - shore, 1.0), 0.0), 1.0)
        rows.append(_blue(roads.band(at(t), d, 0.0, 0.0, y, v, v)[:2]))
    return [[*rows[s], *rows[s + 1][::-1]] for s in range(len(rows) - 1)]


def _arrows(models: dict, present: set, old: dict, delta: dict, log: list) -> tuple[bytes, list[int]]:
    """The one-way roads' arrows (ARROWS) for ARROW_PIECE, in its vertex layout: every arrow piece whose links are all in
    the world, each vertex moved as the link it lies along (by its two spaces' moves, mixed by how far along it is), so
    the arrows follow, and stretch with, their spaces across the board; they keep their own heights (ramps to the sea)."""
    stride = models[ARROW_PIECE[0]].geoms[ARROW_PIECE[1]].stride
    vb, idx = bytearray(), []
    for (f, gi), ls in ARROWS.items():
        if not all(tuple(sorted(l)) in present for l in ls):
            log.append(f"arrows F00_{f} piece {gi}: left out (link {', '.join(f'{a}-{b}' for a, b in ls)} is gone)")
            continue
        pb, pi = _along(models[f], gi, ls, None, old, delta, stride)
        idx += [len(vb) // stride + i for i in pi]
        vb += pb
    return bytes(vb), idx


def _along(m: igbmodel.Model, gi: int, ls: list, present: set | None, old: dict, delta: dict,
           stride: int) -> tuple[bytes, list[int]]:
    """A piece (placed by no matrix) laid along links ls, in a layout `stride` bytes long (the piece's own, or a shorter
    start of it): every vertex moved as the link it lies nearest (by its two spaces' moves across the board, mixed by how
    far along it is), keeping its height; with `present`, only the triangles whose middle lies nearest a link in it."""
    g = m.geoms[gi]
    raw = igbmodel.vertex_bytes(m, gi)
    pos, tris = igbmodel.mesh(m, g)

    def nearest(x: float, z: float) -> tuple:
        best = None
        for a, b in ls:
            (ax, _, az), (bx, _, bz) = old[a], old[b]
            l2 = (bx - ax) ** 2 + (bz - az) ** 2
            t = min(max(((x - ax) * (bx - ax) + (z - az) * (bz - az)) / l2, 0.0), 1.0)
            d = math.dist((x, z), (ax + (bx - ax) * t, az + (bz - az) * t))
            if best is None or d < best[0]:
                best = (d, a, b, t)
        return best[1:]

    if present is not None:
        tris = [t for t in tris if tuple(sorted(nearest(sum(pos[i][0] for i in t) / 3, sum(pos[i][2] for i in t) / 3)[:2]))
                in present]
    used = sorted({i for t in tris for i in t})
    remap = {o: k for k, o in enumerate(used)}
    vb = bytearray()
    for i in used:
        p = pos[i]
        a, b, t = nearest(p[0], p[2])
        v = bytearray(raw[g.stride * i: g.stride * i + stride])
        move = [delta[a][k] * (1 - t) + delta[b][k] * t for k in (0, 2)]
        struct.pack_into("<3f", v, 0, p[0] + move[0], p[1], p[2] + move[1])
        vb += v
    return bytes(vb), [remap[i] for t in tris for i in t]


def _split(ms: terrain.Mesh, limit: int) -> list[terrain.Mesh]:
    """A mesh cut into meshes of at most `limit` vertices (whole triangles; triangles never share vertices across parts)."""
    if len(ms) <= limit:
        return [ms]
    parts, cur, remap = [], terrain.Mesh(), {}
    for t in ms.tris:
        if len(cur) + 3 > limit:
            parts.append(cur)
            cur, remap = terrain.Mesh(), {}
        idx = []
        for i in t:
            if i not in remap:
                remap[i] = len(cur.pos)
                cur.pos.append(ms.pos[i])
                cur.col.append(ms.col[i])
                cur.uv.append(ms.uv[i])
            idx.append(remap[i])
        cur.tris.append(idx)
    parts.append(cur)
    return parts


def _pack(ms: terrain.Mesh, template: bytes, stride: int, M) -> tuple[bytes, list[int]]:
    """Vertex bytes in a piece's own layout and coordinates: position, normal (up), colour, uv, then the rest of the
    template vertex (a second uv set in the 44-byte layout)."""
    inv = igbmodel.inverse(M)
    o, up = igbmodel.apply(inv, (0, 0, 0)), igbmodel.apply(inv, (0, 1, 0))
    n = [up[k] - o[k] for k in range(3)]
    ln = math.sqrt(sum(c * c for c in n)) or 1.0
    n = [c / ln for c in n]
    rest = bytes(template[0x24:stride])
    vb = bytearray()
    for p, c, uv in zip(ms.pos, ms.col, ms.uv):
        vb += struct.pack("<6f", *igbmodel.apply(inv, p), *n) + c + struct.pack("<2f", *uv) + rest
    return bytes(vb), [i for t in ms.tris for i in t]


if __name__ == "__main__":
    main()

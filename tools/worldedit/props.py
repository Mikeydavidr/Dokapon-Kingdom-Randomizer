"""Trees, mountains, hills and bridges as objects that can be placed anywhere on a board: copies of the game's own ones.

What they are on board 0 (F00 model files):
  tree      one cluster of vertices in a wood_01 piece (ha.tga): three crossed quads of leaves, and under 71 of them a
            trunk: a cluster in a road_01 piece in the fieldC bark tile, its foot on the ground. A crown without a trunk
            floats, its lowest point about 10 units above the ground. 71 trees (not the same ones) stand over a soft round
            shadow: a quad about 48 x 42 of the fieldC shadow blob in a road_shadow piece, about (-5, +7) from the tree.
            A copy of a tree has its template's shadow, or none.
  mountain  one cluster in a mountain_01 / mountain_02 piece (MTA.tga), its foot sunk a little into the ground
  hill      a small grassy plateau: a ring of rock-strata cliff (a town_01 piece of its own, objes.tga), its raised grass
            top (a green_01 piece of its own) and the ragged grass edge round the top (in a shared road_side piece); four
            on the board (N 10+11, N 31+32, N 52+53, M 56+57)
  bridge    an arched wooden bridge 22 units long and 14 wide (deck, six posts, two rails; fieldC plank tile, road_01), along
            x or along z; the two in F00_N piece 55 serve as templates. build_world.py puts them where roads cross rivers.
            Over the snow the game's bridge (along x) has snow caps on its rails and deck: "bridge:x:snow".
  clover, flowers, mushroom, ice
            the small decorations, a few quads each in the fieldC tiles of DECO_TILES, in road_01 pieces (some in road_shadow
            ones), most with a small shadow beside them in a road_shadow piece: a clover with a curled leaf (164 of them), a
            bunch of flowers over a tuft of leaves (33), a yellow, purple or orange mushroom (28), a sparkly ice rock on the
            snow (25). They stay at the game's height (a plateau's lift apart).
A prop names its template ("<file>:<piece>:<n>" for a cluster, n = its place in that piece; "hill:<file>:<piece>" for a
hill; "deco:<file>:<piece>:<n>" for a decoration, by its first cluster) and where its middle goes. build_world.py writes
every prop into its template's pieces, so the vertex layout and the material are the game's.
"""
import struct
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel
from units import clusters

TYPES = {"wood_01": "tree", "mountain_01": "mountain", "mountain_02": "mountain"}
SOURCES = {"wood": ("wood_01",), "A": ("mountain_01",), "M": ("mountain_02",)}
LIFT = {"tree": 10.3, "mountain": -0.6}     # where a prop's lowest point goes, above the ground
TRUNK_LIFT = 0.5                             # a tree with a trunk: the trunk's foot, just above the ground
BARK = (0.36, 0.24, 0.52, 0.39)              # the fieldC bark tile
TRUNK_OFFSET, TRUNK_REACH = (1.5, -5.5), 5.0  # a trunk's middle from its crown's middle, give or take TRUNK_REACH
DECO = ("clover", "flowers", "mushroom", "ice")
KEEP_Y = {"hill", "bridge", "shade", *DECO}           # placed at the game's own height (the board's ground is the game's: y 7)
BRIDGE_HALF = 11.0                           # half a bridge's length: where its two ends are
# the Lava Cave is two clusters of a mountain piece (within this radius of its middle): build_world.py keeps them in that
# piece with their space; the piece's other clusters (the mountains by Yukon, spaces 124-128) are copied into another
EXCLUDE = {("A", 25): ((413.0, 66.0), 30.0)}
MOUNTAIN_MOVED = {("A", 25): ("A", 14)}
FILES = ["A", "M", "N", "Anim1", "Anim2", "wood"]
SHADOW_OFFSET, SHADOW_REACH = (-4.9, 6.6), 10.0   # a tree's shadow from the tree's middle, give or take SHADOW_REACH
SHADOW_TILE = (0.81, 0.80, 0.88, 0.89)       # the fieldC tree shadow (only 64 of the 219 trees have a flat one)
# the shadows go into a road_shadow piece drawn after the sea and the surf: the game draws the _Fog_Water pieces in file and
# node order and they hide whatever is drawn after them below their quads, even where they are clear
SHADOW_PIECE = ("Anim2", 13)
# the decorations' parts by fieldC tile (u0, v0, u1, v1, in any whole repeat of the atlas), first match wins; None: a shadow
DECO_TILES = [((0.87, 0.76, 1.0, 0.87), "flowers"), ((0.745, 0.905, 0.815, 1.0), "flowers"),   # flowers, their leaves
              ((0.815, 0.935, 0.875, 1.0), "clover"), ((0.935, 0.86, 1.0, 0.94), "clover"),     # a clover, its curled leaf
              ((0.875, 0.86, 0.935, 0.94), "mushroom"), ((0.865, 0.935, 0.94, 1.0), "mushroom"),
              ((0.935, 0.935, 1.0, 1.0), "mushroom"), ((0.685, 0.755, 0.755, 0.815), "ice"),
              ((0.795, 0.755, 0.85, 0.815), None), ((0.765, 0.805, 0.815, 0.855), None), ((0.745, 0.875, 0.785, 0.905), None)]
DECO_GROUP = 7.0                             # parts whose middles are this close make one decoration
# the road piece is drawn again by build_world.py: the decorations in it go into another road_01 piece of the same layout
DECO_MOVED = {("A", 9): ("A", 204)}
PLANK = (0.37, 0.24, 0.51, 0.38)             # the fieldC plank tile
STRATA = (0.0, 0.37, 0.26, 0.48)             # the objes rock-strata tile
# bridge templates: "<axis>[:snow]" -> (piece, box x0 z0 x1 z1 of its planks, or None: all of the piece), and how high the
# ground at the template is (the snowy bridge, link 172-173, is on the snow plateau: its deck in M 58, its snow caps
# A 80-83, fieldC snow tile)
BRIDGES = {"x": ([("N", 55, (-497, -198, -471, -179))], 0.0), "z": ([("N", 55, (-483, -384, -464, -358))], 0.0),
           "x:snow": ([("M", 58, (14, 218, 43, 246)), ("A", 80, None), ("A", 81, None), ("A", 82, None), ("A", 83, None)], 7.0)}


def _inside(uv, box) -> bool:
    return box[0] <= uv[0] <= box[2] and box[1] <= uv[1] <= box[3]


def _part(m: igbmodel.Model, f: str, gi: int, verts=None) -> dict:
    """One piece's share of a template: its vertices (all, or the given ones), their triangles and their world positions."""
    pos, tris = igbmodel.mesh(m, m.geoms[gi])
    M = m.placement(gi)
    vs = sorted(verts) if verts is not None else list(range(len(pos)))
    keep = set(vs)
    return {"file": f, "piece": gi, "verts": vs, "tris": [t for t in tris if all(i in keep for i in t)],
            "world": {i: igbmodel.apply(M, pos[i]) for i in vs}}


def _measure(t: dict) -> dict:
    ps = [p for part in t["parts"] for p in part["world"].values()]
    xs, ys, zs = [p[0] for p in ps], [p[1] for p in ps], [p[2] for p in ps]
    t.update(centre=((min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2), bottom=min(ys), top=max(ys),
             width=max(max(xs) - min(xs), max(zs) - min(zs)), height=max(ys) - min(ys))
    return t


@lru_cache(maxsize=None)
def templates(F00: Path) -> dict[str, dict]:
    """key -> {type, parts: [{file, piece, verts, tris, world, into?}], centre (x, z), bottom, top, width, height}; a part
    with 'into' is copied into that piece instead of its own. Trees with a shadow also have 'shadow' (the template it is
    copied from) and 'shadow_at' (where its middle is, from the tree's)."""
    models = {f: igbmodel.load(F00 / f"F00_{f}.model") for f in FILES}
    out = {}
    for f, layers in SOURCES.items():
        m = models[f]
        for gi, nd in enumerate(m.mesh_nodes()):
            if nd["name"] not in layers:
                continue
            part = _part(m, f, gi)
            for n, c in enumerate(sorted(clusters([part["world"][i] for i in part["verts"]], part["tris"], weld=True), key=min)):
                t = _measure({"type": TYPES[nd["name"]], "parts": [_part(m, f, gi, c)]})
                if (f, gi) in EXCLUDE and _dist(t["centre"], EXCLUDE[(f, gi)][0]) <= EXCLUDE[(f, gi)][1]:
                    continue
                if (f, gi) in MOUNTAIN_MOVED:
                    t["parts"][0]["into"] = MOUNTAIN_MOVED[(f, gi)]
                out[f"{f}:{gi}:{n}"] = t
    trees = [t for t in out.values() if t["type"] == "tree"]
    # each tree's own shadow (about SHADOW_OFFSET from its middle), measured before the trunks change the middle
    for ti, si, s in _pair(trees, _tree_shadows(models), SHADOW_OFFSET, SHADOW_REACH):
        trees[ti]["shadow"] = s
        trees[ti]["shadow_at"] = (s["centre"][0] - trees[ti]["centre"][0], s["centre"][1] - trees[ti]["centre"][1])
    # each trunk goes with the crown it stands under (about TRUNK_OFFSET from the crown's middle)
    for ti, ki, k in _pair(trees, _trunks(models), TRUNK_OFFSET, TRUNK_REACH):
        trees[ti]["parts"] += k["parts"]
        trees[ti]["trunk"] = True
    for t in trees:
        if t.get("trunk"):
            centre = t["centre"]
            _measure(t)
            if "shadow_at" in t:                     # still from the crown's middle
                t["shadow_at"] = (t["shadow_at"][0] + centre[0] - t["centre"][0], t["shadow_at"][1] + centre[1] - t["centre"][1])
    out.update(_decorations(models))
    out.update(_shades(models))
    # hills: a town_01 piece that is all rock strata and small, with the green_01 piece over its middle as its top
    for f, m in models.items():
        o, n = m.chunk("TEXT")
        tex = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        vo = m.chunk("VERT")[0]
        nodes = m.mesh_nodes()
        for gi, nd in enumerate(nodes):
            if nd["name"] != "town_01" or tex[nd["texture"]] != "objes.tga":
                continue
            g = m.geoms[gi]
            uv = [struct.unpack_from("<2f", m.data, vo + g.vert_offset + g.stride * i + 0x1c) for i in range(g.verts)]
            ring = _part(m, f, gi)
            if not all(_inside(p, STRATA) for p in uv) or len(clusters([ring["world"][i] for i in ring["verts"]], ring["tris"], True)) != 1:
                continue
            rt = _measure({"parts": [ring]})
            if rt["width"] > 70:
                continue
            caps = [(f2, gj) for f2, m2 in models.items() for gj, nd2 in enumerate(m2.mesh_nodes()) if nd2["name"] == "green_01"]
            best = None
            for f2, gj in caps:
                cap = _measure({"parts": [_part(models[f2], f2, gj)]})
                d = (cap["centre"][0] - rt["centre"][0]) ** 2 + (cap["centre"][1] - rt["centre"][1]) ** 2
                if cap["width"] <= rt["width"] + 5 and d < 15 ** 2 and (best is None or d < best[0]):
                    best = (d, f2, gj)
            if best:
                t = _measure({"type": "hill", "parts": [ring, _part(models[best[1]], best[1], best[2])]})
                t["parts"] += _hill_rim(models, t)
                out[f"hill:{f}:{gi}"] = t
    for kind, (sources, base) in BRIDGES.items():
        bparts = []
        for f, gi, box in sources:
            m = models[f]
            part = _part(m, f, gi)
            if box is not None:
                uv = _uvs(m, gi, part["verts"])
                x0, z0, x1, z1 = box
                part = _part(m, f, gi, [i for i, p in part["world"].items()
                                        if x0 <= p[0] <= x1 and z0 <= p[2] <= z1 and _inside(uv[i], PLANK)])
            bparts.append(part)
        out[f"bridge:{kind}"] = _measure({"type": "bridge", "parts": bparts, "base": base})
    return out


def _hill_rim(models, t: dict) -> list[dict]:
    """The ragged grass edge round a hill's top: the road_side triangles over its footprint, no lower than a little under
    its top (they lie in the board's shared edge pieces). Copied into SHADOW_PIECE (the same atlas and material), drawn
    late, like the other edges."""
    cap_y = min(p[1] for p in t["parts"][1]["world"].values())
    ws = [p for part in t["parts"] for p in part["world"].values()]
    x0, x1 = min(p[0] for p in ws) - 4, max(p[0] for p in ws) + 4
    z0, z1 = min(p[2] for p in ws) - 4, max(p[2] for p in ws) + 4
    out = []
    for f in FILES:
        m = models[f]
        for gi, nd in enumerate(m.mesh_nodes()):
            if nd["name"] != "road_side":
                continue
            part = _part(m, f, gi)
            w = part["world"]
            tris = [tr for tr in part["tris"] if all(x0 <= w[i][0] <= x1 and z0 <= w[i][2] <= z1 for i in tr)
                    and min(w[i][1] for i in tr) >= cap_y - 3]
            if tris:
                rim = _part(m, f, gi, {i for tr in tris for i in tr})
                rim["tris"] = tris
                rim["into"] = SHADOW_PIECE
                out.append(rim)
    return out


def _dist(a, b) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _pair(trees: list[dict], things: list[dict], offset, reach: float) -> list[tuple[int, int, dict]]:
    """(tree, thing, the thing) for the things that go with a tree: about `offset` from its middle, within `reach`, each
    tree and each thing once, nearest pairs first."""
    expect = lambda t: (t["centre"][0] + offset[0], t["centre"][1] + offset[1])
    pairs = sorted((_dist(k["centre"], expect(t)), ti, ki) for ti, t in enumerate(trees) for ki, k in enumerate(things))
    taken_t, taken_k, out = set(), set(), []
    for d, ti, ki in pairs:
        if d > reach:
            break
        if ti in taken_t or ki in taken_k:
            continue
        taken_t.add(ti)
        taken_k.add(ki)
        out.append((ti, ki, things[ki]))
    return out


def _textures(m: igbmodel.Model) -> list[str]:
    o, n = m.chunk("TEXT")
    return [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]


def _uvs(m: igbmodel.Model, gi: int, verts) -> dict[int, tuple[float, float]]:
    g, vo = m.geoms[gi], m.chunk("VERT")[0]
    return {i: struct.unpack_from("<2f", m.data, vo + g.vert_offset + g.stride * i + 0x1c) for i in verts}


def _in_tile(uvs, box) -> bool:
    """Whether every uv is in the atlas tile, in any whole repeat of the atlas (a u or v of exactly 1, 2 ... is a tile's far
    edge)."""
    wrap = lambda c: c % 1 if c % 1 > 1e-4 or c < 0.5 else 1.0
    return all(box[0] - 0.006 <= wrap(u) <= box[2] + 0.006 and box[1] - 0.006 <= wrap(v) <= box[3] + 0.006 for u, v in uvs)


def _fieldc_clusters(models, layers: tuple[str, ...]):
    """(file, piece, layer, cluster, its part, its uvs) for every cluster of the fieldC pieces of these layers."""
    for f in FILES:
        m = models[f]
        tex = _textures(m)
        for gi, nd in enumerate(m.mesh_nodes()):
            if nd["name"] not in layers or nd["texture"] < 0 or tex[nd["texture"]] != "fieldC.tga":
                continue
            part = _part(m, f, gi)
            uv = _uvs(m, gi, part["verts"])
            for n, c in enumerate(sorted(clusters([part["world"][i] for i in part["verts"]], part["tris"], weld=True), key=min)):
                yield f, gi, nd["name"], n, c, [uv[i] for i in c]


def _tree_shadows(models) -> list[dict]:
    """The trees' shadows: road_shadow quads of the fieldC tree shadow, 40 to 55 units across, about flat (the seven
    draped over the game's cliffs are left out: laid flat they would stand up)."""
    out = []
    for f, gi, layer, n, c, uv in _fieldc_clusters(models, ("road_shadow",)):
        if _in_tile(uv, SHADOW_TILE):
            q = _measure({"parts": [_part(models[f], f, gi, c)]})
            if 40 <= q["width"] <= 55 and q["height"] < 4:
                out.append(q)
    return out


def _decorations(models) -> dict[str, dict]:
    """key -> template of every decoration: the clusters of DECO_TILES, those within DECO_GROUP of each other together (a
    clover, its leaf and its shadow). Parts in road_shadow pieces are copied into SHADOW_PIECE, drawn late."""
    found = []                                   # (kind or None, key, part)
    for f, gi, layer, n, c, uv in _fieldc_clusters(models, ("road_01", "road_shadow")):
        kind = next((k for box, k in DECO_TILES if _in_tile(uv, box)), False)
        if kind is False:
            continue
        part = _part(models[f], f, gi, c)
        if layer == "road_shadow":
            part["into"] = SHADOW_PIECE
        elif (f, gi) in DECO_MOVED:
            part["into"] = DECO_MOVED[(f, gi)]
        found.append((kind, f"deco:{f}:{gi}:{n}", _measure({"parts": [part]})))
    group = list(range(len(found)))
    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i
    for i in range(len(found)):
        for j in range(i):
            if _dist(found[i][2]["centre"], found[j][2]["centre"]) < DECO_GROUP:
                group[root(i)] = root(j)
    members = {}
    for i in range(len(found)):
        members.setdefault(root(i), []).append(found[i])
    out = {}
    for ms in members.values():
        kinds = {k for k, _, _ in ms if k}
        kind = next((k for k in ("mushroom", "flowers", "clover", "ice") if k in kinds), None)
        if kind is None:                         # a shadow with nothing over it
            continue
        key = next(key for k, key, _ in ms if k)
        out[key] = _measure({"type": kind, "parts": [t["parts"][0] for _, _, t in ms]})
    return out


def _shades(models) -> dict[str, dict]:
    """key -> template of every other shadow of the board (not a tree's, not a decoration's): the dark blobs under buildings,
    mountains and bushes, and the big soft ones on open grass. Each is a road_shadow cluster, copied into SHADOW_PIECE.
    'piece' is the piece it is in, so that build_world.py can leave out the ones whose piece it keeps as it is."""
    out = {}
    for f, gi, layer, n, c, uv in _fieldc_clusters(models, ("road_shadow",)):
        part = _part(models[f], f, gi, c)
        t = _measure({"type": "shade", "parts": [part], "piece": (f, gi)})
        if _in_tile(uv, SHADOW_TILE) and 40 <= t["width"] <= 55 and t["height"] < 4:
            continue                             # a tree's
        if any(_in_tile(uv, box) for box, k in DECO_TILES):
            continue                             # a decoration's
        part["into"] = SHADOW_PIECE
        out[f"shade:{f}:{gi}:{n}"] = t
    return out


def _trunks(models) -> list[dict]:
    """The trees' trunks: standing clusters in road_01 pieces, all in the fieldC bark tile (each under a tree's crown)."""
    out = []
    for f in FILES:
        m = models[f]
        o, n = m.chunk("TEXT")
        tex = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        vo = m.chunk("VERT")[0]
        for gi, nd in enumerate(m.mesh_nodes()):
            if nd["name"] != "road_01" or nd["texture"] < 0 or tex[nd["texture"]] != "fieldC.tga":
                continue
            g = m.geoms[gi]
            part = _part(m, f, gi)
            uv = {i: struct.unpack_from("<2f", m.data, vo + g.vert_offset + g.stride * i + 0x1c) for i in part["verts"]}
            for c in clusters([part["world"][i] for i in part["verts"]], part["tris"], weld=True):
                if all(_inside(uv[i], BARK) for i in c):
                    t = _measure({"parts": [_part(m, f, gi, c)]})
                    if t["width"] >= 8 and t["height"] >= 12:
                        out.append(t)
    return out


def from_game(F00: Path) -> list[dict]:
    """The props of the game's board: every template where it stands (bridges are put in by build_world.py)."""
    return [{"t": t["type"], "v": k, "x": round(t["centre"][0], 2), "z": round(t["centre"][1], 2)}
            for k, t in templates(F00).items() if t["type"] != "bridge"]


def variants(F00: Path) -> dict[str, list[dict]]:
    """Per prop type, its templates from small to large (what the editor offers)."""
    out = {}
    for k, t in templates(F00).items():
        if t["type"] != "bridge":
            out.setdefault(t["type"], []).append({"v": k, "width": round(t["width"], 1), "height": round(t["height"], 1)})
    for v in out.values():
        v.sort(key=lambda d: (d["width"] * d["height"], d["v"]))
    return out


def pieces(F00: Path) -> set[tuple[str, int]]:
    """Every piece props are written into (build_world.py keeps them for that and hides what no prop uses)."""
    out = {SHADOW_PIECE}
    for t in templates(F00).values():
        for part in t["parts"]:
            out.add(part.get("into") or (part["file"], part["piece"]))
    return out


def _copy(parts: dict, models: dict, part: dict, d, into: tuple[str, int] | None = None, rise=None) -> None:
    """Add a copy of a template part, moved by d (board coordinates), to its piece's output (or to piece `into`, a piece of
    the same material whose vertex layout is the same or a shorter start of it). rise(x, z): moved up by this much more at
    each vertex (where it ends up)."""
    m = models[part["file"]]
    g = m.geoms[part["piece"]]
    tf, tp = into or (part["file"], part["piece"])
    stride = models[tf].geoms[tp].stride
    inv = igbmodel.inverse(models[tf].placement(tp))
    raw = igbmodel.vertex_bytes(m, part["piece"])
    vb, idx = parts.setdefault((tf, tp), (bytearray(), []))
    base = len(vb) // stride
    remap = {}
    for i in part["verts"]:
        v = bytearray(raw[g.stride * i: g.stride * i + stride])
        wp = part["world"][i]
        x, z = wp[0] + d[0], wp[2] + d[2]
        struct.pack_into("<3f", v, 0, *igbmodel.apply(inv, (x, wp[1] + d[1] + (rise(x, z) if rise else 0.0), z)))
        remap[i] = base + len(remap)
        vb += v
    idx += [remap[i] for tri in part["tris"] for i in tri]


def build(models: dict[str, igbmodel.Model], props: list[dict], ground_y: float, F00: Path,
          shadow_y: float | None = None, lift=None) -> dict[tuple[str, int], tuple[bytes, list[int]]]:
    """{(file, piece): (vertex bytes, indices)} for every piece a prop is written into (a piece no prop uses is left out, for
    the caller to hide). Props of type 'bridge' may be in the list too (build_world.py adds them). shadow_y: the height of
    the trees' shadows (None: no shadows). lift(x, z): how far the ground there is above ground_y (plateaus): a prop
    stands that much higher, a hill rises by the difference from where the game has it, and a bridge slopes from the
    ground at one end to the ground at the other."""
    lift = lift or (lambda x, z: 0.0)
    tpl = templates(F00)
    parts: dict[tuple[str, int], tuple[bytearray, list[int]]] = {}
    for p in props:
        t = tpl.get(p["v"])
        if t is None:
            raise ValueError(f"prop at ({p['x']}, {p['z']}): unknown template {p['v']}")
        up = lift(p["x"], p["z"])
        rise = None
        if t["type"] == "bridge":
            ax = (1.0, 0.0) if p["v"].split(":")[1] == "x" else (0.0, 1.0)
            a = (p["x"] - ax[0] * BRIDGE_HALF, p["z"] - ax[1] * BRIDGE_HALF)
            la, lb = lift(*a), lift(p["x"] + ax[0] * BRIDGE_HALF, p["z"] + ax[1] * BRIDGE_HALF)
            rise = lambda x, z: la + (lb - la) * min(max(((x - a[0]) * ax[0] + (z - a[1]) * ax[1]) / (2 * BRIDGE_HALF), 0.0), 1.0)
            dy = -t["base"]
        elif t["type"] in KEEP_Y:
            dy = up - lift(*t["centre"])
        else:
            dy = ground_y + up + (TRUNK_LIFT if t.get("trunk") else LIFT.get(t["type"], 0.0)) - t["bottom"]
        d = (p["x"] - t["centre"][0], dy, p["z"] - t["centre"][1])
        for part in t["parts"]:
            _copy(parts, models, part, d, into=part.get("into"), rise=rise)
        if "shadow" in t and shadow_y is not None:
            s, at = t["shadow"], t["shadow_at"]
            _copy(parts, models, s["parts"][0], (p["x"] + at[0] - s["centre"][0], shadow_y + up - s["bottom"],
                                                 p["z"] + at[1] - s["centre"][1]), into=SHADOW_PIECE)
    return {k: (bytes(vb), idx) for k, (vb, idx) in parts.items()}

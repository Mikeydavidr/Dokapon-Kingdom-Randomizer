"""Edit the roads drawn on board 0: remove the road of a link, draw a road for a new link, list links that could be added.

What a road is: flat triangles in the road_01 layer of the F00 model files (in board coordinates once their placement matrices
are applied), textured from the road part of the fieldC.tga atlas: a ragged dirt strip about 22 units wide with a white-and-
orange line down the middle, or the line on its own (on sand, swamp, ice and snow; the game draws dirt only between grass).
Every space where roads meet has a junction tile, a square TILE either side of its road centre, and the strips run between
the tile edges (a straight run may also pass several spaces in one strip). The tile kinds: the rounded cap at a dead end, a
straight square, a corner (the strip square folded on its diagonal), the T tile, and for line-only roads lines from the centre.
  cut   the strip between the two tiles is clipped away; both tiles are cleared and drawn again for the roads they keep.
  add   a strip from tile edge to tile edge, following the ground; both tiles are drawn again with the new road.
New links must be axis-aligned and land in free direction slots (see make_board_test.py: a link in the wrong slot crashes the
game's auto-path), must not pass through another space, and must not cross another road; `check_new_link` tests all of that.

    roads = Roads(assets)
    roads.cut(14, 6)
    roads.add(a, b, "dirt")
    roads.save(mod / "Assets")       # writes the changed model files (mesh pieces may grow: igbmodel.rebuild)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel
from boardlib import load_board

FILES = ["A", "M", "N", "Anim1", "Anim2"]
LAYER, ATLAS = "road_01", "fieldC.tga"
TILE = 11.0                # a junction tile reaches TILE from its centre; a strip is 2 * TILE wide
CLEAR = TILE + 0.3         # how far a tile is cleared and drawn again (the game's tile edges wobble by a few tenths)
CENTRE_DX = -1.0           # the road grid sits 1 unit -x of the space positions (tiles span x -12..+10, z -11..+11)
CUT_REACH = 13.0           # how far across the link a cut reaches (the strip plus its ragged edge)
LINE_V, DIRT_V, DIRT_TILE = 0.48, (0.002, 0.29), 49.0     # atlas rows: the line alone; the straight dirt strip and its length
DIRT_STEP = (DIRT_V[1] - DIRT_V[0]) / DIRT_TILE           # atlas v per unit of dirt strip
LINE_ROW = (0.47, 0.54)                                   # atlas v of the line-alone row
CAP_V, CAP_LENGTH = (0.625, 0.748), 12.6                  # the rounded end of a road (no line), as at dead-end space 49
T_U, T_V = (0.752, 0.998), (0.252, 0.498)                 # the T tile: through road along v, its branch towards u 0.752
CORNER_DV = 0.17           # a corner tile: inner corner (0.502, v), the two side corners (0.748, v), far corner (0.748, v + this)
STEPS = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}  # CHAIN slot = direction: 0 +z, 1 +x, 2 -z, 3 -x
DIRECTIONS = {d: s for s, d in STEPS.items()}
NOT_GROUND = {"sea_01", "wave_01", "uzu_01", "sky_01", "smoke_01", "road_shadow", "it_OP"}   # layers that are not terrain
LAND_Y, GRID = 6.0, 20.0   # terrain this high is land (the sea is at 0-4, ground at 4-7, grass above); sampler bucket size


def road_uv(u: float, v: float) -> bool:
    """Whether an atlas coordinate is part of a road: the strip, its cap and the line row; the T tile; the line T, where the
    line turns blue towards water; the blue line. (road_01 pieces also hold bridges, ice patches, pools and flowers.)"""
    return ((0.495 <= u <= 0.755 and -0.005 <= v <= 0.755) or (0.745 <= u <= 1.001 and 0.245 <= v <= 0.635)
            or (0.745 <= u <= 0.785 and 0.745 <= v <= 0.81))


class Vertex:
    """One vertex: position, normal, colour bytes, uv, and the layout's remaining bytes (copied, not interpolated)."""
    __slots__ = ("pos", "nrm", "col", "uv", "rest")

    def __init__(self, pos, nrm, col, uv, rest):
        self.pos, self.nrm, self.col, self.uv, self.rest = pos, nrm, col, uv, rest

    @classmethod
    def read(cls, b: bytes, o: int, stride: int) -> "Vertex":
        f = struct.unpack_from("<6f", b, o)
        return cls(f[:3], f[3:], b[o + 0x18:o + 0x1c], struct.unpack_from("<2f", b, o + 0x1c), b[o + 0x24:o + stride])

    def pack(self) -> bytes:
        return struct.pack("<6f", *self.pos, *self.nrm) + self.col + struct.pack("<2f", *self.uv) + self.rest

    def lerp(self, o: "Vertex", t: float) -> "Vertex":
        mix = lambda a, b: tuple(x + (y - x) * t for x, y in zip(a, b))
        col = bytes(round(x + (y - x) * t) for x, y in zip(self.col, o.col))
        return Vertex(mix(self.pos, o.pos), mix(self.nrm, o.nrm), col, mix(self.uv, o.uv), self.rest)


def split(poly: list[Vertex], axis: int, value: float) -> tuple[list[Vertex], list[Vertex]]:
    """Cut a convex polygon by the plane pos[axis] = value: (the part below, the part above)."""
    below, above = [], []
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        (below if p.pos[axis] < value else above).append(p)
        if (p.pos[axis] < value) != (q.pos[axis] < value):
            x = p.lerp(q, (value - p.pos[axis]) / (q.pos[axis] - p.pos[axis]))
            below.append(x)
            above.append(x)
    return below, above


def area(poly: list[Vertex]) -> float:
    a = 0.0
    for i in range(1, len(poly) - 1):
        (x0, _, z0), (x1, _, z1), (x2, _, z2) = poly[0].pos, poly[i].pos, poly[i + 1].pos
        a += abs((x1 - x0) * (z2 - z0) - (x2 - x0) * (z1 - z0)) / 2
    return a


class Roads:
    def __init__(self, assets: Path, chain: bytes | None = None, models: dict[str, bytes] | None = None):
        """models: model files that already carry other edits (by name, e.g. "A"), to build on instead of the originals."""
        self.assets = assets
        self.spaces, self.links = load_board(assets, 0)
        self.node = {s["id"]: s["pos"] for s in self.spaces}
        self.chain = bytearray(chain if chain is not None else (assets / "CommonData" / "fieldChain" / "CHAIN_000.DAT").read_bytes())
        folder = assets / "CommonData" / "dataField" / "F00"
        self.models = {f: igbmodel.load(folder / f"F00_{f}.model", (models or {}).get(f)) for f in FILES}
        self.meshes: dict[tuple[str, int], dict] = {}           # the road pieces: vertices and triangles, edited in place
        for f, m in self.models.items():
            names = [m.name_at(struct.unpack_from("<I", m.data, m.chunk("TEXT")[0] + 12 * i)[0]) for i in range(len(m.textures))]
            for gi, nd in enumerate(m.mesh_nodes()):
                if nd["name"] != LAYER or nd["texture"] < 0 or names[nd["texture"]] != ATLAS:
                    continue
                g = m.geoms[gi]
                M = m.placement(gi)                        # positions are kept in board coordinates and put back on save
                vb = igbmodel.vertex_bytes(m, gi)
                verts = [Vertex.read(vb, g.stride * i, g.stride) for i in range(g.verts)]
                for v in verts:
                    v.pos = igbmodel.apply(M, v.pos)
                _, tris = igbmodel.mesh(m, g)
                self.meshes[(f, gi)] = {"verts": verts, "tris": [list(t) for t in tris], "stride": g.stride, "changed": False,
                                        "inverse": igbmodel.inverse(M)}

    # ---- geometry helpers ----------------------------------------------------------------------------------------------
    def axis(self, a: int, b: int) -> tuple[int, int]:
        """(along, across) axis indices of an axis-aligned link; raises for a diagonal one."""
        pa, pb = self.node[a], self.node[b]
        dx, dz = pb[0] - pa[0], pb[2] - pa[2]
        if min(abs(dx), abs(dz)) >= 1.5:
            raise ValueError(f"{a}-{b} is not axis-aligned (dx {dx:.0f}, dz {dz:.0f})")
        return (0, 2) if abs(dx) > abs(dz) else (2, 0)

    def rect(self, a: int, b: int, end_gap: float, reach: float):
        k, j = self.axis(a, b)
        (ax, az), (bx, bz) = self.centre(a), self.centre(b)
        pa, pb = (ax, 0, az), (bx, 0, bz)
        return k, j, min(pa[k], pb[k]) + end_gap, max(pa[k], pb[k]) - end_gap, pa[j] - reach, pa[j] + reach

    def road_tris(self):
        """(mesh key, triangle index, [Vertex]) of every road triangle."""
        for key, ms in self.meshes.items():
            for ti, t in enumerate(ms["tris"]):
                vs = [ms["verts"][i] for i in t]
                if all(road_uv(*v.uv) for v in vs):
                    yield key, ti, vs

    # ---- junction tiles ----------------------------------------------------------------------------------------------------
    def centre(self, n: int) -> tuple[float, float]:
        """Where the roads of space n meet, (x, z): the road grid sits CENTRE_DX off the space positions."""
        p = self.node[n]
        return p[0] + CENTRE_DX, p[2]

    def tile_at(self, n: int) -> tuple[tuple[str, int], float]:
        """(road piece, height) of the junction tile at space n, from the road triangles inside its square (or near it)."""
        cx, cz = self.centre(n)
        count, ys = {}, []
        for key, _, vs in self.road_tris():
            if all(abs(v.pos[0] - cx) <= CLEAR + 1 and abs(v.pos[2] - cz) <= CLEAR + 1 for v in vs):
                count[key] = count.get(key, 0) + 1
                ys += [v.pos[1] for v in vs]
        if count:
            return max(count, key=count.get), sorted(ys)[len(ys) // 2]
        return self.target_mesh(n, n), self.road_height(cx, cz) or self.node[n][1] - 1.0

    def arm_style(self, n: int, s: int) -> str | None:
        """How the road leaving space n in direction s is drawn just outside n's tile: 'dirt', 'line', or None (no road strip,
        e.g. a bridge or a water path)."""
        cx, cz = self.centre(n)
        dx, dz = STEPS[s]
        ends = (TILE + 1, TILE + 7)
        if dx:
            x0, x1, z0, z1 = *sorted(cx + dx * e for e in ends), cz - 3, cz + 3
        else:
            x0, x1, z0, z1 = cx - 3, cx + 3, *sorted(cz + dz * e for e in ends)
        dirt = line = 0
        for _, _, vs in self.road_tris():
            if max(v.pos[0] for v in vs) > x0 and min(v.pos[0] for v in vs) < x1 and max(v.pos[2] for v in vs) > z0 and min(v.pos[2] for v in vs) < z1:
                u, v = sum(p.uv[0] for p in vs) / 3, sum(p.uv[1] for p in vs) / 3
                if u <= 0.76 and v < LINE_ROW[0]:
                    dirt += 1
                else:
                    line += 1
        return "dirt" if dirt else "line" if line else None

    def arms(self, n: int) -> dict[int, str]:
        """{direction slot: style} of every road leaving space n (a road with no strip counts as 'line')."""
        return {self.slot(n, x): self.arm_style(n, self.slot(n, x)) or "line" for x in self.links[n]}

    def band(self, c: tuple[float, float], d: tuple[int, int], t0: float, t1: float, y: float, v0: float, v1: float) -> list:
        """A road-wide quad from c + t0*d to c + t1*d, its texture rows v0 to v1 (u runs across the road)."""
        px, pz = d[1], -d[0]
        pts = [((c[0] + d[0] * t + px * side * CLEAR, y, c[1] + d[1] * t + pz * side * CLEAR), (u, v))
               for t, v in ((t0, v0), (t1, v1)) for side, u in ((-1, 0.502), (1, 0.748))]
        return [pts[0], pts[1], pts[3], pts[2]]

    def build_tile(self, n: int, arms: dict[int, str], key: tuple[str, int], y: float) -> None:
        """Draw the junction tile of space n for the roads leaving it (arms: {direction slot: 'dirt' or 'line'}), the way the
        game's tiles are drawn: one dirt road ends in the rounded cap, two in a straight square or a corner (the strip folded on
        its diagonal), three or four in the T tile; a road drawn as the line alone gets the line from the centre to the edge."""
        c = self.centre(n)
        R = CLEAR
        P = lambda a, b: (c[0] + a, y, c[1] + b)
        dirt = sorted(s for s, st in arms.items() if st == "dirt")
        polys = []
        if len(dirt) == 1:
            r = STEPS[dirt[0]]
            polys.append(self.band(c, r, 1.0, R, y, DIRT_V[0], DIRT_V[0] + (R - 1) * DIRT_STEP))
            polys.append(self.band(c, (-r[0], -r[1]), -1.0, CAP_LENGTH - 1.0, y, *CAP_V))
        elif len(dirt) == 2 and dirt[1] - dirt[0] == 2:
            polys.append(self.band(c, STEPS[dirt[0]], -R, R, y, DIRT_V[0], DIRT_V[0] + 2 * R * DIRT_STEP))
        elif len(dirt) == 2:
            (ax, az), (bx, bz) = STEPS[dirt[0]], STEPS[dirt[1]]
            inner, outer = P(R * (ax + bx), R * (az + bz)), P(-R * (ax + bx), -R * (az + bz))
            side_a, side_b = P(R * (ax - bx), R * (az - bz)), P(R * (bx - ax), R * (bz - az))
            v0 = DIRT_V[0]
            polys += [[(inner, (0.502, v0)), (side_a, (0.748, v0)), (outer, (0.748, v0 + CORNER_DV))],
                      [(side_b, (0.748, v0)), (inner, (0.502, v0)), (outer, (0.748, v0 + CORNER_DV))]]
        elif len(dirt) >= 3:
            through = next(s for s in dirt if (s + 2) % 4 in dirt)
            branch = [s for s in dirt if s not in (through, (through + 2) % 4)]
            (tx, tz), (bx, bz) = STEPS[through], STEPS[branch[0]]
            polys.append([(P(R * (sb * bx + st * tx), R * (sb * bz + st * tz)), (T_U[0] if sb > 0 else T_U[1], T_V[0] if st < 0 else T_V[1]))
                          for sb, st in ((1, 1), (1, -1), (-1, -1), (-1, 1))])
            for s in branch[1:]:                       # a fourth road: its strip on to the centre, over the T
                polys.append(self.band(c, STEPS[s], 0.0, R, y + 0.05, DIRT_V[0], DIRT_V[0] + R * DIRT_STEP))
        for s, st in sorted(arms.items()):
            if st != "dirt":
                polys.append(self.band(c, STEPS[s], 0.0, R, y + (0.05 if dirt else 0.0), LINE_V, LINE_V))
        self.emit(key, polys)

    def emit(self, key: tuple[str, int], polys: list[list[tuple]]) -> None:
        """Add convex polygons of (position, uv) points to a road piece, facing the same way as the game's road triangles."""
        ms = self.meshes[key]
        proto = next(ms["verts"][i] for t in ms["tris"] for i in t if road_uv(*ms["verts"][i].uv))
        for poly in polys:
            base = len(ms["verts"])
            ms["verts"] += [Vertex(pos, (0.0, 1.0, 0.0), b"\xff\xff\xff\xff", uv, proto.rest) for pos, uv in poly]
            for i in range(1, len(poly) - 1):
                t = [base, base + i, base + i + 1]
                (ax, _, az), (bx, _, bz), (cx, _, cz) = (ms["verts"][q].pos for q in t)
                if (bx - ax) * (cz - az) - (cx - ax) * (bz - az) > 0:
                    t = [t[0], t[2], t[1]]
                ms["tris"].append(t)
        ms["changed"] = True

    def clear(self, n: int) -> int:
        cx, cz = self.centre(n)
        return self.clip(cx - CLEAR, cx + CLEAR, cz - CLEAR, cz + CLEAR)

    # ---- cut ------------------------------------------------------------------------------------------------------------
    def check_cut(self, a: int, b: int) -> str | None:
        """Why the road of link a-b cannot be removed, or None if it can. Sea routes are water paths and lake crossings have
        bridges, neither of them road strips, so cutting those links would leave them on screen."""
        if b not in self.links.get(a, []):
            return "not a link"
        try:
            self.axis(a, b)
        except ValueError as e:
            return str(e)
        if self.crosses_water(a, b):
            return "crosses water (a water path or a bridge)"
        return None

    def cut(self, a: int, b: int) -> int:
        """Remove the road drawn between spaces a and b; returns how many triangles were clipped.

        The strip between the two junction tiles is clipped away, and each end's tile is cleared and drawn again for the roads
        it still has (a dead end gets the rounded cap, a T that loses its branch becomes straight, and so on).
        """
        k, _ = self.axis(a, b)
        arms = {n: self.arms(n) for n in (a, b)}
        tiles = {n: self.tile_at(n) for n in (a, b)}
        (ax, az), (bx, bz) = self.centre(a), self.centre(b)
        if k == 0:
            clipped = self.clip(min(ax, bx) + CLEAR, max(ax, bx) - CLEAR, az - CUT_REACH, az + CUT_REACH)
        else:
            clipped = self.clip(ax - CUT_REACH, ax + CUT_REACH, min(az, bz) + CLEAR, max(az, bz) - CLEAR)
        for n, other in ((a, b), (b, a)):
            del arms[n][self.slot(n, other)]
            clipped += self.clear(n)
            self.build_tile(n, arms[n], *tiles[n])
        self.links[a] = [x for x in self.links[a] if x != b]
        self.links[b] = [x for x in self.links[b] if x != a]
        return clipped

    def clip(self, x0: float, x1: float, z0: float, z1: float) -> int:
        """Remove the parts of road triangles inside the box x0..x1, z0..z1; returns how many triangles were cut."""
        clipped = 0
        for key, ms in self.meshes.items():
            keep, hit = [], False
            for t in ms["tris"]:
                vs = [ms["verts"][i] for i in t]
                xs, zs = [v.pos[0] for v in vs], [v.pos[2] for v in vs]
                if not all(road_uv(*v.uv) for v in vs) or max(xs) <= x0 or min(xs) >= x1 or max(zs) <= z0 or min(zs) >= z1:
                    keep.append(t)
                    continue
                clipped += 1
                hit = True
                left, rest = split(vs, 0, x0)
                mid, right = split(rest, 0, x1)
                below, mid = split(mid, 2, z0)
                _, above = split(mid, 2, z1)
                for poly in (left, right, below, above):
                    if len(poly) >= 3 and area(poly) > 1e-4:
                        base = len(ms["verts"])
                        ms["verts"] += poly
                        keep += [[base, base + i, base + i + 1] for i in range(1, len(poly) - 1)]
            if hit:
                ms["changed"] = True
                ms["tris"] = keep
        return clipped

    # ---- terrain ----------------------------------------------------------------------------------------------------------
    def surface(self, x: float, z: float) -> tuple[float, tuple[float, float, float], str] | None:
        """(height, texture colour, layer) of the highest terrain showing at (x, z) (transparent texels are looked through),
        None over open sea. Terrain: every piece but the sea, waves, sky, shadows and road strips; of the town_01 layer
        (buildings and the desert floor) only flat, low, sand-coloured triangles."""
        if not hasattr(self, "_grid"):
            self._grid: dict[tuple[int, int], list] = {}
            for f, m in self.models.items():
                vo = m.chunk("VERT")[0]
                textures = {}
                for gi, nd in enumerate(m.mesh_nodes()):
                    if nd["name"] in NOT_GROUND:
                        continue
                    g = m.geoms[gi]
                    M = m.placement(gi)
                    raw = m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts]
                    pos = [igbmodel.apply(M, struct.unpack_from("<3f", raw, g.stride * i)) for i in range(g.verts)]
                    uvs = [struct.unpack_from("<2f", raw, g.stride * i + 0x1c) for i in range(g.verts)]
                    ti = nd["texture"]
                    if ti >= 0 and ti not in textures:
                        textures[ti] = igbmodel.decode_texture(m, m.textures[ti])
                    for t in igbmodel.mesh(m, g)[1]:
                        tri = [pos[i] for i in t]
                        if nd["name"] == LAYER and all(road_uv(*uvs[i]) for i in t):
                            continue                              # a road strip, not the ground under it
                        if nd["name"] == "town_01" and (max(p[1] for p in tri) > 12 or max(p[1] for p in tri) - min(p[1] for p in tri) > 1):
                            continue                              # a building, not the floor
                        xs, zs = [p[0] for p in tri], [p[2] for p in tri]
                        item = (tri, [uvs[i] for i in t], textures.get(ti), nd["name"])
                        for cx in range(int(min(xs) // GRID), int(max(xs) // GRID) + 1):
                            for cz in range(int(min(zs) // GRID), int(max(zs) // GRID) + 1):
                                self._grid.setdefault((cx, cz), []).append(item)
        hits = []
        for (a, b, c), uv, tex, layer in self._grid.get((int(x // GRID), int(z // GRID)), []):
            den = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(den) < 1e-9:
                continue
            l0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / den
            l1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / den
            l2 = 1 - l0 - l1
            if min(l0, l1, l2) >= -1e-6:
                hits.append((l0 * a[1] + l1 * b[1] + l2 * c[1], uv, (l0, l1, l2), tex, layer))
        for y, uv, l, tex, layer in sorted(hits, key=lambda h: -h[0]):
            rgba = (128, 128, 128, 255)
            if tex is not None:
                u, v = sum(l[k] * uv[k][0] for k in range(3)), sum(l[k] * uv[k][1] for k in range(3))
                rgba = tex.getpixel((int(u % 1 * tex.width) % tex.width, int(v % 1 * tex.height) % tex.height))
            r, g, b = (c / 255 for c in rgba[:3])
            if layer == "town_01" and not (r > b + 0.12 and g > b + 0.06):
                continue                                  # the low base of a building, not the desert floor
            if rgba[3] >= 128:
                return y, (r, g, b), layer
        return None

    def layer_at(self, x: float, z: float) -> str:
        """The layer of the terrain showing at (x, z) ('sea' over open sea): green_01 and town_01 are the floor, road_side
        and road_side_sea the drawn edges (grass borders, beaches), jimem_01 bare ground."""
        s = self.surface(x, z)
        return s[2] if s else "sea"

    def ground_y(self, x: float, z: float) -> float | None:
        s = self.surface(x, z)
        return s[0] if s else None

    def ground_kind(self, x: float, z: float) -> str:
        """'grass', 'sand', 'snow', 'water' (also open sea) or 'other', from the colour of the terrain under (x, z)."""
        s = self.surface(x, z)
        if s is None or s[0] < LAND_Y - 2:
            return "water"
        r, g, b = s[1]
        if g > r + 0.06 and g > b + 0.06:
            return "grass"
        if min(r, g, b) > 0.75 and b >= r - 0.02:
            return "snow"
        if b >= 0.55 and b > r + 0.2 and b >= g:           # bright blue: the dark outline of grass edges is bluish too
            return "water"
        if r > b + 0.12 and g > b + 0.06:
            return "sand"
        return "other"

    def kind_at(self, n: int) -> str:
        """The terrain around space n (the most common kind a few units around its road centre)."""
        cx, cz = self.centre(n)
        kinds = [self.ground_kind(cx + dx, cz + dz) for dx, dz in ((0, 0), (7, 7), (-7, 7), (7, -7), (-7, -7))]
        return max(set(kinds), key=kinds.count)

    def style_for(self, a: int, b: int) -> str:
        """How the game would draw a road from a to b: dirt between two grass spaces, otherwise the line alone."""
        return "dirt" if self.kind_at(a) == self.kind_at(b) == "grass" else "line"

    def crosses_water(self, a: int, b: int, samples: int = 12) -> bool:
        """Whether the link a-b runs over water (two samples or more; the game draws those as water paths or bridges)."""
        (ax, az), (bx, bz) = self.centre(a), self.centre(b)
        return sum(self.ground_kind(ax + (bx - ax) * (i + 0.5) / samples, az + (bz - az) * (i + 0.5) / samples) == "water"
                   for i in range(samples)) >= 2

    # ---- add ------------------------------------------------------------------------------------------------------------
    def road_height(self, x: float, z: float, radius: float = 12.0) -> float | None:
        """Height of the existing road around (x, z): the median of road vertices within radius, None if there are none."""
        ys = sorted(v.pos[1] for _, _, vs in self.road_tris() for v in vs
                    if (v.pos[0] - x) ** 2 + (v.pos[2] - z) ** 2 <= radius * radius)
        return ys[len(ys) // 2] if ys else None

    def target_mesh(self, a: int, b: int) -> tuple[str, int]:
        """The road piece to draw a new road into: the one with most road vertices near the link."""
        mid = [(self.node[a][i] + self.node[b][i]) / 2 for i in range(3)]
        best, score = None, -1
        for key, ms in self.meshes.items():
            near = sum(1 for v in ms["verts"] if road_uv(*v.uv) and abs(v.pos[0] - mid[0]) < 120 and abs(v.pos[2] - mid[2]) < 120)
            if near > score:
                best, score = key, near
        return best

    def add(self, a: int, b: int, style: str = "auto", step: float = 10.0) -> tuple[str, int]:
        """Draw a road from space a to space b and redraw the junction tiles at both ends with it; returns the piece it went into.

        style: 'dirt', 'line', or 'auto' (style_for). The strip runs from tile edge to tile edge at the heights of the two tiles,
        never dipping below the terrain it crosses.
        """
        if style == "auto":
            style = self.style_for(a, b)
        arms = {n: self.arms(n) for n in (a, b)}
        tiles = {n: self.tile_at(n) for n in (a, b)}
        (key, ya), (_, yb) = tiles[a], tiles[b]
        ca, cb = self.centre(a), self.centre(b)
        d = STEPS[self.slot(a, b)]
        length = abs(cb[0] - ca[0]) if d[0] else abs(cb[1] - ca[1])
        span = length - 2 * CLEAR
        n = max(1, round(span / step))
        rows = []
        for s in range(n + 1):
            t = CLEAR + span * s / n
            x, z = ca[0] + (cb[0] - ca[0]) * t / length, ca[1] + (cb[1] - ca[1]) * t / length   # the ends may sit a unit apart across
            ground = max((self.ground_y(x + d[1] * e, z - d[0] * e) or -99) for e in (0, -CLEAR, CLEAR))
            y = max(ya + (yb - ya) * t / length, ground + 0.3)
            if style == "line":
                v = LINE_V
            else:                                          # the dirt strip, mirrored every repeat so the seams match
                ph = (span * s / n / DIRT_TILE) % 2
                v = DIRT_V[0] + (DIRT_V[1] - DIRT_V[0]) * (ph if ph <= 1 else 2 - ph)
            rows.append(self.band((x, z), d, 0.0, 0.0, y, v, v)[:2])
        self.emit(key, [[*rows[s], *rows[s + 1][::-1]] for s in range(n)])
        for n_, other in ((a, b), (b, a)):
            arms[n_][self.slot(n_, other)] = style
            self.clear(n_)
            self.build_tile(n_, arms[n_], *tiles[n_])
        self.links[a] = self.links[a] + [b]
        self.links[b] = self.links[b] + [a]
        return key

    # ---- new links --------------------------------------------------------------------------------------------------------
    def slot(self, a: int, b: int) -> int:
        pa, pb = self.node[a], self.node[b]
        dx, dz = pb[0] - pa[0], pb[2] - pa[2]
        return DIRECTIONS[(0, 1 if dz > 0 else -1)] if abs(dz) > abs(dx) else DIRECTIONS[(1 if dx > 0 else -1, 0)]

    def slots(self, a: int) -> list[int]:
        o = 2 + 10 * a
        assert struct.unpack_from("<H", self.chain, o)[0] == a
        return list(struct.unpack_from("<4H", self.chain, o + 2))

    def check_new_link(self, a: int, b: int, max_length: float = 130.0) -> str | None:
        """Why a-b cannot be a new link, or None if it can."""
        if b in self.links.get(a, []):
            return "already linked"
        try:
            k, j = self.axis(a, b)
        except ValueError as e:
            return str(e)
        pa, pb = self.node[a], self.node[b]
        if abs(pb[k] - pa[k]) > max_length:
            return f"too long ({abs(pb[k] - pa[k]):.0f})"
        if self.slots(a)[self.slot(a, b)] != 0xFFFF or self.slots(b)[self.slot(b, a)] != 0xFFFF:
            return "direction slot taken"
        lo, hi = sorted((pa[k], pb[k]))
        for s in self.spaces:
            p = s["pos"]
            if s["id"] not in (a, b) and lo - 1 < p[k] < hi + 1 and abs(p[j] - pa[j]) < 2 * TILE:
                return f"passes space {s['id']}"
        k, j, lo, hi, jlo, jhi = self.rect(a, b, TILE + 2, TILE)
        for key, _, vs in self.road_tris():
            ks, js = [v.pos[k] for v in vs], [v.pos[j] for v in vs]
            if max(ks) > lo and min(ks) < hi and max(js) > jlo and min(js) < jhi:
                return f"crosses a road ({key[0]} piece {key[1]})"
        if self.crosses_water(a, b):
            return "crosses water"
        return None

    def link(self, a: int, b: int) -> None:
        """Add a-b to CHAIN in the slot of its direction at both ends (check_new_link first)."""
        for x, y in ((a, b), (b, a)):
            o = 2 + 10 * x + 2 + 2 * self.slot(x, y)
            assert struct.unpack_from("<H", self.chain, o)[0] == 0xFFFF, f"space {x}: slot {self.slot(x, y)} is taken"
            struct.pack_into("<H", self.chain, o, y)

    def unlink(self, a: int, b: int) -> None:
        for x, y in ((a, b), (b, a)):
            vals = self.slots(x)
            vals[vals.index(y)] = 0xFFFF
            struct.pack_into("<4H", self.chain, 2 + 10 * x + 2, *vals)

    def reachable(self, start: int = 0) -> int:
        seen, todo = set(), [start]
        while todo:
            x = todo.pop()
            if x not in seen:
                seen.add(x)
                todo += [v for v in self.slots(x) if v != 0xFFFF]
        return len(seen)

    def components(self) -> list[frozenset[int]]:
        """The groups of spaces connected by links (the board is several groups: continents joined some other way)."""
        out, done = [], set()
        for s in sorted(self.node):
            if s in done:
                continue
            seen, todo = set(), [s]
            while todo:
                x = todo.pop()
                if x not in seen:
                    seen.add(x)
                    todo += [v for v in self.slots(x) if v != 0xFFFF]
            out.append(frozenset(seen))
            done |= seen
        return sorted(out, key=min)

    def candidates(self, max_length: float = 130.0) -> list[tuple[int, int]]:
        out = []
        ids = sorted(self.node)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if self.check_new_link(a, b, max_length) is None:
                    out.append((a, b))
        return out

    def road_mask(self, dirt: float = 6.0, line: float = 4.0, disc: float = 8.0):
        """A test blocked(x, z): whether a point is on a drawn road (within `dirt` or `line` of a link's centre line, by the
        way its strip is drawn) or on a space's disc (within `disc` of its centre)."""
        rects = []
        for a in self.links:
            for b in self.links[a]:
                if a < b:
                    w = dirt if self.arm_style(a, self.slot(a, b)) == "dirt" else line
                    (ax, az), (bx, bz) = self.centre(a), self.centre(b)
                    rects.append((min(ax, bx) - w, max(ax, bx) + w, min(az, bz) - w, max(az, bz) + w))
        discs = [p for p in self.node.values()]
        return lambda x, z: (any(x0 <= x <= x1 and z0 <= z <= z1 for x0, x1, z0, z1 in rects)
                             or any((x - p[0]) ** 2 + (z - p[2]) ** 2 <= disc * disc for p in discs))

    # ---- output ---------------------------------------------------------------------------------------------------------
    def save(self, out: Path, base: dict[str, bytes] | None = None) -> list[Path]:
        """Write every model file with changed road pieces. base: newer copies of the files with other in-place edits (moved
        shadows, made after this Roads was loaded) to build on."""
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for f, m in self.models.items():
            replace = {}
            for (ff, gi), ms in self.meshes.items():
                if ff == f and ms["changed"]:
                    used = sorted({i for t in ms["tris"] for i in t})
                    remap = {old: new for new, old in enumerate(used)}
                    local = [Vertex(igbmodel.apply(ms["inverse"], v.pos), v.nrm, v.col, v.uv, v.rest) for v in (ms["verts"][i] for i in used)]
                    vb = b"".join(v.pack() for v in local)
                    replace[gi] = (vb, [remap[i] for t in ms["tris"] for i in t])
            if replace:
                path = out / f"F00_{f}.model"
                path.write_bytes(igbmodel.rebuild(m, replace, (base or {}).get(f)))
                written.append(path)
        return written

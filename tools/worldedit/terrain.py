"""Board terrain as a painted grid of ground types, and the meshes that draw it with the game's own textures.

How board 0 draws its ground (found from the F00 model files; see README.md in this folder):
  sea      one big plane of water_test.tga (sea_01 in F00_Anim1) at y 3.8 under everything, with a hole at Dokapon
           Castle, whose moat is a piece of its own
  moat     Dokapon Castle's: water at y -2.5 (sea_01 in F00_N) between leaning walls of the objes rock-strata tile (town_01),
           the grass's ragged edge (road_side) hanging over the rims
  grass    green_01 pieces, test.tga tiled; forest is the same grass darkened by vertex colour (5b7fae)
  dirt     jimem_01 pieces, jimem.tga tiled
  sand, poison, swamp water   flat town_01 triangles textured from tiles of the objes.tga building atlas
  snow     flat road_01 triangles textured from the snow tile of the fieldC.tga atlas
  coast    road_side_sea ribbons: the fieldC strip that runs grass -> sand -> surf, laid along every shore; along narrow
           water (rivers) the sand and surf are squeezed so that water shows between the strips of the two banks; the
           narrowest water (the ends of creeks) has only the surf part at water level, under a grass edge
  edges    road_side ribbons: the fieldC strip of grass ending in a ragged edge, laid along grass that meets other ground
The grid holds one ground code per square cell; meshes() turns it into the fills and ribbons above. Fill borders follow
the 0.5 contour of each ground's (smoothed) cell field, so they are curves, not cell steps; the ribbons are laid along the
same contours and cover the seams, as the game's own ribbons do.
"""
import json
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel


@dataclass(frozen=True)
class Ground:
    code: str
    name: str
    colour: str                # how the editor paints it
    fill: str | None           # 'base' (the grass floor), 'overlay' (drawn over the grass floor) or None (sea)
    texture: str | None = None # where an overlay's texture comes from: 'objes', 'fieldC' (atlas tiles) or 'jimem' (own texture)
    uv: tuple = ()             # atlas tile (u0, v0, u1, v1), or (scale,) for a texture of its own


GROUNDS = {g.code: g for g in [
    Ground(".", "sea", "#2a6fc9", None),
    Ground("g", "grass", "#7bd334", "base"),
    Ground("f", "forest", "#2f7a3a", "base"),
    Ground("s", "sand", "#f2d48a", "overlay", "objes", (0.002, 0.502, 0.248, 0.748)),
    Ground("w", "snow", "#e6f4ff", "overlay", "fieldC", (0.752, 0.002, 0.998, 0.248)),
    Ground("d", "dirt", "#b5703a", "overlay", "jimem", (1 / 24,)),
    Ground("p", "poison", "#8a3fd1", "overlay", "objes", (0.004, 0.254, 0.123, 0.373)),
    Ground("m", "swamp", "#3f8f9a", "overlay", "objes", (0.127, 0.254, 0.246, 0.373)),
    Ground("o", "moat", "#173f86", None),
]}
WATER = ".o"                            # the codes with no ground fill
OVERLAYS = [c for c, g in GROUNDS.items() if g.fill == "overlay"]

# heights, as on the game's board: sea plane 3.8, grass 7.0, beach strips 7.5, grass edges 8.6, roads 9.4, spaces 10
BASE_Y, BEACH_Y, OVERLAY_Y, EDGE_Y = 7.0, 7.5, 7.8, 8.6
GRASS_UV = 1 / 60                       # test.tga repeats every 60 units
WHITE, FOREST = b"\xff\xff\xff\xff", bytes.fromhex("5b7faeff")
BLOCK = 12                              # fills are cut into blocks of BLOCK cells; an atlas tile is mirrored once per block
# ribbons: the atlas strip across (u at the inner and outer side), its rows along (v0, v1) and how long one repeat is
BEACH = {"u": (0.254, 0.604), "v": (0.752, 0.998), "inner": 14.5, "outer": 14.5, "repeat": 35.0}   # grass | sand | surf
EDGE = {"u": (0.002, 0.248), "v": (0.752, 0.998), "inner": 8.0, "outer": 10.0, "repeat": 34.0}     # grass | ragged edge
# the narrowest water (the ends of creeks, under CREEK across) has no beach: the surf line alone at water level, under a
# grass edge; wider rivers have beaches whose sand and surf are squeezed into SQUEEZE of the water's width
BANK = {"u": (0.561, 0.623), "v": (0.752, 0.998), "inner": 1.0, "outer": 6.0, "repeat": 50.0}
SHORE = {**EDGE, "inner": 10.0, "outer": 6.0}
BANK_Y, CREEK, SQUEEZE = 3.85, 18.0, 0.33
# snow meets the sea in an ice cliff, topped by a wavy snow lip (both run along u in the fieldC ice tile, across v)
ICE_WALL = {"u": (0.502, 0.62), "v": (0.252, 0.498), "inner": 0.0, "outer": 1.5, "repeat": 30.0, "transposed": True}
ICE_RIM = {"u": (0.627, 0.748), "v": (0.252, 0.498), "inner": 6.0, "outer": 1.0, "repeat": 30.0, "transposed": True}
# (the game's animated wave_01 strips, see_st.tga, are no surf: they are the light lanes along the sea routes between
# Ocean spaces, kept by build_world.py; a shore's foam is the outer end of its beach strip)
OPEN = (0.45, 0.8)                       # openness (meshes()): from closed-in water to the open sea, for the shore kinds
# where the grass of the game's strips stops (fieldC, measured): the beach strip is grass up to u 0.43, then sand, foam at
# 0.57 and water; the edge strip is grass up to its ragged end at u 0.17. BEACH is laid with u 0.43 on the shore line.
STRIP_GRASS = {"road_side_sea": 0.43, "road_side": 0.17}
# water with land within NARROW units across it is narrow (a river: roads cross it on bridges); FAR: as good
# as open sea
NARROW, FAR = 40.0, 90.0
# heights: a plateau (level '1') is PLATEAU above the ground, a slope ('/') eases between them. Its edges are leaning
# cliffs of the objes rock-strata tile (v from its top row to its foot, u along, one repeat every 24 units), or of the
# fieldC ice tile on snow, leaning out LEAN units per unit they drop, shaded bluish at the foot
PLATEAU, RAMP, LEAN = 7.0, "/", 0.8
HILL_Y = 18.0                            # fills higher than this are hill tops (props), not plateaus
LEVELS = {"0": "ground", "1": "plateau", RAMP: "slope"}
STRATA = {"u": (0.377, 0.473), "v": (0.002, 0.248), "inner": 0.0, "outer": LEAN * PLATEAU, "repeat": 24.0,
          "transposed": True}
ICE_LEAN = 0.35                          # ice cliffs stand steeper than rock
ICE_CLIFF = {**ICE_WALL, "outer": ICE_LEAN * PLATEAU}
CLIFF_FOOT = bytes.fromhex("c2cdffff")
SEA_Y, SEA_UV = 3.8, (-0.015058, 7.23, -39.838)   # the game's sea plane: u = a*x + b, v = a*z + c
# a moat ('o', Dokapon Castle's): water sunk to MOAT_Y in a cut through the ground, its sides walls of the rock-strata tile
# leaning in MOAT_LEAN units per unit they drop (about 10 units across at the top, 5 at the water), with the grass's ragged
# edge hanging over the rim; the sea plane has a hole over it. Its water is water_test.tga, repeating every 1/MOAT_UV units.
MOAT_Y, MOAT_LEAN, MOAT_UV = -2.5, 0.29, 0.0385
MOAT_WALL = {**STRATA, "u": (0.377, 0.496), "outer": MOAT_LEAN * (BASE_Y - MOAT_Y)}
# the rim: the edge strip's grass lying flat a little out over the wall's top (MOAT_RIM), then its ragged end (short of
# its tips: to u 0.225, as the game's) hanging HANG_DROP down over the water (MOAT_HANG), shaded darker (RIM_SHADE)
MOAT_RIM = {**EDGE, "u": (0.002, 0.17), "inner": 6.0, "outer": 1.4}
MOAT_HANG = {**EDGE, "u": (0.17, 0.225), "inner": 0.0, "outer": 3.5}
HANG_DROP, RIM_SHADE = 6.0, bytes.fromhex("788da1ff")
MOAT_FOOT = bytes.fromhex("cec3ffff")


class Grid:
    """cells[j, i]: the ground code of the square [x0 + i*cell, x0 + (i+1)*cell) x [z0 + j*cell, z0 + (j+1)*cell).
    levels[j, i]: its height code (LEVELS: '0' the ground, '1' a plateau PLATEAU units higher, '/' a slope between them)."""

    def __init__(self, x0: float, z0: float, cell: float, cells: np.ndarray, levels: np.ndarray | None = None):
        self.x0, self.z0, self.cell, self.cells = x0, z0, cell, cells
        self.levels = levels if levels is not None else np.full(cells.shape, ord("0"), np.uint8)
        self._lift = self._corners = None

    @property
    def w(self) -> int:
        return self.cells.shape[1]

    @property
    def h(self) -> int:
        return self.cells.shape[0]

    @classmethod
    def empty(cls, box=(-760.0, -860.0, 680.0, 440.0), cell: float = 5.0, code: str = ".") -> "Grid":
        x0, z0, x1, z1 = box
        w, h = math.ceil((x1 - x0) / cell), math.ceil((z1 - z0) / cell)
        return cls(x0, z0, cell, np.full((h, w), ord(code), np.uint8))

    def to_json(self) -> dict:
        out = {"x0": self.x0, "z0": self.z0, "cell": self.cell, "w": self.w, "h": self.h,
               "rows": [bytes(r).decode("ascii") for r in self.cells]}
        if (self.levels != ord("0")).any():
            out["levels"] = [bytes(r).decode("ascii") for r in self.levels]
        return out

    @classmethod
    def from_json(cls, d: dict) -> "Grid":
        cells = np.array([list(r.encode("ascii")) for r in d["rows"]], np.uint8)
        assert cells.shape == (d["h"], d["w"]), "grid rows do not match w and h"
        levels = None
        if d.get("levels"):
            levels = np.array([list(r.encode("ascii")) for r in d["levels"]], np.uint8)
            assert levels.shape == cells.shape, "grid levels do not match its rows"
        return cls(d["x0"], d["z0"], d["cell"], cells, levels)

    def lifts(self) -> np.ndarray:
        """Per cell, how far its ground is above BASE_Y: 0 or PLATEAU by its level; on a slope eased between the nearest
        ground and the nearest plateau cell; in water, that of the nearest land."""
        if self._lift is None:
            lv = self.levels
            out = np.where(lv == ord("1"), PLATEAU, 0.0)
            slope = lv == ord(RAMP)
            if slope.any():
                d0 = ndimage.distance_transform_edt(lv != ord("0"))
                d1 = ndimage.distance_transform_edt(lv != ord("1"))
                out = np.where(slope, PLATEAU * d0 / np.maximum(d0 + d1, 1e-6), out)
            water = np.isin(self.cells, np.frombuffer(WATER.encode("ascii"), np.uint8))
            if water.any() and not water.all():
                idx = ndimage.distance_transform_edt(water, return_distances=False, return_indices=True)
                out = out[idx[0], idx[1]]
            self._lift = out.astype(np.float32)
        return self._lift

    def corner_lifts(self) -> np.ndarray:
        """The lift at every cell corner (h+1, w+1) for slopes: a plateau's where a plateau cell touches the corner, the
        ground's where a ground cell does, else the slope cells' average; so a slope meets both levels without a step."""
        if self._corners is None:
            pad = lambda a, v: np.pad(a, 1, mode="constant", constant_values=v)
            lifts, lv = pad(self.lifts(), 0.0), pad(self.levels, ord("0"))
            land = pad(~np.isin(self.cells, np.frombuffer(WATER.encode("ascii"), np.uint8)), False)
            quad = lambda a: [a[:-1, :-1], a[1:, :-1], a[:-1, 1:], a[1:, 1:]]
            avg = sum(quad(lifts)) / 4
            high = np.logical_or.reduce([q == ord("1") for q in quad(lv)])
            low = np.logical_or.reduce([(q == ord("0")) & l for q, l in zip(quad(lv), quad(land))])
            self._corners = np.where(high, PLATEAU, np.where(low, 0.0, avg)).astype(np.float32)
        return self._corners

    def lift(self, x: float, z: float) -> float:
        """How far the ground at (x, z) is above BASE_Y: the cell's own lift on a level; on and next to a slope, eased
        between its corners (so the slope's ground, roads and spaces climb it smoothly); sharp at a cliff."""
        fi, fj = (x - self.x0) / self.cell, (z - self.z0) / self.cell
        i, j = min(max(int(math.floor(fi)), 0), self.w - 1), min(max(int(math.floor(fj)), 0), self.h - 1)
        if self.levels[j, i] != ord(RAMP):
            return float(self.lifts()[j, i])
        return _bilinear(self.corner_lifts(), min(max(fi, 0.0), self.w), min(max(fj, 0.0), self.h))

    def code_at(self, x: float, z: float) -> str:
        i, j = int((x - self.x0) // self.cell), int((z - self.z0) // self.cell)
        if 0 <= i < self.w and 0 <= j < self.h:
            return chr(self.cells[j, i])
        return "."

    def field(self, codes: str, where: np.ndarray | None = None) -> np.ndarray:
        """At every cell corner, (h+1, w+1): how much of the ground around it is one of `codes` (and in `where`, a mask of
        cells), smoothed so that the 0.5 contour runs as a curve between the cells."""
        m = np.isin(self.cells, np.frombuffer(codes.encode("ascii"), np.uint8))
        if where is not None:
            m &= where
        p = np.pad(m.astype(np.float32), 1, mode="edge")
        f = (p[:-1, :-1] + p[1:, :-1] + p[:-1, 1:] + p[1:, 1:]) / 4          # the four cells around each corner
        q = np.pad(f, 1, mode="edge")
        return (q[:-2, 1:-1] + q[2:, 1:-1] + q[1:-1, :-2] + q[1:-1, 2:] + 4 * q[1:-1, 1:-1]) / 8


# ---- contours -------------------------------------------------------------------------------------------------------------
def _cell_polygon(f: np.ndarray, i: int, j: int, t: float = 0.5):
    """Marching squares for cell (i, j): the inside polygon (corner or edge points, counter-clockwise in x/z) and the contour
    segments, each from the point where the walk leaves the inside to where it comes back in (inside on the left).
    Points are (gi, gj) in corner units; edge points also carry a key shared with the neighbouring cell."""
    corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
    vals = [f[cj, ci] for ci, cj in corners]
    edge_keys = [("h", i, j), ("v", i + 1, j), ("h", i, j + 1), ("v", i, j)]
    poly, crossings = [], []
    for k in range(4):
        a, b = vals[k], vals[(k + 1) % 4]
        if a >= t:
            poly.append((corners[k], None))
        if (a >= t) != (b >= t):
            s = (t - a) / (b - a)
            (ai, aj), (bi, bj) = corners[k], corners[(k + 1) % 4]
            pt = (ai + (bi - ai) * s, aj + (bj - aj) * s)
            poly.append((pt, edge_keys[k]))
            crossings.append((len(poly) - 1, a >= t))           # a >= t: the walk leaves the inside here
    segs = []
    n = len(poly)
    for idx, leaving in crossings:
        if leaving:                                             # the next crossing along the polygon is where it comes back
            back = (idx + 1) % n
            segs.append((poly[idx], poly[back]))
    return [p for p, _ in poly], segs


def contours(f: np.ndarray, t: float = 0.5) -> list[tuple[list[tuple[float, float]], bool]]:
    """The 0.5 contour lines of a corner field as (points in corner units, closed), inside on the left."""
    h, w = f.shape[0] - 1, f.shape[1] - 1
    inside = f >= t
    mixed = ~(inside[:-1, :-1] == inside[1:, :-1]) | ~(inside[:-1, :-1] == inside[:-1, 1:]) | ~(inside[:-1, :-1] == inside[1:, 1:])
    nxt, pts, starts = {}, {}, {}
    for j, i in zip(*np.nonzero(mixed)):
        for (pa, ka), (pb, kb) in _cell_polygon(f, i, j, t)[1]:
            nxt[ka] = kb
            pts[ka], pts[kb] = pa, pb
            starts[kb] = ka
    out, used = [], set()
    open_starts = [k for k in nxt if k not in starts]            # lines that run off the grid start at its edge
    for k0 in open_starts + list(nxt):
        if k0 in used:
            continue
        line, k, closed = [], k0, False
        while k is not None and k not in used:
            used.add(k)
            line.append(pts[k])
            k = nxt.get(k)
        if k == k0:
            closed = True
        elif k is not None:
            line.append(pts[k])
        if len(line) >= 2:
            out.append((line, closed))
    return out


def chaikin(pts: list, closed: bool, rounds: int = 2) -> list:
    for _ in range(rounds):
        if len(pts) < 3:
            return pts
        src = pts + [pts[0]] if closed else pts
        new = [] if closed else [pts[0]]
        for a, b in zip(src, src[1:]):
            new += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        if not closed:
            new.append(pts[-1])
        pts = new
    return pts


def mirror(x: float, period: float) -> float:
    """0..1..0 over two periods: atlas tiles are repeated mirrored so that every seam matches."""
    ph = (x / period) % 2
    return ph if ph <= 1 else 2 - ph


# ---- meshes ---------------------------------------------------------------------------------------------------------------
class Mesh:
    """Triangles in board coordinates: per vertex position, colour bytes and uv."""

    def __init__(self):
        self.pos, self.col, self.uv, self.tris = [], [], [], []

    def add(self, poly: list, facing_down: bool = True) -> None:
        """A convex polygon of (position, colour, uv), fanned into triangles that all face the same way as the game's
        terrain triangles (negative x/z winding)."""
        base = len(self.pos)
        for p, c, uv in poly:
            self.pos.append(p)
            self.col.append(c)
            self.uv.append(uv)
        for k in range(1, len(poly) - 1):
            t = [base, base + k, base + k + 1]
            (ax, _, az), (bx, _, bz), (cx, _, cz) = (self.pos[q] for q in t)
            cross = (bx - ax) * (cz - az) - (cx - ax) * (bz - az)
            if abs(cross) < 1e-9:
                continue
            if (cross > 0) == facing_down:
                t = [t[0], t[2], t[1]]
            self.tris.append(t)

    def extend(self, other: "Mesh") -> None:
        base = len(self.pos)
        self.pos += other.pos
        self.col += other.col
        self.uv += other.uv
        self.tris += [[base + i for i in t] for t in other.tris]

    def __len__(self) -> int:
        return len(self.pos)


def _uv_for(ground: Ground, x: float, z: float, bx: float, bz: float, period: float) -> tuple[float, float]:
    if ground.fill == "base":
        return x * GRASS_UV, z * GRASS_UV
    if len(ground.uv) == 1:
        return x * ground.uv[0], z * ground.uv[0]
    u0, v0, u1, v1 = ground.uv
    # mirrored once per block: inside a block the texture runs one way, so it is linear between the block's vertices
    tu, tv = (x - bx) / period, (z - bz) / period
    return u0 + (u1 - u0) * tu, v0 + (v1 - v0) * tv


def fill(grid: Grid, codes: str, ground: Ground, y: float, colour=None, shade: bytes = FOREST, where=None,
         lift=None) -> Mesh:
    """The area where the field of `codes` is 0.5 or more, as triangles: whole cells are merged into rectangles inside each
    block, cells on the border are cut along the contour. colour: a corner field to blend the vertex colour from white to
    `shade` by (grass to forest on the base fill). where: only these cells (a mask); lift(x, z): added to y at every
    vertex (a slope: its cells are not merged)."""
    f = grid.field(codes, where)
    inside = f >= 0.5
    full = inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]
    none = ~(inside[:-1, :-1] | inside[1:, :-1] | inside[:-1, 1:] | inside[1:, 1:])
    c, x0, z0 = grid.cell, grid.x0, grid.z0
    period = BLOCK * c
    mesh = Mesh()

    def vert(gi: float, gj: float, bi: int, bj: int):
        x, z = x0 + gi * c, z0 + gj * c
        bx, bz = x0 + bi * c, z0 + bj * c
        u, v = _uv_for(ground, x, z, bx, bz, period)
        if len(ground.uv) == 4:                                  # mirror every other block so the seams match
            u0, v0, u1, v1 = ground.uv
            if (bi // BLOCK) % 2:
                u = u0 + u1 - u
            if (bj // BLOCK) % 2:
                v = v0 + v1 - v
        col = WHITE
        if colour is not None:
            a = _bilinear(colour, gi, gj)
            col = bytes(round(w + (k - w) * a) for w, k in zip(WHITE, shade))
        return (x, y + (lift(x, z) if lift else 0.0), z), col, (u, v)

    tint = np.zeros(full.shape, np.int32)                       # whole cells merge only with cells of the same tint
    whole = full if lift is None else np.zeros(full.shape, bool)
    if colour is not None:
        q = np.round(colour * 8).astype(np.int32)
        tint = q[:-1, :-1]
        whole = whole & (tint == q[1:, :-1]) & (tint == q[:-1, 1:]) & (tint == q[1:, 1:])
    for bj in range(0, grid.h, BLOCK):
        for bi in range(0, grid.w, BLOCK):
            bj1, bi1 = min(bj + BLOCK, grid.h), min(bi + BLOCK, grid.w)
            open_runs = {}                                       # (start, end, tint) -> first row
            for j in range(bj, bj1):
                runs, i = [], bi
                while i < bi1:
                    if whole[j, i]:
                        s = i
                        while i < bi1 and whole[j, i] and tint[j, i] == tint[j, s]:
                            i += 1
                        runs.append((s, i, tint[j, s]))
                    else:
                        i += 1
                grown = {r: open_runs.pop(r, j) for r in runs}   # the same run as the row before: one taller rectangle
                for (s, e, _), j0 in open_runs.items():
                    _rect(mesh, vert, s, e, j0, j, bi, bj)
                open_runs = grown
            for (s, e, _), j0 in open_runs.items():
                _rect(mesh, vert, s, e, j0, bj1, bi, bj)
            for j in range(bj, bj1):
                for i in range(bi, bi1):
                    if whole[j, i] or none[j, i]:
                        continue
                    poly, _ = _cell_polygon(f, i, j)
                    if len(poly) >= 3:
                        mesh.add([vert(gi, gj, bi, bj) for gi, gj in poly])
    return mesh


def _rect(mesh: Mesh, vert, s: int, e: int, j0: int, j1: int, bi: int, bj: int) -> None:
    mesh.add([vert(s, j0, bi, bj), vert(e, j0, bi, bj), vert(e, j1, bi, bj), vert(s, j1, bi, bj)])


def _bilinear(f: np.ndarray, gi: float, gj: float) -> float:
    i0, j0 = min(int(gi), f.shape[1] - 2), min(int(gj), f.shape[0] - 2)
    a, b = gi - i0, gj - j0
    return float((f[j0, i0] * (1 - a) + f[j0, i0 + 1] * a) * (1 - b) + (f[j0 + 1, i0] * (1 - a) + f[j0 + 1, i0 + 1] * a) * b)


def resample(pts: list, closed: bool, step: float = 3.0) -> list:
    """The line with its points evenly spaced, about `step` apart (a closed line is returned without repeating its start)."""
    src = pts + [pts[0]] if closed else pts
    total = sum(math.dist(a, b) for a, b in zip(src, src[1:]))
    n = max(3 if closed else 2, round(total / step) + (0 if closed else 1))
    out, k, acc = [], 0, 0.0
    seg = math.dist(src[0], src[1]) if len(src) > 1 else 0.0
    for i in range(n):
        target = total * i / (n if closed else max(n - 1, 1))
        while k < len(src) - 2 and acc + seg < target:
            acc += seg
            k += 1
            seg = math.dist(src[k], src[k + 1])
        t = 0.0 if seg < 1e-9 else min(max((target - acc) / seg, 0.0), 1.0)
        a, b = src[k], src[k + 1]
        out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def normals(pts: list, closed: bool, smooth: int = 3) -> list:
    """Outward normal (right of the direction of travel) at every point, averaged over `smooth` points either side so that
    strips laid along tight bends do not fold over."""
    n = len(pts)
    raw = []
    for k in range(n):
        a = pts[(k - 1) % n] if closed or k > 0 else pts[0]
        b = pts[(k + 1) % n] if closed or k < n - 1 else pts[-1]
        dx, dz = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dz) or 1.0
        raw.append((dz / d, -dx / d))
    out = []
    for k in range(n):
        idx = [(k + o) % n for o in range(-smooth, smooth + 1)] if closed else range(max(0, k - smooth), min(n, k + smooth + 1))
        sx, sz = sum(raw[i][0] for i in idx), sum(raw[i][1] for i in idx)
        d = math.hypot(sx, sz) or 1.0
        out.append((sx / d, sz / d))
    return out


def settle(mask: list, closed: bool, shortest: int = 8) -> list:
    """A per-point choice with its short runs (fewer than `shortest` points) given to their neighbours, so a strip does not
    flick between two styles along a shore."""
    n = len(mask)
    if n == 0 or all(mask) or not any(mask):
        return list(mask)
    m = list(mask)
    for _ in range(3):
        runs, k = [], 0
        while k < n:
            e = k
            while e < n and m[e] == m[k]:
                e += 1
            runs.append([k, e])
            k = e
        if closed and len(runs) > 1 and m[0] == m[-1]:      # a run across the start of a closed line is one run
            runs[0][0] = runs[-1][0] - n
            runs.pop()
        changed = False
        for s, e in runs:
            if e - s < shortest and len(runs) > 1:
                for i in range(s, e):
                    m[i % n] = not m[i % n]
                changed = True
        if not changed:
            break
    return m


def taper(mask: list, closed: bool, ramp: int = 6) -> list:
    """Per point, a width share for a strip drawn where mask is set: 1 in the middle of each run, falling to a tenth over
    `ramp` points towards the run's ends (where another strip takes over), so the strips do not stop in a hard edge. Points
    off the runs get 0: the last stretch of a run ends on one."""
    n = len(mask)
    out = [1.0 if m else 0.0 for m in mask]
    unset = lambda i: (closed or 0 <= i < n) and not mask[i % n]       # the open ends of a line are not run ends
    for k in range(n):
        if mask[k]:
            d = next((d for d in range(ramp) if unset(k - d - 1) or unset(k + d + 1)), ramp)
            out[k] = 0.1 + 0.9 * d / ramp
    return out


def fit(pts: list, closed: bool, nrm: list, scale: list, inner: float, outer: float, mask=None, reach=None,
        rounds: int = 16, ramp: int = 6) -> tuple[list, list]:
    """Per point, how much of a strip's inner and outer width to lay (shares of `inner` and `outer` units, on top of
    scale) so that neither side runs backwards around a tight bend: where a side would move less than a quarter as far as
    the line itself, both its ends are pulled in, then the pull is eased out over `ramp` points either side. (Pulling in
    only ever helps: a side runs backwards only on the outside of the bend's curve, and it moves towards the line.)
    reach[k]: the most units the outer side may lay off point k (water narrower than two strips)."""
    n = len(pts)
    fi, fo = [1.0] * n, [1.0] * n
    if reach is not None:
        fo = [min(1.0, r / (outer * s)) if outer * s > 1e-9 else 1.0 for r, s in zip(reach, scale)]
    pairs = [(k, k + 1) for k in range(n - 1)] + ([(n - 1, 0)] if closed else [])
    for _ in range(rounds):
        bad = False
        for a, b in pairs:
            if mask is not None and not mask[a]:
                continue
            dx, dz = pts[b][0] - pts[a][0], pts[b][1] - pts[a][1]
            l2 = dx * dx + dz * dz
            if l2 < 1e-12:
                continue
            for f, w in ((fi, -inner), (fo, outer)):
                ka, kb = w * scale[a] * f[a], w * scale[b] * f[b]
                ex, ez = dx + nrm[b][0] * kb - nrm[a][0] * ka, dz + nrm[b][1] * kb - nrm[a][1] * ka
                if ex * dx + ez * dz < 0.25 * l2:
                    f[a] *= 0.75
                    f[b] *= 0.75
                    bad = True
        if not bad:
            break
    for f in (fi, fo):
        g = list(f)
        for k in range(n):
            for o in range(-ramp, ramp + 1):
                j = k + o
                if closed:
                    j %= n
                elif not 0 <= j < n:
                    continue
                g[k] = min(g[k], f[j] + abs(o) / ramp)
        f[:] = g
    return fi, fo


def ease(vals: list, closed: bool, slope: float = 1.5, span: int = 20) -> list:
    """Per-point limits lowered so that they change by at most `slope` from one point to the next (within `span` points):
    a strip held back somewhere narrows towards that point gradually, not in one step."""
    n = len(vals)
    out = list(vals)
    for k in range(n):
        for o in range(-span, span + 1):
            j = k + o
            if closed:
                j %= n
            elif not 0 <= j < n:
                continue
            out[k] = min(out[k], vals[j] + slope * abs(o))
    return out


def ribbon(mesh: Mesh, pts: list, closed: bool, strip: dict, y, flip: bool = False, mask=None, colour=None,
           nrm=None, sides=None, scale=None, reach=None, lift=None) -> None:
    """Lay an atlas strip along a contour (points in board x/z, evenly spaced, the inside on the left). The strip's first u
    is laid strip['inner'] units inside, its second u strip['outer'] units outside (flip swaps the two ends of the strip);
    the rows repeat mirrored every strip['repeat'] units along the line. A strip marked 'transposed' runs the other way in
    its atlas: what is said here of u goes into v and the other way round. y: the height, or (inner, outer) heights for a
    strip that slopes or stands (an ice cliff), or a list of those per point (a cliff whose height changes); lift(x, z):
    added to the height at every vertex (a strip on raised ground). mask[k]: whether to draw the stretch from point k to the next; colour(x, z):
    colour bytes at a point; sides: (inner, outer) colour bytes instead (a strip that fades out at its edges; None: that
    side takes colour's); nrm: the
    points' normals (normals()) if already worked out; scale[k]: the strip's width at point k as a share of its full width
    (taper(): strips that narrow to nothing where they stop); reach[k]: the most units its outer side may lay off point k.
    Around bends too tight for the strip's width the strip is narrowed (fit()); a stretch whose side still runs backwards is
    left out."""
    if len(pts) < 2:
        return
    nrm = nrm or normals(pts, closed)
    idx = list(range(len(pts))) + ([0] if closed else [])
    wi, wo = strip["inner"], strip["outer"]
    sc = scale or [1.0] * len(pts)
    fi, fo = fit(pts, closed, nrm, sc, wi, wo, mask, reach)
    hs = y if isinstance(y, list) else [y if isinstance(y, tuple) else (y, y)] * len(pts)
    # split the line where the mirrored rows turn, so every quad stays inside one repeat
    rep = strip["repeat"]
    line, s = [(pts[0], nrm[0], 0.0, 0, sc[0] * fi[0], sc[0] * fo[0], hs[0])], 0.0
    for a, b in zip(idx, idx[1:]):
        (ax, az), (bx, bz) = pts[a], pts[b]
        seg = math.hypot(bx - ax, bz - az)
        if seg < 1e-9:
            continue
        m = math.floor(s / rep) + 1
        while m * rep < s + seg - 1e-6:
            t = (m * rep - s) / seg
            na, nb = nrm[a], nrm[b]
            nn = (na[0] + (nb[0] - na[0]) * t, na[1] + (nb[1] - na[1]) * t)
            d = math.hypot(*nn) or 1.0
            ki = sc[a] * fi[a] + (sc[b] * fi[b] - sc[a] * fi[a]) * t
            ko = sc[a] * fo[a] + (sc[b] * fo[b] - sc[a] * fo[a]) * t
            hh = tuple(p + (q - p) * t for p, q in zip(hs[a], hs[b]))
            line.append(((ax + (bx - ax) * t, az + (bz - az) * t), (nn[0] / d, nn[1] / d), m * rep, a, ki, ko, hh))
            m += 1
        s += seg
        line.append((pts[b], nrm[b], s, b, sc[b] * fi[b], sc[b] * fo[b], hs[b]))
    (ui, uo), (v0, v1) = strip["u"], strip["v"]
    if flip:
        ui, uo = uo, ui
    uv = (lambda a, b: (b, a)) if strip.get("transposed") else (lambda a, b: (a, b))
    up = (lambda q, h: h + lift(*q)) if lift else (lambda q, h: h)
    for (pa, na, sa, ka, ia_, oa_, (yia, yoa)), (pb, nb, sb, _, ib_, ob_, (yib, yob)) in zip(line, line[1:]):
        if mask is not None and not mask[ka]:
            continue
        dx, dz = pb[0] - pa[0], pb[1] - pa[1]
        qa = (pa[0] - na[0] * wi * ia_, pa[1] - na[1] * wi * ia_)
        qb = (pb[0] - nb[0] * wi * ib_, pb[1] - nb[1] * wi * ib_)
        ra = (pa[0] + na[0] * wo * oa_, pa[1] + na[1] * wo * oa_)
        rb = (pb[0] + nb[0] * wo * ob_, pb[1] + nb[1] * wo * ob_)
        if (qb[0] - qa[0]) * dx + (qb[1] - qa[1]) * dz <= 0 or (rb[0] - ra[0]) * dx + (rb[1] - ra[1]) * dz <= 0:
            continue
        mid = (sa + sb) / 2
        period = math.floor(mid / rep)
        ta, tb = (sa - period * rep) / rep, (sb - period * rep) / rep
        if period % 2:
            ta, tb = 1 - ta, 1 - tb
        va, vb = v0 + (v1 - v0) * ta, v0 + (v1 - v0) * tb
        ca = cb = WHITE
        if colour:
            ca, cb = colour(*pa), colour(*pb)
        ia, oa, ib, ob = ca, ca, cb, cb
        if sides:
            ia, ib = (sides[0], sides[0]) if sides[0] else (ia, ib)
            oa, ob = (sides[1], sides[1]) if sides[1] else (oa, ob)
        mesh.add([((qa[0], up(qa, yia), qa[1]), ia, uv(ui, va)),
                  ((ra[0], up(ra, yoa), ra[1]), oa, uv(uo, va)),
                  ((rb[0], up(rb, yob), rb[1]), ob, uv(uo, vb)),
                  ((qb[0], up(qb, yib), qb[1]), ib, uv(ui, vb))])


def sea(extent=(-3420.0, -1040.0, 3030.0, 1650.0), step: float = 500.0, holes=()) -> Mesh:
    """The sea: one flat plane of water at SEA_Y under the whole board, with the game's texture scale (water_test.tga
    repeats every 66.4 units), and a hole at each box of `holes` (x0, z0, x1, z1: the moats, whose water lies lower)."""
    mesh = Mesh()
    x0, z0, x1, z1 = extent
    nx, nz = math.ceil((x1 - x0) / step), math.ceil((z1 - z0) / step)
    xs = sorted({x0 + (x1 - x0) * i / nx for i in range(nx + 1)} | {x for h in holes for x in (h[0], h[2])})
    zs = sorted({z0 + (z1 - z0) * j / nz for j in range(nz + 1)} | {z for h in holes for z in (h[1], h[3])})
    uv = lambda x, z: (SEA_UV[0] * x + SEA_UV[1], SEA_UV[0] * z + SEA_UV[2])
    for za, zb in zip(zs, zs[1:]):
        for xa, xb in zip(xs, xs[1:]):
            if any(h[0] <= xa and xb <= h[2] and h[1] <= za and zb <= h[3] for h in holes):
                continue
            mesh.add([((x, SEA_Y, z), WHITE, uv(x, z)) for x, z in ((xa, za), (xb, za), (xb, zb), (xa, zb))])
    return mesh


def moat_water(grid: Grid, box: tuple[int, int, int, int]) -> Mesh:
    """A moat's water: one quad per cell over its cells' box (i0, j0, i1, j1, cells, the far ends excluded) at MOAT_Y,
    shaded MOAT_FOOT at the corners that touch the ground (where the walls come down to it, as in the game's)."""
    mesh = Mesh()
    i0, j0, i1, j1 = box
    wet = np.pad(grid.cells == ord("o"), 1)
    for j in range(j0, j1):
        for i in range(i0, i1):
            quad = []
            for ci, cj in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)):
                x, z = grid.x0 + ci * grid.cell, grid.z0 + cj * grid.cell
                inside = wet[cj:cj + 2, ci:ci + 2].all()
                quad.append(((x, MOAT_Y, z), WHITE if inside else MOAT_FOOT, (MOAT_UV * x, MOAT_UV * z)))
            mesh.add(quad)
    return mesh


def meshes(grid: Grid, shores: list | None = None) -> dict[str, Mesh]:
    """Every terrain mesh of the grid, by what it is drawn with: 'base' (grass/forest floor), 'beach' (coast strips: beaches,
    river banks, ice cliffs), 'edge' (grass edges), 'cliff' (the rock edges of plateaus and moats), 'moat'
    (the moats' water), 'sea', and one per overlay ground code. Everything on a plateau or slope is raised by the grid's lift. shores: a list
    to add every shore point to, as (x, z, 'sea' (an open shore) | 'bank' | 'ice' | 'cliff')."""
    c = grid.cell
    out = {}
    land = "".join(k for k in GROUNDS if k not in WATER)
    shore_land = land + "o"                                # a moat is no shore: it is cut into the land
    forest = grid.field("f")
    lv = grid.levels
    raised = lv != ord("0")

    def filled(codes: str, ground: Ground, y: float, **kw) -> Mesh:
        """fill() once per height: the ground, the plateaus (PLATEAU higher) and the slopes (following the lift)."""
        mesh, has = Mesh(), np.isin(grid.cells, np.frombuffer(codes.encode("ascii"), np.uint8))
        for key, up, lift in ((ord("0"), 0.0, None), (ord("1"), PLATEAU, None), (ord(RAMP), 0.0, grid.lift)):
            where = lv == key
            if (has & where).any():
                mesh.extend(fill(grid, codes, ground, y + up, where=where if raised.any() else None, lift=lift, **kw))
        return mesh

    out["base"] = filled(land, GROUNDS["g"], BASE_Y, colour=forest)
    for code in OVERLAYS:
        if (grid.cells == ord(code)).any():
            out[code] = filled(code, GROUNDS[code], OVERLAY_Y)
    to_xz = lambda p: (grid.x0 + p[0] * c, grid.z0 + p[1] * c)
    level_at = lambda x, z: chr(lv[min(max(int((z - grid.z0) // c), 0), grid.h - 1), min(max(int((x - grid.x0) // c), 0), grid.w - 1)])

    def tint(x: float, z: float) -> bytes:
        a = _bilinear(forest, min(max((x - grid.x0) / c, 0), grid.w), min(max((z - grid.z0) / c, 0), grid.h))
        return bytes(round(w + (k - w) * a) for w, k in zip(WHITE, FOREST))

    def narrow(p, n) -> bool:
        """Whether the water off this shore point has land again within NARROW units."""
        return any(grid.code_at(p[0] + n[0] * d, p[1] + n[1] * d) != "." for d in range(8, int(NARROW) + 1, 4))

    def across(p, n, step: int = 2) -> float:
        """How far the water off this shore point reaches along its normal before there is land again (FAR: open sea)."""
        return next((d for d in range(3, int(FAR), step) if grid.code_at(p[0] + n[0] * d, p[1] + n[1] * d) != "."), FAR)

    def openness(p, n) -> float:
        """0 (water closed in) to 1 (open sea): how far the water reaches on average over a fan of directions off the shore."""
        fan = [math.radians(a) for a in (-60, -30, 0, 30, 60)]
        q = (p[0] + n[0] * 8, p[1] + n[1] * 8)            # from a little offshore, so the slanted rays clear the shore itself
        return sum(across(q, (n[0] * math.cos(a) - n[1] * math.sin(a), n[0] * math.sin(a) + n[1] * math.cos(a)), 3)
                   for a in fan) / len(fan) / FAR

    def line_of(line, closed):
        pts = resample(chaikin([to_xz(p) for p in line], closed), closed)
        return pts, normals(pts, closed)

    beach, edge = Mesh(), Mesh()                          # banks and ice go with the beaches: strips of the same atlas
    for line, closed in contours(grid.field(shore_land)):
        pts, nrm = line_of(line, closed)
        tight = settle([narrow(p, n) for p, n in zip(pts, nrm)], closed)
        # a raised shore is a cliff into the sea (drawn below with the plateau's other edges): no beach, ice or surf
        high = settle([level_at(p[0] - n[0] * c, p[1] - n[1] * c) != "0" for p, n in zip(pts, nrm)], closed)
        snowy = settle([grid.code_at(p[0] - n[0] * 2 * c, p[1] - n[1] * 2 * c) == "w" for p, n in zip(pts, nrm)], closed)
        snowy = [w and not h for w, h in zip(snowy, high)]
        wide = [not t and not w and not h for t, w, h in zip(tight, snowy, high)]
        tight = [t and not w and not h for t, w, h in zip(tight, snowy, high)]
        gap = [across(p, n) for p, n in zip(pts, nrm)]
        # every shore but snow and the narrowest water has a beach, as on the game's board: along rivers its sand and foam
        # are squeezed so that water still shows between the beaches of the two banks
        moat = [m and not w and not h for m, w, h in zip(settle([g < CREEK for g in gap], closed), snowy, high)]
        sandy = [not w and not m and not h for w, m, h in zip(snowy, moat, high)]
        squeeze = ease([g * SQUEEZE for g in gap], closed)
        ribbon(beach, pts, closed, BEACH, BEACH_Y, mask=sandy, colour=tint, nrm=nrm, scale=taper(sandy, closed), reach=squeeze)
        ribbon(beach, pts, closed, BANK, BANK_Y, mask=moat, nrm=nrm, reach=[g / 2 for g in gap])
        ribbon(edge, pts, closed, SHORE, EDGE_Y, mask=moat, colour=tint, nrm=nrm, reach=[g / 2 for g in gap])
        ribbon(beach, pts, closed, ICE_WALL, (OVERLAY_Y, SEA_Y - 0.2), mask=snowy, nrm=nrm)
        ribbon(beach, pts, closed, ICE_RIM, OVERLAY_Y + 0.08, mask=snowy, nrm=nrm)
        if shores is not None:
            # an open shore (on the sea, not a river or a closed-in bay): how open, eased along the shore
            ramp = taper(wide, closed)
            sea_ = ease([min(max((openness(p, n) - OPEN[0]) / (OPEN[1] - OPEN[0]), 0.0), 1.0) for p, n in zip(pts, nrm)],
                        closed, slope=0.06)
            shores += [(p[0], p[1], "cliff" if h else "sea" if w and f * r > 0.3 else "ice" if i else "bank")
                       for p, w, f, r, i, h in zip(pts, wide, sea_, ramp, snowy, high)]
    # the edges of plateaus and slopes: leaning cliffs from the raised ground down to the ground or into the sea (none where
    # a slope has come down to the ground)
    cliff = Mesh()
    for line, closed in contours(grid.field(land, raised)) if raised.any() else ():
        pts, nrm = line_of(line, closed)
        # from the raised ground's surface (an overlay lies a little above the grass) down
        tops = [BASE_Y + grid.lift(p[0] - n[0] * 0.8 * c, p[1] - n[1] * 0.8 * c)
                + (OVERLAY_Y - BASE_Y if grid.code_at(p[0] - n[0] * 0.8 * c, p[1] - n[1] * 0.8 * c) in OVERLAYS else 0.0)
                for p, n in zip(pts, nrm)]
        foot = [SEA_Y - 0.2 if grid.code_at(p[0] + n[0] * 1.5 * c, p[1] + n[1] * 1.5 * c) == "." else BASE_Y
                for p, n in zip(pts, nrm)]
        # (where a plateau drops into a moat, the moat's wall is the cliff)
        steep = settle([t - f > 1.5 and grid.code_at(p[0] + n[0] * 0.5 * c, p[1] + n[1] * 0.5 * c) != "o"
                        for t, f, p, n in zip(tops, foot, pts, nrm)], closed)
        icy = settle([grid.code_at(p[0] - n[0] * 2 * c, p[1] - n[1] * 2 * c) == "w" for p, n in zip(pts, nrm)], closed)
        heights = [(t, f) for t, f in zip(tops, foot)]
        drop = [max(t - f, 0.0) / PLATEAU for t, f in zip(tops, foot)]
        ribbon(cliff, pts, closed, STRATA, heights, mask=[s and not i for s, i in zip(steep, icy)], nrm=nrm, scale=drop,
               sides=(WHITE, CLIFF_FOOT))
        cold = [s and i for s, i in zip(steep, icy)]
        ribbon(beach, pts, closed, ICE_CLIFF, heights, mask=cold, nrm=nrm, scale=drop)
        ribbon(beach, pts, closed, ICE_RIM, [(t + 0.08, t + 0.08) for t in tops], mask=cold, nrm=nrm)
    # moats: walls from the ground down to the sunk water, the grass's ragged edge hanging over their rims, the water, and
    # a hole in the sea plane over each
    holes = []
    moats = grid.cells == ord("o")
    if moats.any():
        dry = "".join(k for k in GROUNDS if k != "o")
        for line, closed in contours(grid.field(dry)):
            pts, nrm = line_of(line, closed)
            inside = [(p[0] - n[0] * 0.8 * c, p[1] - n[1] * 0.8 * c) for p, n in zip(pts, nrm)]
            tops = [BASE_Y + grid.lift(*q) + (OVERLAY_Y - BASE_Y if grid.code_at(*q) in OVERLAYS else 0.0) for q in inside]
            ribbon(cliff, pts, closed, MOAT_WALL, [(t, MOAT_Y) for t in tops], nrm=nrm,
                   scale=[(t - MOAT_Y) / (BASE_Y - MOAT_Y) for t in tops], sides=(WHITE, MOAT_FOOT))
            ribbon(edge, pts, closed, MOAT_RIM, [(t + 0.05, t + 0.05) for t in tops], colour=tint, nrm=nrm)
            out_by = MOAT_RIM["outer"]
            ribbon(edge, [(p[0] + n[0] * out_by, p[1] + n[1] * out_by) for p, n in zip(pts, nrm)], closed, MOAT_HANG,
                   [(t + 0.05, t - HANG_DROP) for t in tops], colour=tint, nrm=nrm, sides=(None, RIM_SHADE))
        water = Mesh()
        lab, n = ndimage.label(moats)
        for sl in ndimage.find_objects(lab):
            box = (max(sl[1].start - 1, 0), max(sl[0].start - 1, 0), min(sl[1].stop + 1, grid.w), min(sl[0].stop + 1, grid.h))
            water.extend(moat_water(grid, box))
            holes.append((grid.x0 + box[0] * c, grid.z0 + box[1] * c, grid.x0 + box[2] * c, grid.z0 + box[3] * c))
        out["moat"] = water
    if len(cliff):
        out["cliff"] = cliff
    out["beach"] = beach
    for code in OVERLAYS:
        if code not in out:
            continue
        # the grass is outside the overlay: the strip's grass end goes outside, its ragged end over the overlay,
        # and only where there is grass to come from (not along a shore)
        for line, closed in contours(grid.field(code)):
            pts, nrm = line_of(line, closed)
            grassy = settle([grid.code_at(p[0] + n[0] * 1.5 * c, p[1] + n[1] * 1.5 * c) in "gf" for p, n in zip(pts, nrm)], closed)
            # its grass stops short of water just beyond (a desert by a river)
            dry = ease([max(1.0, next((d for d in range(1, int(EDGE["outer"]) + 3)
                                       if grid.code_at(p[0] + n[0] * d, p[1] + n[1] * d) == "."), 99) - 2.0)
                        for p, n in zip(pts, nrm)], closed)
            ribbon(edge, pts, closed, EDGE, EDGE_Y, flip=True, mask=grassy, colour=tint, nrm=nrm, reach=dry,
                   lift=grid.lift if raised.any() else None)
    out["edge"] = edge
    out["sea"] = sea(holes=holes)
    return out


# ---- reading the game's board ---------------------------------------------------------------------------------------------
def _in(uv, box) -> bool:
    return box[0] - 0.01 <= uv[0] <= box[2] + 0.01 and box[1] - 0.01 <= uv[1] <= box[3] + 0.01


def classify_model_files(folder: Path, files=("A", "M", "N", "Anim1", "Anim2", "wood"), grid: Grid | None = None) -> Grid:
    """The ground of a board, read from its F00 model files: every cell gets the ground of the highest fill triangle over
    its centre (green_01 grass or forest by vertex colour, jimem_01 dirt, flat town_01 triangles in the objes sand, poison
    or swamp tiles, road_01 triangles in the fieldC snow tile); cells with none are sea, the water of the moat is moat. Beaches and edges are left out:
    meshes() lays them again along the borders."""
    grid = grid or Grid.empty()
    top = np.full(grid.cells.shape, -1e9, np.float32)
    atlas = {c: g.uv for c, g in GROUNDS.items() if g.fill == "overlay" and len(g.uv) == 4}
    strips = []                                                  # (layer, triangle, u per corner, code)
    moats = []                                                   # triangles of water pieces other than the sea plane
    for f in files:
        m = igbmodel.load(folder / f"F00_{f}.model")
        o, n = m.chunk("TEXT")
        texnames = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        vo = m.chunk("VERT")[0]
        for gi, nd in enumerate(m.mesh_nodes()):
            layer = nd["name"]
            tex = texnames[nd["texture"]] if nd["texture"] >= 0 else ""
            if layer not in ("green_01", "jimem_01", "town_01", "road_01", "road_side_sea", "road_side", "sea_01"):
                continue
            g = m.geoms[gi]
            M = m.placement(gi)
            raw = m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts]
            pos = [igbmodel.apply(M, struct.unpack_from("<3f", raw, g.stride * i)) for i in range(g.verts)]
            uvs = [struct.unpack_from("<2f", raw, g.stride * i + 0x1c) for i in range(g.verts)]
            cols = [raw[g.stride * i + 0x18: g.stride * i + 0x1b] for i in range(g.verts)]
            for t in igbmodel.mesh(m, g)[1]:
                tri = [pos[i] for i in t]
                ys = [p[1] for p in tri]
                uv = (sum(uvs[i][0] for i in t) / 3, sum(uvs[i][1] for i in t) / 3)
                lum = sum(sum(cols[i][:2]) / 2 for i in t) / 3 / 255
                if layer == "sea_01":
                    # water apart from the sea plane (Dokapon Castle's moat): moat over any strip's grass
                    if max(p[0] for p in pos) - min(p[0] for p in pos) < 500:
                        moats.append(tri)
                    continue
                if layer in ("road_side_sea", "road_side"):
                    # the grass end of a beach or edge strip is land too: up to where its grass stops
                    strip = BEACH if layer == "road_side_sea" else EDGE
                    lo, hi = min(strip["u"]) - 0.01, max(strip["u"]) + 0.01
                    if tex == "fieldC.tga" and uv[1] >= 0.74 and all(lo <= uvs[i][0] <= hi for i in t):
                        strips.append((layer, tri, [uvs[i][0] for i in t], "f" if lum < 0.6 else "g"))
                    continue
                if layer == "green_01":
                    code = "f" if lum < 0.6 else "g"
                elif layer == "jimem_01":
                    code = "d"
                elif layer == "town_01":
                    if tex != "objes.tga" or max(ys) - min(ys) > 1.0 or max(ys) > 12:
                        continue
                    code = next((k for k in "spm" if _in(uv, atlas[k])), None)
                else:
                    code = "w" if tex == "fieldC.tga" and _in(uv, atlas["w"]) and max(ys) - min(ys) < 2 else None
                if code is None:
                    continue
                if sum(ys) / 3 > HILL_Y:                         # the tops of the hills (props, raised on their own)
                    continue
                _raster(grid, top, tri, sum(ys) / 3, ord(code))
    # the strips draw the shore over the fills: a beach strip is the coastline where its grass stops (the game's grass
    # fill often runs on under its sand and surf, so a river's fills nearly meet), and an edge strip's grass is land too.
    # A beach strip's grass covers any ground (the game keeps grass between a desert and its beach); an edge strip's only
    # takes water (over snow or sand its ragged end shows the ground through).
    water = grid.cells == ord(".")
    before = grid.cells.copy()
    wet = np.zeros(water.shape, bool)
    for layer, tri, us, code in strips:
        if layer == "road_side_sea":
            sl, whole = _covered(grid, tri)
            if sl is not None:
                wet[sl] |= whole & ~_covered(grid, tri, us, STRIP_GRASS[layer])[1]
    grid.cells[wet] = ord(".")
    cover = {"road_side_sea": np.zeros(water.shape, bool), "road_side": np.zeros(water.shape, bool)}
    for layer, tri, us, code in strips:
        sl, hit = _covered(grid, tri, us, STRIP_GRASS[layer])
        if sl is not None:
            cover[layer][sl] |= hit
            grid.cells[sl][hit] = ord(code)
    restore = cover["road_side"] & ~cover["road_side_sea"] & ~water
    grid.cells[restore] = before[restore]
    for tri in moats:
        _raster(grid, top, tri, 2e9, ord("o"), touch=True)
    _drop_specks(grid)
    _levels(grid, top)
    return grid


def _levels(grid: Grid, top: np.ndarray) -> None:
    """The height codes from the fills' heights (top, per cell): a plateau where the ground is about PLATEAU up, a slope
    where it is between; land the strips added (no fill of its own) takes the height of the nearest filled cell."""
    has = (top > -1e8) & (top < 1e8)                             # (a moat's cells have no height of their own)
    if not has.any():
        return
    idx = ndimage.distance_transform_edt(~has, return_distances=False, return_indices=True)
    up = top[idx[0], idx[1]] - BASE_Y
    land = ~np.isin(grid.cells, np.frombuffer(WATER.encode("ascii"), np.uint8))
    lv = np.full(grid.cells.shape, ord("0"), np.uint8)
    lv[land & (up >= PLATEAU - 1.5)] = ord("1")
    lv[land & (up >= 1.5) & (up < PLATEAU - 1.5)] = ord(RAMP)
    lab, n = ndimage.label(lv == ord("1"))                      # plateaus too small to stand on are bumps: ground
    sizes = np.bincount(lab.ravel())
    lv[(lab > 0) & (sizes[lab] < 8)] = ord("0")
    slope = lv == ord(RAMP)                                      # a slope one cell wide is the foot of a cliff: ground
    lv[slope & ~ndimage.binary_opening(slope)] = ord("0")
    lab, n = ndimage.label(lv == ord(RAMP))                      # slopes that lead to no plateau are ground too
    near = ndimage.binary_dilation(lv == ord("1"), iterations=2)
    for k in range(1, n + 1):
        if not (near & (lab == k)).any():
            lv[lab == k] = ord("0")
    grid.levels = lv
    grid._lift = grid._corners = None


def _drop_specks(grid: Grid, smallest: int = 10) -> None:
    """Patches of an overlay ground smaller than `smallest` cells (left over where the strips' grass covered most of a
    patch) become the ground around them."""
    for code in OVERLAYS:
        lab, n = ndimage.label(grid.cells == ord(code))
        sizes = np.bincount(lab.ravel())
        for k in range(1, n + 1):
            if sizes[k] >= smallest:
                continue
            patch = lab == k
            ring = ndimage.binary_dilation(patch) & ~patch
            around = grid.cells[ring]
            around = around[(around != ord(code)) & ~np.isin(around, np.frombuffer(WATER.encode("ascii"), np.uint8))]
            if len(around):
                grid.cells[patch] = np.bincount(around).argmax()


def _raster(grid: Grid, top: np.ndarray, tri, y: float, code: int, touch: bool = False) -> None:
    """Give the cells whose centres the triangle covers `code`, where y is above what they have. touch: every cell the
    triangle reaches into (a thin feature, so that it is wide enough in the grid to keep)."""
    sl, hit = _covered(grid, tri, touch=touch)
    if sl is None:
        return
    sub = top[sl]
    win = hit & (y > sub)
    sub[win] = y
    grid.cells[sl][win] = code


def _covered(grid: Grid, tri, us=None, below: float = 0.0, touch: bool = False):
    """(the grid slice around the triangle, which of its cells the triangle covers), or (None, None). us, below: only where
    the u coordinate (us at the corners) is less than `below`; touch: as in _raster."""
    (ax, _, az), (bx, _, bz), (cx, _, cz) = tri
    c = grid.cell
    i0 = max(int((min(ax, bx, cx) - grid.x0) / c - 1.5), 0)
    i1 = min(int((max(ax, bx, cx) - grid.x0) / c + 1.5) + 1, grid.w)
    j0 = max(int((min(az, bz, cz) - grid.z0) / c - 1.5), 0)
    j1 = min(int((max(az, bz, cz) - grid.z0) / c + 1.5) + 1, grid.h)
    den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
    if i0 >= i1 or j0 >= j1 or abs(den) < 1e-9:
        return None, None
    xs = grid.x0 + (np.arange(i0, i1) + 0.5) * c
    zs = grid.z0 + (np.arange(j0, j1) + 0.5) * c
    X, Z = np.meshgrid(xs, zs)
    hit = np.zeros(X.shape, bool)
    reach = (-0.45 * c, 0.0, 0.45 * c) if touch else (0.0,)
    for ox in reach:
        for oz in reach:
            l0 = ((bz - cz) * (X + ox - cx) + (cx - bx) * (Z + oz - cz)) / den
            l1 = ((cz - az) * (X + ox - cx) + (ax - cx) * (Z + oz - cz)) / den
            h = (l0 >= -1e-6) & (l1 >= -1e-6) & (1 - l0 - l1 >= -1e-6)
            if us is not None:
                h &= l0 * us[0] + l1 * us[1] + (1 - l0 - l1) * us[2] < below
            hit |= h
    return (slice(j0, j1), slice(i0, i1)), hit


if __name__ == "__main__":
    # python terrain.py <out.json>: the ground of the game's board 0 as a grid
    F00 = Path("G:/Programming/Dokapon-Workspace/assets/CommonData/dataField/F00")
    gr = classify_model_files(F00)
    Path(sys.argv[1]).write_text(json.dumps(gr.to_json()))
    counts = {GROUNDS[chr(k)].name: int(v) for k, v in zip(*np.unique(gr.cells, return_counts=True))}
    print(f"{gr.w}x{gr.h} cells of {gr.cell}: {counts}")

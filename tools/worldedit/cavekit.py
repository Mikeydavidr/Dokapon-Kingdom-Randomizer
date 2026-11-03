"""Ground kits for dungeons: which of a dungeon's own textures draw which ground, how to read its ground from the game's
art, and the meshes that draw a painted ground grid with them. One kit so far: the lava caves (boards 3, 4 and 5).

How the lava caves are drawn (F03-F05, all from one texture set):
  floor      f03_06 (cracked rock), flat at about y 0, tiled every 53 units; raised parts up to y 6
  lava       f03_08, a flat sheet at y -15 in the F0x_UV file (the game scrolls it: flowing lava)
  drops      f03_07 walls from the floor edge down into the lava: tiled along the wall every 17 units, top to bottom
             brown rock -> red -> white glow over the 15-unit drop (v 0 at the floor, 1 at the lava)
  cliffs     f03_05 banded rock rising from the floor (or the lava) up to y 50 at the cave's edge: bands across, every 20
             units along and 31 up; dark (vertex colour near black) towards the top
  cap        f03_01, dark, flat at y 50 over everything outside the cave
  pits       holes in the floor with no art in them: the dark background shows (painted pits get walls of cliff rock
             going down into black and a black floor just above the lava)
  details    f03_03 / f03_04 rock bumps and wall feet, f04_20 a lava fall (board 5): left out of painted caves
Paths (street02), the stores of board 5 (magic, weapon) and the obI_A object are not ground and stay.
"""
import math
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel
import terrain
from terrain import WHITE, Ground, Grid, Mesh

KITS = {
    "lava cave": {
        "boards": (3, 4, 5),
        "grounds": [Ground("#", "cave wall", "#2a1c2e", None), Ground("r", "rock floor", "#9c6b4e", "overlay", "f03_06", (1 / 53,)),
                    Ground("l", "lava", "#ff6a1a", None), Ground("p", "pit", "#000000", None)],
        "walkable": "r",
        "textures": {"floor": "f03_06.tga", "drop": "f03_07.tga", "lava": "f03_08.tga", "cliff": "f03_05.tga",
                     "cap": "f03_01.tga"},
        "hide": {"f03_03.tga", "f03_04.tga", "f04_20.tga"},
        "floor_y": 0.0, "lava_y": -15.0, "cap_y": 50.0, "pit_y": -14.0,
    },
}
DROP_U, DROP_V = 1 / 17, 1 / 15         # drop walls: u per unit along, v per unit down (v 0 at the floor, 1 at the lava)
CLIFF_U, CLIFF_V = 1 / 20, 1 / 31
LAVA_UV, CAP_UV = 1 / 36, 1 / 33
SKIRT = 2.0                             # drops reach this far below the lava surface
LEAN = 0.7                              # drops lean out over the lava, cliffs back into the wall: sideways per unit of height
CAP_DARK = bytes.fromhex("060318ff")    # the cap is near black (its texture is a gradient that would show as stripes)
FLOOR_DARK = bytes.fromhex("5c4a78ff")  # the floor darkens towards the cave walls, as the game's does
CLIFF_TOP = bytes.fromhex("060318ff")   # cliffs fade to near black at the top


def kit_for(board: int) -> str | None:
    return next((name for name, k in KITS.items() if board in k["boards"]), None)


def grounds(kit: str) -> list[Ground]:
    return KITS[kit]["grounds"]


# ---- reading the game's cave ----------------------------------------------------------------------------------------------
def classify(folder: Path, board: int, box, cell: float = 4.0) -> Grid:
    """The ground of a lava cave from its model files: rock floor where a floor triangle (f03_06, or the f03_03 / f03_04
    rock on it) is the highest flat thing over a cell, lava where only the lava sheet is, cave wall under the dark cap;
    cells with none of these are cave wall if they reach the edge of the grid that way, else (small gaps by the cliffs
    and the lava that the art does not cover; the game's lava caves have no pits) the ground around them."""
    k = KITS[kit_for(board)]
    tex = k["textures"]
    x0, z0, x1, z1 = box
    grid = Grid(x0, z0, cell, np.full((math.ceil((z1 - z0) / cell), math.ceil((x1 - x0) / cell)), ord("p"), np.uint8))
    top = np.full(grid.cells.shape, -1e9, np.float32)
    kinds = {tex["floor"]: "r", "f03_03.tga": "r", "f03_04.tga": "r", tex["lava"]: "l", tex["cap"]: "#"}
    for f in sorted(folder.glob(f"F{board:02d}_*.model")):
        try:
            m = igbmodel.load(f)
            nodes = m.mesh_nodes()
        except (ValueError, KeyError):
            continue
        o, n = m.chunk("TEXT")
        names = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        for gi, nd in enumerate(nodes):
            code = kinds.get(names[nd["texture"]] if nd["texture"] >= 0 else "")
            if code is None:
                continue
            M = m.placement(gi)
            pos, tris = igbmodel.mesh(m, m.geoms[gi])
            w = [igbmodel.apply(M, p) for p in pos]
            for t in tris:
                tri = [w[i] for i in t]
                ys = [p[1] for p in tri]
                if code == "r" and min(ys) < k["floor_y"] - 3:
                    continue                                  # the floor's skirt down into the lava
                if code != "r" and max(ys) - min(ys) > 3.0:
                    continue                                  # a slope of the cap, not its top
                # (steep floor triangles count: the dark spots on the floor are rock mounds, f03_03 / f03_04)
                terrain._raster(grid, top, tri, sum(ys) / 3, ord(code))
    # empty cells joined to the edge of the grid are outside the cave: cave wall
    todo = [(j, i) for j in range(grid.h) for i in (0, grid.w - 1)] + [(j, i) for i in range(grid.w) for j in (0, grid.h - 1)]
    while todo:
        j, i = todo.pop()
        if 0 <= j < grid.h and 0 <= i < grid.w and grid.cells[j, i] == ord("p"):
            grid.cells[j, i] = ord("#")
            todo += [(j + 1, i), (j - 1, i), (j, i + 1), (j, i - 1)]
    pit = ord("p")
    while (grid.cells == pit).any():
        p = np.pad(grid.cells, 1, mode="edge")
        around = [p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]]
        best = np.full(grid.cells.shape, pit, np.uint8)
        for code in (ord("#"), ord("l"), ord("r")):             # the most common ground around a gap fills it
            n = sum((a == code).astype(np.int32) for a in around)
            nb = sum((a == best).astype(np.int32) * (best != pit) for a in around)
            best = np.where((n > 0) & (n >= nb), code, best)
        grid.cells = np.where(grid.cells == pit, best, grid.cells).astype(np.uint8)
    return grid


# ---- meshes ---------------------------------------------------------------------------------------------------------------
def _plane(box, y: float, scale: float, step: float = 100.0) -> Mesh:
    mesh = Mesh()
    x0, z0, x1, z1 = box
    nx, nz = max(1, math.ceil((x1 - x0) / step)), max(1, math.ceil((z1 - z0) / step))
    for j in range(nz):
        for i in range(nx):
            xa, xb = x0 + (x1 - x0) * i / nx, x0 + (x1 - x0) * (i + 1) / nx
            za, zb = z0 + (z1 - z0) * j / nz, z0 + (z1 - z0) * (j + 1) / nz
            mesh.add([((x, y, z), WHITE, (x * scale, z * scale)) for x, z in ((xa, za), (xb, za), (xb, zb), (xa, zb))])
    return mesh


def wall(mesh: Mesh, pts: list, nrm: list, closed: bool, y_top: float, y_bottom, u_scale: float, v_of_y, colour_of_y=None,
         mask=None, top_shift=0.0, bottom_shift=0.0) -> None:
    """A wall on a contour line (points evenly spaced, nrm their outward normals) from y_top down to y_bottom (a number, or a
    function of the point index for walls whose foot changes along the line). Its top and foot are moved top_shift and
    bottom_shift (a number or a function of the point index) along the normal, so it leans. Texture u runs along the
    wall, v = v_of_y(y). Drawn from both sides (which way the game culls walls is not known). mask[k]: draw the stretch
    from point k."""
    idx = list(range(len(pts))) + ([0] if closed else [])
    at = lambda v, i: v(i) if callable(v) else v
    s = 0.0
    for a, b in zip(idx, idx[1:]):
        (ax, az), (bx, bz) = pts[a], pts[b]
        seg = math.hypot(bx - ax, bz - az)
        if mask is not None and not mask[a]:
            s += seg
            continue
        ua, ub = s * u_scale, (s + seg) * u_scale
        s += seg
        ba, bb = at(y_bottom, a), at(y_bottom, b)
        ct = colour_of_y(y_top) if colour_of_y else WHITE
        cba, cbb = (colour_of_y(ba), colour_of_y(bb)) if colour_of_y else (WHITE, WHITE)
        (nax, naz), (nbx, nbz) = nrm[a], nrm[b]
        ta, tb, fa, fb = at(top_shift, a), at(top_shift, b), at(bottom_shift, a), at(bottom_shift, b)
        quad = [((ax + nax * ta, y_top, az + naz * ta), ct, (ua, v_of_y(y_top))),
                ((bx + nbx * tb, y_top, bz + nbz * tb), ct, (ub, v_of_y(y_top))),
                ((bx + nbx * fb, bb, bz + nbz * fb), cbb, (ub, v_of_y(bb))),
                ((ax + nax * fa, ba, az + naz * fa), cba, (ua, v_of_y(ba)))]
        base = len(mesh.pos)
        for p, c, uv in quad:
            mesh.pos.append(p)
            mesh.col.append(c)
            mesh.uv.append(uv)
        mesh.tris += [[base, base + 1, base + 2], [base, base + 2, base + 3], [base, base + 2, base + 1], [base, base + 3, base + 2]]


def meshes(grid: Grid, kit: str) -> dict[str, Mesh]:
    """{channel: mesh} for a painted cave: 'floor', 'lava', 'drop', 'cliff', 'cap' (the keys of the kit's textures). The
    grid's outermost cells count as cave wall whatever they hold, so the cave is closed."""
    k = KITS[kit]
    grid = Grid(grid.x0, grid.z0, grid.cell, grid.cells.copy())
    grid.cells[[0, -1], :] = ord("#")
    grid.cells[:, [0, -1]] = ord("#")
    fy, ly, cy, py = k["floor_y"], k["lava_y"], k["cap_y"], k["pit_y"]
    c = grid.cell
    box = (grid.x0, grid.z0, grid.x0 + grid.w * c, grid.z0 + grid.h * c)
    floor_ground = next(g for g in k["grounds"] if g.code == "r")
    near_wall = grid.field("#")
    near_wall = np.clip(np.maximum(near_wall, _blur(near_wall, 3) * 1.6), 0, 1) * 0.7
    black = np.ones((grid.h + 1, grid.w + 1))
    cap_ground = Ground("#", "cap", "", "overlay", "cap", (CAP_UV,))
    out = {"floor": terrain.fill(grid, "r", floor_ground, fy, colour=near_wall, shade=FLOOR_DARK),
           "lava": _plane((box[0] - 200, box[1] - 200, box[2] + 200, box[3] + 200), ly, LAVA_UV),
           "cap": terrain.fill(_eroded(grid, "#", LEAN * (cy - fy)), "#", cap_ground, cy, colour=black, shade=CAP_DARK)}
    # a black floor above the lava under the pits and the cave wall, a little wider than they are (the rock floor covers
    # the rest): pits show black, and so does any gap between a thin wall's cliffs and the cap
    pit_floor = terrain.fill(_grown(grid, "p#", 2, keep_off="l"), "p", cap_ground, py, colour=black, shade=CAP_DARK)
    base = len(out["cap"])
    out["cap"].pos += pit_floor.pos
    out["cap"].col += pit_floor.col
    out["cap"].uv += pit_floor.uv
    out["cap"].tris += [[base + i for i in t] for t in pit_floor.tris]
    to_xz = lambda p: (grid.x0 + p[0] * c, grid.z0 + p[1] * c)

    def line_of(line, closed):
        pts = terrain.resample(terrain.chaikin([to_xz(p) for p in line], closed), closed)
        return pts, terrain.normals(pts, closed)

    # drops: along the floor's edge where lava lies beyond it
    drop = Mesh()
    for line, closed in terrain.contours(grid.field("r")):
        pts, nrm = line_of(line, closed)
        over_lava = terrain.settle([grid.code_at(p[0] + n[0] * 1.5 * c, p[1] + n[1] * 1.5 * c) == "l" for p, n in zip(pts, nrm)],
                                   closed, 4)
        wall(drop, pts, nrm, closed, fy, ly - SKIRT, DROP_U, lambda y: (fy - y) * DROP_V, mask=over_lava,
             bottom_shift=LEAN * (fy - ly + SKIRT))
    out["drop"] = drop

    # pits: cliff rock going down from the floor's edge into black, straight down (they are often small)
    shade = lambda y: bytes(round(w + (t - w) * min(max((fy - y) / (fy - py), 0.0), 1.0) ** 0.6) for w, t in zip(WHITE, CLIFF_TOP))
    pit = Mesh()
    for line, closed in terrain.contours(grid.field("r")):
        pts, nrm = line_of(line, closed)
        over_pit = terrain.settle([grid.code_at(p[0] + n[0] * 1.5 * c, p[1] + n[1] * 1.5 * c) == "p" for p, n in zip(pts, nrm)],
                                  closed, 4)
        wall(pit, pts, nrm, closed, fy, py, CLIFF_U, lambda y: (fy - y) * CLIFF_V, colour_of_y=shade, mask=over_pit)

    # cliffs: along the cave wall's edge, standing on the floor or rising out of the lava
    shade = lambda y: bytes(round(w + (t - w) * min(max((y - fy) / (cy - fy), 0.0), 1.0) ** 0.7) for w, t in zip(WHITE, CLIFF_TOP))
    cliff = pit
    lean = LEAN * (cy - fy)

    def depth(p, n) -> float:
        """How far the cave wall reaches behind a point of its edge (up to twice the lean)."""
        d = 2.0
        while d < 2 * lean and grid.code_at(p[0] - n[0] * d, p[1] - n[1] * d) == "#":
            d += 2.0
        return d

    for line, closed in terrain.contours(grid.field("#")):
        pts, nrm = line_of(line, closed)
        foot = [fy if grid.code_at(p[0] + n[0] * 1.5 * c, p[1] + n[1] * 1.5 * c) == "r" else ly - SKIRT for p, n in zip(pts, nrm)]
        # the cliff leans back into the wall from its foot on the contour, its top the same distance in everywhere so
        # that the cap (taken back by as much) meets it; where the wall is thinner, only halfway across, so the cliffs of
        # both sides meet in a ridge
        back = [min(lean, depth(p, n) / 2) for p, n in zip(pts, nrm)]
        wall(cliff, pts, nrm, closed, cy, lambda i: foot[i], CLIFF_U, lambda y: (cy - y) * CLIFF_V, colour_of_y=shade,
             top_shift=lambda i: -back[i])
    out["cliff"] = cliff
    return out


def _grown(grid: Grid, codes: str, cells: int, keep_off: str = "") -> Grid:
    """A grid of 'p' where any of `codes` is or lies within `cells` cells (but not on `keep_off` ground), 'r' elsewhere."""
    m = np.isin(grid.cells, np.frombuffer(codes.encode("ascii"), np.uint8))
    for _ in range(cells):
        p = np.pad(m, 1, mode="edge")
        m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    if keep_off:
        m &= ~np.isin(grid.cells, np.frombuffer(keep_off.encode("ascii"), np.uint8))
    return Grid(grid.x0, grid.z0, grid.cell, np.where(m, ord("p"), ord("r")).astype(np.uint8))


def _eroded(grid: Grid, code: str, distance: float) -> Grid:
    """A copy of the grid with `code` taken back `distance` units from wherever it meets other ground."""
    m = grid.cells == ord(code)
    for _ in range(max(0, round(distance / grid.cell))):
        p = np.pad(m, 1, mode="edge")
        m = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    cells = np.where(m, ord(code), ord("r")).astype(np.uint8)
    return Grid(grid.x0, grid.z0, grid.cell, cells)


def _blur(f: np.ndarray, r: int) -> np.ndarray:
    out = f.copy()
    for _ in range(r):
        p = np.pad(out, 1, mode="edge")
        out = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] + p[1:-1, 1:-1]) / 5
    return out


def build(grid: Grid, kit: str, folder: Path, board: int) -> tuple[dict[str, dict], list[str]]:
    """{model file stem: {piece: (vertex bytes, indices)}} for the painted ground of a cave: each mesh in the board's own
    piece with its texture (the largest one), every other piece of the kit's textures hidden; and log lines."""
    k = KITS[kit]
    ms = meshes(grid, kit)
    want = {t: ch for ch, t in k["textures"].items()}
    found, other = {}, []                                  # channel -> (stem, piece, model); pieces to hide
    for f in sorted(folder.glob(f"F{board:02d}_*.model")):
        try:
            m = igbmodel.load(f)
            nodes = m.mesh_nodes()
        except (ValueError, KeyError):
            continue
        o, n = m.chunk("TEXT")
        names = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        for gi, nd in enumerate(nodes):
            t = names[nd["texture"]] if nd["texture"] >= 0 else ""
            if t in want:
                ch = want[t]
                if ch not in found or m.geoms[gi].verts > found[ch][2].geoms[found[ch][1]].verts:
                    if ch in found:
                        other.append(found[ch][:2])
                    found[ch] = (f.stem, gi, m)
                else:
                    other.append((f.stem, gi))
            elif t in k["hide"]:
                other.append((f.stem, gi))
    out, log = {}, []
    for ch, mesh in ms.items():
        if ch not in found:
            log.append(f"ground {ch}: board {board} has no {k['textures'][ch]} piece, left out")
            continue
        stem, gi, m = found[ch]
        g = m.geoms[gi]
        if len(mesh) > 60000:
            sys.exit(f"ground {ch}: {len(mesh)} vertices, more than one piece holds")
        template = igbmodel.vertex_bytes(m, gi)[:g.stride]
        inv = igbmodel.inverse(m.placement(gi))
        vb = bytearray()
        for p, col, uv in zip(mesh.pos, mesh.col, mesh.uv):
            vb += struct.pack("<6f", *igbmodel.apply(inv, p), 0.0, 1.0, 0.0) + col + struct.pack("<2f", *uv) + template[0x24:]
        out.setdefault(stem, {})[gi] = (bytes(vb), [i for t in mesh.tris for i in t])
        log.append(f"ground {ch}: {len(mesh)} vertices into {stem} piece {gi}")
    for stem, gi in other:
        m = igbmodel.load(folder / f"{stem}.model")
        out.setdefault(stem, {})[gi] = (igbmodel.vertex_bytes(m, gi)[:m.geoms[gi].stride], [0, 0, 0])
    log.append(f"ground: {len(other)} other pieces of the cave's art hidden")
    return out, log

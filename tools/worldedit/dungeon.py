"""Build a mod for a dungeon board (boards 1-22) from a world file: its spaces where the file puts them, its links, and every
path drawn again for them. The dungeon's own art (floors, walls, water, lava, buildings) stays as it is.

How a dungeon draws its paths (all 22 boards): flat strips of street02.tga (orange | white | orange across, repeating along;
boards 19 and 21 have path textures of their own), about 8 units wide (6.4 in boards 13-14), 0.5 below the spaces, running
from space to space and bending over every bump of the floor (a straight strip would dip under it in places). New strips
lie where the old ones did, and just above the floor where the game had no path (Surface). They are pieces of their own
(layers like F01_street02, F11_road_m1), apart from the floor art, so they can be drawn again without touching the floor.
Some links have no path strip: the game shows them another way (bridges in boards 6 and 22, paths painted into the floor
art in boards 10 and 21) or not at all (board 19's secret passages to its loot spaces). The world file lists them as
no_path_links and they stay without a strip; that art does not follow a moved space.
The links obey board 0's rules (CHAIN slot = direction: 0 +z, 1 +x, 2 -z, 3 -x); dungeon 6 has one link 2 units off
straight, so dungeons allow STRAIGHT units. Dungeons have no camera-limit record in their stg file.
"""
import math
import struct
import sys
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "boardview"))
sys.path.insert(0, str(HERE.parent / "igb"))
import cavekit
import igbmodel
from boardlib import load_board
from terrain import Grid

PATH_TEXTURES = {"street02.tga", "F19_road.tga", "F21_road.tga"}
STRAIGHT = 3.0                  # a link may be this far off straight across
PATH_DROP = 0.5                 # paths lie this far below the spaces
STEP = 4.0                      # paths are cut into pieces this long to follow the ground
FLOOR_LIFT = 0.3                # a path where the game had none lies this far above the floor
SPACE_LIFT = 1.0                # on a painted (flat) cave floor the spaces stand this high, the paths PATH_DROP lower
STEPS = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}


def slot(a, b) -> int:
    dx, dz = b[0] - a[0], b[2] - a[2]
    return (0 if dz > 0 else 2) if abs(dz) > abs(dx) else (1 if dx > 0 else 3)


def path_pieces(folder: Path, board: int) -> dict[tuple[str, int], igbmodel.Model]:
    """{(file stem, piece): model} of every path piece of the board."""
    out = {}
    for f in sorted(folder.glob(f"F{board:02d}_*.model")):
        try:
            m = igbmodel.load(f)
            nodes = m.mesh_nodes()
        except (ValueError, KeyError):
            continue
        o, n = m.chunk("TEXT")
        names = [m.name_at(struct.unpack_from("<I", m.data, o + 12 * i)[0]) for i in range(n // 12)]
        for gi, nd in enumerate(nodes):
            if nd["texture"] >= 0 and names[nd["texture"]] in PATH_TEXTURES:
                out[(f.stem, gi)] = m
    return out


def no_path_links(assets: Path, board: int) -> list[list[int]]:
    """The links of a dungeon with no path strip under them (no path triangle under the points a quarter, half and three
    quarters of the way along): bridges, paths painted into the floor art, secret passages."""
    folder = assets / "CommonData" / "dataField" / f"F{board:02d}"
    spaces, links = load_board(assets, board)
    pos = {s["id"]: s["pos"] for s in spaces}
    tris = []
    for (_, gi), m in path_pieces(folder, board).items():
        M = m.placement(gi)
        p, ts = igbmodel.mesh(m, m.geoms[gi])
        w = [igbmodel.apply(M, q) for q in p]
        tris += [[(w[i][0], w[i][2]) for i in t] for t in ts]

    def covered(x: float, z: float) -> bool:
        for (ax, az), (bx, bz), (cx, cz) in tris:
            den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(den) < 1e-9:
                continue
            l0 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / den
            l1 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / den
            if l0 >= -0.02 and l1 >= -0.02 and 1 - l0 - l1 >= -0.02:
                return True
        return False

    out = []
    for a, bs in links.items():
        for c in bs:
            if a < c and not any(covered(pos[a][0] + (pos[c][0] - pos[a][0]) * t, pos[a][2] + (pos[c][2] - pos[a][2]) * t)
                                 for t in (0.25, 0.5, 0.75)):
                out.append([a, c])
    return sorted(out)


class Surface:
    """Heights a path can lie at, from the board's model files: the game's own path strips (where a path ran, its new strip
    lies exactly where the old one did) and the rest of the art (the floor, for a path where the game had none)."""
    CELL = 20.0

    def __init__(self, folder: Path, board: int, pieces: dict):
        self.buckets: dict[tuple[int, int], list] = {}
        for f in sorted(folder.glob(f"F{board:02d}_*.model")):
            try:
                m = igbmodel.load(f)
                nodes = m.mesh_nodes()
            except (ValueError, KeyError):
                continue
            for gi in range(len(nodes)):
                M = m.placement(gi)
                pos, tris = igbmodel.mesh(m, m.geoms[gi])
                w = [igbmodel.apply(M, p) for p in pos]
                is_path = (f.stem, gi) in pieces
                for t in tris:
                    tri = [w[i] for i in t]
                    xs, zs = [p[0] for p in tri], [p[2] for p in tri]
                    for bx in range(int(min(xs) // self.CELL), int(max(xs) // self.CELL) + 1):
                        for bz in range(int(min(zs) // self.CELL), int(max(zs) // self.CELL) + 1):
                            self.buckets.setdefault((bx, bz), []).append((tri, is_path))

    def heights(self, x: float, z: float):
        """(y, is a path triangle) of every triangle over (x, z)."""
        for (a, b, c), is_path in self.buckets.get((int(x // self.CELL), int(z // self.CELL)), []):
            den = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(den) < 1e-9:
                continue
            l0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / den
            l1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / den
            if l0 >= -1e-6 and l1 >= -1e-6 and 1 - l0 - l1 >= -1e-6:
                yield l0 * a[1] + l1 * b[1] + (1 - l0 - l1) * c[1], is_path

    def path_y(self, x: float, z: float, expect: float) -> float:
        """Where a path through (x, z) should lie, near the height `expect` (the straight line between its spaces): on the
        game's own path there, else just above the highest floor not far above or below it, else at `expect`."""
        hs = list(self.heights(x, z))
        paths = [y for y, p in hs if p and abs(y - expect) <= 6.0]
        if paths:
            return min(paths, key=lambda y: abs(y - expect))
        floors = [y for y, p in hs if not p and expect - 12.0 <= y <= expect + 4.0]
        return max(floors) + FLOOR_LIFT if floors else expect


def measure(pieces: dict) -> tuple[float, float]:
    """(width, units per repeat along) of the board's paths, from their texture coordinates."""
    widths, reps = [], []
    for (_, gi), m in pieces.items():
        g = m.geoms[gi]
        vo = m.chunk("VERT")[0]
        M = m.placement(gi)
        pos, tris = igbmodel.mesh(m, g)
        w = [igbmodel.apply(M, p) for p in pos]
        uv = [struct.unpack_from("<2f", m.data, vo + g.vert_offset + g.stride * i + 0x1c) for i in range(g.verts)]
        for t in tris:
            for a, c in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                du, dv, d = abs(uv[a][0] - uv[c][0]), abs(uv[a][1] - uv[c][1]), math.dist(w[a], w[c])
                if du > 0.9 and dv < 0.01:
                    widths.append(d / du)
                elif du < 0.01 and dv > 0.05:
                    reps.append(d / dv)
    return (median(widths) if widths else 8.0), (median(reps) if reps else 40.0)


def build(w: dict, assets: Path, out: Path, log: list[str]) -> None:
    board = w["board"]
    folder = assets / "CommonData" / "dataField" / f"F{board:02d}"
    spaces, game_links = load_board(assets, board)
    old = {s["id"]: s["pos"] for s in spaces}
    by_id = {s["id"]: s for s in w["spaces"]}
    if set(by_id) != set(old):
        sys.exit("the world must keep every space of the board (adding or removing spaces is not supported yet)")
    painted = w.get("terrain") is not None                  # a cave painted with a ground kit: its floor is flat
    kit = cavekit.KITS[w["terrain"]["kit"]] if painted else None
    new = {n: (by_id[n]["x"], kit["floor_y"] + SPACE_LIFT if painted else by_id[n]["y"], by_id[n]["z"]) for n in old}
    delta = {n: tuple(new[n][k] - old[n][k] for k in range(3)) for n in old}

    # ---- positions: Z#### are the spaces; W points (walk waypoints) move with their nearest space; camera points stay --
    name = f"MASU{board:02d}.position"
    b = bytearray((assets / "CommonData" / "fieldPosition" / name).read_bytes())
    count, base = struct.unpack_from("<II", b, 0)
    q = 8
    for i in range(count):
        e = b.index(0, q)
        nm, q = b[q:e].decode("ascii"), e + 1
        p = struct.unpack_from("<3f", b, base + 12 * i)
        if nm[0] == "Z" and nm[1:].isdigit():
            struct.pack_into("<3f", b, base + 12 * i, *new[int(nm[1:])])
        elif nm[0] in "Ww" and nm[1:].isdigit():
            n = min(old, key=lambda k: (old[k][0] - p[0]) ** 2 + (old[k][2] - p[2]) ** 2)
            struct.pack_into("<3f", b, base + 12 * i, *(p[k] + delta[n][k] for k in range(3)))
    (out / name).write_bytes(b)

    # ---- links ---------------------------------------------------------------------------------------------------------
    links = {n: [] for n in old}
    for a, c in w["links"]:
        links[a].append(c)
        links[c].append(a)
    chain = bytearray((assets / "CommonData" / "fieldChain" / f"CHAIN_{board:03d}.DAT").read_bytes())
    problems = []
    for n in old:
        slots = [0xFFFF] * 4
        for m in links[n]:
            dx, dz = new[m][0] - new[n][0], new[m][2] - new[n][2]
            if min(abs(dx), abs(dz)) >= STRAIGHT:
                problems.append(f"link {n}-{m} is not straight (dx {dx:.0f}, dz {dz:.0f})")
            s = slot(new[n], new[m])
            if slots[s] != 0xFFFF:
                problems.append(f"space {n}: links to {slots[s]} and {m} leave in the same direction")
            slots[s] = m
        o = 2 + 10 * n
        assert struct.unpack_from("<H", chain, o)[0] == n
        struct.pack_into("<4H", chain, o + 2, *slots)
    if problems:
        sys.exit("cannot build:\n  " + "\n  ".join(sorted(set(problems))))
    (out / f"CHAIN_{board:03d}.DAT").write_bytes(bytes(chain))
    changed = sum(1 for n in old if sorted(links[n]) != sorted(game_links.get(n, [])))
    moved = sum(1 for n in old if math.dist(new[n], old[n]) > 0.01)
    log.append(f"dungeon board {board}: {moved} spaces moved, {changed} spaces have links other than the game's")

    # ---- paths ---------------------------------------------------------------------------------------------------------
    pieces = path_pieces(folder, board)
    if not pieces:
        sys.exit(f"board {board}: no path pieces found")
    width, rep = measure(pieces)
    target = max(pieces, key=lambda k: pieces[k].geoms[k[1]].verts)
    tm = pieces[target]
    tg = tm.geoms[target[1]]
    template = igbmodel.vertex_bytes(tm, target[1])[:tg.stride]
    inv = igbmodel.inverse(tm.placement(target[1]))
    verts, idx = bytearray(), []

    def quad(corners, uvs):
        base = len(verts) // tg.stride
        for p, (u, v) in zip(corners, uvs):
            verts.extend(struct.pack("<6f", *igbmodel.apply(inv, p), 0.0, 1.0, 0.0) + template[0x18:0x1c]
                         + struct.pack("<2f", u, v) + template[0x24:])
        (ax, _, az), (bx, _, bz), (cx, _, cz) = corners[:3]
        tri = [0, 1, 2, 0, 2, 3] if (bx - ax) * (cz - az) - (cx - ax) * (bz - az) < 0 else [0, 2, 1, 0, 3, 2]
        idx.extend(base + k for k in tri)

    half = width / 2
    ground = Surface(folder, board, pieces) if not painted else None
    hidden = {tuple(sorted(l)) for l in w.get("no_path_links", [])}     # shown some other way, or not at all
    for a in sorted(links):
        for c in links[a]:
            if a > c or (a, c) in hidden:
                continue
            pa, pc = new[a], new[c]
            dx, dz = pc[0] - pa[0], pc[2] - pa[2]
            ln = math.hypot(dx, dz) or 1.0
            ux, uz = dx / ln, dz / ln                          # along the link; across is (uz, -ux)
            lift = 0.02 if abs(dx) > abs(dz) else 0.0          # where two paths cross at a space, one lies on the other
            # each path reaches half a width past both spaces, so corners and crossings are covered; it is cut into
            # STEP-long pieces that follow the ground (the game's paths bend over every bump of the floor)
            length = ln + width
            n = max(1, math.ceil(length / STEP))
            rows = []
            for k in range(n + 1):
                t = -half + length * k / n
                f = min(max(t / ln, 0.0), 1.0)
                x, z = pa[0] + ux * t, pa[2] + uz * t
                expect = pa[1] + (pc[1] - pa[1]) * f - PATH_DROP
                y = (ground.path_y(x, z, expect) if ground else expect) + lift
                rows.append(((x - uz * half, y, z + ux * half), (x + uz * half, y, z - ux * half), (t + half) / rep))
            for (l0, r0, v0), (l1, r1, v1) in zip(rows, rows[1:]):
                quad([l0, r0, r1, l1], [(0.0, v0), (1.0, v0), (1.0, v1), (0.0, v1)])
    replace: dict[str, dict] = {}
    if painted:
        grid = Grid.from_json(w["terrain"])
        replace, ground_log = cavekit.build(grid, w["terrain"]["kit"], folder, board)
        log += ground_log
    for (f, gi), m in pieces.items():
        g = m.geoms[gi]
        replace.setdefault(f, {})[gi] = (bytes(verts), idx) if (f, gi) == target else             (igbmodel.vertex_bytes(m, gi)[:g.stride], [0, 0, 0])                    # hidden: one degenerate triangle
    for f, rep in sorted(replace.items()):
        (out / f"{f}.model").write_bytes(igbmodel.rebuild(igbmodel.load(folder / f"{f}.model"), rep))
    shown = sum(len(v) for v in links.values()) // 2 - len(hidden)
    log.append(f"paths: {shown} links drawn {width:.1f} wide into {target[0]} piece {target[1]} ({len(hidden)} links "
               f"without a strip); {len(pieces) - 1} other path pieces hidden. The dungeon's own art is not moved.")

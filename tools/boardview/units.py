"""Move board 0 buildings as units: the building, its shadow and any decor that belongs to it, all by the same offset.

The units are listed in board0_buildings.json. Every part is picked in the ORIGINAL model files and written as original
position + offset, so moving several units that share a mesh (Anim2 mesh 6 holds most shadows) cannot pick or shift the
wrong vertices, and an offset of 0 restores the original bytes.

    art = Art(assets)
    art.move(units[2], (dx, dy, dz))
    art.save(mod / "Assets")          # writes only the model files that changed
"""
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
import igbmodel

TABLE = Path(__file__).with_name("board0_buildings.json")
LIFT = 0.8                 # how much further back (+z) the board camera shows a point per unit it floats above the ground


def load_units(path: Path = TABLE) -> dict[int, dict]:
    """The movable units, keyed by space id."""
    return {int(k): v for k, v in json.loads(path.read_text())["units"].items()}


def clusters(pos, tris, weld: bool) -> list[list[int]]:
    """Vertex sets connected through triangles; with weld, vertices that share a position are joined too."""
    parent = list(range(len(pos)))

    def root(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    if weld:
        seen: dict[tuple, int] = {}
        for i, p in enumerate(pos):
            parent[root(i)] = root(seen.setdefault((round(p[0], 1), round(p[1], 1), round(p[2], 1)), i))
    for t in tris:
        for v in t[1:]:
            parent[root(v)] = root(t[0])
    groups: dict[int, list[int]] = {}
    for i in range(len(pos)):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def centre(pos, vs) -> tuple[float, float]:
    xs, zs = [pos[i][0] for i in vs], [pos[i][2] for i in vs]
    return (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2


class Art:
    def __init__(self, assets: Path):
        self.folder = assets / "CommonData" / "dataField" / "F00"
        self.models: dict[str, igbmodel.Model] = {}
        self.data: dict[str, bytearray] = {}
        self.taken: dict[tuple, str] = {}            # (model, mesh or "mtrx", index) -> the unit that moved it, to catch overlaps
        self.textures: dict[tuple, object] = {}

    def model(self, name: str) -> igbmodel.Model:
        if name not in self.models:
            self.models[name] = igbmodel.load(self.folder / f"F00_{name}.model")
            self.data[name] = bytearray(self.models[name].data)
        return self.models[name]

    def pick(self, part: dict) -> tuple[str, int, list[int]]:
        """(model, mesh, vertex indices) of a cluster or area part, chosen in the original file."""
        name, gi = part.get("cluster") or part["area"]
        m = self.model(name)
        pos, tris = igbmodel.mesh(m, m.geoms[gi])
        cx, cz = part["centre"]

        def dist(vs):
            x, z = centre(pos, vs)
            return ((x - cx) ** 2 + (z - cz) ** 2) ** 0.5

        if "cluster" in part:
            vs = min(clusters(pos, tris, weld=False), key=dist)
            if "vertices" in part and len(vs) != part["vertices"]:
                raise ValueError(f"F00_{name} mesh {gi}: the cluster nearest {part['centre']} has {len(vs)} vertices, the table says {part['vertices']}")
        else:
            vs = sorted(i for c in clusters(pos, tris, weld=True) if dist(c) <= part["radius"] for i in c)
            if not vs:
                raise ValueError(f"F00_{name} mesh {gi}: nothing within {part['radius']} of {part['centre']}")
        return name, gi, vs

    def move(self, unit: dict, offset: tuple[float, float, float], label: str = "") -> list[str]:
        """Shift every part of the unit by offset from its original position; returns a line per part. A part's "adjust"
        (x, y, z) is added when the unit leaves home (a shadow that sits off its building where scenery hides it)."""
        out = []
        for part in unit["parts"]:
            shift = tuple(offset[k] + (part.get("adjust", (0, 0, 0))[k] if any(offset) else 0) for k in range(3))
            if "matrix" in part:
                name, i = part["matrix"]
                m = self.model(name)
                o = m.chunk("MTRX")[0] + 64 * i + 48          # the last row of the matrix is the translation
                self.claim((name, "mtrx", i), label)
                t = struct.unpack_from("<3f", m.data, o)
                struct.pack_into("<3f", self.data[name], o, *(t[k] + shift[k] for k in range(3)))
                out.append(f"{part['role']}: F00_{name} matrix {i}")
            else:
                name, gi, vs = self.pick(part)
                m = self.model(name)
                g = m.geoms[gi]
                inv = igbmodel.inverse(m.placement(gi))        # a piece placed by a matrix moves by the offset in its own units
                o0, o1 = igbmodel.apply(inv, (0, 0, 0)), igbmodel.apply(inv, shift)
                local = tuple(o1[k] - o0[k] for k in range(3))
                base = m.chunk("VERT")[0] + g.vert_offset
                for v in vs:
                    self.claim((name, gi, v), label)
                    o = base + v * g.stride
                    p = struct.unpack_from("<3f", m.data, o)
                    struct.pack_into("<3f", self.data[name], o, *(p[k] + local[k] for k in range(3)))
                igbmodel.fit_bbox(m, self.data[name], gi)       # the piece's box must still hold the moved vertices
                out.append(f"{part['role']}: F00_{name} mesh {gi}, {len(vs)} vertices")
        return out

    # ---- shadows ----------------------------------------------------------------------------------------------------------
    def anchor(self, unit: dict, offset: tuple[float, float, float]) -> tuple[float, float]:
        """Where the unit's building stands now, (x, z): its matrix translation, or the centre of its vertices."""
        part = next(p for p in unit["parts"] if p["role"] == "building")
        if "matrix" in part:
            name, i = part["matrix"]
            o = self.model(name).chunk("MTRX")[0] + 64 * i + 48
            t = struct.unpack_from("<3f", self.data[name], o)
            return t[0], t[2]
        return part["centre"][0] + offset[0], part["centre"][1] + offset[2]

    def drawn(self, name: str, m: igbmodel.Model, gi: int, keep=None, step: float = 2.0):
        """(x, z, y, triangle) board points every `step` units where piece gi of model m is drawn (texture alpha above a
        quarter); keep: a test on a triangle's vertex indices, to sample only some of the piece."""
        ti = m.mesh_nodes()[gi]["texture"]
        if ti < 0:
            return
        if (name, ti) not in self.textures:
            self.textures[(name, ti)] = igbmodel.decode_texture(m, m.textures[ti])
        tex, g, M, vo = self.textures[(name, ti)], m.geoms[gi], m.placement(gi), m.chunk("VERT")[0]
        pos, tris = igbmodel.mesh(m, g)
        uvs = [struct.unpack_from("<2f", m.data, vo + g.vert_offset + g.stride * i + 0x1c) for i in range(g.verts)]
        for k, t in enumerate(tris):
            if keep is not None and not keep(t):
                continue
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = (igbmodel.apply(M, pos[i]) for i in t)
            den = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(den) < 1e-9:
                continue
            x = math.floor(min(ax, bx, cx) / step) * step
            while x <= max(ax, bx, cx):
                z = math.floor(min(az, bz, cz) / step) * step
                while z <= max(az, bz, cz):
                    l0 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / den
                    l1 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / den
                    l2 = 1 - l0 - l1
                    if min(l0, l1, l2) >= 0:
                        u = l0 * uvs[t[0]][0] + l1 * uvs[t[1]][0] + l2 * uvs[t[2]][0]
                        v = l0 * uvs[t[0]][1] + l1 * uvs[t[1]][1] + l2 * uvs[t[2]][1]
                        if tex.getpixel((int(u % 1 * tex.width) % tex.width, int(v % 1 * tex.height) % tex.height))[3] > 64:
                            yield x, z, l0 * ay + l1 * by + l2 * cy, k
                    z += step
                x += step

    def shadow_pieces(self, part: dict) -> tuple[str, igbmodel.Model, list]:
        """(model name, the model as moved, [(piece, keep test)]) of a shadow part."""
        name = (part.get("matrix") or part.get("cluster") or part["area"])[0]
        m = igbmodel.load(self.folder / f"F00_{name}.model", self.data[name] if name in self.data else None)
        if "matrix" in part:
            return name, m, [(gi, None) for gi, nd in enumerate(m.mesh_nodes()) if nd["matrix"] == part["matrix"][1]]
        _, gi, vs = self.pick(part)
        vs = set(vs)
        return name, m, [(gi, lambda t: all(i in vs for i in t))]

    def shadow_points(self, part: dict, step: float = 2.0) -> list[tuple[float, float, float]]:
        """Board (x, z, y) points, every `step` units, where a shadow part is drawn, as moved."""
        name, m, pieces = self.shadow_pieces(part)
        return [(x, z, y) for gi, keep in pieces for x, z, y, _ in self.drawn(name, m, gi, keep, step)]

    def decals(self, current: bool = True) -> dict[tuple[int, int], set]:
        """Where the flat decals of the road_shadow layer are drawn (building and tree shadows, green pools, the pale glow of
        sand dunes), as {2-unit cell: {(model, piece, triangle)}}; current: with the moves made so far, else as shipped."""
        out: dict[tuple[int, int], set] = {}
        for name in ("A", "M", "N", "Anim1", "Anim2"):
            self.model(name)
            m = igbmodel.load(self.folder / f"F00_{name}.model", self.data[name] if current else None)
            for gi, nd in enumerate(m.mesh_nodes()):
                if nd["name"] == "road_shadow":
                    for x, z, _, k in self.drawn(name, m, gi):
                        out.setdefault((int(x // 2), int(z // 2)), set()).add((name, gi, k))
        return out

    def shadow_keys(self, part: dict) -> set:
        """The (model, piece, triangle) keys of a shadow part's own triangles, so it is not counted as covering itself."""
        name, m, pieces = self.shadow_pieces(part)
        keys = set()
        for gi, keep in pieces:
            for k, t in enumerate(igbmodel.mesh(m, m.geoms[gi])[1]):
                if keep is None or keep(t):
                    keys.add((name, gi, k))
        return keys

    def fit_shadows(self, unit: dict, offset: tuple[float, float, float], roads, mask=None, decals=None, home_decals=None,
                    sizes: tuple[float, ...] = (1.0, 0.95, 0.9), allowed: int = 2) -> list[str]:
        """Keep each moved shadow of the unit at the first of `sizes` (scaled towards the building, x and z only) where no more
        of its drawn points are bad than at home (and at most `allowed` if none were); a shadow that fits at none of them is
        dropped (squashed flat): the user found a missing shadow less jarring than a broken one, and a shadow shrunk further
        loses its front under the building. Returns a line per shadow that was shrunk or dropped.

        A point is bad where the camera sees it on a road or a space's disc (roads.road_mask), over another kind of ground
        than the building stands on (roads.ground_kind), or over another decal of the road_shadow layer (decals: a dune's
        glow cuts a hard-edged patch out of it). Seen in game: castle 260's shadow at space 268 reached the space behind,
        was cut off by the grass beside it and by a dune's glow; castle 123's at space 122 hung over the beach. Shadows
        float a few units above the ground, and the tilted camera shows a floating point LIFT * height further back (+z)."""
        mask = mask or roads.road_mask()
        decals = decals if decals is not None else self.decals(True)
        home_decals = home_decals if home_decals is not None else self.decals(False)
        ax, az = self.anchor(unit, offset)
        same = lambda k, floor: k == floor or {k, floor} <= {"snow", "water"}      # ice reads as both
        floor, home_floor = roads.ground_kind(ax, az), roads.ground_kind(ax - offset[0], az - offset[2])

        def bad(x, z, y, floor_kind, cells, own):
            ground = roads.ground_y(x, z)
            seen_z = z + LIFT * max(0.0, y - ground) if ground is not None else z
            return (mask(x, seen_z) or not same(roads.ground_kind(x, z), floor_kind)
                    or bool(cells.get((int(x // 2), int(z // 2)), set()) - own))

        out = []
        for part in unit["parts"]:
            if part["role"] != "shadow":
                continue
            pts, own = self.shadow_points(part), self.shadow_keys(part)
            limit = max(allowed, sum(bad(x - offset[0], z - offset[2], y - offset[1], home_floor, home_decals, own)
                                     for x, z, y in pts))
            count = lambda f: sum(bad(ax + f * (x - ax), az + f * (z - az), y, floor, decals, own) for x, z, y in pts)
            label = f"shadow {part.get('matrix') or part.get('cluster') or part['area']}"
            fits = next((f for f in sizes if count(f) <= limit), None)
            if fits is None:
                self.scale(part, (ax, az), 0.0)
                out.append(f"{label} dropped ({count(sizes[-1])} points off at {sizes[-1]:.2f}, {limit} at home)")
            elif fits < 1.0:
                self.scale(part, (ax, az), fits)
                out.append(f"{label} scaled {fits:.2f}")
        return out

    def scale(self, part: dict, anchor: tuple[float, float], f: float) -> None:
        """Scale a (moved) part by f in x and z about anchor."""
        ax, az = anchor
        if "matrix" in part:
            name, i = part["matrix"]
            o = self.model(name).chunk("MTRX")[0] + 64 * i
            M = struct.unpack_from("<16f", self.data[name], o)
            S = (f, 0, 0, 0, 0, 1, 0, 0, 0, 0, f, 0, ax * (1 - f), 0, az * (1 - f), 1)
            struct.pack_into("<16f", self.data[name], o, *igbmodel.multiply(M, S))
            return
        name, gi, vs = self.pick(part)
        m = self.model(name)
        g = m.geoms[gi]
        assert m.placement(gi) is None, "scaling a cluster inside a placed piece is not supported"
        base = m.chunk("VERT")[0] + g.vert_offset
        for v in vs:
            o = base + v * g.stride
            x, y, z = struct.unpack_from("<3f", self.data[name], o)
            struct.pack_into("<3f", self.data[name], o, ax + f * (x - ax), y, az + f * (z - az))
        igbmodel.fit_bbox(m, self.data[name], gi)

    def claim(self, key: tuple, label: str) -> None:
        if key in self.taken and self.taken[key] != label:
            raise ValueError(f"{key} belongs to both {self.taken[key]} and {label}")
        self.taken[key] = label

    def save(self, out: Path) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        written = []
        for name, data in self.data.items():
            if bytes(data) != self.models[name].data:
                path = out / f"F00_{name}.model"
                path.write_bytes(data)
                written.append(path)
        return written

"""Read-only reader for the .model files in CommonData/dataField (Alchemy IGB files with the string table split out).

Layout, as far as it is decoded (file is little-endian):
  'MDL ' u32(8)
  'NAME' u32 size, then null-terminated names (node, material and texture names)
  u32 0, 'IMG ' u32 size, then the textures back to back, each a PVR3 file (ETC2 RGB = format 22, ETC2 RGBA = format 23)
  an index of (u32, u32) pairs, then tagged chunks, each 'TAG ' u32 size + payload:
    VERT  vertex data, several vertex layouts back to back
    INDX  u16 triangle-list indices
    DECL  vertex declarations
    GEOM  one 32-byte record per mesh piece: [decl offset, stride, vertex count, byte offset into VERT,
                                              index count, byte offset into INDX, -1, -1]
    UNIF  shader uniforms,  MTRX  4x4 float matrices (placement),  CHLD  child lists
    MATR  28-byte materials: [shader name, texture name, -1, -1, -1, 4, uniform offset]   (names are byte offsets into NAME)
    NOD2  the scene tree, 13 words per node (node 0 is the root): [MTRX offset or -1, child count, bbox min xyz, bbox max xyz,
          byte offset of its children in CHLD, MATR offset or -1, GEOM offset or -1, flags, name or -1]. Flags: the low
          bit marks a mesh node; the dungeon boards set higher bits too (0x10001, 0x40001, 0x50001), meaning not known.
          CHLD holds the children as u16 node indices. A piece's place on the board is the product of the matrices on its path
          to the root: many terrain, road and building pieces are stored in their own coordinates (some near the origin, some
          far off the board), and some groups shift their children back by the opposite amount.
    TERM  end of file
  The textures are listed in a 'TEXT' table that closes the IMG block: [name, size, offset in IMG] per texture.
Every size field counts its own 8-byte header. Positions are three floats at the start of every vertex (checked on the 44 and
36 byte layouts of the field maps); the first uv pair is at byte 0x1c. Matrices are row-vector 4x4: world = [x y z 1] @ M, the
translation in the last row; the bbox is in the piece's own coordinates.
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path

PVR_FORMATS = {22: "ETC2_RGB", 23: "ETC2_RGBA"}


@dataclass
class Texture:
    offset: int
    size: int
    fmt: int
    width: int
    height: int
    mips: int


@dataclass
class Geom:
    decl: int
    stride: int
    verts: int
    vert_offset: int
    indices: int
    index_offset: int


@dataclass
class Model:
    path: Path
    data: bytes
    names: list[str]
    textures: list[Texture] = field(default_factory=list)
    chunks: dict[str, list[tuple[int, int]]] = field(default_factory=dict)   # tag -> [(payload offset, size)]
    geoms: list[Geom] = field(default_factory=list)

    def chunk(self, tag: str) -> tuple[int, int]:
        return self.chunks[tag][0]

    def matrices(self) -> list[tuple[float, ...]]:
        if "MTRX" not in self.chunks:                  # some dungeon files place nothing by matrix and have no MTRX chunk
            return []
        o, n = self.chunk("MTRX")
        return [struct.unpack_from("<16f", self.data, o + 64 * i) for i in range(n // 64)]

    def name_at(self, offset: int) -> str:
        """A string of the NAME block by its byte offset (how MATR, TEXT and NOD2 refer to names)."""
        blob = self.data[16:16 + struct.unpack_from("<I", self.data, 12)[0]]
        return blob[offset:blob.index(b"\0", offset)].decode("latin-1")

    def materials(self) -> list[tuple[str, int]]:
        """(shader name, texture index) per MATR record."""
        o, n = self.chunk("TEXT")
        tex = {struct.unpack_from("<I", self.data, o + 12 * i)[0]: i for i in range(n // 12)}
        o, n = self.chunk("MATR")
        out = []
        for i in range(n // 28):
            shader, texture = struct.unpack_from("<2I", self.data, o + 28 * i)
            out.append((self.name_at(shader), tex.get(texture, -1)))
        return out

    def tree(self) -> tuple[list[tuple], list[int]]:
        """The NOD2 records as tuples of 13 signed words, and each node's parent (-1 for the root)."""
        o, n = self.chunk("NOD2")
        w = struct.unpack_from(f"<{n // 4}i", self.data, o)
        recs = [w[13 * i: 13 * i + 13] for i in range(n // 52)]
        co, _ = self.chunk("CHLD")
        parent = [-1] * len(recs)
        for i, r in enumerate(recs):
            for c in struct.unpack_from(f"<{r[1]}H", self.data, co + r[8]) if r[1] > 0 else ():
                parent[c] = i
        return recs, parent

    def mesh_nodes(self) -> list[dict]:
        """Per mesh piece: its node name, material index, texture index, bounding box (own coordinates), the index of its own
        matrix (None if it has none) and its node index, from the NOD2 chunk."""
        o, _ = self.chunk("NOD2")
        recs, _ = self.tree()
        mats, out = self.materials(), {}
        for i, r in enumerate(recs):
            if r[10] < 0 or not r[11] & 1:
                continue
            mi = r[9] // 28
            out[r[10] // 32] = {"name": self.name_at(r[12]), "material": mi, "texture": mats[mi][1] if mi >= 0 else -1,
                                "bbox": struct.unpack_from("<6f", self.data, o + 52 * i + 8), "bbox_offset": o + 52 * i + 8,
                                "matrix": r[0] // 64 if r[0] >= 0 else None, "node": i, "flags": r[11]}
        return [out[gi] for gi in range(len(self.geoms))]

    def placement(self, gi: int) -> tuple[float, ...] | None:
        """The matrix that takes piece gi's vertices to board coordinates (its own and all its parents'), None if there is none."""
        recs, parent = self.tree()
        mats, total, i = self.matrices(), None, self.mesh_nodes()[gi]["node"]
        while i >= 0:
            if recs[i][0] >= 0:
                M = mats[recs[i][0] // 64]
                total = M if total is None else multiply(total, M)
            i = parent[i]
        return total


def _mip_bytes(fmt: int, w: int, h: int) -> int:
    block = 8 if fmt == 22 else 16
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block


def load(path: str | Path, data: bytes | None = None) -> Model:
    """Parse a model file (from `data` if given: an edited copy of the file at `path`)."""
    d = bytes(data) if data is not None else Path(path).read_bytes()
    if d[:4] != b"MDL " or d[8:12] != b"NAME":
        raise ValueError(f"{path}: not a field .model file")
    name_size = struct.unpack_from("<I", d, 12)[0]
    names = [n.decode("latin-1") for n in d[16:16 + name_size].split(b"\0") if n]
    m = Model(Path(path), d, names)

    p = 16 + name_size + 4
    if d[p:p + 4] != b"IMG ":
        raise ValueError(f"{path}: no IMG block at {p:#x}")
    img_size = struct.unpack_from("<I", d, p + 4)[0]
    q, img_end = p + 8, p + 8 + img_size
    while q < img_end and d[q:q + 4] == b"PVR\x03":
        _, _, fmt, _, _, h, w, _, _, _, mips, meta = struct.unpack_from("<IIQIIIIIIIII", d, q)
        size = 52 + meta + sum(_mip_bytes(fmt, max(1, w >> i), max(1, h >> i)) for i in range(mips))
        m.textures.append(Texture(q, size, fmt, w, h, mips))
        q += size
    if q != p + img_size:              # the size counts the IMG header, so the textures fill the block exactly
        raise ValueError(f"{path}: textures end at {q:#x}, IMG block at {p + img_size:#x}")

    q = p + img_size                                   # the chunks follow one another; each size counts its 8-byte header
    while q + 8 <= len(d):
        tag, size = d[q:q + 4].decode("latin-1"), struct.unpack_from("<I", d, q + 4)[0]
        m.chunks.setdefault(tag, []).append((q + 8, size - 8))
        if tag == "TERM" or size < 8:
            break
        q += size
    o, n = m.chunk("GEOM")
    for i in range(n // 32):
        w = struct.unpack_from("<8I", d, o + 32 * i)
        m.geoms.append(Geom(w[0], w[1], w[2], w[3], w[4], w[5]))
    return m


def decode_texture(m: Model, t: Texture):
    """Return a PIL RGBA image of the top mip level (needs the texture2ddecoder package)."""
    import texture2ddecoder
    from PIL import Image
    body = m.data[t.offset + 52: t.offset + t.size]
    top = _mip_bytes(t.fmt, t.width, t.height)
    raw = (texture2ddecoder.decode_etc2a8 if t.fmt == 23 else texture2ddecoder.decode_etc2)(body[:top], t.width, t.height)
    return Image.frombuffer("RGBA", (t.width, t.height), raw, "raw", "BGRA", 0, 1)


def mesh(m: Model, g: Geom):
    """(positions, triangles) of one mesh piece; indices are relative to the piece's first vertex."""
    vo, _ = m.chunk("VERT")
    io, _ = m.chunk("INDX")
    pos = [struct.unpack_from("<3f", m.data, vo + g.vert_offset + g.stride * i) for i in range(g.verts)]
    idx = struct.unpack_from(f"<{g.indices}H", m.data, io + g.index_offset)
    return pos, [idx[i:i + 3] for i in range(0, len(idx) - 2, 3)]


def apply(M: tuple[float, ...] | None, p) -> tuple[float, float, float]:
    """A point through a placement matrix (row vectors); None leaves it as it is."""
    if M is None:
        return tuple(p)
    x, y, z = p
    return tuple(x * M[c] + y * M[4 + c] + z * M[8 + c] + M[12 + c] for c in range(3))


def multiply(A: tuple[float, ...], B: tuple[float, ...]) -> tuple[float, ...]:
    """A then B, for row vectors: p @ A @ B."""
    return tuple(sum(A[4 * r + k] * B[4 * k + c] for k in range(4)) for r in range(4) for c in range(4))


def inverse(M: tuple[float, ...] | None) -> tuple[float, ...] | None:
    """The inverse of an affine placement matrix (so board coordinates can be written back into a placed piece)."""
    if M is None:
        return None
    a = [[M[4 * r + c] for c in range(3)] for r in range(3)]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    inv = [[(a[(c + 1) % 3][(r + 1) % 3] * a[(c + 2) % 3][(r + 2) % 3] - a[(c + 1) % 3][(r + 2) % 3] * a[(c + 2) % 3][(r + 1) % 3]) / det
            for c in range(3)] for r in range(3)]
    t = [-sum(M[12 + k] * inv[k][c] for k in range(3)) for c in range(3)]
    return (*inv[0], 0.0, *inv[1], 0.0, *inv[2], 0.0, *t, 1.0)


def vertex_bytes(m: Model, gi: int) -> bytes:
    g = m.geoms[gi]
    vo, _ = m.chunk("VERT")
    return bytes(m.data[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts])


def fit_bbox(m: Model, data: bytearray, gi: int) -> None:
    """Refit the NOD2 bounding box of piece gi to its vertices in `data` (a same-layout copy of the file with moved vertices);
    the box is what the game can cull the piece by, so a vertex moved outside it could vanish from some views."""
    g = m.geoms[gi]
    vo = m.chunk("VERT")[0] + g.vert_offset
    pos = [struct.unpack_from("<3f", data, vo + g.stride * i) for i in range(g.verts)]
    struct.pack_into("<6f", data, m.mesh_nodes()[gi]["bbox_offset"],
                     *[min(p[k] for p in pos) for k in range(3)], *[max(p[k] for p in pos) for k in range(3)])


def rebuild(m: Model, replace: dict[int, tuple[bytes, list[int]]], data: bytes | None = None) -> bytes:
    """The file with the vertices and indices of some mesh pieces replaced (any size): {piece: (vertex bytes, indices)}.

    VERT and INDX are repacked piece by piece (INDX padded to 4 bytes with 0xFF, as the game's files are), the GEOM records get the new
    counts and offsets, and the NOD2 bounding box of every replaced piece is recomputed. Everything else is copied, from `data`
    if given (a copy of the file that already has other edits, such as moved matrices) or else from the loaded file.
    """
    d = bytearray(data if data is not None else m.data)
    nodes = m.mesh_nodes()
    verts, idx = bytearray(), bytearray()
    geom_o, _ = m.chunk("GEOM")
    vo, _ = m.chunk("VERT")
    io, _ = m.chunk("INDX")
    for gi, g in enumerate(m.geoms):
        if gi in replace:
            vb, ib = replace[gi]
            n = len(vb) // g.stride
            assert len(vb) == n * g.stride and len(ib) % 3 == 0 and (not ib or max(ib) < min(n, 0x10000))
            pos = [struct.unpack_from("<3f", vb, g.stride * i) for i in range(n)]
            if pos:
                lo, hi = [min(p[k] for p in pos) for k in range(3)], [max(p[k] for p in pos) for k in range(3)]
                struct.pack_into("<6f", d, nodes[gi]["bbox_offset"], *lo, *hi)
            ib = struct.pack(f"<{len(ib)}H", *ib)
        else:
            vb = d[vo + g.vert_offset: vo + g.vert_offset + g.stride * g.verts]
            ib = d[io + g.index_offset: io + g.index_offset + 2 * g.indices]
        struct.pack_into("<4I", d, geom_o + 32 * gi + 8, len(vb) // g.stride, len(verts), len(ib) // 2, len(idx))
        verts += vb
        idx += ib
    idx += b"\xff" * (-len(idx) % 4)
    head, tail = d[:vo - 8], d[io + m.chunk("INDX")[1]:]
    return bytes(head + b"VERT" + struct.pack("<I", len(verts) + 8) + verts + b"INDX" + struct.pack("<I", len(idx) + 8) + idx + tail)


def export_obj(m: Model, path: str | Path) -> int:
    """Write every piece as an OBJ object (no uvs or materials); returns the vertex count."""
    base, lines = 1, []
    for k, g in enumerate(m.geoms):
        pos, tris = mesh(m, g)
        lines.append(f"o piece{k}")
        lines += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in pos]
        lines += [f"f {a + base} {b + base} {c + base}" for a, b, c in tris]
        base += len(pos)
    Path(path).write_text("\n".join(lines) + "\n")
    return base - 1


if __name__ == "__main__":
    import sys
    mod = load(sys.argv[1])
    print(f"{len(mod.names)} names, {len(mod.textures)} textures, chunks {[(k, len(v)) for k, v in mod.chunks.items()]}, "
          f"{len(mod.geoms)} mesh pieces, {len(mod.matrices())} matrices")
    for t in mod.textures:
        print(f"  texture {PVR_FORMATS.get(t.fmt, t.fmt)} {t.width}x{t.height} mips {t.mips} at {t.offset:#x}")

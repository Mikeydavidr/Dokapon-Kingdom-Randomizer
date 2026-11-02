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
    UNIF  shader uniforms,  MATR  material table,  MTRX  4x4 float matrices (placement),  CHLD  child lists
Positions are three floats at the start of every vertex (checked on the 44 and 36 byte layouts of the field maps).
"""
import re
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
        o, n = self.chunk("MTRX")
        return [struct.unpack_from("<16f", self.data, o + 64 * i) for i in range(n // 64)]


def _mip_bytes(fmt: int, w: int, h: int) -> int:
    block = 8 if fmt == 22 else 16
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block


def load(path: str | Path) -> Model:
    d = Path(path).read_bytes()
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
    if not 0 <= img_end - q <= 8:      # the block's size covers 8 bytes past the last texture (a trailer, not decoded)
        raise ValueError(f"{path}: textures end at {q:#x}, IMG block at {img_end:#x}")

    for tag in (b"VERT", b"INDX", b"DECL", b"GEOM", b"UNIF", b"MATR", b"MTRX", b"CHLD"):
        for mt in re.finditer(tag, d[img_end:]):
            pos = img_end + mt.start()
            size = struct.unpack_from("<I", d, pos + 4)[0]
            if pos + 8 + size <= len(d):
                m.chunks.setdefault(tag.decode(), []).append((pos + 8, size))
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

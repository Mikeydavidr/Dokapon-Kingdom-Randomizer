"""Render board art from above, textured, to check edits to the board models without starting the game.

usage: python render_top.py <out.png> [--board N] [--dir <folder with F00_*.model files>] [--scale S] [--box x0,z0,x1,z1]
       [--files A,M,...] [--spaces] [--only name,name]
Draws every mesh piece, through the matrix that places it, with its texture, vertex colour and alpha, lowest triangles first. The picture is turned 180 degrees like the numbered board map (+x left, +z up).
--board: which board (default 0; the dungeons are 1-22, their art in dataField/F01..F22); --files: which of its model files
(default: board 0's six, every file of any other board); --box: default the board's spaces with a margin;
--dir: models to draw (missing files come from the extracted assets); --spaces: dots and numbers for the spaces;
--only: draw only pieces whose node name is listed (e.g. road_01).
"""
import argparse
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import igbmodel

ASSETS = Path("G:/Programming/Dokapon-Workspace/assets")
F00 = ASSETS / "CommonData" / "dataField" / "F00"
FILES = ["Anim1", "A", "N", "M", "Anim2", "wood"]
TALL = 60.0                                             # the highest ground a tilted picture leaves room for


def triangles(path: Path, only: set[str] | None):
    """Yield (xz positions 3x2, y mean, uv 3x2, colour 3x4, texture array, y per corner) per triangle, in board coordinates."""
    m = igbmodel.load(path)
    textures = [np.asarray(igbmodel.decode_texture(m, t), dtype=np.float32) / 255 for t in m.textures]
    vo, _ = m.chunk("VERT")
    nodes = m.mesh_nodes()
    for gi, nd in enumerate(nodes):
        if only and nd["name"] not in only:
            continue
        g = m.geoms[gi]
        tex = textures[nd["texture"]] if nd["texture"] >= 0 else None
        raw = np.frombuffer(m.data, dtype=np.uint8, count=g.stride * g.verts, offset=vo + g.vert_offset).reshape(g.verts, g.stride)
        pos = raw[:, :12].copy().view("<f4").reshape(-1, 3).astype(np.float64)
        M = m.placement(gi)
        if M is not None:                               # placed by matrices: into board coordinates
            pos = (np.c_[pos, np.ones(len(pos))] @ np.array(M).reshape(4, 4))[:, :3]
        col = raw[:, 0x18:0x1c].astype(np.float32) / 255
        uv = raw[:, 0x1c:0x24].copy().view("<f4").reshape(-1, 2)
        _, tris = igbmodel.mesh(m, g)
        for t in tris:
            t = list(t)
            yield pos[t][:, [0, 2]], pos[t][:, 1].mean(), uv[t], col[t], tex, pos[t][:, 1]


def board_files(board: int) -> list[str]:
    """The model files of a board, by the part of their name after 'F##_' (board 0: drawn sea first, as FILES)."""
    if board == 0:
        return FILES
    folder = ASSETS / "CommonData" / "dataField" / f"F{board:02d}"
    return [p.stem.split("_", 1)[1] for p in sorted(folder.glob(f"F{board:02d}_*.model"))]


def board_box(board: int, margin: float = 80.0) -> tuple[float, float, float, float]:
    from boardlib import load_board
    pos = [s["pos"] for s in load_board(ASSETS, board)[0] if s["pos"]]
    return (min(p[0] for p in pos) - margin, min(p[2] for p in pos) - margin, max(p[0] for p in pos) + margin,
            max(p[2] for p in pos) + margin)


def render(out: Path, folder: Path | None, scale: float, box, files, spaces: bool, only, board: int = 0,
           tilt: float | None = None) -> None:
    """tilt: look down at this many degrees from the horizon (towards +z, as the game's camera does) instead of straight
    down, so heights show; drawn far to near."""
    x0, z0, x1, z1 = box
    prefix = f"F{board:02d}"
    home = ASSETS / "CommonData" / "dataField" / prefix
    sin, cos = (math.sin(math.radians(tilt)), math.cos(math.radians(tilt))) if tilt else (1.0, 0.0)
    top = z1 * sin + TALL * cos
    W, H = int((x1 - x0) * scale), int((top - (z0 * sin - 10 * cos)) * scale)
    canvas = np.zeros((H, W, 3), np.float32)
    canvas[:] = (0.12, 0.25, 0.45)                      # sea
    tris = []
    for f in files:
        name = f"{prefix}_{f}.model"
        path = folder / name if folder and (folder / name).exists() else home / name
        try:
            tris += list(triangles(path, only))
        except (ValueError, KeyError) as e:                # a file the reader cannot read yet (e.g. one with no textures)
            print(f"skipped {name}: {e}")
    if tilt:
        tris.sort(key=lambda t: (t[1] > 3.81, -(t[0][:, 1].mean() * cos - t[1] * sin)))   # the sea plane first
    else:
        tris.sort(key=lambda t: t[1])
    for xz, _, uv, col, tex, ys in tris:
        # 180 degrees: +x left, +z up (and, tilted, higher ground further up the picture)
        px = np.stack([(x1 - xz[:, 0]) * scale, (top - (xz[:, 1] * sin + ys * cos)) * scale], 1)
        lo, hi = np.floor(px.min(0)).astype(int), np.ceil(px.max(0)).astype(int)
        lo, hi = np.maximum(lo, 0), np.minimum(hi, [W - 1, H - 1])
        if (hi < lo).any():
            continue
        ys, xs = np.mgrid[lo[1]:hi[1] + 1, lo[0]:hi[0] + 1]
        p = np.stack([xs + 0.5, ys + 0.5], -1).reshape(-1, 2)
        a, b, c = px
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        l0 = ((b[1] - c[1]) * (p[:, 0] - c[0]) + (c[0] - b[0]) * (p[:, 1] - c[1])) / den
        l1 = ((c[1] - a[1]) * (p[:, 0] - c[0]) + (a[0] - c[0]) * (p[:, 1] - c[1])) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not inside.any():
            continue
        w = np.stack([l0, l1, l2], 1)[inside]
        u = w @ uv
        cl = w @ col
        if tex is not None:
            th, tw = tex.shape[:2]
            tx = ((u[:, 0] % 1) * tw).astype(int) % tw
            ty = ((u[:, 1] % 1) * th).astype(int) % th
            texel = tex[ty, tx]
        else:
            texel = np.ones((len(u), 4), np.float32)
        rgb, alpha = texel[:, :3] * cl[:, :3], texel[:, 3] * cl[:, 3]
        yy, xx = p[inside, 1].astype(int), p[inside, 0].astype(int)
        canvas[yy, xx] = canvas[yy, xx] * (1 - alpha[:, None]) + rgb * alpha[:, None]
    img = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8))
    if spaces:
        from boardlib import load_board
        sp, _ = load_board(ASSETS, board)
        d = ImageDraw.Draw(img)
        for s in sp:
            if not s["pos"]:
                continue
            x, z = (x1 - s["pos"][0]) * scale, (top - (s["pos"][2] * sin + s["pos"][1] * cos)) * scale
            d.ellipse([x - 3, z - 3, x + 3, z + 3], outline=(255, 0, 0))
            d.text((x + 4, z - 12), str(s["id"]), fill=(255, 255, 255))
    img.save(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--dir", default=None)
    ap.add_argument("--scale", type=float, default=1.5)
    ap.add_argument("--board", type=int, default=0)
    ap.add_argument("--box", default=None)
    ap.add_argument("--files", default=None)
    ap.add_argument("--spaces", action="store_true")
    ap.add_argument("--only", default=None)
    ap.add_argument("--tilt", type=float, default=None)
    a = ap.parse_args()
    box = [float(v) for v in a.box.split(",")] if a.box else (board_box(a.board) if a.board else (-700, -720, 700, 480))
    render(Path(a.out), Path(a.dir) if a.dir else None, a.scale, box, a.files.split(",") if a.files else board_files(a.board),
           a.spaces, set(a.only.split(",")) if a.only else None, a.board, a.tilt)

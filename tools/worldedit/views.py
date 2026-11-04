"""Side-by-side comparison of the rebuilt board and the original through the game's tilted camera, at every space.

usage: python views.py <rebuilt Assets folder> <out folder> [--top N] [--tilt 50] [--dist 220] [--only 7,69,...] [--at x,z ...]
For each space (or the --only list, or --at points) renders the original and the rebuilt board with render3d from the same camera,
scores the pair (mean colour difference after a small blur, plus the share of strongly different pixels), and writes
  views.txt                   all views ranked worst first
  view_<space>.png            original | rebuilt | difference, for the worst N
  contact.png                 the worst N rebuilt views in one sheet
The renders are not the game's own (see render3d.py), so use the ranking to pick where to look, then check in game.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "igb"), str(HERE.parent / "boardview")]
import render3d
import render_top as rt


def score(a: np.ndarray, b: np.ndarray) -> tuple[float, float, np.ndarray]:
    blur = lambda x: np.asarray(Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)), np.float32) / 255
    d = np.abs(blur(a) - blur(b)).mean(2)
    return float(d.mean()), float((d > 0.2).mean()), d


def run(rebuilt: Path, out: Path, top: int = 20, tilt: float = 50, dist: float = 220, only=None, points=(), size=(640, 400),
        orig_folder: Path | None = None) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    cache = out.parent / "scene_cache"
    cache.mkdir(exist_ok=True)
    o = render3d.Scene.load(orig_folder, cache / "orig.pkl")
    n = render3d.Scene.load(rebuilt, out / "rebuilt.pkl")                # the rebuilt scene is per build
    from boardlib import load_board
    spaces = [s for s in load_board(rt.ASSETS, 0)[0] if s["pos"]]
    views = [(f"s{s['id']}", s["pos"][0], s["pos"][2]) for s in spaces if only is None or s["id"] in only]
    views += [(f"p{int(x)}_{int(z)}", x, z) for x, z in points]
    rows, kept = [], {}
    for name, x, z in views:
        tgt = (x, 8, z + 15)                                             # a little ahead of the space, as the game frames it
        a = o.render(tgt, tilt, dist, 45, size)
        b = n.render(tgt, tilt, dist, 45, size)
        mean, strong, d = score(a, b)
        rows.append({"view": name, "x": round(x), "z": round(z), "mean": mean, "strong": strong})
        kept[name] = (a, b, d)
    rows.sort(key=lambda r: -(r["mean"] + r["strong"]))
    lines = [f"{'view':>9} {'x,z':>12} {'mean':>6} {'strong':>7}"]
    lines += [f"{r['view']:>9} {r['x']:>5},{r['z']:>5} {r['mean']:6.3f} {r['strong']:7.3f}" for r in rows]
    lines.append(f"\nboard mean {np.mean([r['mean'] for r in rows]):.4f}, strong {np.mean([r['strong'] for r in rows]):.4f} over {len(rows)} views")
    (out / "views.txt").write_text("\n".join(lines))
    thumbs = []
    for r in rows[:top]:
        a, b, d = kept[r["view"]]
        dd = np.repeat(np.clip(d * 4, 0, 1)[..., None], 3, 2)
        sheet = np.concatenate([a, b, dd], 1)
        im = Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8))
        ImageDraw.Draw(im).text((4, 4), f"{r['view']}  original | rebuilt | difference", fill=(255, 255, 255))
        im.save(out / f"view_{r['view']}.png")
        t = Image.fromarray((np.clip(b, 0, 1) * 255).astype(np.uint8)).resize((size[0] // 2, size[1] // 2))
        ImageDraw.Draw(t).text((4, 4), r["view"], fill=(255, 255, 255))
        thumbs.append(t)
    if thumbs:
        cols = 4
        w, h = thumbs[0].size
        sheet = Image.new("RGB", (cols * w, ((len(thumbs) + cols - 1) // cols) * h))
        for k, t in enumerate(thumbs):
            sheet.paste(t, ((k % cols) * w, (k // cols) * h))
        sheet.save(out / "contact.png")
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("rebuilt")
    ap.add_argument("out")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--tilt", type=float, default=50)
    ap.add_argument("--dist", type=float, default=220)
    ap.add_argument("--only", default=None)
    ap.add_argument("--at", action="append", default=[])
    a = ap.parse_args()
    rows = run(Path(a.rebuilt), Path(a.out), a.top, a.tilt, a.dist, {int(v) for v in a.only.split(",")} if a.only else None,
               [tuple(float(v) for v in p.split(",")) for p in a.at])
    print((Path(a.out) / "views.txt").read_text().splitlines()[0])
    for r in rows[:15]:
        print(f"{r['view']:>9} {r['x']:>5},{r['z']:>5} {r['mean']:6.3f} {r['strong']:7.3f}")
    print("board mean %.4f strong %.4f over %d views" % (np.mean([r["mean"] for r in rows]), np.mean([r["strong"] for r in rows]), len(rows)))

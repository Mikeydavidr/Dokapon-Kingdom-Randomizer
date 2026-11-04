"""Compare a rebuilt board with the original, programmatically.

usage: python compare.py <rebuilt Assets folder> <out folder> [--scale S] [--tile T] [--tilt DEG] [--top N] [--box x0,z0,x1,z1]

Renders the original board and the rebuilt one with tools/igb/render_top.py (same box, same view), blurs both a little so
single-texel noise does not count, and scores every T x T world-unit tile by its mean colour difference. Writes:
  original.png, rebuilt.png    the two renders
  heat.png                     the rebuilt render with a red wash where it differs (stronger = worse), and tile numbers
  report.txt                   the worst tiles: world position, nearest space, score; then a side-by-side crop of each as
                               tile_NN.png (original | rebuilt | difference)
The renderer ignores the game's fog, water depth writes and blend order, so a score points at where to look, not at a proven bug.
Run it flat (default) for layout/texture differences and with --tilt 50 for height differences (cliffs, plateaus).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "igb"), str(HERE.parent / "boardview")]
import render_top as rt


def draw(out: Path, folder, scale, box, tilt):
    rt.render(out, folder, scale, box, rt.FILES, False, None, 0, tilt)
    return Image.open(out).convert("RGB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rebuilt")
    ap.add_argument("out")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--tile", type=float, default=40.0)
    ap.add_argument("--tilt", type=float, default=None)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--box", default="-700,-720,700,480")
    ap.add_argument("--blur", type=float, default=1.5)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    box = tuple(float(v) for v in a.box.split(","))
    x0, z0, x1, z1 = box
    orig = draw(out / "original.png", None, a.scale, box, a.tilt)
    new = draw(out / "rebuilt.png", Path(a.rebuilt), a.scale, box, a.tilt)
    soft = lambda im: np.asarray(im.filter(ImageFilter.GaussianBlur(a.blur * a.scale)), np.float32) / 255
    d = np.abs(soft(orig) - soft(new)).mean(2)                      # 0..1 per pixel
    H, W = d.shape
    t = max(int(a.tile * a.scale), 4)
    # the picture is turned 180 degrees (+x left); the tilted one also squashes z, so report tiles by picture position and
    # convert flat pictures back to world units
    tiles = []
    for j in range(0, H - t // 2, t):
        for i in range(0, W - t // 2, t):
            s = float(d[j:j + t, i:i + t].mean())
            tiles.append((s, i, j))
    tiles.sort(reverse=True)
    heat = np.asarray(new, np.float32) / 255
    wash = np.clip(d * 4, 0, 1)[..., None]
    heat = heat * (1 - 0.6 * wash) + np.array([1, 0, 0], np.float32) * 0.6 * wash
    himg = Image.fromarray((heat * 255).astype(np.uint8))
    dr = ImageDraw.Draw(himg)
    try:
        from boardlib import load_board
        spaces = [s for s in load_board(rt.ASSETS, 0)[0] if s["pos"]]
    except Exception:
        spaces = []
    lines = [f"{'#':>2} {'score':>6}  {'world x,z':>14}  nearest space"]
    for n, (s, i, j) in enumerate(tiles[:a.top], 1):
        cx, cy = i + t / 2, j + t / 2
        wx, wz = x1 - cx / a.scale, None
        if not a.tilt:
            wz = (rt.TALL * 0 + z1) - cy / a.scale                   # flat: top == z1
        near = ""
        if spaces and wz is not None:
            sp = min(spaces, key=lambda p: (p["pos"][0] - wx) ** 2 + (p["pos"][2] - wz) ** 2)
            near = f"{sp['id']} ({((sp['pos'][0]-wx)**2 + (sp['pos'][2]-wz)**2) ** .5:.0f} away)"
        lines.append(f"{n:>2} {s:6.3f}  {wx:7.0f},{wz if wz is not None else float('nan'):6.0f}  {near}")
        dr.rectangle([i, j, i + t, j + t], outline=(255, 255, 0))
        dr.text((i + 2, j + 2), str(n), fill=(255, 255, 0))
        pad = t // 2
        box_ = (max(i - pad, 0), max(j - pad, 0), min(i + t + pad, W), min(j + t + pad, H))
        co, cn = orig.crop(box_), new.crop(box_)
        dd = Image.fromarray((np.clip(d[box_[1]:box_[3], box_[0]:box_[2]] * 4, 0, 1) * 255).astype(np.uint8)).convert("RGB")
        sheet = Image.new("RGB", (co.width * 3 + 8, co.height), (40, 40, 40))
        for k, im in enumerate((co, cn, dd)):
            sheet.paste(im, (k * (co.width + 4), 0))
        sheet = sheet.resize((sheet.width * 2, sheet.height * 2), Image.NEAREST)
        sheet.save(out / f"tile_{n:02d}.png")
    himg.save(out / "heat.png")
    lines.append(f"\nmean difference over the board: {float(d.mean()):.4f}")
    (out / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

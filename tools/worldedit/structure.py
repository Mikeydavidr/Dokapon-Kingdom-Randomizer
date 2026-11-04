"""Structural comparison: what the ground IS, not how it looks.

usage: python structure.py <rebuilt Assets folder> <out folder> [--min N]

Reads the ground of the original board and of the rebuilt one from their model files with terrain.classify_model_files (the
same reader that made the world grid), then compares them cell by cell, on both layers (ground code, height level). Cells that
differ are grouped into connected patches; the report lists each patch big enough to matter: where it is, the nearest space,
what the original has against what the rebuild has, and its size. Writes structure.png (red = ground differs, yellow = height
differs, over the original's ground) and structure.json (the numbers, for tracking progress between builds).
Only features the reader can see are compared (fills, strips, moat water, heights); props, roads and art are not.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "igb"), str(HERE.parent / "boardview")]
import terrain
import render_top as rt

NAMES = {c: g.name for c, g in terrain.GROUNDS.items()}
NAMES.update({"0": "ground", "1": "plateau", "/": "slope"})


def compare(rebuilt: Path, smallest: int = 12) -> dict:
    a = terrain.classify_model_files(rt.F00)
    b = terrain.classify_model_files(rebuilt)
    assert a.cells.shape == b.cells.shape
    # a sea cell next to land flips with one cell of coast smoothing: only count cells whose 3x3 neighbourhood differs too
    dg = a.cells != b.cells
    # our moat water is a disc under the castle's island (the game's is a ring), and the reader sees water under the island
    dg &= ~((b.cells == ord("o")) & (a.cells != ord(".")))
    # heights are compared as heights: a smooth ramp read back through the level bands always comes out narrower than it was
    # built, so comparing the level codes would flag every slope
    both_land = (a.cells != ord(".")) & (b.cells != ord(".")) & ~np.isin(a.cells, [ord("o")]) & ~np.isin(b.cells, [ord("o")])
    dl = both_land & (np.abs(a.up - b.up) > 2.5)
    both = dg | dl
    solid = ndimage.binary_opening(both, structure=np.ones((2, 2), bool))     # one-cell coast jitter is not a difference
    labels, n = ndimage.label(solid, structure=np.ones((3, 3), bool))
    try:
        from boardlib import load_board
        spaces = [s for s in load_board(rt.ASSETS, 0)[0] if s["pos"]]
    except Exception:
        spaces = []
    patches = []
    for k in range(1, n + 1):
        js, is_ = np.nonzero(labels == k)
        if len(js) < smallest:
            continue
        ca = Counter(chr(v) for v in a.cells[js, is_])
        cb = Counter(chr(v) for v in b.cells[js, is_])
        ha, hb = float(a.up[js, is_].mean()), float(b.up[js, is_].mean())
        x = a.x0 + (is_.mean() + 0.5) * a.cell
        z = a.z0 + (js.mean() + 0.5) * a.cell
        near = min(spaces, key=lambda p: (p["pos"][0] - x) ** 2 + (p["pos"][2] - z) ** 2)["id"] if spaces else None
        ground = bool(dg[js, is_].mean() > 0.5)
        patches.append({"cells": int(len(js)), "x": round(float(x)), "z": round(float(z)), "space": near, "kind": "ground" if ground else "height",
                        "original": ca.most_common(1)[0][0] if ground else f"{ha:+.1f}",
                        "rebuilt": cb.most_common(1)[0][0] if ground else f"{hb:+.1f}"})
    patches.sort(key=lambda p: -p["cells"])
    land = a.cells != ord(".")
    err = float(np.abs(a.up - b.up)[both_land].mean())
    return {"mean_height_error": round(err, 3), "cells_ground_differ": int(dg.sum()), "cells_height_differ": int(dl.sum()), "land_cells": int(land.sum()),
            "ground_match": round(1 - float((dg & land).sum() / max(land.sum(), 1)), 4),
            "patches": patches, "_grids": (a, b, dg, dl)}


def picture(res: dict, out: Path) -> None:
    a, b, dg, dl = res["_grids"]
    img = np.zeros(a.cells.shape + (3,), np.uint8)
    for c, g in terrain.GROUNDS.items():
        img[a.cells == ord(c)] = [int(g.colour[i:i + 2], 16) // 2 for i in (1, 3, 5)]
    img[dg] = (255, 40, 40)
    img[dl] = (255, 220, 40)
    Image.fromarray(img[::-1, ::-1]).resize((a.w * 2, a.h * 2), Image.NEAREST).save(out)    # turned 180 like the other pictures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rebuilt")
    ap.add_argument("out")
    ap.add_argument("--min", type=int, default=12)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = compare(Path(a.rebuilt), a.min)
    picture(res, out / "structure.png")
    res.pop("_grids")
    (out / "structure.json").write_text(json.dumps(res, indent=1))
    print(f"ground match on land: {res['ground_match']:.1%}   cells: ground differs {res['cells_ground_differ']}, height differs {res['cells_height_differ']}")
    print(f"{'cells':>5}  {'x,z':>10}  space  what")
    for p in res["patches"][:30]:
        print(f"{p['cells']:>5}  {p['x']:>5},{p['z']:>5}  {p['space']!s:>5}  {p['kind']}: original {p['original']!r} ({___name(p['original'])}) -> rebuilt {p['rebuilt']!r} ({___name(p['rebuilt'])})")
    print(f"{len(res['patches'])} patches of {a.min}+ cells")


def ___name(c: str) -> str:
    return NAMES.get(c, c)


if __name__ == "__main__":
    main()

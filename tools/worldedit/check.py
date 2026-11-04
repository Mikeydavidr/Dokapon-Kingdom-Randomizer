"""One command to build a world and score it against the original board.

usage: python check.py <world.json> <mod folder> [--tilt DEG] [--history history.jsonl]

Runs build_world.py, then structure.py (what the ground is) and compare.py (how it looks) on the result, prints one summary
line and appends it to the history file in the mod folder's parent, so each change shows as a number against the last build.
The reports and pictures land in <mod folder>/check/.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "igb"), str(HERE.parent / "boardview")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("mod")
    ap.add_argument("--tilt", type=float, default=None)
    ap.add_argument("--history", default=None)
    ap.add_argument("--no-build", action="store_true", help="score the mod folder as it is")
    a = ap.parse_args()
    mod = Path(a.mod)
    if not a.no_build:
        subprocess.run([sys.executable, str(HERE / "build_world.py"), a.world, str(mod), "--no-picture"], check=True,
                       stdout=subprocess.DEVNULL)
    out = mod / "check"
    out.mkdir(parents=True, exist_ok=True)
    import numpy as np
    from PIL import Image, ImageFilter
    import structure
    import compare
    import render_top as rt
    res = structure.compare(mod / "Assets")
    structure.picture(res, out / "structure.png")
    res.pop("_grids")
    (out / "structure.json").write_text(json.dumps(res, indent=1))
    box = (-700.0, -720.0, 700.0, 480.0)
    orig = compare.draw(out / "original.png", None, 1.0, box, a.tilt)
    new = compare.draw(out / "rebuilt.png", mod / "Assets", 1.0, box, a.tilt)
    blur = lambda im: np.asarray(im.filter(ImageFilter.GaussianBlur(1.5)), np.float32) / 255
    d = np.abs(blur(orig) - blur(new)).mean(2)
    row = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "mod": mod.name, "tilt": a.tilt, "picture_diff": round(float(d.mean()), 4),
           "ground_match": res["ground_match"], "ground_cells": res["cells_ground_differ"], "height_cells": res["cells_height_differ"], "height_error": res["mean_height_error"],
           "patches": len(res["patches"])}
    hist = Path(a.history) if a.history else mod.parent / "check_history.jsonl"
    last = None
    if hist.exists():
        lines = [l for l in hist.read_text().splitlines() if l.strip()]
        last = json.loads(lines[-1]) if lines else None
    with hist.open("a") as f:
        f.write(json.dumps(row) + "\n")
    delta = ""
    if last:
        delta = f"   (was picture {last['picture_diff']}, match {last['ground_match']}, {last['patches']} patches)"
    print(f"{mod.name}: picture difference {row['picture_diff']}, ground match {row['ground_match']:.1%}, "
          f"{row['ground_cells']} ground + {row["height_cells"]} height cells differ (mean height error {row["height_error"]}), {row['patches']} patches{delta}")
    for p in res["patches"][:8]:
        print(f"  {p['cells']:>4} cells near space {p['space']} ({p['x']},{p['z']}): {p['kind']} {p['original']!r} -> {p['rebuilt']!r}")
    print("pictures and report:", out)


if __name__ == "__main__":
    main()

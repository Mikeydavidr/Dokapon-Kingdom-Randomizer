"""Board 0 shuffle (prototype of the randomizer's board mode): move stores and castles, cut links, add links with roads.

usage: python make_board_seed.py <mod folder> [--seed N] [--cuts K] [--adds K] [--mix]
                                 [--swap a-b,...] [--cut a-b,...] [--add a-b[:dirt|line],...] [--assets <folder>]
  stores (item and magic) trade places among the store spaces and castles among the castle spaces (--mix: all in one pool);
  each move takes the space record, the sign and its placement, the building, its shadow and decor
  (tools/boardview/board0_buildings.json). --swap gives the moves instead: each pair trades places.
  --cuts K removes K random links and their roads, never splitting a group of connected spaces and never a sea route or
  bridge (roads.check_cut; --cut: these links);
  --adds K adds K random new links with roads (--add: these), each checked by roads.check_new_link (axis-aligned, free
  direction slots, no space in between, no road or water crossed) and written in the slot of its direction; the road is dirt
  between two grass spaces and the line alone otherwise, unless the style is given.
  A moved shadow that would fall across a road or space, other ground or another decal shrinks a little (to 90% at most)
  or, if that is not enough, is dropped (units.Art.fit_shadows).
Writes stg000_EN.DAT, CHAIN_000.DAT and the changed F00_*.model files to <mod>/Assets (copy a clean baseline there first),
plus <mod>/board_log.txt and <mod>/board_map.png (the new board from above: moved buildings ringed, cut links red, new green).
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "igb"))
from PIL import Image, ImageDraw

import render_top
from roads import Roads
from stage import Stage
from units import Art, load_units

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--cuts", type=int, default=4)
ap.add_argument("--adds", type=int, default=4)
ap.add_argument("--mix", action="store_true")
ap.add_argument("--swap", default=None)
ap.add_argument("--cut", default=None)
ap.add_argument("--add", default=None)
ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
args = ap.parse_args()
assets, mod = Path(args.assets), Path(args.mod)
out = mod / "Assets"
rng = random.Random(args.seed)
pairs = lambda s: [tuple(int(v) for v in p.split(":")[0].split("-")) for p in s.split(",") if p]
log = [f"board seed {args.seed}" if not (args.swap or args.cut or args.add) else "board edit"]

# ---- buildings ------------------------------------------------------------------------------------------------------------
units = load_units()
if args.swap is not None:
    dest = {x: y for a, b in pairs(args.swap) for x, y in ((a, b), (b, a))}
else:
    pools = [sorted(units)] if args.mix else [sorted(u for u in units if units[u]["kind"] != "castle"),
                                              sorted(u for u in units if units[u]["kind"] == "castle")]
    dest = {}
    for pool in pools:
        targets = pool[:]
        rng.shuffle(targets)
        dest.update(zip(pool, targets))
stage, art = Stage(assets), Art(assets)
node = Roads(assets).node
stage.move(dest)
offsets = {}
for u, t in sorted(dest.items()):
    if u != t:
        offsets[u] = tuple(node[t][k] - node[u][k] for k in range(3))
        art.move(units[u], offsets[u], label=str(u))
        log.append(f"{units[u]['kind']} {u} -> space {t}")

# ---- links and roads ----------------------------------------------------------------------------------------------------------
roads = Roads(assets, models={name: bytes(data) for name, data in art.data.items()})
groups = roads.components()
if args.cut is not None:
    plan = pairs(args.cut)
    for a, b in plan:
        why = roads.check_cut(a, b)
        assert why is None, f"cut {a}-{b}: {why}"
else:
    plan = sorted((a, b) for a in roads.links for b in roads.links[a] if a < b)
    rng.shuffle(plan)
    plan = [(a, b) for a, b in plan if roads.check_cut(a, b) is None]
cut = []
for a, b in plan:
    if args.cut is None and len(cut) == args.cuts:
        break
    roads.unlink(a, b)
    if len(roads.components()) != len(groups):     # it would split a group: put it back
        assert args.cut is None, f"cutting {a}-{b} splits a group of spaces"
        roads.link(a, b)
        continue
    roads.cut(a, b)
    cut.append((a, b))
    log.append(f"cut {a}-{b}")
added = []
wanted = [(int(p.split(":")[0].split("-")[0]), int(p.split(":")[0].split("-")[1]), p.split(":")[1] if ":" in p else "auto")
          for p in args.add.split(",") if p] if args.add is not None else None
for i in range(len(wanted) if wanted is not None else args.adds):
    if wanted is not None:
        a, b, style = wanted[i]
        why = roads.check_new_link(a, b)
        assert why is None, f"new link {a}-{b}: {why}"
    else:
        options = [c for c in roads.candidates() if c not in cut]    # not straight back where a road was just removed
        if not options:
            log.append("no more links can be added")
            break
        (a, b), style = rng.choice(options), "auto"
    style = roads.style_for(a, b) if style == "auto" else style
    roads.add(a, b, style)
    roads.link(a, b)
    added.append((a, b))
    log.append(f"add {a}-{b} ({style})")
assert all(any(g <= h for h in roads.components()) for g in groups)

# ---- shadows that now fall across a road ---------------------------------------------------------------------------------------
mask, decals, home_decals = roads.road_mask(), art.decals(True), art.decals(False)
for u, off in sorted(offsets.items()):
    for line in art.fit_shadows(units[u], off, roads, mask, decals, home_decals):
        log.append(f"{units[u]['kind']} {u}: {line}")

# ---- write --------------------------------------------------------------------------------------------------------------------
stage.save(out)
art.save(out)
roads.save(out, base={name: bytes(data) for name, data in art.data.items()})
(out / "CHAIN_000.DAT").write_bytes(roads.chain)
(mod / "board_log.txt").write_text("\n".join(log) + "\n")
print("\n".join(log))

x0, z0, x1, z1, scale = -700, -720, 700, 480, 1.2
render_top.render(mod / "board_map.png", out, scale, (x0, z0, x1, z1), render_top.FILES, True, None)
img = Image.open(mod / "board_map.png")
d = ImageDraw.Draw(img)
px = lambda p: ((x1 - p[0]) * scale, (z1 - p[2]) * scale)
for u, t in dest.items():
    if u != t:
        x, y = px(node[t])
        d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=(255, 0, 255), width=3)
        d.text((x + 16, y + 2), f"{units[u]['kind']} {u}", fill=(255, 0, 255))
for pairs_, colour in ((cut, (255, 30, 30)), (added, (30, 255, 30))):
    for a, b in pairs_:
        d.line([px(node[a]), px(node[b])], fill=colour, width=4)
img.save(mod / "board_map.png")
print("wrote", mod / "board_map.png")

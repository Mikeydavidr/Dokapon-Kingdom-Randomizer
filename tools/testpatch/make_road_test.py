"""Road test mod: remove the roads of some links and draw roads for new ones, in the art and (unless --art-only) in CHAIN.

usage: python make_road_test.py <mod folder> [--cut=a-b,c-d] [--add=a-b[:line],...] [--art-only] [--assets <folder>]
Writes <mod>/Assets/F00_*.model for the pieces that change and, without --art-only, CHAIN_000.DAT. A new link must pass
roads.check_new_link (axis-aligned, free direction slots at both ends, no space in between, no road crossed); the links are
written in the slot of their direction. No cut may split a group of connected spaces.
Model files already in <mod>/Assets with in-place edits (from make_unit_swap.py, say) keep those edits; run that tool first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from roads import Roads

args = {a.split("=")[0]: a.split("=", 1)[1] if "=" in a else True for a in sys.argv[2:]}
mod = Path(sys.argv[1])
assets = Path(args.get("--assets", "G:/Programming/Dokapon-Workspace/assets"))
pairs = lambda s: [tuple(p.split(":")[0].split("-")) for p in s.split(",")] if s else []
cuts = [(int(a), int(b)) for a, b in pairs(args.get("--cut", ""))]
adds = [(int(p.split(":")[0].split("-")[0]), int(p.split(":")[0].split("-")[1]), p.split(":")[1] if ":" in p else "dirt")
        for p in args.get("--add", "").split(",") if p]

out = mod / "Assets"
staged = {f: (out / f"F00_{f}.model").read_bytes() for f in ("A", "M", "N", "Anim1", "Anim2") if (out / f"F00_{f}.model").exists()}
roads = Roads(assets, models=staged)    # builds on model files another tool already edited (make_unit_swap.py, say)
before = roads.components()
for a, b, _ in adds:                     # checked against the unmodified board, before cuts free any slots
    why = roads.check_new_link(a, b)
    assert why is None, f"new link {a}-{b}: {why}"
for a, b in cuts:
    assert b in roads.links[a], f"{a}-{b} is not a link"
    print(f"cut {a}-{b}: {roads.cut(a, b)} road triangles clipped")
    roads.unlink(a, b)
for a, b, style in adds:
    print(f"add {a}-{b} ({style}) into F00_{'/'.join(map(str, roads.add(a, b, style)))}")
    roads.link(a, b)
after = roads.components()
print(f"connected groups of spaces: {[len(c) for c in before]} before, {[len(c) for c in after]} after")
assert len(after) <= len(before) and all(any(c <= d for d in after) for c in before), "a cut splits a group of spaces"

for p in roads.save(out):
    print("wrote", p.name)
if "--art-only" not in args:
    (out / "CHAIN_000.DAT").write_bytes(roads.chain)
    print("wrote CHAIN_000.DAT")

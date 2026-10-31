import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from boardlib import load_board

assets, outdir, board = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
outdir.mkdir(parents=True, exist_ok=True)
spaces, links = load_board(assets, board)
byid = {s["id"]: s for s in spaces}

# connected components
seen, comps = set(), []
for s in spaces:
    if s["id"] in seen:
        continue
    stack, comp = [s["id"]], []
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        comp.append(x)
        stack.extend(m for m in links.get(x, []) if m not in seen)
    comps.append(sorted(comp))

# a coarser grouping: spaces whose positions are close, even if no link joins them (continents are separated by water)
print(f"{len(comps)} link-connected groups")
for i, c in enumerate(sorted(comps, key=lambda c: -len(c))):
    xs = [byid[k]["pos"][0] for k in c]; zs = [byid[k]["pos"][2] for k in c]
    print(f"  group {i}: {len(c)} spaces, ids {min(c)}..{max(c)}, x {min(xs):.0f}..{max(xs):.0f}, z {min(zs):.0f}..{max(zs):.0f}")

cmap = plt.get_cmap("tab20")
for i, c in enumerate(sorted(comps, key=lambda c: -len(c))):
    sub = [byid[k] for k in c]
    xs = [s["pos"][0] for s in sub]; zs = [s["pos"][2] for s in sub]
    w, h = max(xs) - min(xs), max(zs) - min(zs)
    sc = 12 / max(w, h, 1)
    fig, ax = plt.subplots(figsize=(max(6, w * sc + 2), max(6, h * sc + 2)), dpi=90)
    freq = Counter(s["type"] for s in sub)
    color = {t: cmap(j % 20) for j, (t, _) in enumerate(freq.most_common())}
    for a in c:
        for b in links.get(a, []):
            if a < b:
                pa, pb = byid[a]["pos"], byid[b]["pos"]
                ax.plot([pa[0], pb[0]], [pa[2], pb[2]], color="#888", lw=1.2, zorder=1)
    for s in sub:
        x, _, z = s["pos"]
        ax.scatter([x], [z], s=420, color=color[s["type"]], edgecolor="black", zorder=2)
        ax.text(x, z, str(s["id"]), ha="center", va="center", fontsize=7, zorder=3)
    handles = [plt.Line2D([], [], marker="o", ls="", color=color[t], markeredgecolor="black", label=f"{t[0]:02X} {t[1]:02X}  x{n}") for t, n in freq.most_common()]
    ax.legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0), title="type code")
    ax.set_title(f"Board {board}, group {i}: {len(sub)} spaces")
    ax.set_aspect("equal"); ax.invert_yaxis(); ax.axis("off")
    fig.savefig(outdir / f"b{board:02d}_group{i}.png", bbox_inches="tight")
    plt.close(fig)

import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from boardlib import load_board

assets = Path(sys.argv[1])
outdir = Path(sys.argv[2])
boards = [int(a) for a in sys.argv[3:]] or list(range(23))
outdir.mkdir(parents=True, exist_ok=True)

cmap = plt.get_cmap("tab20")

for n in boards:
    spaces, links = load_board(assets, n)
    xs = [s["pos"][0] for s in spaces]
    zs = [s["pos"][2] for s in spaces]
    w, h = max(xs) - min(xs), max(zs) - min(zs)
    scale = 14 / max(w, h)
    fig, ax = plt.subplots(figsize=(max(6, w * scale + 2), max(6, h * scale + 2)), dpi=90)

    # one color per type code, most common first
    freq = Counter(s["type"] for s in spaces)
    color = {t: cmap(i % 20) for i, (t, _) in enumerate(freq.most_common())}

    byid = {s["id"]: s for s in spaces}
    for a, nbs in links.items():
        for b in nbs:
            if a < b and a in byid and b in byid:
                pa, pb = byid[a]["pos"], byid[b]["pos"]
                ax.plot([pa[0], pb[0]], [pa[2], pb[2]], color="#999999", lw=1.2, zorder=1)
    for s in spaces:
        x, _, z = s["pos"]
        ax.scatter([x], [z], s=330 if len(spaces) < 120 else 90, color=color[s["type"]], edgecolor="black", zorder=2)
        ax.text(x, z, str(s["id"]), ha="center", va="center", fontsize=7 if len(spaces) < 120 else 4, zorder=3)

    handles = [plt.Line2D([], [], marker="o", ls="", color=color[t], markeredgecolor="black", label=f"{t[0]:02X} {t[1]:02X}  x{c}") for t, c in freq.most_common()]
    ax.legend(handles=handles, fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1.0), title="type code")
    ax.set_title(f"Board {n}: {len(spaces)} spaces   (x right, z down; north-up if z is down)")
    ax.set_aspect("equal")
    ax.invert_yaxis()  # z grows downward, like a screen
    ax.axis("off")
    fig.savefig(outdir / f"board_{n:02d}.png", bbox_inches="tight")
    plt.close(fig)
    print(f"board {n}: {len(spaces)} spaces, extent {w:.0f} x {h:.0f}")

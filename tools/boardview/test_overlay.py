"""Numbered map of board 0 with the spaces and links of the current board test highlighted.

usage: python test_overlay.py <out.png> [assets folder]
Edit LINKS / CUTS / CHECK below to match the test mod (they mirror make_board_test.py and make_art_swap.py).
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
from boardlib import load_board

out = sys.argv[1]
assets = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("G:/Programming/Dokapon-Workspace/assets")
LINKS = {(78, 85): "short new link (53)", (26, 91): "long new link (153)"}
CUTS = {(14, 6): "cut link: castle 14 to 6"}
CHECK = {   # space id: what to look at
    78: "new link, end of short", 85: "new link, end of short", 26: "new link, end of long", 91: "new link, end of long",
    122: "Magic Store record + building", 268: "Item Store record + building",
    87: "castle record + building", 170: "Magic Store record + building",
    21: "Balle (id 6 now)", 20: "Balle (id 5 now)", 5: "Magic Store on a plain space", 2: "town (id 5) on the old Magic Store space",
    18: "Weapon Store rules", 24: "Item Store rules",
}
KINDS = {0x14: "#2a7", 0x15: "#a2a", 0x16: "#c52", 0x17: "#25c", 0x18: "#c9a000", 0x1b: "k", 0x1c: "k"}

spaces, links = load_board(assets, 0)
b = {s["id"]: s for s in spaces}
fig, ax = plt.subplots(figsize=(24, 24), dpi=70)
for a, ns in links.items():
    for n in ns:
        if a < n and (a, n) not in CUTS:
            ax.plot([b[a]["pos"][0], b[n]["pos"][0]], [b[a]["pos"][2], b[n]["pos"][2]], color="#bbb", lw=1, zorder=1)
for (a, n), _ in LINKS.items():
    ax.plot([b[a]["pos"][0], b[n]["pos"][0]], [b[a]["pos"][2], b[n]["pos"][2]], color="#0a0", lw=5, zorder=2)
for (a, n), _ in CUTS.items():
    ax.plot([b[a]["pos"][0], b[n]["pos"][0]], [b[a]["pos"][2], b[n]["pos"][2]], color="#d00", lw=4, ls=":", zorder=2)
for s in spaces:
    x, z = s["pos"][0], s["pos"][2]
    c = KINDS.get(s["type"][0])
    ax.scatter([x], [z], s=150 if c else 12, color=c or "#999", zorder=3)
    if c:
        ax.annotate(str(s["id"]), (x, z), xytext=(5, 5), textcoords="offset points", fontsize=8, zorder=4)
for i, text in CHECK.items():
    x, z = b[i]["pos"][0], b[i]["pos"][2]
    ax.scatter([x], [z], s=1000, facecolors="none", edgecolors="#e0a000" if i not in (78, 85, 26, 91) else "#0a0", linewidths=3, zorder=5)
    ax.annotate(f"{i}: {text}", (x, z), xytext=(16, -20), textcoords="offset points", fontsize=11, weight="bold",
                color="#0a0" if i in (78, 85, 26, 91) else "#a60", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
ax.set_aspect("equal")
ax.invert_xaxis()
ax.set_title("Board 0 as on screen. Green thick = new links to try, red dotted = cut link, orange = spaces to look at. Numbers are space ids.", fontsize=14)
fig.savefig(out, bbox_inches="tight")
print(out)

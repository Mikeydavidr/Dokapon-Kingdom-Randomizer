"""A board as one editable JSON file: its ground (terrain.Grid), its spaces, its links and its props.

    {"version": 1, "board": 0,                                       0 = the world map, 1-22 the dungeons
     "terrain": {x0, z0, cell, w, h, rows: ["..ggg..", ...]},     row j covers z0 + j*cell, column i covers x0 + i*cell
                                                                      (a dungeon with a ground kit has "kit" too and its own
                                                                      ground codes, cavekit.py; null for one without: its own
                                                                      art is kept)
     "spaces": [{"id", "x", "y", "z", "kind", "skin", "grp", "param"}],   kind/skin/param as in stg000 (hex param string)
     "links": [[a, b], ...],                                          each link once, a < b
     "no_path_links": [[a, b], ...],                                  dungeon links the builder draws no path strip for: the
                                                                      game shows them another way (bridges, paths painted into
                                                                      the floor art) or not at all (board 19's secret passages)
     "props": [{"t": type, "v": template, "x", "z"}]}               copies of the game's trees, mountains, hills and
                                                                      decorations (props.py: tree, mountain, hill, clover,
                                                                      flowers, mushroom, ice)

usage: python world.py <out.json> [--board N] [--assets <folder>]     a board of the game as a world file (the editor's
       starting point; board 0 by default)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
import cavekit
import dungeon
import props
from boardlib import load_board
from terrain import Grid, classify_model_files

ASSETS = Path("G:/Programming/Dokapon-Workspace/assets")


def from_game(assets: Path = ASSETS, board: int = 0) -> dict:
    """A board as a world file. Board 0 gets its ground and props; a dungeon (1-22) keeps its own art, so it has neither."""
    spaces, links = load_board(assets, board)
    F = assets / "CommonData" / "dataField" / f"F{board:02d}"
    return {
        "version": 1, "board": board,
        "terrain": classify_model_files(F).to_json() if board == 0 else kit_terrain(F, board),
        "spaces": [{"id": s["id"], "x": round(s["pos"][0], 3), "y": round(s["pos"][1], 3), "z": round(s["pos"][2], 3),
                    "kind": s["type"][0], "skin": s["type"][1], "grp": s["grp"], "param": bytes(s["param"]).hex()} for s in spaces],
        "links": sorted({tuple(sorted((a, b))) for a, bs in links.items() for b in bs}),
        "no_path_links": dungeon.no_path_links(assets, board) if board else [],
        "props": props.from_game(F) if board == 0 else [],
    }


def kit_terrain(F: Path, board: int) -> dict | None:
    """A dungeon's ground as a grid, for a dungeon that has a ground kit (cavekit.py), else None (its art stays)."""
    kit = cavekit.kit_for(board)
    if kit is None:
        return None
    import render_top
    t = cavekit.classify(F, board, render_top.board_box(board, 150.0)).to_json()
    t["kit"] = kit
    return t


def load(path: Path) -> dict:
    w = json.loads(Path(path).read_text())
    if w.get("version") != 1:
        raise ValueError(f"{path}: not a version 1 world file")
    return w


def save(world: dict, path: Path) -> None:
    """One line per terrain row and per space, so the file diffs well."""
    t = world["terrain"]
    lines = ["{", f' "version": {world["version"]}, "board": {world["board"]},']
    if t is None:
        lines.append(' "terrain": null,')
    else:
        head = {k: v for k, v in t.items() if k != "rows"}
        lines.append(f' "terrain": {json.dumps(head)[:-1]}, "rows": [')
        lines += [f'  "{r}"' + ("," if k < len(t["rows"]) - 1 else "") for k, r in enumerate(t["rows"])]
        lines.append(" ]},")
    lines.append(' "spaces": [')
    lines += ["  " + json.dumps(s) + ("," if k < len(world["spaces"]) - 1 else "") for k, s in enumerate(world["spaces"])]
    lines.append(" ],")
    lines.append(' "links": ' + json.dumps([list(l) for l in world["links"]]) + ",")
    lines.append(' "no_path_links": ' + json.dumps([list(l) for l in world.get("no_path_links", [])]) + ",")
    pr = world.get("props", [])
    lines.append(' "props": [')
    lines += ["  " + json.dumps(p) + ("," if k < len(pr) - 1 else "") for k, p in enumerate(pr)]
    lines.append(" ]")
    lines.append("}")
    Path(path).write_text("\n".join(lines) + "\n")


def grid(world: dict) -> Grid:
    return Grid.from_json(world["terrain"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--board", type=int, default=0)
    ap.add_argument("--assets", default=str(ASSETS))
    a = ap.parse_args()
    w = from_game(Path(a.assets), a.board)
    save(w, Path(a.out))
    t = w["terrain"]
    print(f"wrote {a.out}: board {a.board}, {len(w['spaces'])} spaces, {len(w['links'])} links, {len(w['props'])} props, "
          + (f"terrain {t['w']}x{t['h']}" if t else "no terrain (the dungeon's own art)"))

"""The world editor: a local web page for painting a board's ground, moving its spaces and changing its links.

usage: python server.py <world.json> [--port 8765] [--mod <folder>] [--assets <folder>]
Then open http://localhost:8765. Make a world file from the game's board first: python world.py <world.json>.

A dungeon's world file (python world.py <world.json> --board N, N = 1-22) opens without the ground and prop tools: its
own art is shown under the spaces, which can be moved (and raised or lowered) and linked.

The page edits the world file (world.py) in place: Save writes it (the first save of a session keeps the previous file as
<world>.bak). Build saves, then runs build_world.py into the mod folder (default: <world folder>/<world name>_mod) and shows
its log and the board it drew. The reference picture is the game's own board from above, rendered once and kept next to
the world file as <world>.ref.png. Only this computer can reach the server (it listens on 127.0.0.1).
"""
import argparse
import json
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "igb"))
import cavekit
import dungeon
import props
import render_top
import world as worldfile
from terrain import GROUNDS, LEVELS, RAMP

LEVEL_COLOURS = {"0": "#00000000", "1": "#c8783c", RAMP: "#e6d23c"}   # how the editor tints raised cells

KINDS = {0x01: "Item", 0x02: "Magic", 0x03: "Red Loot", 0x04: "White Loot", 0x05: "Locked Box", 0x06: "Money", 0x07: "Weapon",
         0x08: "Shield", 0x09: "Battle Magic", 0x0A: "Bank", 0x0B: "Collection", 0x0C: "Poison Swamp", 0x0D: "Snowfield",
         0x0F: "Warp", 0x11: "Dark", 0x12: "Trap", 0x13: "Doom", 0x14: "Town", 0x15: "Castle", 0x16: "Weapon Store",
         0x17: "Item Store", 0x18: "Magic Store", 0x1B: "Casino", 0x1C: "Coliseum", 0x1D: "Dokapon Castle", 0x1E: "Plain",
         0x1F: "Forest", 0x20: "Mountain", 0x21: "Desert", 0x22: "Ocean", 0x23: "Swamp", 0x24: "Cave", 0x25: "Lava"}


class Editor(BaseHTTPRequestHandler):
    world: Path
    mod: Path
    assets: Path
    backed_up = False

    def log_message(self, fmt, *args):
        pass

    def send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code: int = 200) -> None:
        self.send(json.dumps(obj).encode(), "application/json", code)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send((HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/world":
            self.send(self.world.read_bytes(), "application/json")
        elif path == "/api/meta":
            w = worldfile.load(self.world)
            board, kit = w["board"], (w["terrain"] or {}).get("kit")
            grounds = cavekit.grounds(kit) if kit else list(GROUNDS.values())
            walkable = cavekit.KITS[kit]["walkable"] if kit else "gfswdpm"
            self.send_json({"board": board, "box": self.box(), "straight": dungeon.STRAIGHT if board else 1.5, "kit": kit,
                            "grounds": [{"code": g.code, "name": g.name, "colour": g.colour, "walkable": g.code in walkable}
                                        for g in grounds],
                            "levels": [] if kit or board else [{"code": c, "name": n, "colour": LEVEL_COLOURS[c]}
                                                               for c, n in LEVELS.items()],
                            "kinds": {str(k): v for k, v in KINDS.items()}, "world": str(self.world), "mod": str(self.mod),
                            "props": props.variants(self.assets / "CommonData" / "dataField" / "F00")})
        elif path == "/api/reference.png":
            ref = self.reference()
            self.send(ref.read_bytes(), "image/png") if ref else self.send(b"", "text/plain", 404)
        elif path == "/api/build/map.png":
            p = self.mod / "world_map.png"
            self.send(p.read_bytes(), "image/png") if p.exists() else self.send(b"", "text/plain", 404)
        else:
            self.send(b"not found", "text/plain", 404)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        path = self.path.split("?")[0]
        if path == "/api/world":
            try:
                w = json.loads(body)
                assert w.get("version") == 1 and "terrain" in w and "spaces" in w and "links" in w
            except (ValueError, AssertionError):
                return self.send_json({"ok": False, "error": "not a world file"}, 400)
            self.save(w)
            self.send_json({"ok": True})
        elif path == "/api/build":
            r = subprocess.run([sys.executable, str(HERE / "build_world.py"), str(self.world), str(self.mod), "--assets", str(self.assets)],
                               capture_output=True, text=True)
            self.send_json({"ok": r.returncode == 0, "log": (r.stdout + r.stderr).strip(), "mod": str(self.mod)})
        else:
            self.send(b"not found", "text/plain", 404)

    def save(self, w: dict) -> None:
        if not Editor.backed_up and self.world.exists():
            shutil.copyfile(self.world, self.world.with_suffix(".bak"))
            Editor.backed_up = True
        worldfile.save(w, self.world)

    def box(self) -> tuple:
        """The part of the board the editor shows and the reference picture covers: the ground grid's, or for a dungeon the
        game's spaces with a margin."""
        w = worldfile.load(self.world)
        t = w["terrain"]
        if t is None:
            return render_top.board_box(w["board"], 120.0)
        return (t["x0"], t["z0"], t["x0"] + t["w"] * t["cell"], t["z0"] + t["h"] * t["cell"])

    def reference(self) -> Path | None:
        ref = self.world.with_suffix(".ref.png")
        if not ref.exists():
            board = worldfile.load(self.world)["board"]
            render_top.render(ref, None, 1.0 if board == 0 else 2.0, self.box(), render_top.board_files(board), False, None, board)
        return ref


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("world")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--mod")
    ap.add_argument("--assets", default=str(worldfile.ASSETS))
    a = ap.parse_args()
    Editor.world = Path(a.world).resolve()
    if not Editor.world.exists():
        sys.exit(f"{Editor.world} does not exist: make one with  python world.py {a.world}")
    Editor.mod = Path(a.mod).resolve() if a.mod else Editor.world.with_name(Editor.world.stem + "_mod")
    Editor.assets = Path(a.assets)
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Editor)
    print(f"world editor on http://localhost:{a.port}  (world {Editor.world}, mod {Editor.mod}); Ctrl+C stops it")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

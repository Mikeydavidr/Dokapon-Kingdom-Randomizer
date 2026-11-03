"""Change the kind of some board 0 spaces (the first type byte), keeping everything else of the record (encounter tables etc.).

usage: python make_kind_test.py <mod folder> --set SPACE:KIND[,SPACE:KIND...] [--base <mod Assets>] [--assets <folder>]
  KIND in hex (1e Plain, 0d Snowfield, 0c Poison Swamp, ...; see SpaceTypes.md). Reads stg000_EN.DAT from --base if given (to go
  on top of another mod) and writes it to <mod>/Assets, plus <mod>/kind_log.txt.
  Snow test: the snowy island's Snowfield spaces 168,169,173,178 to Plain and plains by the starting castles (36, 40, 6) to
  Snowfield, to see whether the falling snow follows the Snowfield spaces or stays on the island.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boardview"))
from boardlib import load_board

ap = argparse.ArgumentParser()
ap.add_argument("mod")
ap.add_argument("--set", required=True)
ap.add_argument("--base", default=None)
ap.add_argument("--assets", default="G:/Programming/Dokapon-Workspace/assets")
args = ap.parse_args()
assets, mod = Path(args.assets), Path(args.mod)
name = "stg000_EN.DAT"
src = Path(args.base) / name if args.base and (Path(args.base) / name).exists() else assets / "Data_eng" / "dataSeq_EN" / name
data = bytearray(src.read_bytes())
offset = {s["id"]: s["offset"] for s in load_board(assets, 0)[0]}
log = []
for item in args.set.split(","):
    space, kind = item.split(":")
    o = offset[int(space)] + 8
    log.append(f"space {space}: kind {data[o]:02x} -> {int(kind, 16):02x}")
    data[o] = int(kind, 16)
(mod / "Assets").mkdir(parents=True, exist_ok=True)
(mod / "Assets" / name).write_bytes(data)
(mod / "kind_log.txt").write_text("\n".join(log) + "\n")
print("\n".join(log))

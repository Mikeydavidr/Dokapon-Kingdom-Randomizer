"""Read-only decoder for Dokapon Kingdom board data.

Three files describe each board N:
  stgNNN_EN.DAT          16-byte space records: 33 00 00 00 | index u32 | type 2 bytes | group 1 | 00 | param 4 bytes
  CHAIN_NNN.DAT          u16 count, then count records of 5 u16: id, 4 neighbour slots (0xFFFF = none)
  MASUNN.position        u32 node count, u32 data offset, null-terminated node names, then x/y/z float32 per node
"""
import struct
from pathlib import Path


def load_board(assets: Path, n: int):
    stg = (assets / "Data_eng" / "dataSeq_EN" / f"stg{n:03d}_EN.DAT").read_bytes()
    chain = (assets / "CommonData" / "fieldChain" / f"CHAIN_{n:03d}.DAT").read_bytes()
    posb = (assets / "CommonData" / "fieldPosition" / f"MASU{n:02d}.position").read_bytes()

    # space records: find the one with index 0, then read while the index counts up
    start = -1
    for i in range(len(stg) - 16):
        if stg[i:i + 4] == b"\x33\x00\x00\x00" and struct.unpack_from("<I", stg, i + 4)[0] == 0:
            start = i
            break
    spaces = []
    k = 0
    while start >= 0 and start + 16 * (k + 1) <= len(stg):
        o = start + 16 * k
        if stg[o:o + 4] != b"\x33\x00\x00\x00" or struct.unpack_from("<I", stg, o + 4)[0] != k:
            break
        spaces.append({"id": k, "type": (stg[o + 8], stg[o + 9]), "grp": stg[o + 10], "param": tuple(stg[o + 12:o + 16]), "offset": o})
        k += 1

    # links
    count = struct.unpack_from("<H", chain, 0)[0]
    links = {}
    for i in range(count):
        o = 2 + 10 * i
        vals = struct.unpack_from("<5H", chain, o)
        links[vals[0]] = [v for v in vals[1:] if v != 0xFFFF]

    # positions
    ncount, data_off = struct.unpack_from("<II", posb, 0)
    names, q = [], 8
    for _ in range(ncount):
        s = q
        while posb[q] != 0:
            q += 1
        names.append(posb[s:q].decode("ascii"))
        q += 1
    pos = {}
    for i, nm in enumerate(names):
        o = data_off + 12 * i
        if o + 12 <= len(posb):
            pos[nm] = struct.unpack_from("<3f", posb, o)
    for sp in spaces:
        sp["pos"] = pos.get(f"Z{sp['id']:04d}")
    return spaces, links

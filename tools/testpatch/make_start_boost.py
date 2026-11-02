"""Max the stats of the starting weapon and shield (ids 1: Knife and Wooden Shield) so a test game is easy to walk around in.

usage: python make_start_boost.py <mod folder> [vanilla stageBase_EN.DAT]
Writes <mod>/Assets/stageBase_EN.DAT from the UNMODIFIED file. Weapon: ATK/DEF/MAG/SPD 999. Shield: DEF/ATK/MAG/SPD 999, HP 9999.
Everyone, NPCs included, starts with these (see docs/item-records-and-effects.md, the starting loadout table).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dokapon_rando.gamefile import FILE_NAME, GameFile
from dokapon_rando.shield_effects import shield_spec
from dokapon_rando.tables import read_table, write_table
from dokapon_rando.weapon_effects import weapon_spec

mod = Path(sys.argv[1])
dat = sys.argv[2] if len(sys.argv) > 2 else "G:/Programming/Dokapon-Workspace/ActualGame/assets/Data_eng/dataSeq_EN/stageBase_EN.DAT.backup"
game = GameFile(dat)
for spec, hp in ((weapon_spec(game), False), (shield_spec(game), True)):
    table = read_table(game.data, spec)
    r = table.records[0]
    assert r.id == 1
    tail = bytearray(r.tail)
    struct.pack_into("<4H", tail, 8, 999, 999, 999, 999)
    if hp:
        struct.pack_into("<H", tail, 16, 9999)
    r.tail = bytes(tail)
    write_table(game.data, table)
    print(f"{spec.label}: {r.name} -> stats 999" + (", HP 9999" if hp else ""))
(mod / "Assets").mkdir(parents=True, exist_ok=True)
game.save(mod / "Assets" / FILE_NAME)

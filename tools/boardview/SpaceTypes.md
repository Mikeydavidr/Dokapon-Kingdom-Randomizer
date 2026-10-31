# Board data notes (PC version)

Decoded by matching the overworld continent screenshot against board 0. All 68 spaces on that continent
matched the legend colours one for one, and the 10 town spaces matched their town signs.

## Files
| File | Holds |
|---|---|
| `Data_eng/dataSeq_EN/stgNNN_EN.DAT` | one 16-byte record per space: `33 00 00 00`, index u32, type (2 bytes), group (1), 00, param (4 bytes) |
| `CommonData/fieldChain/CHAIN_NNN.DAT` | u16 count, then per space: id + 4 neighbour slots (u16, `FFFF` = none). Links are always two-way. |
| `CommonData/fieldPosition/MASUNN.position` | node names (`Z0000`...), then x/y/z float32 per node |
| `Data_eng/dataSeq_EN/stageBase_EN.DAT` | space-kind names (marker `87`, from 0x5B0), town/castle table (marker `6D`, from 0xF34) |
| `CommonData/map/NamePlate_EN.texpack` | the board's name signs: 82 PNGs, 256x64 |

Board 0 is the overworld (337 spaces). Its screenshot is rotated 180 degrees from the board's x/z axes
(screen x = -1.17 * x + 136, screen y = -1.17 * z + 459 for the first continent).

## Space type, first byte = kind (names come from stageBase_EN.DAT)
`01` Item, `02` Magic, `03` Red Loot, `04` White Loot, `05` Locked Box, `06` Money, `07` Weapon, `08` Shield,
`09` Battle Magic, `0A` Bank, `0B` Collection, `0C` Poison Swamp, `0D` Snowfield, `0F` Warp, `11` Dark, `12` Trap,
`13` Doom, `14` **Town**, `15` **Castle**, `16` Weapon Store, `17` Item Store, `18` Magic Store, `1B` Casino,
`1C` Coliseum, `1D` Dokapon Castle, `1E` Plain, `1F` Forest, `20` Mountain, `21` Desert, `22` Ocean, `23` Swamp,
`24` Cave, `25` Lava, `26`-`5D` dungeon names and entrances/exits (`2D` Spring Cave Entrance, etc.).
Run `decode_tables.py` for the full list.

Second byte of the type: `FF`, or a skin value (it repeats in `param` for towns).
The overlay legend "Empty Space" is any of `1E`-`25` (terrain) plus `0D`/`0C` when the area has that effect.

## Town and castle spaces
`param` = `[town id u16][skin u16]`. Town id 8 = Ural. Castle ids (`15`) start at 0x32 (Khan's Castle).
Stores and the Coliseum have no id in `param`.

## Town table (stageBase_EN.DAT, marker `6D`, 55 records)
`6D 00 00 00 | id | continent | byte | 00 | name (null-terminated, padded to 4) | u32 | price u32 | u32`.
Name field capacity is the padded length (Ural: 8 bytes, 7 characters usable).

## Signs
`NamePlate_EN.texpack`: u32 count (82), 12 zero bytes, count x `[4 byte tag][u32 PNG size]`, then count x
`[16 byte name "NN.png"][PNG][pad to 16]`. Sign number = position in the town table + 3
(0-2 are the stores; castles follow the towns; temples, casino, caves etc. follow).
Not yet checked: whether the game ever builds a sign from text.

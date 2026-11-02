# Board data notes (PC version)

Decoded by matching the overworld continent screenshot against board 0. All 68 spaces on that continent
matched the legend colours one for one, and the 10 town spaces matched their town signs.

## Files
| File | Holds |
|---|---|
| `Data_eng/dataSeq_EN/stgNNN_EN.DAT` | one 16-byte record per space: `33 00 00 00`, index u32, type (2 bytes), group (1), 00, param (4 bytes) |
| `CommonData/fieldChain/CHAIN_NNN.DAT` | u16 count, then per space: id + 4 neighbour slots (u16, `FFFF` = none). Links are always two-way. The slot is the DIRECTION: 0 = +z, 1 = +x, 2 = -z, 3 = -x (true of all 754 links on board 0), and the reverse link uses slot (i+2)%4. So every road is axis-aligned. A link in the wrong slot or between spaces that are not on one axis lands fine but crashes the game when auto-path routes through it. Roads are drawn by the map model, not from this file: cutting a link leaves the road on screen. |
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

## What was tested in game (board 0)
- Swapping type + group + param between two space records: stores, towns and plain spaces all work (rules, shop stock and the sign follow the record). The building art does not follow.
- Building art: `dataField/F00/F00_{N,M,A}.model`; see `tools/igb/igbmodel.py`. Store, town-disc and castle buildings are placed by a 4x4 matrix in the file's MTRX chunk (translation in the last row), usually about 25 units from their space. Changing a matrix's translation moves the building (a game restart is enough, the installer repacks the model). Building to matrix: F00_M 24 castle 170, 43 magic 87, 5 magic 152, 44 magic 268, 20 item 122, 2 item 218, 45 item 237; F00_N 1 castle 76, 37 castle 311, 46 item 18, 14 item 59, 32 magic 287, 33 item 314. Weapon store 105 is baked into the geometry (not matrix placed). The Magic Store building is the purple potion with a star book and a wand; the Item Store is the blue building with a heart or window.
- Keep each building's own offset from its space when moving it, or it floats or sinks (ground height differs per area).

## Signs, shadows and the live tools (board 0, all tested in game)
- Nameplates (the wooden store/castle signs and the purple town pennants) are placed by a list at the end of `stg000_EN.DAT`: 92 entries of `u32 0x92, u16 space, u16 plate` starting at the entry for Item Store 18. Plate 1 = item store, 2 = weapon store, 3 = magic store, 4.. = individual towns, castles and so on (castles 52..58). Editing the space moves the plaque; swapping two spaces' records without swapping their plaques leaves the signs on the old spaces. `make_board_test.py` does both. The plate artwork is `NamePlate_EN.texpack`; an earlier test's shuffled copy stays patched in the CPK unless the vanilla one is shipped in the mod.
- Shadows are not tied to the building matrix. The ones tested are small flat clusters of vertices inside shared batch meshes (`F00_A` meshes 29 and 30 hold translucent patches of many kinds: building shadows, tree shadows and green water pools). A shadow can be moved by shifting only its cluster's vertices. Found so far: Magic Store 152 -> a 4-vertex square at about (317, -53) in `F00_A` mesh 30 (the building matrix sits 28 units from the space, so look near the building, not the space); the fan at (343, -102) is a tree. Item Store 218 -> `F00_A` mesh 18 (10 vertices, world positioned). The shadow of Item Store 59 is not in `F00_A` and not under an `F00_N` matrix.
- Everything is testable without reinstalling while the game runs on the board: `tools/live/matrix_poke.py` (one matrix), `matrix_live.py` (step through all matrices with pad or keyboard), `hide_near.py` (hide all matrices near a space), `mesh_poke.py` (collapse or show a mesh piece), `shadow_move.py` (shift one vertex cluster of a mesh). The game keeps both the matrices and the vertex data in ordinary writable memory, two copies each, and redraws from them.

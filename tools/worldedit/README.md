# World editor (board 0)

Paint a board's ground, move its spaces, change its links and place trees and mountains, then build a mod that draws it.
The ground is drawn only with the game's own textures and materials, so nothing new has to be added to the model files.

```
python world.py   world.json                 # the game's board 0 as a world file (ground, spaces, links, trees, mountains)
python world.py   d6.json --board 6          # a dungeon (boards 1-22) as a world file: spaces and links on its own art
python server.py  world.json                 # the editor: open http://localhost:8765
python build_world.py world.json mod_folder  # what the editor's Build button runs: mod_folder/Assets + world_map.png
```

Files: `terrain.py` (the ground grid and its meshes), `props.py` (trees, mountains, hills, bridges and decorations), `world.py` (the world file),
`build_world.py` (the mod), `dungeon.py` (the mod for a dungeon), `server.py` + `editor.html` (the editor). Board and art details are in
`tools/boardview/SpaceTypes.md`; the model file format is in `tools/igb/igbmodel.py`.

## The editor

| Tool | What it does |
|---|---|
| Paint (P) | Paints the chosen ground with a round brush (`[` `]` change its size). Alt+click picks the ground under the cursor. |
| Fill (F) | Fills a connected area of one ground. |
| Move (M) | Drag a space. It snaps into line with the spaces it links to (hold Shift to stop that). Arrow keys nudge it 1 unit, or 10 with Shift. |
| Link (L) | Click two spaces to add or remove the link between them. |
| Props (T) | Click to place a tree, mountain, hill, clover, flowers, mushroom or ice rock (the size slider picks one of the game's own). Drag to scatter trees. Shift+click removes the nearest one. Bridges are not placed by hand: the build puts them wherever a road crosses a river. |

- **Navigation:** right-drag or middle-drag pans, the wheel zooms, and Ctrl+Z / Ctrl+Y undo and redo.
- **Orientation:** the board is shown as on the numbered board map, with +x to the left and +z up.
- **Problems panel:** lists everything the build would refuse.
  - A link must be straight (axis-aligned).
  - Two links from one space can't leave in the same direction.
  - A space standing on the sea is a warning only (Ocean and dungeon spaces are left out).
- **Game board picture:** overlays the game's own board. It is rendered once and kept as `<world>.ref.png`.
- **Saving:** Save writes the world file; the first save of a session keeps the old one as `<world>.bak`.
- **Building:** Build also writes the mod to `<world>_mod` (or `--mod`) and shows the board it drew.

Not editable yet:
- Space kinds (shown, not changed).
- Adding or removing spaces.
- Building positions, which follow their spaces.
- Heights: the board is flat.

## How board 0 draws its ground

These findings come from the F00 model files. All of these are mesh pieces in `F00_A/M/N/Anim1/Anim2/wood.model`.

| Ground | Piece layer | Texture | Notes |
|---|---|---|---|
| Sea | `sea_01` (Anim1 piece 9) | `water_test.tga` | One plane at y 3.8 under the whole board. It has a rectangular hole at Dokapon Castle, whose moat is a separate `sea_01` piece (N 42) at y -2.5. |
| Grass | `green_01` | `test.tga`, tiled | Flat at about y 7. |
| Forest | `green_01` | `test.tga` | Grass darkened by vertex colour `5b7fae`, plus trees (`wood_01`, `ha.tga`). |
| Dirt | `jimem_01` | `jimem.tga`, tiled | |
| Sand, poison, swamp water | flat `town_01` triangles | tiles of the `objes.tga` building atlas | Sand is u 0-0.25 / v 0.5-0.75; poison and swamp water are the two halves of u 0-0.25 / v 0.25-0.375. |
| Snow | flat `road_01` triangles | snow tile of `fieldC.tga` | u 0.75-1 / v 0-0.25. |
| Coasts | `road_side_sea` ribbons | `fieldC.tga` | One strip, u 0.254 → 0.604: grass, ragged grass edge, sand, surf. It is about 29 units wide, flat at y 7.5, with the sand and surf hanging over the sea. |
| Rivers | `road_side_sea` | `fieldC.tga` | The beach strip, its sand and surf squeezed: each bank's strip reaches about a third of the way across. The game's grass fill runs on under the sand, so the shore is where the strip's grass stops (u 0.43), not where the fill does. |
| Moat | `sea_01` (N 42), `town_01` (N 38), `road_side` (A 211, Anim1 10) | `water_test.tga`, `objes.tga` rock strata, `fieldC.tga` | Dokapon Castle's: water at y -2.5 in a cut about 10 units across at the top and 5 at the water. Its sides are walls of the rock-strata tile (v 0.377 at the top to 0.496 at the foot, shaded `cec3ff` there), leaning in about 0.29 units per unit of drop. The grass's edge strip lies flat out over the wall's top, then its ragged end (up to u 0.225) hangs about 6 units down over the water, shaded darker (`788da1`). |
| Grass edges | `road_side` ribbons | `fieldC.tga` (u 0-0.248) | Grass ending in a ragged edge. Laid at y 8.6 wherever grass meets sand, dirt, the forest or narrow water. |
| Mountains | `mountain_01` / `mountain_02` | `MTA.tga` | One cone per cluster of vertices. |
| Trees | `wood_01` | `ha.tga` | Three crossed quads of leaves per tree, floating about 10 units above the ground; 71 stand on a bark trunk (`road_01`). 71 have a soft round shadow (not the same 71): a quad about 48 x 42 of the fieldC shadow blob in a `road_shadow` piece, about (-5, +7) from the tree; seven of these are draped over cliffs. |
| Hills | `town_01` + `green_01` | `objes.tga` rock-strata tile, `test.tga` | A ring of strata cliff (a piece of its own) around a raised grass top (another piece of its own). Four on the board: N 10+11, N 31+32, N 52+53, M 56+57. |
| Bridges | `road_01` | fieldC plank tile | An arched deck 22 units long and 14 wide, six posts, two rails; one along x and one along z in `F00_N` piece 55. The 73-vertex plank clusters elsewhere are the signposts. The bridge on the snow (link 172-173, along x) is in M 58, with snow caps on its deck and rails in A 80-83 (fieldC snow tile). |
| Snow coast | `road_01` + `road_side_sea` | fieldC ice tile (u 0.25-0.5) | An ice cliff straight down to the sea (v 0.5 at the top to 0.62 at the water), with a wavy snow lip along its top (v 0.625 to 0.75). Both run along u and across v, the other way round from the beach strip. |
| Sea lanes | `wave_01` (Anim2 5, 10) | `see_st.tga` | Not surf: light lanes about 22 units wide along every link with an Ocean space, at y 6; vertex alpha 0 at both edges and 0.7 (`b2`) in the middle. The game scrolls them through the material's `uTexOffset` uniform (there is no animation data in the files). The board has no surf off its shores: a shore's foam is the outer end of its beach strip. |
| Sea routes | `road_01` (A 29, A 62, A 212, A 219 ...) | fieldC blue line (u 0.752-0.998, v 0.623) | The blue line between two Ocean spaces, 22 wide at about y 6.5 over the lane, from tile to tile, with a tile of the same at each Ocean space. |
| One-way roads | `it_OP` (A 216, Anim2 16) | `it_002.tga`, scrolling | Red-and-white edged strips of arrows instead of a road: 285-286-287, and 223-226-227 (on to the sea). |
| Plateaus | `green_01` / overlays at y 14 | as on the ground | Two big ones (spaces 150-164 and 334, and 165-178 on the snow) and a few small raised spots, 7 units above the ground; spaces on them stand at 16.8. Roads climb them by slopes. |
| Plateau cliffs | `town_01` (M 2, M 5, M 14 ...) | `objes.tga` rock-strata tile (u 0-0.25 along, every ~24 units; v 0.377 at the top to 0.473 at the foot) | Leaning walls from the plateau down to the ground or into the sea, leaning out about 0.8 units per unit of drop, shaded bluish (`c2cdff`) at the foot. On snow the cliffs are of the fieldC ice tile instead, and steeper. |
| Decorations | `road_01` (a few in `road_shadow`), their shadows in `road_shadow` | `fieldC.tga`, bottom right corner | 164 clovers (a clover, a curled leaf and a small shadow), 33 bunches of flowers over a tuft of leaves, 29 mushrooms (yellow, purple, orange; each with a shadow) and 25 sparkly ice rocks on the snowfields. Many are pieces of their own, each placed by its own matrix. |
| Shadows, pools | `road_shadow` decals | `fieldC.tga` | |

Roads:
- **Roads:** `road_01` (see `tools/boardview/roads.py`).
- **Water paths:** the blue lines between two Ocean spaces are in the model files (see Sea routes above), on the light sea lanes.
- **Roads into the sea:** a road from land to an Ocean space is the plain line turning blue where it leaves the land (fieldC rows v 0.53-0.62, u 0.75-1), on to the Ocean space's blue tile.

Shaders:
- There are only two: `Map_ColoredTexture_Fog` and `Map_ColoredTexture_Fog_Water`.
- The `_Water` one ignores vertex colour, according to the board renders compared with the game. So tinting only works on `_Fog` pieces, such as grass and beaches.
- **Draw order (seen in game):** `_Fog_Water` pieces are drawn in file and node order (F00_A before the sea in Anim1, the sea before the surf in Anim2). They write depth even where they are clear, so anything drawn after them and below them is hidden there, leaving a flat blue patch. `_Fog` pieces such as the beaches don't do this.
  - So the tree shadows go into `Anim2:13` and the grass edges into `Anim2:14`: static `road_shadow` pieces drawn after the sea and the surf. Built into the shadows' old piece (A:10) and the edges' old one (A:211), they blanked out the beaches and water around them.

## How build_world.py draws a world

1. **Ground grid.** The ground is a grid of 5-unit cells, one letter each:
   - `.` sea, `g` grass, `f` forest, `s` sand, `w` snow, `d` dirt, `p` poison, `m` swamp, `o` moat.
   - A second layer, `levels`, gives each cell a height: `0` the ground, `1` a plateau 7 units up, `/` a slope between them (its height eased by distance to the nearest ground and plateau cells). The editor paints it under "Height".
   - `terrain.classify_model_files` reads the game's own board into this grid. It takes the highest fill triangle over each cell, then lets the game's strips redraw the shore: the grass end of a beach or edge strip is land, the sand and surf end of a beach strip is water. The plateau levels come from the fills' heights (hill tops above y 18 are left to the hill props).
2. **Fills.** Each ground's cell field is smoothed. Fills follow its 0.5 contour (marching squares), so their borders are curves.
   - Land gets a grass floor, with forest blended in by vertex colour.
   - Overlays (sand, snow, dirt, poison, swamp) are drawn over it.
   - Atlas tiles are mirrored once per 60-unit block, so their seams match.
3. **Ribbons.** These are laid along the smoothed contours:
   - Beaches on every shore; on rivers their sand and surf are squeezed to a third of the water's width.
   - Surf banks plus a grass edge on the narrowest water (under 18 units: the ends of creeks).
   - Moats: rock walls from the ground down to water at y -2.5 (in the moat piece, N 42), the grass edge lying over their rims and hanging down; a moat is not a shore, so it gets no beach or surf.
   - Grass edges around overlays, where there is grass beside them.
   - Cliffs along the edges of plateaus and slopes, from the raised ground down to the ground or into the sea; a raised shore has no beach or surf.
   - The sea plane is drawn again, with a rectangular hole over each moat (its box, one cell larger).
   - Everything on a plateau or slope is raised: its fills, edges, spaces, roads, trees and shadows. A bridge slopes from the ground at one end to the ground at the other.
4. **Where the meshes go.** Every mesh goes into a game piece that has the right layer, texture and shader, and that the board would hide anyway. Pieces can grow, up to 60,000 vertices each.
5. **Props.** Trees, mountains, hills and decorations are copies of the game's own, written into their template's pieces (`props.py`). Every tree is raised to the game's height; a tree whose template has a shadow in the game gets that shadow, where the game has it. Decorations keep the game's height, and their parts from `road_shadow` pieces go into `Anim2:13` with the tree shadows. The ones in the road piece (A:9, drawn again for the roads) go into A:204.
   - **Bridges:** wherever a road between two land spaces crosses water up to 60 units wide, the build puts the game's bridge across it (end to end, if one is not enough) and leaves the road strip out there. On the game's own board this finds the game's river crossings (80-19, 46-45, 88-101 ...) and a few more.
   - **Coasts:** snow meets the sea in the ice cliff and its lip instead of a beach. A beach narrows to nothing over a few metres where it gives way to a river bank, instead of stopping in a hard edge.
   - **Sea:** the game's sea lanes, moved along with the spaces of their links (a lane whose link is gone is left out); the blue line between Ocean spaces and a blue tile at each; roads from land run to that tile, turning blue at the shore. A space out on the open sea that is no Ocean space (the whirlpool) has only its lane. Spaces and roads out on the sea are not raised by a nearby plateau.
   - **One-way roads:** the arrow strips stand in for the road on their links, moved and stretched with their spaces, all in Anim2 16 (drawn after the ground).
6. **Everything else** is as in `tools/testpatch/make_void_board.py`:
   - Roads are drawn again for every link, with dirt only between two grass or forest spaces, and the line alone otherwise.
   - Buildings are moved with their spaces.
   - The camera limits grow with the board.
   - The Lava Cave, Daunting Mountain and the whirlpool are kept and moved.
   - Every other piece is hidden.

**Checking a build:** the regenerated vanilla board (`world.py` straight into `build_world.py`) is the reference to check a build against in game.

## Dungeons (boards 1-22)

Each dungeon has art of its own, made from its own textures:
- **Caves:** ice and water caves (1, 2, 15), lava caves (3-5).
- **Outdoor:** jungle (6), canyons (7-9), a meadow with a lake and bridges (22).
- **Built:** the sky palace (10), underwater ruins (11, 12), the fire castle (13, 14), the dark castle (16-18), the demon's hall (20).
- **Other:** hell (19), space (21).

All of it is in `CommonData/dataField/F01`-`F22`. `render_top.py --board N` draws any of them.

**What the editor does on a dungeon:**
- **Art:** the dungeon's art stays as it is and is shown under the spaces.
- **Spaces:** can be moved, and raised or lowered (Page Up / Page Down).
- **Links:** can be added and removed. They follow board 0's rules, allowing up to 3 units off straight (one link in dungeon 6 is 2 units off).
- **Paths:** every path is drawn again.

**Dungeon paths:**
- **What they are:** strips of their own pieces, apart from the floor.
- **Texture:** `street02.tga` (orange, white, orange across, repeating along). Boards 19 and 21 have path textures of their own: board 19's is a 27.8-wide glowing red line.
- **Size and height:** about 8 units wide (6.2 in some), 0.5 below the spaces.
- **Shape:** they bend over every bump of the floor. `dungeon.Surface` lays the new strips exactly where the old ones were, and just above the floor where the game had no path. A straight strip between two spaces would dip under the floor in places.
- **Links without a strip:** listed as `no_path_links` and left without one. The game shows these another way or not at all:
  - bridges (6, 22);
  - paths painted into the floor art (10, 21);
  - secret passages to loot spaces (19).
- **Toggling a strip:** Shift+click the second space with the Link tool switches a link between having a strip and not.

**Round trip:** exporting every dungeon unchanged and building it gives the same paths as the game, judged from renders of all 22.

**Not done for dungeons:**
- The floor, walls, stores and any art tied to a space do not move. A space moved off its floor stands in the void.
- `no_path_links` art, such as a bridge, does not follow a moved space.
- Ground painting needs a ground kit for each dungeon family. Only the lava caves have one so far (see below).

### Ground kits (`cavekit.py`): painting a dungeon's ground

A kit says which of a dungeon family's own textures draw which ground. It also reads that ground back from the game's art and builds a painted grid from the same textures. A dungeon with a kit is exported with a ground grid (`terrain.kit` is set). The editor then offers that kit's grounds, and `dungeon.py` draws the painted ground in place of the game's.

**Lava caves (boards 3, 4, 5).** The grounds are rock floor, lava, cave wall and pit.

| Part | Texture | How it is drawn |
|---|---|---|
| Floor | `f03_06` | Cracked rock, flat at y 0, darkened towards the cave walls. |
| Lava | `f03_08` | A sheet at y -15, written into the `F0x_UV` piece the game scrolls. |
| Drops into the lava | `f03_07` | Brown rock to red to white glow over the 15-unit drop. They lean out over the lava by 0.7 units per unit down, as the game's do; from above they are the glowing rim of every lava channel. |
| Cliffs at the cave's edge | `f03_05` | Banded rock up to y 50, fading to black. They lean back into the wall by the same 0.7; a thin wall's cliffs lean only halfway, so both sides meet in a ridge. |
| Cap | `f03_01` | Made near black by vertex colour (its texture is a gradient that would show as stripes), over the wall from where the cliffs top out. |
| Pits | `f03_05` walls | Rock walls straight down into black, with a black floor just above the lava. The game's caves have none; they can be painted. |
| Underlay | | A black floor under the wall and pits also hides any gap between a thin wall's cliffs and the cap. |

**Reading the game's caves:**
- The dark spots on the original floors are rock mounds (`f03_03`/`f03_04`), not holes, so they read as floor.
- Small gaps the art leaves by the cliffs and the lava take the ground around them.
- The rock details and board 5's lava fall are left out of a painted cave.

**Fixed heights:** a painted cave's floor is flat. Its spaces stand at y 1 and its paths lie at y 0.5.

**Checking it:**
- Exporting caves 3-5 and building them unchanged gives the same layout of floor, lava and walls as the game, judged from renders.
- The editor's paint, undo, save and build were tested on cave 5.

## Not done yet

- **Plateaus:** only one plateau height, and no cliffs between a slope's sides and the ground. Checked in tilted renders (`render_top.py --tilt 50`), not yet in game.
- **Shadows:** buildings have no shadows (their shadows are mixed into shared batch pieces; `units.py` knows some of them). The seven tree shadows the game drapes over cliffs are left out.
- **Moats:** checked in renders only. A moat's sea hole is its whole box, so a moat that reaches the sea leaves sunk water there; roads cross a moat with no bridge.
- **Decorations:** checked in renders only. A decoration moved onto other ground keeps the game's height above the old spot (plateaus apart).
- **Sea lanes:** a new link with an Ocean space gets the blue line but no light lane.
- **Snowy bridges:** only along x (the game has none along z).
- **Small spikes:** a few remain on the strips at very tight bends.
- **Not seen in game yet:** the moat, the decorations, the arrows, the sea routes and the snowy bridge. All of these have only been checked in renders.
- **Forest edge:** the forest edge is a soft blend, not the game's ragged dark edge.
- **Falling snow:** it is an exe effect around a fixed point (see `make_snow_patch.py`). It does not follow painted snow.
- **Not checked in game:**
  - Whether the game culls pieces by the bounding boxes of their parent nodes. If generated ground vanishes at some camera angles, that is the first thing to check.
  - Whether the vertex-colour forest tint shows.

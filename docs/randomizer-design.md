# Randomizer design: the big picture

Captured from a brainstorm. Nothing here is promised; it is the map of what we want, what it depends on, and the order to build it.
Facts about the game are in `item-records-and-effects.md`; this file is about the plan. Steam/PC build only.

## 0. Principles

- **Separate identity from behaviour.** An item is a bundle of: *identity* (name, icon, model, description), *stats and price*, and
  *effect* (an ability with odds). Today the game ties all three to one slot id. Every feature below is easier if we can move each
  part independently, so the data model (section 2) comes first.
- **Everything is seeded and logged.** One seed produces one result. Every run writes a spoiler log, and the seed plus the settings
  are summarised in a short hash so two players can check they have the same seed.
- **Logic, not chaos, where the game needs it.** Spaces, shops and monsters control whether the game can be finished. Those features
  go through a validator (section 4) rather than pure random draws.
- **Three tiers everywhere** (from the effects randomizer): *unchanged*, *shuffled* (same pieces, new places) and *randomized*
  (each piece rolls). Per-type percentages, weights and pinning work the same in every feature.
- **Patch code only when data can't do it.** Data edits go into `stageBase_EN.DAT`; code edits are hex mods that go in the slack at
  the end of `.text`, and each is a small, separately testable piece.

## 1. Feature list

### 1.1 Effects (the first big chunk)

a) **Mixed pool.** Effects can cross equipment kinds: a sword with a shield ability, a shield with a weapon ability, an accessory with
   either. Which effects are allowed to cross is a setting (per effect, per direction), because some do not make sense across kinds
   (for example a defender-side effect on a weapon has to fire when the *wielder is hit*).
b) **New effects.** The effect list can grow beyond the 22 weapon, 9 shield and ~10 accessory effects in the base game: new effects
   are small code routines added to a table-driven dispatcher.
c) **Accessories on the same footing.** Accessories get the same randomization tiers, odds control and mixed-pool status as
   weapons and shields. This needs their per-site hard-wired checks replaced with one table (section 2.3).

### 1.2 Equipment

- **Name and look swap (stats stay).** The Dokapon Sword might be Knife tier. Programmatically this is a remap of identity fields,
  not of ids (ids are referenced by shops, events and effect code), so it depends on the identity/stat split.
- **Logic-aware equipment placement.** Items are placed so the game is beatable, but not in vanilla order. For example the first
  shop might sell a cheap weapon that makes grinding that island possible, strong enough to beat the continent's town bosses and
  its roaming monsters. Needs a power model (section 4).
- **Shopkeeper/interior swap.** Enter the weapon shop but see the Magic Shop interior, selling weapons. Presentation (interior,
  keeper) is separate from stock, so this is mostly a mapping from shop to interior scene.

### 1.3 Classes

- Shuffle which abilities belong to which class, then roll or shuffle abilities per class (three tiers).
- Change which three classes you start with (for example Alchemist, Monk, Cleric). With static abilities each class keeps its
  empowered abilities; otherwise they roll or shuffle.
- Randomize per-level stat growth, skill costs and unlock levels.

### 1.4 Monsters

- **Skin swap:** the stat block stays (a bandit-level monster is as easy as a bandit) but it looks like a dragon.
- **Shuffle:** a dragon can appear on part of the first continent. Needs either more safe spaces, or a rule keeping the continent
  boss and other too-strong monsters out of early areas. Uses the same power model as equipment.
- Randomize stats, moves, drops, gold and XP rewards, and which boss gates which continent.

### 1.5 World

- **Dungeon entrance shuffle:** enter "Spring Cave" and end up in the lava mountain. Signs show the true destination so players
  are not surprised. Optionally use the world editor to move the actual structure to the entrance, so the swap is not jarring.
- **Shuffled spaces:** each continent's spaces are jumbled, with structures moved to match.
- **Space randomizer:** place every required structure first (towns, castles, shops), then every other space rolls from a chance
  sheet. Guarantee a few plain spaces per region so players can grind. The validator checks reachability and that every region has
  enough safe ground.
- **Week events:** weights for the weekly special event (frequent good ones, rare bad ones), or a fixed schedule from the seed. A
  stretch idea is an in-game item that forces the next week's event.
- **Continent shifts** and **custom dungeons/maps** come last; they depend on the world editor and on more graphics work.

### 1.6 Quality of life

- All hairstyles unlocked from the start.
- Starting state: gold, stats, class and equipment, including "choose one of three random starts".

### 1.7 More ideas worth adding

- Shop stock and prices, treasure and mystery-space rewards, town and town-boss rewards, and Magic Shop spell stock.
- Dice distribution and movement spells.
- Cosmetics: music and sound effects, palette swaps for monsters and players, randomized town names and flavour text.
- Difficulty modifiers: hard mode, one-hit KO, and handicaps for humans versus the AI.
- Tooling: spoiler log, seed hash shown in-game, presets, a GUI, and the beatability validator.

## 2. Data model

### 2.1 Items (identity, stats, effect)

Each item in a slot (kind + id) is described by three independent parts. `dokapon_rando/effect_model.py` is the start of this.

| Part | Today | Moves how |
|---|---|---|
| Identity: name, description | record text (`stageBase_EN.DAT`) | rewrite strings, keeping total description length |
| Stats, price | record tail | rewrite the tail; already works |
| Effect: id + odds | exe code keyed on the slot id | an `effect id` table per slot kind, read by the exe through a patch |

### 2.2 Effects as one list

An **effect** is a unit of behaviour with: a kind of *hook* (when it fires), a *vanilla source* (where its code lives), its vanilla
odds, and whether it can cross kinds. Effects are identified by a single id across all equipment, not by the slot that carried them
in the base game.

The hooks, as far as we know them:

| Hook | When | Where it lives | Read from |
|---|---|---|---|
| `attack` | the wielder hits | weapon effect function `0x140178C50`, `rcx` = action, weapon at `[rcx+0x18]` | the weapon struct |
| `defend` | the wielder is attacked, or picks Defend | shield dispatcher `0x1401786D0`, `rcx` = action, defender's shield at `[rcx+0x98]` | the shield struct |
| `turn start` | start of the wearer's turn | event picker `0x1401B1690`, odds in game-state ints | player accessory byte (`+0xC0`) |
| `passive` | stat changes, movement, Wanted, etc. | scattered, one site each | the player's accessory id |

### 2.3 What mixed pooling needs from the code

The game asks each hook one question: *which effect does the item in this slot have?* Today each hook answers from the slot id of
its own kind of item. To mix kinds:

1. Add a per-kind **effect table** (slot id -> effect id) in the exe's slack, and send every id read through it. Shields and
   weapons are already done this way (`patch_shield_effects.py`, `patch_exe.py`). Accessories still need it (section 3).
2. Make a hook ask about **all three equipped items**, not just its own kind. For `defend`, that means: the shield's effect, else
   the weapon's effect if it is a `defend` effect, else the accessory's. The action struct already carries the pointers, so a small
   helper in the slack can do this. A fixed priority order decides ties; stacking two effects of one hook is out of scope at first.
3. Hooks with unique code paths per effect (the accessories) need their sites turned into table lookups, one at a time.

Open risk: a few effects write the action's flag bits or call code that assumes an owner (for example Cursed and Dark damage the
*wielder*; Sun heals at Defend selection). Before an effect is allowed to cross kinds it needs a test that it still works from the
other hook.

### 2.4 Odds

Odds follow the effect, not the slot, once effects can move. Weapons already read the record's chance byte. Shields keep their
effect's compiled odds, and the shield patch rewrites those compares to read the record. Accessories are mixed: four read the
record, the Crystal Choker and Wallace Badge read game-state ints.

## 3. Investigation log: effect slots

What is known (see `item-records-and-effects.md` for addresses and evidence), and what is still open.

Known:
- Weapon and shield effects are table-driven switches keyed on id, so remapping them is solved. Both dispatchers are called with the
  battle action struct. The weapon function reads the attacker's weapon at `[action+0x18]`; the shield dispatcher reads the
  defender's shield at `[action+0x98]`. So a helper that sits in either path can reach the action's other fields, and finding where
  the action struct is filled (to learn where the defender's weapon and accessory pointers are) is the next step.
- Accessory effects are separate code at each site. Four read the record chance byte; the Crystal Choker and Wallace Badge read
  game-state ints; the rest are fixed.
- Shield effects are not just the dispatcher: the animation script reads the shield id (a value fetch at `0x1401717D6`). Any new
  id-read site we find needs the same remap.

Open, in the order to do them:
1. **Static pass for every reader of the weapon, shield and accessory id** in `.text` (struct offsets `+0x14A`, `+0x148`, `+0x140`
   on item structs, and the player bytes `+0xBE/+0xBF/+0xC0`). Output: a list of sites with a classification
   (effect code, script fetch, UI, shop, stat calc). Safe to do without the game.
2. ~~**Where the action struct is filled.**~~ Found: the constructor at `0x140055650` zeroes the pointer fields `+0x10..+0x28`
   and `+0x60..+0xB8`. Combined with the two dispatchers' reads, the layout is **(inferred, not yet watched)**: attacker character
   `+0x10`, weapon `+0x18`, shield `+0x20`, accessory `+0x28`; defender character `+0x88`, weapon `+0x90`, shield `+0x98`,
   accessory `+0xA0`. Confirmed ends: the weapon function reads `[+0x18]` and the shield dispatcher `[+0x98]`. If it holds, a cross-kind
   helper can find all six equipped items from the action struct alone. Next: check the other constructor sites
   (`0x140061D90`, `0x140079126`, `0x14008A01B`) agree, and find who fills the fields.
3. **Accessory effect inventory:** one row per accessory (id, name, hook, site, chance source, passive or not), so the accessory
   table can be designed. Needs live checks for the passive ones (needs the game and a controller; deferred).
4. **Cross-kind proof of concept:** a Wooden Sword that carries the Mirror reflect effect, via the helper in 2.3. Needs a live test.
5. **New effect proof of concept:** one new effect (for example a flat damage bonus) added as a new table entry.

Things that need the game running are queued behind the user being at the machine with a controller. The hardware-watch tools in
`tools/live` can be driven by a script, but the game needs a human to play a fight; a fully headless battle is not available.

## 4. Logic and validation

Anything that decides whether the game can be finished goes through a validator.

- **A power model:** a number for what a character can beat. Items, monsters and classes get a power rating from their stats and
  effects; the continent and region define the power needed to progress (town bosses, the continent boss).
- **Progression checks:** by each region, a player can afford at least one weapon and shield that clears the region's bosses and
  roaming monsters (the OoTR-style idea: ordering is shuffled, but the game stays beatable); every region has plain spaces to grind.
- **Reachability:** for the space randomizer and dungeon shuffle, every required place is reachable.
- The validator is built early and starts simple (equipment and shops only), then grows with each feature that needs it.

## 5. Build order

1. **Foundation:** seed handling, spoiler log, seed hash, the validator skeleton, and the item/effect data model (identity,
   stats, effect).
2. **Effects:** mixed pools, new effects, accessories on the same footing (needs section 3 steps 1-4).
3. **Equipment and shops:** name/look swap, logic-aware placement, shop interior swap.
4. **Classes.**
5. **Monsters.**
6. **Spaces and dungeons:** shuffle first, then the space randomizer, then entrance shuffle.
7. **Week events.**
8. **Continent shifts and custom maps.**

## 6. Known constraints

- Effect odds for shields live as literals in code; any new effect has to go through a table.
- Description text must keep its total length (the game reads descriptions sequentially).
- Hex mods only fit the current (October 2025) Steam build and the slack at the end of `.text`; the slack is finite
  (the weapon patch ends at RVA `0x44C490`, the shield patch at `0x44C580`). Bigger code needs a new section (`tools/testpatch/add_section.py`).
- Dynamic changes to spaces work live until a battle rebuilds the board.

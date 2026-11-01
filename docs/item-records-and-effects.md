# Item records and item effects (PC build, post Oct 2025 update)

Working notes on how weapons, shields and accessories are stored in `stageBase_EN.DAT`, which of the stored fields the game
actually uses, and where the item-effect code lives in `DkkStm.exe`. Written so nobody has to re-derive it. Everything here was
checked against the Steam PC build unless marked **(unverified)**. Addresses are virtual addresses (image base `0x140000000`);
for `.text`, file offset = VA - 0x140000000 - 0x1000 + 0x400.

## 1. The record file: `stageBase_EN.DAT`

Item tables are runs of records. Each record is a small header, a NUL-terminated name, padding to 4 bytes, then a fixed 20-byte
"tail" holding the numbers. Descriptions are stored separately, as one run of strings per item type, in item-id order.

| Item type | Marker byte | Count | Notes |
|---|---|---|---|
| Weapons | `0x58` | 67 | first record is at the start of the table the randomizer already locates |
| Shields | `0x5E` | 40 | table starts at `0xAB54` (`LocStatsShields` in `Randomizer.cs`) |
| Accessories | `0x52`..`0x5A` (a per-record type) | 33 | table at `0xBDAC`; header is `[u32 variant][u32 0x64][u16 id][u16 type]`, name at +12 |

### 20-byte tail

| Tail byte(s) | Weapon | Shield | Accessory |
|---|---|---|---|
| 0 | | **chance** | chance (`0x64` = always / passive) |
| 1 | | | tier |
| 2 | **chance** | | |
| 4-7 | price (u32 LE) | price | price |
| 8-15 | ATK / DEF / MAG / SPD | DEF / ATK / MAG / SPD | stats |
| 16-17 | | HP | |

Other places in the same file:

- Weapon descriptions start at `0x9B28`; shield descriptions follow the shield table (about `0xB200`), 40 strings. A line break is
  the two literal characters `\` `n`. The game reads the strings sequentially, so a replaced description must keep the total
  length (pad with spaces, keep one terminator) or every later description shifts. Accessory descriptions use `{c3}...{c-}` colour tags.
- Shop stock lists start at `0x5054`: per shop, `[weapon ids] 00 [shield ids] 00`. The count per shop is fixed.
- Starting equipment is a table at `0x1ACD0`: six 3-byte entries `(threshold, weapon id, shield id)`:
  `09 01 01 | 13 06 05 | 1d 0a 07 | 27 11 0a | 31 1d 10 | ff 24 16`. The new-character setup (`0x1402953F1..0x1402954F1`) takes
  the first entry whose threshold covers byte `+0x4B9` of the player, so a level-1 character gets `09 01 01` (Knife, Wooden Shield).
  The code at `0x1401104xx` / `0x140110aae` ("slot empty, give default 1") is only a fallback and does not set the starting loadout.

## 2. Why stat edits work but "chance" edits mostly don't

The game copies each record into an in-memory item struct at load. What reads those copies:

- **Stats and price** are read straight from the struct by the normal stat, shop and UI code. Editing them in the record changes
  the game. This is what the randomizer's stat shuffling relies on.
- **Chance** is only read where the code asks for it. The original developers wrote each ability with its odds as a **constant
  compiled into the roll** (`cmp cx, 25`), and the data field is just a copy that was left in the file (it matches the code
  constants, which is why it looks authoritative).
  - **Weapons:** the effect code did not read the field. `tools/testpatch/patch_exe.py` rewrites the first roll of each case to
    read the weapon struct's chance byte (`+0x139`), so for patched exes the field works.
  - **Shields:** nothing reads it. Changing a shield's chance byte has **no effect** in an unpatched exe. Proof: with every shield
    chance set to 100 in the file and the live game memory confirmed at `0x64`, a Binder still failed to interrupt attacks, and a
    watchpoint on the Binder record's chance byte (`+0x139`) never fired during battles. The odds live in the function in section 4.
  - **Accessories:** **(unverified)** the always-on ones (Criminal Studs and similar) are compared against their id directly in
    scattered code; see section 5.

Consequence for a shuffle: moving an effect to another item needs the code-side table to be redirected (done for weapons, planned
for shields), and the odds need to be edited in code or via a rewritten roll. Changing only the record is not enough.

## 3. In-memory layout (game state base `B`)

`B` is not fixed (ASLR/heap). Find it by scanning for the `Wooden Shield\0` name at `B + 0x31A80 + 0x150 + 0x14`
(see `watch_shield.py`).

| Structure | Address | Stride | Id | Chance | Notes |
|---|---|---|---|---|---|
| Weapons | `B + 0x2B5C0` | `0x170` | `+0x14A` | `+0x139` | |
| Shields | `B + 0x31A80` | `0x150` | `+0x148` | `+0x139` | 45 slots; the record for id N is slot N |
| Accessories | `B + 0x35598` | `0x148` | `+0x140` | `+0x139` | 40 slots |
| Players | `B + 0x24A0` | `0x508` | | | `+0x4A6` > 0 = special player with fixed ids; `[+0x70] == 0` = human; equipped weapon/shield/accessory ids are bytes `+0xBE`, `+0xBF`, `+0xC0` |
| Battle character | allocated per fight | `0x78` | | | `+0x18` weapon struct ptr, `+0x20` shield struct ptr, `+0x28` accessory struct ptr |

The player byte at `+0xBF` is the equipped shield id, not a pointer.

## 4. Shield effects: where the procs happen

One function dispatches every ability shield. It lives at roughly `0x1401786E0` (the head is inside a jump-table-heavy area, so a
linear disassembly is misaligned just before it):

```
1401786e6  movzx eax, byte ptr [rax + 0x148]   ; shield id
1401786f4  add   eax, -0xf                      ; id - 15
1401786f7  cmp   eax, 0x18                      ; ids 15..39 only
1401786fa  ja    default (0x140178a70)
140178709  mov   eax, [rdx + rax*4 + 0x178a74]  ; jump table, RVAs, file offset 0x177e74
```

Case table (id -> case address -> roll compare). Each roll draws from a shared random table (`word [0x...4a7820 + (n & 0xfff)*2]`
reduced mod 101) and procs when `roll < N`. Every case first checks `byte [global + 0x160] & 0x40` and skips the roll when set
(an "always" switch; **(unverified)** it is probably a debug option).

| Id | Shield | Case VA | Compare (VA of `cmp cx, imm8`) | Odds | Returns |
|---|---|---|---|---|---|
| 15 | Warrior | `0x1401788CB` | `0x14017891E` | 25 | `r9 = 1` |
| 20 | Mirror | `0x1401789FA` | `0x140178A57` | 12 | `r9 = 4` |
| 21 | Binder | `0x14017892A` | `0x140178983` | 25 | `r9 = 2` |
| 30 | Metal Guard | `0x140178992` | `0x1401789EB` | 12 | `r9 = 2` |
| 31 | Sun | `0x1401787F3` | `0x14017883C` | 12 | sets `0x800` in `[r8+0x138]`, sets `[r8+0x13E]` |
| 32 | Cursed | `0x14017874C` | `0x140178795` | 25 | sets `0x800` in `[r8+0x138]`, `[r8+0x13E]` = quotient |
| 36 | Athena's | `0x140178A6A` | none | always | `r9 = 8` |
| 38 | Dark | `0x140178715` | none | always | sets `0x800` in `[rcx+0x138]`, damage = 2 x level |
| 39 | Dokapon | `0x140178867` | `0x1401788B0` | 12 | sets `0x800` in `[r8+0x138]` |

The flag values 1, 2, 4, 8 are the return code consumed by the
caller; that Warrior = 1 (status block), Mirror = 4, Athena's = 8 is **inferred** from the shield descriptions, not traced.
Binder and Metal Guard both return 2, so what separates them is decided by the caller or by a second id check **(unverified)**.
Ids 16-19, 22-29, 33-35, 37 fall to the default (no effect), including Paladin (18) and Shell (22), whose effects, if any, are
elsewhere.

### Who calls the dispatcher, and the attack-type gate

The dispatcher (entry `0x1401786D0`) has one caller, the battle-action resolver at `0x140177390` (`rcx` = battle action struct):

```
140177401  cmp ebp, 5            ; ebp = [action + 0x58]; 5 = skip shield handling entirely
14017740a  mov ecx, edi          ; edi = [action + 0xD0]
14017740c  sub ecx, 1 ; je ->  call 0x1401786d0   ; type 1: ability-shield dispatcher
140177411  cmp ecx, 3 ; jne skip; call 0x140178ae0 ; type 4: a separate function (own table, keyed off [attacker + 0x120])
140177428  mov r14d, eax         ; the flags, then passed to 0x140175b60 / 0x140179e70 / 0x14017abb0 / 0x140178c50
```

So whether a shield effect can fire is decided by the attack's type field (`+0xD0`) and action field (`+0x58`), not by the shield.
Two shields that return the same flag get the same treatment. Binder (id 21) and Metal Guard (id 30) both return flag 2, and in
play both interrupt the attack and send damage back, so they are the same effect; only the odds (25% vs 12%) and the animation
differ. **(Observed, not yet explained in code.)** The shield descriptions ("interrupts attacks" vs "reflects exact damage") are
two names for one behaviour. Which command types map to `+0xD0 == 1` (for example whether Strike counts) is not yet traced.

## 4b. Test results so far (always-proc patch + effect remap installed)

Observed in play on the PC build, with every shield effect forced to proc each time (`make_shield_always.py`):

| Shield (id) | Result |
|---|---|
| Mirror (20) | Reflects battle magic every time. |
| Binder (21) and Metal Guard (30) | Same behaviour: the attack is interrupted and the damage the attack would have dealt is sent back to the attacker (it killed a stronger attacker; it did 66 to an attacker vs a 30 ATK / 18 DEF exchange, far above the wielder's own damage). Different animation only. Neither triggers against a Strike. |
| Sun (31) | Heals the defender **when the Defend command is chosen**, not after an attack, and without needing an attack at all. |
| Effect remap (`patch_shield_effects.py`, three id reads) | Verified in play: shield 1 (Wooden) mapped to effect 20 reflects and its Pickpocket animation is interrupted exactly like the real Mirror Shield; shield 15 (Warrior) mapped to effect 31 heals on Defend with Sun's tell; the real Mirror Shield is unchanged; shield 20 mapped to effect 0 stops reflecting. |

Not yet observed: Warrior (status block), Cursed, Dokapon, Athena's and Dark.

Consequences for building on this:
- The effect code does not apply the effect inside the dispatcher alone: it writes flag bits into the battle action
  (`[action + 0x138]`, `0x800` set by Sun, Cursed and Dokapon; `+0x13E` a value) that other code reads. One reader is `0x1402013D3`
  (`test word [r15 + 0x138], 0x800`), which forces a result to 100. Sun's heal is applied at Defend selection, which is a
  different call into the same dispatcher, so odds apply once per Defend choice.
- **Accessory odds are data-driven.** The Mirror Necklace roll at `0x140201443`..`0x1402014C3` compares a 0..99 roll against the accessory
  struct's chance byte (`[acc + 0x139]`, struct base `B + 0x35598`, stride `0x148`), so editing an accessory's chance in the record
  does change its odds. Shield odds, in contrast, are literals in the dispatcher (section 4).

### The presentation reads the id too (battle-script fetch)

With only the dispatcher remapped, a Wooden Shield wired to Mirror reflected correctly but the Pickpocket animation and message played
as if nothing happened. The animation and message scripts get the defender's shield id from a value-fetch switch at
`0x1401717D6` (`movzx r9d, byte [rax + 0x148]`, `rax` = the battle character's shield struct; sibling cases of the same switch
fetch the weapon id at `+0x14A`, and so on). The scripts compare it against shield ids in data. Sending that read through the same
id table makes the scripts see the effect's id, and the right animation and text play. Found by hardware read watchpoints on the
real Mirror Shield's id byte and on the Wooden Shield's during a Pickpocket (see section 6); the only non-dispatcher reader that
fired in the fight was this one.

To test: setting every compare's immediate to 101 (`66 83 F9 65`) makes every shield proc each time. `tools/testpatch/make_shield_always.py` builds that hex mod; `make_shield_test.py` makes the data side (cheap shields, shop stock).

Other shield-id sites seen: `0x140175405` (Dokapon, id 0x27, tests battle-char flag `0x800`) and range checks on id `0x25`.

## 5. Weapon effects and accessories

- Weapon effects: the attacker function at `0x140178C50`, effect switch head at `0x140178CB5`/`0x140178CD2`, original byte table
  `0x179E38`. See `tools/testpatch/patch_exe.py` (docstring and constants) for the case-to-VA map and the redirected table.
- Accessories: **(unverified)** scattered direct id compares, e.g. Mirror Necklace (`0x14`) around `0x140201415`, Dodge Necklace
  (`0x15`) `0x1400EB5E1`, Angel Choker (`0x16`) `0x1400E6A9C`, Criminal Studs (`0x1F`, +30 stat when Wanted) `0x1401F1547`,
  Wind Bracelet (`0x12`) `0x14017A62A`, Crystal Choker (`0x13`) `0x14010BB5F`. A helper at `0x1401EAA10(flags@char+0xC4, abilityId)`
  answers some "ability flag" queries.

## 6. How this was found (to repeat or extend)

Scripts live in the scratchpad used for the work; the technique is simple:

1. Launch the game under a Win32 debugger (ctypes `CreateProcess` with `DEBUG_ONLY_THIS_PROCESS`).
2. Scan memory for the item name to find the struct base, then set hardware watchpoints (DR0-DR3, read/write) on the byte you
   care about and log the RIP and stack of each hit.
3. Disassemble around the logged RIPs. A write watch finds who changes a field; a read/write watch on the **id** byte found the
   shield dispatcher above. A watch on the **chance** byte found nothing, which is how we proved it is not used.

Dead-code check: a static scan (`.pdata` functions plus uncovered gaps, treating any data pointer as a root) found 341 functions
(25 KB) with no static reference. That is not proof they are unused (the Steam networking code is live but reached indirectly), so
treat those as candidates only.

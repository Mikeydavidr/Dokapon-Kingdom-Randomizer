"""Start every human player with a battle magic and/or a skill (for example Rust and Waterfall, the two abilities that break equipment).

What the game does (static reading of the exe; see docs/randomizer-design.md): a player holds the equipped battle magic as an id byte at
player+0xC1, the equipped skill at +0xC2 (the same byte the "slot empty" fallback fills with 0x16), and a bit per known battle magic in the dword
at +0x74. The new-game setup function (0x1402953E0) fills the starting weapon and shield for each player, then runs
    mov edx, 4 / mov rcx, rbx / call 0x1401F1260        ; rbx = the player
The first instruction (5 bytes) becomes a jump to a cave that, for human players (player+0x70 == 0), sets those fields, then runs
the displaced instruction and jumps back. Spell and skill ids are the records' ids in stageBase_EN.DAT (Rust = 23, Waterfall = 38).
UNTESTED IN PLAY: the meaning of +0xC1/+0xC2/+0x74 is inferred from how the game's own loaders write them.
"""
import struct

from .exe import Exe, HexMod, foff, rva_to_va

HOOK_VA = 0x1402954F1                                   # mov edx, 4
HOOK_OLD = bytes.fromhex("BA 04 00 00 00")
RETURN_VA = 0x1402954F6                                 # mov rcx, rbx (the next instruction)
CAVE_RVA, CAVE_END = 0x44C5A0, 0x44C600                 # after the shield patch (it ends at 0x44C580); .text slack ends at 0x44C600

RUST, WATERFALL = 23, 38                                # record ids in stageBase_EN.DAT


def build_cave(cave_va: int, spell: int | None, skill: int | None, humans_only: bool = True) -> bytes:
    body = b""
    if spell is not None:
        if not 1 <= spell < 32:
            raise ValueError("battle magic ids are tracked in one dword, so 1..31")
        body += b"\xC6\x83" + struct.pack("<iB", 0xC1, spell)               # mov byte [rbx+0xC1], spell
        body += b"\x81\x4B\x74" + struct.pack("<I", 1 << spell)             # or dword [rbx+0x74], 1 << spell
    if skill is not None:
        if not 1 <= skill < 256:
            raise ValueError("skill id is one byte")
        body += b"\xC6\x83" + struct.pack("<iB", 0xC2, skill)               # mov byte [rbx+0xC2], skill
    head = b"\x83\x7B\x70\x00" + b"\x75" + bytes([len(body)]) if humans_only else b""   # cmp dword [rbx+0x70],0 / jne skip
    tail_at = cave_va + len(head) + len(body)
    tail = b"\xBA\x04\x00\x00\x00"                                          # the displaced mov edx, 4
    jmp = b"\xE9" + struct.pack("<i", RETURN_VA - (tail_at + len(tail) + 5))
    return head + body + tail + jmp


def apply_start_abilities(exe: Exe, mod: HexMod, spell: int | None = RUST, skill: int | None = WATERFALL, humans_only: bool = True) -> None:
    """Add the hook and cave to `mod`. Pass None to leave the spell or the skill out."""
    if spell is None and skill is None:
        return
    exe.expect(HOOK_VA, HOOK_OLD)
    exe.check_cave_empty(CAVE_RVA, CAVE_END)
    cave_va = rva_to_va(CAVE_RVA)
    cave = build_cave(cave_va, spell, skill, humans_only)
    if CAVE_RVA + len(cave) > CAVE_END:
        raise ValueError("start-ability cave does not fit")
    mod.add(*exe.map_slack_edit())
    mod.add(foff(cave_va), cave)
    mod.add(foff(HOOK_VA), b"\xE9" + struct.pack("<i", cave_va - (HOOK_VA + 5)))

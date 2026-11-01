"""Rewrites the shop descriptions of shields whose effect isn't their own, so they say what the shield really does.
The shield descriptions are 40 null-terminated strings in id order (first: "A shield made of oak."), each padded to a multiple of
4 bytes. The game walks them one after another, so a rewritten one must keep its slot size: the text is padded with spaces and
ends in a single terminator. A line break is the two characters backslash, n.

usage: python write_shield_descriptions.py <stageBase_EN.DAT> [shield_id=effect_id[:odds] ...]
  effect_id as in patch_shield_effects.py (0 = no effect); odds is the percent the shield procs (default: the effect's own).
  Edited in place. Shields not listed, or listed with their own effect, keep their original text.
"""
import sys

# effect id -> (full line, short line, vanilla odds in percent; 100 = always on).
# Warrior, Cursed, Athena's, Dark and Dokapon are worded from the community wiki and have not all been watched in play.
EFFECTS = {
    15: ("Block status ailments", "Block ailments", 25),
    20: ("Reflect battle magic", "Reflect magic", 12),
    21: ("Reflect an attack's damage", "Reflect attack", 25),
    30: ("Reflect an attack's damage", "Reflect attack", 12),
    31: ("Fully heal when defending", "Heal on defend", 12),
    32: ("Damages the wielder", "Hurts wielder", 25),
    36: ("Halve battle magic damage", "Half magic dmg", 100),
    38: ("Damages wielder, 2x level", "Hurts wielder", 100),
    39: ("Reduce opponent's damage", "Reduce damage", 12),
}

NUL = bytes([0])


def slots(sb):
    """(position, size) of the 40 descriptions. Anchored on the second one so that re-running over an edited file still works."""
    pos = sb.find(b"A very lightweight shield")
    assert pos >= 0, "shield descriptions not found"
    while sb[pos - 1] == 0:      # back over the padding after the first description
        pos -= 1
    while sb[pos - 1] != 0:      # back over its text, to the padding of the weapon run before it
        pos -= 1
    out = []
    for _ in range(40):
        end = sb.index(NUL, pos)
        nxt = end
        while sb[nxt] == 0:
            nxt += 1
        out.append((pos, nxt - pos))
        pos = nxt
    assert sb[out[39][0]:].startswith(b"An evil shield said t"), "last shield description is not where expected"
    return out


def text_for(effect, odds, size):
    if effect == 0:
        return "No special effect."
    full, short, _ = EFFECTS[effect]
    chance = "Always on" if odds >= 100 else f"{odds}% chance"
    text = full + "\\n" + chance
    if len(text) >= size:
        text = short + ("" if odds >= 100 else f" {odds}%")
    return text


def write(sb, mapping):
    """mapping: shield id -> (effect id, odds or None). Returns the number of descriptions rewritten."""
    sl = slots(sb)
    n = 0
    for sid, (eff, odds) in mapping.items():
        if eff == sid and odds is None:
            continue
        odds = EFFECTS[eff][2] if (odds is None and eff) else (odds or 0)
        pos, size = sl[sid - 1]
        text = text_for(eff, odds, size)
        if len(text) >= size:
            print(f"  shield {sid}: no room for {text!r} in {size} bytes, left alone")
            continue
        sb[pos:pos + size] = text.ljust(size - 1).encode("ascii") + NUL
        print(f"  shield {sid}: {text!r}")
        n += 1
    return n


if __name__ == "__main__":
    path = sys.argv[1]
    mapping = {}
    for a in sys.argv[2:]:
        sid, rest = a.split("=")
        eff, _, odds = rest.partition(":")
        mapping[int(sid)] = (int(eff), int(odds) if odds else None)
    sb = bytearray(open(path, "rb").read())
    n = write(sb, mapping)
    open(path, "wb").write(sb)
    print(f"rewrote {n} shield descriptions")

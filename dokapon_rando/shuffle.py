"""The shuffle framework: deal the game's own data out to different slots.

A slot keeps its id, price and stats, so every part of the game keeps the power curve it was balanced around. The identity
(name, type, special ability data) is what moves between slots.
"""
import random
from dataclasses import dataclass

from .gamefile import GameFile
from .tables import Table, TableSpec, read_table, write_table

# Items at or below this base price are story/unbuyable items (2 is also the lowest price the game uses)
STORY_ITEM_MAX_PRICE = 2


def equipment_specs(game: GameFile) -> list[TableSpec]:
    """Weapons, shields and accessories as the shuffler sees them. Moves: type, name, ability data. Stays: price, stats, order."""
    b = game.build
    return [
        TableSpec("WEAPON", b.weapons, 0x58, 1, "SII", "IIII" + "S" * 16, 4),
        TableSpec("SHIELD", b.shields, 0x5E, 1, "SII", "IIII" + "S" * 16, 4),
        TableSpec("ACCESSORY", b.accessories, 0x64, 1, "SII", "IIII" + "S" * 16 + "IIII", 4),
    ]


@dataclass
class ShuffleResult:
    label: str
    moves: list[tuple[int, str, int | None, str]]   # (id, original name, price, name now)


def shuffle_table(table: Table, rng: random.Random, include_story: bool) -> tuple[list[int], bytes]:
    """Shuffle one table. Returns (order, new bytes): slot i received the identity that started on slot order[i]."""
    spec, records = table.spec, table.records
    pool = [i for i in range(len(records))
            if include_story or spec.price_offset < 0 or records[i].price(spec) > STORY_ITEM_MAX_PRICE]
    order = list(range(len(records)))
    # Fisher-Yates over the pool
    for i in range(len(pool) - 1, 0, -1):
        j = rng.randrange(i + 1)
        order[pool[i]], order[pool[j]] = order[pool[j]], order[pool[i]]

    out = bytearray()
    for i, slot in enumerate(records):
        donor = records[order[i]]
        out += slot.head
        out += bytes(donor.prefix[k] if spec.prefix_mask[k] == "I" else slot.prefix[k] for k in range(len(slot.prefix)))
        out += donor.name_field
        out += bytes(donor.tail[k] if spec.tail_mask[k] == "I" else slot.tail[k] for k in range(len(slot.tail)))
    return order, bytes(out)


def shuffle_tables(game: GameFile, specs: list[TableSpec], seed: int, salt: int = 0, include_story: bool = False) -> list[ShuffleResult]:
    """Shuffle every table in the list. Each table is its own pool."""
    rng = random.Random(seed + salt)
    results = []
    for spec in specs:
        table = read_table(game.data, spec)
        if table is None:
            print(f"Couldn't recognize the {spec.label.lower()} table layout, skipping it.")
            continue
        order, blob = shuffle_table(table, rng, include_story)
        if len(blob) != table.end - table.start:
            print(f"The shuffled {spec.label.lower()} table changed size, skipping it.")
            continue
        game.data[table.start:table.end] = blob
        results.append(ShuffleResult(spec.label, [
            (r.id, r.name, r.price(spec) if spec.price_offset >= 0 else None, table.records[order[i]].name)
            for i, r in enumerate(table.records)]))
    return results


def shuffle_equipment(game: GameFile, seed: int, include_story: bool = False) -> list[ShuffleResult]:
    """Weapons, shields and accessories each keep their own pool."""
    return shuffle_tables(game, equipment_specs(game), seed, 0, include_story)


def format_log(results: list[ShuffleResult]) -> str:
    lines = []
    for res in results:
        lines.append(f"\n\n == {res.label} SHUFFLE (slot: original -> now) == ")
        for i, price, name, now in ((r[0], r[2], r[1], r[3]) for r in res.moves):
            lines.append(f"ID #{i}" + (f" ({price}G)" if price is not None else "") + f": {name} -> {now}")
    return "\n".join(lines)

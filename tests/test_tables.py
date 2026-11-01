"""Checks against the real game file, which can't be committed. Point DKK_STAGEBASE at an UNMODIFIED stageBase_EN.DAT
(the .backup the randomizer makes is one); the tests are skipped when it isn't set."""
import os
import random
from pathlib import Path

import pytest

from dokapon_rando.gamefile import GameFile
from dokapon_rando.shuffle import equipment_specs, shuffle_equipment, shuffle_table
from dokapon_rando.tables import read_table, write_table

PATH = os.environ.get("DKK_STAGEBASE")
pytestmark = pytest.mark.skipif(not PATH or not Path(PATH).exists(), reason="set DKK_STAGEBASE to an unmodified stageBase_EN.DAT")


@pytest.fixture
def game():
    return GameFile(PATH)


def test_record_counts(game):
    counts = {s.label: len(read_table(game.data, s).records) for s in equipment_specs(game)}
    assert counts == {"WEAPON": 67, "SHIELD": 40, "ACCESSORY": 33}


def test_tables_round_trip_byte_for_byte(game):
    original = bytes(game.data)
    for spec in equipment_specs(game):
        table = read_table(game.data, spec)
        assert table.serialize() == original[table.start:table.end]
        write_table(game.data, table)
    assert bytes(game.data) == original


def test_known_records(game):
    shields = {r.id: r.name for r in read_table(game.data, equipment_specs(game)[1]).records}
    assert shields[1] == "Wooden Shield" and shields[20] == "Mirror Shield" and shields[21] == "Binder"


def test_shuffle_keeps_size_and_the_set_of_names(game):
    before = {s.label: sorted(r.name for r in read_table(game.data, s).records) for s in equipment_specs(game)}
    size = len(game.data)
    shuffle_equipment(game, seed=1234)
    assert len(game.data) == size
    after = {s.label: sorted(r.name for r in read_table(game.data, s).records) for s in equipment_specs(game)}
    assert before == after


def test_shuffle_keeps_prices_and_stats_in_their_slots(game):
    specs = equipment_specs(game)
    before = {s.label: [(r.id, r.tail[4:8], r.tail[8:24]) for r in read_table(game.data, s).records] for s in specs[:2]}
    shuffle_equipment(game, seed=99)
    after = {s.label: [(r.id, r.tail[4:8], r.tail[8:24]) for r in read_table(game.data, s).records] for s in specs[:2]}
    assert before == after


def test_same_seed_same_result_and_different_seed_differs(game):
    a, b, c = (GameFile(PATH) for _ in range(3))
    shuffle_equipment(a, 5)
    shuffle_equipment(b, 5)
    shuffle_equipment(c, 6)
    assert a.data == b.data and a.data != c.data


def test_story_items_stay_unless_asked(game):
    spec = equipment_specs(game)[0]
    table = read_table(game.data, spec)
    story = [i for i, r in enumerate(table.records) if r.price(spec) <= 2]
    order, _ = shuffle_table(table, random.Random(7), include_story=False)
    assert all(order[i] == i for i in story)

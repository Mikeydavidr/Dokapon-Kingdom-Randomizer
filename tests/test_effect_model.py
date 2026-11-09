import unittest

from dokapon_rando import effect_model as m


class EffectModelTest(unittest.TestCase):
    def test_counts_and_unique_keys(self):
        effects = m.all_effects()
        self.assertEqual(len([e for e in effects if e.kind == m.Kind.WEAPON]), 22)
        self.assertEqual(len([e for e in effects if e.kind == m.Kind.SHIELD]), 9)
        self.assertEqual(len(m.by_key()), len(effects))

    def test_hooks_match_kinds(self):
        for e in m.all_effects():
            if e.kind == m.Kind.WEAPON:
                self.assertEqual(e.hook, m.Hook.ATTACK)
            if e.kind == m.Kind.SHIELD:
                self.assertEqual(e.hook, m.Hook.DEFEND)

    def test_candidates_stay_in_kind_until_something_is_movable(self):
        shield_pool = m.candidates_for(m.Kind.SHIELD, allow_cross=True)
        self.assertTrue(all(e.kind == m.Kind.SHIELD or e.movable for e in shield_pool))
        self.assertEqual(len(m.candidates_for(m.Kind.WEAPON)), 22)


if __name__ == "__main__":
    unittest.main()

import unittest
from proxy_helper import assign_cards

class TestProxyHelper(unittest.TestCase):
    def test_all_real(self):
        # All cards owned, no proxies needed
        decklists = {"Deck1": [("A", 1), ("B", 1)], "Deck2": [("A", 1), ("C", 1)]}
        collection = {"A": 2, "B": 1, "C": 1}
        assignments, _, _, _, status = assign_cards(decklists, collection)
        for a in assignments:
            self.assertEqual(a["qualityProxy"], 0)
            self.assertEqual(a["tempProxy"], 0)
            self.assertEqual(a["missingOwned"], 0)
            self.assertEqual(a["missingUnowned"], 0)
        self.assertEqual(
            len([k for k in status if status[k]["has_missingOwned"] or 
                                       status[k]["has_missingUnowned"] or
                                       status[k]["has_qualityProxy"] or 
                                       status[k]["has_tempProxy"]]), 0)
        for s in status.values():
            self.assertFalse(s["has_missingOwned"])
            self.assertFalse(s["has_missingUnowned"])
            self.assertFalse(s["has_qualityProxy"])
            self.assertFalse(s["has_tempProxy"])

    def test_binder_reserve(self):
        # Not enough for all decks, new greedy algorithm should complete one deck with real cards
        # and assign missing owned proxies to the other deck
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 1}
        assignments, binder_reserved, _, _, _ = assign_cards(decklists, collection)
        
        # With greedy algorithm, one deck gets real cards, other gets missing owned proxies
        real_counts = [a["real"] for a in assignments if a["card"] == "A"]
        missing_owned_counts = [a["missingOwned"] for a in assignments if a["card"] == "A"]
        missing_unowned_counts = [a["missingUnowned"] for a in assignments if a["card"] == "A"]
        
        # Should have exactly one real card assignment and one missing owned assignment
        self.assertEqual(sum(real_counts), 1)
        self.assertEqual(sum(missing_owned_counts), 1)
        self.assertTrue(all(up == 0 for up in missing_unowned_counts))

if __name__ == "__main__":
    unittest.main(verbosity=2)
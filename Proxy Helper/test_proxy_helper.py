import unittest
from proxy_helper import assign_cards

class TestProxyHelper(unittest.TestCase):
    def test_all_real(self):
        # All cards owned, no proxies needed
        decklists = {"Deck1": [("A", 1), ("B", 1)], "Deck2": [("A", 1), ("C", 1)]}
        collection = {"A": 2, "B": 1, "C": 1}
        assignments, _, _, _, status = assign_cards(decklists, collection)
        for a in assignments:
            self.assertEqual(a["owned_proxy"], 0)
            self.assertEqual(a["unowned_proxy"], 0)
        self.assertEqual(len([k for k in status if status[k]["has_owned_proxy"] or status[k]["has_unowned_proxy"]]), 0)
        for s in status.values():
            self.assertFalse(s["has_owned_proxy"])
            self.assertFalse(s["has_unowned_proxy"])

    def test_binder_reserve(self):
        # Not enough for all decks, should reserve 1 in binder, both decks get owned proxies
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 1}
        assignments, binder_reserved, _, _, _ = assign_cards(decklists, collection)
        self.assertIn("A", binder_reserved)
        real_counts = [a["real"] for a in assignments if a["card"] == "A"]
        self.assertTrue(all(r == 0 for r in real_counts))
        owned_proxy_counts = [a["owned_proxy"] for a in assignments if a["card"] == "A"]
        self.assertTrue(all(op == 1 for op in owned_proxy_counts))
        unowned_proxy_counts = [a["unowned_proxy"] for a in assignments if a["card"] == "A"]
        self.assertTrue(all(up == 0 for up in unowned_proxy_counts))

    def test_owned_proxy(self):
        # Not enough for all decks, but have some owned for proxies (same as above)
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 1}
        assignments, binder_reserved, _, _, _ = assign_cards(decklists, collection)
        self.assertIn("A", binder_reserved)
        owned_proxy_total = sum(a["owned_proxy"] for a in assignments if a["card"] == "A")
        unowned_proxy_total = sum(a["unowned_proxy"] for a in assignments if a["card"] == "A")
        self.assertEqual(owned_proxy_total, 2)
        self.assertEqual(unowned_proxy_total, 0)

    def test_unowned_proxy(self):
        # No cards owned, all proxies must be unowned
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 0}
        assignments, binder_reserved, slu, _, _ = assign_cards(decklists, collection)
        for a in assignments:
            self.assertEqual(a["real"], 0)
            self.assertEqual(a["owned_proxy"], 0)
            self.assertEqual(a["unowned_proxy"], a["needed"])
        self.assertEqual(len(binder_reserved), 0)
        self.assertEqual(len(slu), 2)  # Both decks in shopping list unowned

    def test_deck_completion_stats(self):
        # Both decks complete (all real) if enough copies
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 2}
        assignments, _, _, _, status = assign_cards(decklists, collection)
        complete = [d for d, s in status.items() if not s["has_owned_proxy"] and not s["has_unowned_proxy"]]
        self.assertEqual(len(complete), 2)
        for a in assignments:
            if a["card"] == "A":
                self.assertEqual(a["real"], 1)
                self.assertEqual(a["owned_proxy"], 0)
                self.assertEqual(a["unowned_proxy"], 0)

    def test_no_negative_assignments(self):
        # Edge case: not enough cards, ensure no negative assignments
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)]}
        collection = {"A": 0}
        assignments, _, _, _, _ = assign_cards(decklists, collection)
        for a in assignments:
            self.assertGreaterEqual(a["real"], 0)
            self.assertGreaterEqual(a["owned_proxy"], 0)
            self.assertGreaterEqual(a["unowned_proxy"], 0)

    def test_multiple_cards(self):
        # Multiple cards, mixed ownership, 2 copies of each card so both decks get real, nothing reserved
        decklists = {"Deck1": [("A", 1), ("B", 1)], "Deck2": [("A", 1), ("B", 1)]}
        collection = {"A": 2, "B": 2}
        assignments, binder_reserved, _, _, _ = assign_cards(decklists, collection)
        self.assertNotIn("A", binder_reserved)
        self.assertNotIn("B", binder_reserved)
        a_real = [a["real"] for a in assignments if a["card"] == "A"]
        b_real = [a["real"] for a in assignments if a["card"] == "B"]
        self.assertEqual(sorted(a_real), [1, 1])
        self.assertEqual(sorted(b_real), [1, 1])
        a_owned_proxy = [a["owned_proxy"] for a in assignments if a["card"] == "A"]
        b_owned_proxy = [a["owned_proxy"] for a in assignments if a["card"] == "B"]
        self.assertEqual(sorted(a_owned_proxy), [0, 0])
        self.assertEqual(sorted(b_owned_proxy), [0, 0])

    def test_mixed_real_and_owned_proxies(self):
        # 3 decks, 2 cards owned
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)], "Deck3": [("A", 1)]}
        collection = {"A": 2}
        assignments, binder_reserved, _, _, _ = assign_cards(decklists, collection)
        real = [a["real"] for a in assignments if a["card"] == "A"]
        owned_proxy = [a["owned_proxy"] for a in assignments if a["card"] == "A"]
        self.assertEqual(real.count(1), 1)  # Only one real card assigned
        self.assertEqual(owned_proxy.count(1), 2)  # Two decks get owned proxies
        self.assertIn("A", binder_reserved)
        self.assertEqual(binder_reserved["A"], 1)

    def test_mixed_owned_and_unowned_proxies(self):
        # 3 decks, 1 card owned
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)], "Deck3": [("A", 1)]}
        collection = {"A": 1}
        assignments, binder_reserved, slu, _, _ = assign_cards(decklists, collection)
        owned_proxy = [a["owned_proxy"] for a in assignments if a["card"] == "A"]
        unowned_proxy = [a["unowned_proxy"] for a in assignments if a["card"] == "A"]
        self.assertEqual(owned_proxy.count(1), 3)  # All decks get owned proxies
        self.assertEqual(unowned_proxy.count(1), 0)  # No unowned proxies
        self.assertIn("A", binder_reserved)
        self.assertEqual(binder_reserved["A"], 1)
        self.assertEqual(len(slu), 0)  # No unowned proxy shopping list

    def test_reserve_binder_and_shopping_list(self):
        # 4 decks, 1 card owned
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)], "Deck3": [("A", 1)], "Deck4": [("A", 1)]}
        collection = {"A": 1}
        assignments, binder_reserved, slu, _, _ = assign_cards(decklists, collection)
        owned_proxy = [a["owned_proxy"] for a in assignments if a["card"] == "A"]
        unowned_proxy = [a["unowned_proxy"] for a in assignments if a["card"] == "A"]
        self.assertEqual(owned_proxy.count(1), 4)  # All decks get owned proxies
        self.assertEqual(unowned_proxy.count(1), 0)  # No unowned proxies
        self.assertIn("A", binder_reserved)
        self.assertEqual(binder_reserved["A"], 1)
        self.assertEqual(len(slu), 0)  # No unowned proxy shopping list

    def test_deck_status_mixed_proxies(self):
        # 3 decks, 1 card owned
        decklists = {"Deck1": [("A", 1)], "Deck2": [("A", 1)], "Deck3": [("A", 1)]}
        collection = {"A": 1}
        _, _, _, _, status = assign_cards(decklists, collection)
        # All decks should have only owned proxies, no unowned proxies
        self.assertTrue(all(s["has_owned_proxy"] and not s["has_unowned_proxy"] for s in status.values()))

    def test_singleton_owned_proxy_shopping_list(self):
        # Bug repro: singleton cards should never have >1 in owned proxy shopping list or negative assignments
        decklists = {"We're All on Fire": [("Sol Ring", 1), ("Swiftfoot Boots", 1)]}
        # Test both 1 owned and 0 owned
        for owned in [1, 0]:
            collection = {"Sol Ring": owned, "Swiftfoot Boots": owned}
            assignments, _, slu, slm, _ = assign_cards(decklists, collection)
            for a in assignments:
                # No negative assignments
                self.assertGreaterEqual(a["real"], 0, f"Negative real for {a}")
                self.assertGreaterEqual(a["owned_proxy"], 0, f"Negative owned_proxy for {a}")
                self.assertGreaterEqual(a["unowned_proxy"], 0, f"Negative unowned_proxy for {a}")
                # The sum of assignments never exceeds needed
                self.assertLessEqual(a["real"] + a["owned_proxy"] + a["unowned_proxy"], a["needed"], f"Over-assigned for {a}")
            # Check shopping list for owned proxies (slm)
            for row in slm:
                self.assertLessEqual(row["needed"], 1, f"Owned proxy shopping list >1 for singleton: {row}")
            # Check shopping list for unowned proxies (slu)
            for row in slu:
                self.assertLessEqual(row["needed"], 1, f"Unowned proxy shopping list >1 for singleton: {row}")

if __name__ == "__main__":
    unittest.main(verbosity=2)

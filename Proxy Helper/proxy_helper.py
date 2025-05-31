import os
import pandas as pd
from collections import defaultdict, Counter
from copy import deepcopy

# === CONFIGURATION ===
COLLECTION_PATH = "Proxy Helper/Collection/ManaBox_Collection.csv"
DECKS_FOLDER = "Proxy Helper/Decks"
OUTPUT_FOLDER = "Proxy Helper/Output"
ASSIGNMENT_OUTPUT = os.path.join(OUTPUT_FOLDER, "deck_card_assignments.csv")
BINDER_OUTPUT = os.path.join(OUTPUT_FOLDER, "binder_reserved.csv")
SHOPPING_OUTPUT = os.path.join(OUTPUT_FOLDER, "shopping_list.csv")

# === Ensure output directory exists ===
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# === Load and preprocess collection (FIX: group only by card name) ===
collection_df = pd.read_csv(COLLECTION_PATH)
collection_df.columns = [col.strip().lower().replace(" ", "_") for col in collection_df.columns]
collection = collection_df[~collection_df["binder_type"].str.lower().eq("list")].copy()
collection["name"] = collection["name"].str.strip()

# FIX: Group only by card name to get total owned, regardless of binder/deck
summary = (
    collection.groupby(["name"])
    .agg({"quantity": "sum"})
    .reset_index()
)

# === Parse decklist .txt files ===
def parse_decklist(filepath):
    deck = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue
            qty, rest = parts
            try:
                qty = int(qty)
            except ValueError:
                continue
            name = rest.split("(")[0].strip()
            deck.append((name, qty))
    return deck

decklists = {}
for filename in os.listdir(DECKS_FOLDER):
    if filename.endswith(".txt"):
        deckname = os.path.splitext(filename)[0]
        decklists[deckname] = parse_decklist(os.path.join(DECKS_FOLDER, filename))

# === Assign cards to decks (robust logic) ===
deck_assignments = []
binder_reserved = defaultdict(int)
shopping_list = defaultdict(int)
shopping_list_unowned = []
shopping_list_missing = []

# Aggregate total needed per card across all decks
card_total_needed = Counter()
deck_card_needs = []
for deckname, deck in decklists.items():
    for card, qty in deck:
        card_total_needed[card] += qty
        deck_card_needs.append((deckname, card, qty))

binder_pool = defaultdict(int)
# When building binder_pool, use summary['name'] and summary['quantity']
for _, row in summary.iterrows():
    binder_pool[row["name"]] = row["quantity"]

# === Deck-level completion optimization ===
# Step 1: Build deck needs
deck_needs = defaultdict(list)  # deck -> list of (card, qty)
for deckname, deck in decklists.items():
    for card, qty in deck:
        deck_needs[deckname].append((card, qty))

# Step 2: Build card pool (after binder reserve)
card_total_needed = Counter()
for deck, needs in deck_needs.items():
    for card, qty in needs:
        card_total_needed[card] += qty

binder_pool = defaultdict(int)
for _, row in summary.iterrows():
    binder_pool[row["name"]] = row["quantity"]

binder_reserved = defaultdict(int)
for card, total_needed in card_total_needed.items():
    owned = binder_pool.get(card, 0)
    if 0 < owned < total_needed:
        binder_reserved[card] = 1

# Card pool after reserve
card_pool = {}
for card, owned in binder_pool.items():
    card_pool[card] = owned - binder_reserved.get(card, 0)

# Step 3: Find all decks that can be completed
completed_decks = set()
card_pool_working = deepcopy(card_pool)
for deck, needs in deck_needs.items():
    can_complete = True
    for card, qty in needs:
        if card_pool_working.get(card, 0) < qty:
            can_complete = False
            break
    if can_complete:
        completed_decks.add(deck)
        for card, qty in needs:
            card_pool_working[card] -= qty

# Step 4: Assign cards to decks
# Reset pools for assignment
card_pool_assign = deepcopy(card_pool)
deck_assignments = []
shopping_list_unowned = []
shopping_list_missing = []

for deck, needs in deck_needs.items():
    if deck in completed_decks:
        # Assign all real cards
        for card, qty in needs:
            if card not in card_pool_assign:
                card_pool_assign[card] = 0
            deck_assignments.append({
                "deck": deck,
                "card": card,
                "needed": qty,
                "real": qty,
                "owned_proxy": 0,
                "unowned_proxy": 0
            })
            card_pool_assign[card] -= qty
    else:
        # Assign as many real cards as possible, then proxies
        for card, qty in needs:
            if card not in card_pool_assign:
                card_pool_assign[card] = 0
            real = min(qty, card_pool_assign.get(card, 0))
            card_pool_assign[card] -= real
            owned = binder_pool.get(card, 0)
            reserve = binder_reserved.get(card, 0)
            owned_proxy = 0
            unowned_proxy = 0
            if real < qty:
                # Assign proxies
                owned_proxy = min(qty - real, owned if reserve else 0)
                unowned_proxy = qty - real - owned_proxy
                if owned == 0:
                    shopping_list_unowned.append({"deck": deck, "card": card, "needed": qty - real})
                elif unowned_proxy > 0:
                    shopping_list_missing.append({"deck": deck, "card": card, "needed": unowned_proxy})
            deck_assignments.append({
                "deck": deck,
                "card": card,
                "needed": qty,
                "real": real,
                "owned_proxy": owned_proxy,
                "unowned_proxy": unowned_proxy
            })

# === Save outputs ===
pd.DataFrame(deck_assignments).to_csv(ASSIGNMENT_OUTPUT, index=False)
pd.DataFrame([{"card": card} for card in binder_reserved.keys()]).to_csv(BINDER_OUTPUT, index=False)
# Save new shopping lists with improved naming
pd.DataFrame([{"deck": row["deck"], "card": row["card"], "needed": row["needed"]} for row in shopping_list_unowned]).to_csv(os.path.join(OUTPUT_FOLDER, "shopping_list_unowned.csv"), index=False)
# NEW: Always include all owned_proxy assignments in shopping_list_ownedproxy
ownedproxy_rows = []
for assignment in deck_assignments:
    if assignment["owned_proxy"] > 0:
        needed = min(assignment["owned_proxy"], assignment["needed"])
        needed = max(needed, 0)
        ownedproxy_rows.append({
            "deck": assignment["deck"],
            "card": assignment["card"],
            "needed": needed
        })
pd.DataFrame(ownedproxy_rows).to_csv(os.path.join(OUTPUT_FOLDER, "shopping_list_ownedproxy.csv"), index=False)

# === Write TXT versions of reserved and shopping lists (card names only, one per line) ===
# Reserved binder cards
with open(os.path.join(OUTPUT_FOLDER, "binder_reserved.txt"), "w", encoding="utf-8") as f:
    for card in binder_reserved.keys():
        f.write(f"{card}\n")
# Owned proxy shopping list (card names only)
ownedproxy_cardnames = set(row["card"] for row in ownedproxy_rows)
with open(os.path.join(OUTPUT_FOLDER, "shopping_list_ownedproxy.txt"), "w", encoding="utf-8") as f:
    for card in sorted(ownedproxy_cardnames):
        f.write(f"{card}\n")
# Unowned proxy shopping list (card names only)
unownedproxy_cardnames = set(row["card"] for row in shopping_list_unowned)
with open(os.path.join(OUTPUT_FOLDER, "shopping_list_unowned.txt"), "w", encoding="utf-8") as f:
    for card in sorted(unownedproxy_cardnames):
        f.write(f"{card}\n")

# === Deck completion stats (improved logic) ===
deck_status = defaultdict(lambda: {"real": 0, "owned_proxy": 0, "unowned_proxy": 0, "needed": 0, "has_owned_proxy": False, "has_unowned_proxy": False})
for assignment in deck_assignments:
    deck = assignment["deck"]
    deck_status[deck]["real"] += assignment["real"]
    deck_status[deck]["owned_proxy"] += assignment["owned_proxy"]
    deck_status[deck]["unowned_proxy"] += assignment["unowned_proxy"]
    deck_status[deck]["needed"] += assignment["needed"]
    if assignment["owned_proxy"] > 0:
        deck_status[deck]["has_owned_proxy"] = True
    if assignment["unowned_proxy"] > 0:
        deck_status[deck]["has_unowned_proxy"] = True

complete = 0
owned_proxy_only = 0
unowned_proxy = 0
for deck, stats in deck_status.items():
    if not stats["has_owned_proxy"] and not stats["has_unowned_proxy"]:
        complete += 1
    elif not stats["has_unowned_proxy"] and stats["has_owned_proxy"]:
        owned_proxy_only += 1
    elif stats["has_unowned_proxy"]:
        unowned_proxy += 1

num_unowned_proxy_cards = sum(row["needed"] for row in shopping_list_unowned)
total_owned_proxies = sum(assignment["owned_proxy"] for assignment in deck_assignments)

# === Output summary statistics ===
# Compute overall totals for real cards and proxies used in decks
_total_real = sum(a["real"] for a in deck_assignments)
_total_owned_proxy = sum(a["owned_proxy"] for a in deck_assignments)
_total_unowned_proxy = sum(a["unowned_proxy"] for a in deck_assignments)
_total_proxies = _total_owned_proxy + _total_unowned_proxy
_total_cards = _total_real + _total_proxies
_percentage_real = (_total_real / _total_cards * 100) if _total_cards > 0 else 0

print("\n=== Deck Optimizer Summary ===")
print("Files written to /Output:")
print(f"- {ASSIGNMENT_OUTPUT}")
print(f"- {BINDER_OUTPUT}")
print(f"- {os.path.join(OUTPUT_FOLDER, 'shopping_list_unowned.csv')}")
print(f"- {os.path.join(OUTPUT_FOLDER, 'shopping_list_ownedproxy.csv')}")

print("\nDeck Completion Stats:")
print(f"  Complete decks (all real cards):         {complete}")
print(f"  Decks with only owned proxies:           {owned_proxy_only}")
print(f"  Decks with unowned proxies:              {unowned_proxy}")

print("\nCard Assignment Totals:")
print(f"  Total real cards assigned:               {_total_real}")
print(f"  Total owned proxies assigned:            {_total_owned_proxy}")
print(f"  Total unowned proxies assigned:          {_total_unowned_proxy}")
print(f"  Total proxies assigned:                  {_total_proxies}")
print(f"  Total cards assigned (real + proxies):   {_total_cards}")
print(f"  Percentage of real cards:                {_percentage_real:.2f}%")

print("\nShopping List Totals:")
print(f"  Total unowned proxy cards in shopping list: {num_unowned_proxy_cards}")
print(f"  Total owned proxies in decks:               {total_owned_proxies}")

# === Output deck status CSV ===
deck_status_rows = []
for deck, stats in deck_status.items():
    if not stats["has_owned_proxy"] and not stats["has_unowned_proxy"]:
        deck_status_rows.append({"deck": deck, "status": "complete"})
for deck, stats in deck_status.items():
    if not stats["has_unowned_proxy"] and stats["has_owned_proxy"]:
        deck_status_rows.append({"deck": deck, "status": "owned_proxy_only"})
for deck, stats in deck_status.items():
    if stats["has_unowned_proxy"]:
        deck_status_rows.append({"deck": deck, "status": "unowned_proxy"})

pd.DataFrame(deck_status_rows).to_csv(os.path.join(OUTPUT_FOLDER, "deck_status.csv"), index=False)

def assign_cards(decklists, collection):
    """
    Assigns cards from collection to decks, minimizing proxies and maximizing complete decks.
    Allows unlimited owned proxies as long as a card is owned (even if reserved).
    Args:
        decklists: dict of deck_name -> list of (card, qty)
        collection: dict of card_name -> owned count
    Returns:
        deck_assignments, binder_reserved, shopping_list_unowned, shopping_list_ownedproxy, deck_status
    """
    from collections import defaultdict, Counter

    # Build a list of (deck, card, qty) for all needs
    deck_card_needs = []
    for deck, cards in decklists.items():
        for card, qty in cards:
            deck_card_needs.append((deck, card, qty))

    # Aggregate total needed per card
    card_total_needed = Counter()
    for _, card, qty in deck_card_needs:
        card_total_needed[card] += qty

    # Build binder pool
    binder_pool = defaultdict(int)
    for card, qty in collection.items():
        binder_pool[card] = qty

    binder_reserved = {}
    assignments = []
    slu = []  # shopping list unowned
    slm = []  # shopping list missing
    deck_status = {deck: {"has_owned_proxy": False, "has_unowned_proxy": False} for deck in decklists}

    # For each card, assign to decks
    card_deck_assignments = defaultdict(list)
    for deck, card, qty in deck_card_needs:
        card_deck_assignments[card].append((deck, qty))

    for card, needs in card_deck_assignments.items():
        total_needed = sum(qty for _, qty in needs)
        owned = binder_pool.get(card, 0)
        reserve = 0
        if 0 < owned < total_needed:
            reserve = 1
            binder_reserved[card] = 1
        assignable = max(owned - reserve, 0)
        # Sort needs by ascending qty to maximize completed decks
        sorted_needs = sorted(needs, key=lambda x: x[1])
        real_left = assignable
        # Unlimited owned proxies as long as owned > 0
        real_assignments = []
        # First pass: assign real cards to fully complete as many decks as possible
        for deckname, qty in sorted_needs:
            if real_left >= qty:
                real_assignments.append((deckname, qty, qty, 0, 0))
                real_left -= qty
            else:
                break
        # Second pass: assign proxies to remaining decks
        proxy_start = len(real_assignments)
        for i in range(proxy_start, len(sorted_needs)):
            deckname, qty = sorted_needs[i]
            real = 0
            if owned > 0:
                owned_proxy = qty
                unowned_proxy = 0
            else:
                owned_proxy = 0
                unowned_proxy = qty
            if owned == 0:
                slu.append({"deck": deckname, "card": card, "needed": qty})
            elif unowned_proxy > 0:
                slm.append({"deck": deckname, "card": card, "needed": unowned_proxy})
            real_assignments.append((deckname, qty, real, owned_proxy, unowned_proxy))
        # Write all assignments in original deck order
        deck_order = {deckname: i for i, (deckname, _) in enumerate(needs)}
        real_assignments.sort(key=lambda x, deck_order=deck_order: deck_order[x[0]])
        for deckname, qty, real, owned_proxy, unowned_proxy in real_assignments:
            assignments.append({
                "deck": deckname,
                "card": card,
                "needed": qty,
                "real": real,
                "owned_proxy": owned_proxy,
                "unowned_proxy": unowned_proxy
            })
            if owned_proxy > 0:
                deck_status[deckname]["has_owned_proxy"] = True
            if unowned_proxy > 0:
                deck_status[deckname]["has_unowned_proxy"] = True

    return assignments, binder_reserved, slu, slm, deck_status


import os
import pandas as pd
from collections import defaultdict, Counter
from copy import deepcopy

# === CONFIGURATION ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COLLECTION_PATH = os.path.join(BASE_DIR, "Collection", "ManaBox_Collection.csv")
DECKS_FOLDER = os.path.join(BASE_DIR, "Decks")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "Output")
EXISTING_PROXIES_PATH = os.path.join(BASE_DIR, "Collection", "Existing_Proxies.csv")  # Path to existing proxies CSV
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

# === Load existing proxies data if file exists ===
existing_proxies = {}  # card_name -> total count of existing proxies
existing_quality_proxies = {}  # card_name -> count of quality proxies
existing_temp_proxies = {}  # card_name -> count of temporary proxies
if os.path.exists(EXISTING_PROXIES_PATH):
    try:
        # Add explicit encoding and error handling
        with open(EXISTING_PROXIES_PATH, 'r', encoding='utf-8') as f:
            # Manually parse the CSV
            lines = [line.strip() for line in f.readlines() if line.strip()]
            if len(lines) > 0:
                headers = [h.strip() for h in lines[0].split(',')]
                
                # Check for correct headers
                if "card" in headers and "quantity" in headers:
                    # Old format - treat all as temp proxies for backward compatibility
                    if set(headers) == {"card", "quantity"}:
                        for line in lines[1:]:
                            parts = line.split(',')
                            if len(parts) >= 2:
                                card = parts[0].strip()
                                try:
                                    qty = int(parts[-1].strip())
                                    existing_proxies[card] = existing_proxies.get(card, 0) + qty
                                    existing_temp_proxies[card] = existing_temp_proxies.get(card, 0) + qty
                                except ValueError:
                                    continue
                        print(f"Loaded {len(existing_proxies)} cards from existing proxies list (old format)")
                    
                # New format (card, quality, temp, quantity)
                elif all(col in headers for col in ['card', 'quality', 'temp', 'quantity']):
                    card_idx = headers.index("card")
                    quality_idx = headers.index("quality")
                    temp_idx = headers.index("temp")
                    quantity_idx = headers.index("quantity")
                    
                    for line in lines[1:]:
                        parts = line.split(',')
                        if len(parts) >= max(card_idx, quality_idx, temp_idx, quantity_idx) + 1:
                            card = parts[card_idx].strip()
                            try:
                                quality = int(parts[quality_idx].strip())
                                temp = int(parts[temp_idx].strip())
                                qty = int(parts[quantity_idx].strip())
                                
                                # Add to total proxies
                                existing_proxies[card] = existing_proxies.get(card, 0) + qty
                                
                                # Add to quality or temp proxies
                                if quality == 1:
                                    existing_quality_proxies[card] = existing_quality_proxies.get(card, 0) + qty
                                elif temp == 1:
                                    existing_temp_proxies[card] = existing_temp_proxies.get(card, 0) + qty
                            except ValueError:
                                continue
                    
                    print(f"Loaded {len(existing_proxies)} cards from existing proxies list")
                    print(f"  - Quality proxies: {len(existing_quality_proxies)}")
                    print(f"  - Temporary proxies: {len(existing_temp_proxies)}")
                else:
                    print(f"Warning: Existing proxies file doesn't have required columns (card, quality, temp, quantity)")
    except Exception as e:
        print(f"Error loading existing proxies: {e}")
else:
    print(f"Note: No existing proxies file found at {EXISTING_PROXIES_PATH}")

# Check for Reserved Binder in the collection
reserved_binder_cards = {}
reserved_collection = collection[collection["binder_type"].str.lower() == "reserved binder"].copy()
if not reserved_collection.empty:
    reserved_binder_df = reserved_collection.groupby(["name"])["quantity"].sum().reset_index()
    reserved_binder_cards = dict(zip(reserved_binder_df["name"], reserved_binder_df["quantity"]))
    print(f"Found {len(reserved_binder_cards)} cards in the Reserved Binder")

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

def assign_cards(decklists, collection, existing_proxies=None, existing_quality_proxies=None, 
              existing_temp_proxies=None, reserved_binder=None):
    """
    Assigns cards from collection to decks, minimizing proxies and maximizing complete decks.
    Allows unlimited missingOwned proxies as long as a card is owned (even if reserved).
    
    Args:
        decklists: dict of deck_name -> list of (card, qty)
        collection: dict of card_name -> owned count
        existing_proxies: dict of card_name -> count of existing proxies (optional)
        existing_quality_proxies: dict of card_name -> count of quality proxies (optional)
        existing_temp_proxies: dict of card_name -> count of temp proxies (optional)
        reserved_binder: dict of card_name -> count of cards already in reserve binder (optional)
        
    Returns:
        deck_assignments, binder_reserved, shopping_list_missingUnowned, shopping_list_missingOwned, deck_status
    """
    # Initialize empty dictionary if None is provided
    existing_proxies = existing_proxies or {}
    existing_quality_proxies = existing_quality_proxies or {}
    existing_temp_proxies = existing_temp_proxies or {}
    reserved_binder = reserved_binder or {}
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

    # Calculate adjusted binder reserve considering the reserved_binder
    binder_reserved = {}
    for card, total_needed in card_total_needed.items():
        owned = binder_pool.get(card, 0)
        # Only reserve a card if it's not already in the reserved binder
        # and there's not enough for all decks
        if 0 < owned < total_needed and card not in reserved_binder:
            binder_reserved[card] = 1

    assignments = []
    slu = []  # shopping list missing unowned
    slm = []  # shopping list missing owned
    deck_status = {deck: {"has_missingOwned": False, "has_missingUnowned": False,
                         "has_qualityProxy": False, "has_tempProxy": False} 
                  for deck in decklists}

    # For each card, assign to decks
    card_deck_assignments = defaultdict(list)
    for deck, card, qty in deck_card_needs:
        card_deck_assignments[card].append((deck, qty))

    for card, needs in card_deck_assignments.items():
        total_needed = sum(qty for _, qty in needs)
        owned = binder_pool.get(card, 0)
        # If card is in the reserved binder, don't count it as needing to be reserved
        # it's already reserved
        reserve = 0
        if 0 < owned < total_needed and card not in reserved_binder:
            reserve = 1
            binder_reserved[card] = 1
        assignable = max(owned - reserve, 0)
        
        # Sort needs by ascending qty to maximize completed decks
        sorted_needs = sorted(needs, key=lambda x: x[1])
        real_left = assignable
        
        # Get existing proxy counts for the card
        existing_quality_count = existing_quality_proxies.get(card, 0) 
        existing_temp_count = existing_temp_proxies.get(card, 0)
        
        real_assignments = []
        
        # First pass: assign real cards to fully complete as many decks as possible
        for deckname, qty in sorted_needs:
            if real_left >= qty:
                # Enough real cards for this deck
                real_assignments.append((deckname, qty, qty, 0, 0, 0, 0))
                real_left -= qty
            else:
                break
                
        # Second pass: assign proxies to remaining decks
        proxy_start = len(real_assignments)
        for i in range(proxy_start, len(sorted_needs)):
            deckname, qty = sorted_needs[i]
            # Initialize with zero real cards for this deck
            real = 0
            quality_proxy = 0
            temp_proxy = 0
            missing_owned = 0
            missing_unowned = 0
            
            # Prioritize: real → quality proxy → temp proxy → missing owned → missing unowned
            remaining = qty - real
            
            # If card is owned (but not enough real copies), allow for missingOwned proxies
            # Otherwise it's missingUnowned
            if owned > 0:
                # First try to use quality proxies
                quality_available = min(existing_quality_count, remaining)
                quality_proxy = quality_available
                existing_quality_count -= quality_available
                remaining -= quality_available
                
                # Then try temp proxies
                temp_available = min(existing_temp_count, remaining)
                temp_proxy = temp_available
                existing_temp_count -= temp_available
                remaining -= temp_available
                
                # Any remaining needed are missing owned proxies
                missing_owned = remaining
                missing_unowned = 0
            else:
                # Not owned at all
                # Still try to use quality & temp proxies but mark as missing unowned
                quality_available = min(existing_quality_count, remaining)
                quality_proxy = quality_available
                existing_quality_count -= quality_available
                remaining -= quality_available
                
                # Then try temp proxies
                temp_available = min(existing_temp_count, remaining)
                temp_proxy = temp_available
                existing_temp_count -= temp_available
                remaining -= temp_available
                
                # Any remaining needed are missing unowned proxies
                missing_owned = 0
                missing_unowned = remaining
            
            # Shopping list logic
            if missing_unowned > 0:
                slu.append({
                    "deck": deckname, 
                    "card": card, 
                    "needed": missing_unowned
                })
            elif missing_owned > 0:
                slm.append({
                    "deck": deckname, 
                    "card": card, 
                    "needed": missing_owned
                })
                
            real_assignments.append((
                deckname, qty, real, quality_proxy, temp_proxy, 
                missing_owned, missing_unowned
            ))
            
        # Write all assignments in original deck order
        deck_order = {deckname: i for i, (deckname, _) in enumerate(needs)}
        real_assignments.sort(key=lambda x, deck_order=deck_order: deck_order[x[0]])
        
        for deckname, qty, real, quality_proxy, temp_proxy, missing_owned, missing_unowned in real_assignments:
            assignments.append({
                "deck": deckname,
                "card": card,
                "needed": qty,
                "real": real,
                "qualityProxy": quality_proxy,
                "tempProxy": temp_proxy,
                "missingOwned": missing_owned,
                "missingUnowned": missing_unowned
            })
            
            # Update deck status flags
            if quality_proxy > 0:
                deck_status[deckname]["has_qualityProxy"] = True
            if temp_proxy > 0:
                deck_status[deckname]["has_tempProxy"] = True
            if missing_owned > 0:
                deck_status[deckname]["has_missingOwned"] = True
            if missing_unowned > 0:
                deck_status[deckname]["has_missingUnowned"] = True

    return assignments, binder_reserved, slu, slm, deck_status

decklists = {}
for filename in os.listdir(DECKS_FOLDER):
    if filename.endswith(".txt"):
        deckname = os.path.splitext(filename)[0]
        decklists[deckname] = parse_decklist(os.path.join(DECKS_FOLDER, filename))

# === Assign cards to decks using the updated function ===
# Pass existing proxies, quality proxies, temp proxies, and reserved binder information
deck_assignments, binder_reserved, shopping_list_unowned, shopping_list_missing, deck_status = assign_cards(
    decklists, 
    {row["name"]: row["quantity"] for _, row in summary.iterrows()},
    existing_proxies,
    existing_quality_proxies,
    existing_temp_proxies,
    reserved_binder_cards
)

# === Save outputs ===
pd.DataFrame(deck_assignments).to_csv(ASSIGNMENT_OUTPUT, index=False)
pd.DataFrame([{"card": card} for card in binder_reserved.keys()]).to_csv(BINDER_OUTPUT, index=False)

# Process shopping lists with existing proxies consideration
shopping_list_unowned_adjusted = []
for row in shopping_list_unowned:
    card = row["card"]
    existing_count = existing_proxies.get(card, 0)
    needed = row["needed"]
    if existing_count >= needed:
        # We have enough existing proxies for this card
        continue
    else:
        # Adjust needed count by existing proxies
        adjusted_needed = needed - existing_count
        shopping_list_unowned_adjusted.append({
            "deck": row["deck"],
            "card": card,
            "needed": adjusted_needed,
            "existing": existing_count
        })

# Save adjusted missing unowned shopping list under the same filename for backward compatibility
pd.DataFrame(shopping_list_unowned_adjusted).to_csv(
    os.path.join(OUTPUT_FOLDER, "shopping_list_unowned.csv"), index=False)

# Process missing owned shopping list
missing_owned_rows = []
for assignment in deck_assignments:
    if assignment["missingOwned"] > 0:
        card = assignment["card"]
        deck = assignment["deck"]
        needed = min(assignment["missingOwned"], assignment["needed"])
        needed = max(needed, 0)
        
        # Check if we have existing proxies for this card
        existing_count = existing_proxies.get(card, 0)
        if existing_count >= needed:
            # We have enough existing proxies for this card
            continue
        else:
            # Adjust needed count by existing proxies
            adjusted_needed = needed - existing_count
            missing_owned_rows.append({
                "deck": deck,
                "card": card,
                "needed": adjusted_needed,
                "existing": existing_count
            })

# Calculate totals for summary stats
total_missing_owned = sum(assignment["missingOwned"] for assignment in deck_assignments)
total_missing_owned_needed = sum(row["needed"] for row in missing_owned_rows)

# Save adjusted missing owned proxy shopping list (keep backward compatible name)
pd.DataFrame(missing_owned_rows).to_csv(
    os.path.join(OUTPUT_FOLDER, "shopping_list_ownedproxy.csv"), index=False)

# Save adjusted owned proxy shopping list
pd.DataFrame(missing_owned_rows).to_csv(
    os.path.join(OUTPUT_FOLDER, "shopping_list_ownedproxy.csv"), index=False)

# === Write TXT versions of reserved and shopping lists (card names only, one per line) ===
# Reserved binder cards
with open(os.path.join(OUTPUT_FOLDER, "binder_reserved.txt"), "w", encoding="utf-8") as f:
    for card in binder_reserved.keys():
        f.write(f"{card}\n")
# Missing owned shopping list (card names only)
missing_owned_cardnames = set(row["card"] for row in missing_owned_rows)
with open(os.path.join(OUTPUT_FOLDER, "shopping_list_ownedproxy.txt"), "w", encoding="utf-8") as f:
    for card in sorted(missing_owned_cardnames):
        f.write(f"{card}\n")
# Missing unowned shopping list (card names only)
missing_unowned_cardnames = set(row["card"] for row in shopping_list_unowned_adjusted)
with open(os.path.join(OUTPUT_FOLDER, "shopping_list_unowned.txt"), "w", encoding="utf-8") as f:
    for card in sorted(missing_unowned_cardnames):
        f.write(f"{card}\n")

# === Deck completion stats (improved logic) ===
deck_status = defaultdict(lambda: {
    "real": 0, 
    "qualityProxy": 0, 
    "tempProxy": 0, 
    "missingOwned": 0, 
    "missingUnowned": 0, 
    "needed": 0, 
    "has_qualityProxy": False, 
    "has_tempProxy": False,
    "has_missingOwned": False, 
    "has_missingUnowned": False
})
for assignment in deck_assignments:
    deck = assignment["deck"]
    deck_status[deck]["real"] += assignment["real"]
    deck_status[deck]["qualityProxy"] += assignment["qualityProxy"]
    deck_status[deck]["tempProxy"] += assignment["tempProxy"]
    deck_status[deck]["missingOwned"] += assignment["missingOwned"]
    deck_status[deck]["missingUnowned"] += assignment["missingUnowned"]
    deck_status[deck]["needed"] += assignment["needed"]
    if assignment["qualityProxy"] > 0:
        deck_status[deck]["has_qualityProxy"] = True
    if assignment["tempProxy"] > 0:
        deck_status[deck]["has_tempProxy"] = True
    if assignment["missingOwned"] > 0:
        deck_status[deck]["has_missingOwned"] = True
    if assignment["missingUnowned"] > 0:
        deck_status[deck]["has_missingUnowned"] = True

complete = 0
missing_owned_only = 0
quality_proxy_only = 0
temp_proxy_only = 0
missing_unowned = 0

for deck, stats in deck_status.items():
    # Deck is complete if it has no proxies of any kind
    if (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
        not stats["has_qualityProxy"] and not stats["has_tempProxy"]):
        complete += 1
    # Deck has quality proxies only
    elif (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
          stats["has_qualityProxy"] and not stats["has_tempProxy"]):
        quality_proxy_only += 1
    # Deck has temp proxies only
    elif (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
          not stats["has_qualityProxy"] and stats["has_tempProxy"]):
        temp_proxy_only += 1
    # Deck has only missing owned proxies (no missing unowned)
    elif stats["has_missingOwned"] and not stats["has_missingUnowned"]:
        missing_owned_only += 1
    # Deck has missing unowned proxies
    elif stats["has_missingUnowned"]:
        missing_unowned += 1

num_unowned_proxy_cards = sum(row["needed"] for row in shopping_list_unowned)
num_unowned_proxy_cards_adjusted = sum(row["needed"] for row in shopping_list_unowned_adjusted)
total_owned_proxies = sum(assignment["missingOwned"] for assignment in deck_assignments)
total_owned_proxies_needed = sum(row["needed"] for row in missing_owned_rows)
total_existing_proxies_used = sum(min(existing_proxies.get(row["card"], 0), row["needed"]) for row in shopping_list_unowned) + \
                             sum(min(existing_proxies.get(assignment["card"], 0), assignment["missingOwned"]) 
                                 for assignment in deck_assignments if assignment["missingOwned"] > 0)

# === Output summary statistics ===
# Compute overall totals for real cards and proxies used in decks
_total_real = sum(a["real"] for a in deck_assignments)
_total_quality_proxy = sum(a["qualityProxy"] for a in deck_assignments)
_total_temp_proxy = sum(a["tempProxy"] for a in deck_assignments)
_total_missing_owned = sum(a["missingOwned"] for a in deck_assignments)
_total_missing_unowned = sum(a["missingUnowned"] for a in deck_assignments)
_total_proxies = _total_quality_proxy + _total_temp_proxy + _total_missing_owned + _total_missing_unowned
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
print(f"  Decks with quality proxies only:         {quality_proxy_only}")
print(f"  Decks with temp proxies only:            {temp_proxy_only}")
print(f"  Decks with missing owned only:           {missing_owned_only}")
print(f"  Decks with missing unowned:              {missing_unowned}")

print("\nCard Assignment Totals:")
print(f"  Total real cards assigned:               {_total_real}")
print(f"  Total quality proxies assigned:          {_total_quality_proxy}")
print(f"  Total temp proxies assigned:             {_total_temp_proxy}")
print(f"  Total missing owned assigned:            {_total_missing_owned}")
print(f"  Total missing unowned assigned:          {_total_missing_unowned}")
print(f"  Total proxies assigned:                  {_total_proxies}")
print(f"  Total cards assigned (real + proxies):   {_total_cards}")
print(f"  Percentage of real cards:                {_percentage_real:.2f}%")

print("\nShopping List Totals:")
print(f"  Total existing proxies available:             {sum(existing_proxies.values()) if existing_proxies else 0}")
print(f"  - Quality proxies:                          {sum(existing_quality_proxies.values()) if existing_quality_proxies else 0}")
print(f"  - Temporary proxies:                        {sum(existing_temp_proxies.values()) if existing_temp_proxies else 0}")
print(f"  Existing proxies used:                       {total_existing_proxies_used}")
print(f"  Total missing unowned before adjustment:     {num_unowned_proxy_cards}")
print(f"  Total missing unowned after adjustment:      {num_unowned_proxy_cards_adjusted}")
print(f"  Total missing owned needed:                  {total_missing_owned}")

# === Output deck status CSV ===
deck_status_rows = []
for deck, stats in deck_status.items():
    # Complete decks (all real cards)
    if (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
        not stats["has_qualityProxy"] and not stats["has_tempProxy"]):
        deck_status_rows.append({"deck": deck, "status": "complete"})
    # Decks with quality proxies only
    elif (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
          stats["has_qualityProxy"] and not stats["has_tempProxy"]):
        deck_status_rows.append({"deck": deck, "status": "quality_proxy_only"})
    # Decks with temp proxies only
    elif (not stats["has_missingOwned"] and not stats["has_missingUnowned"] and 
          not stats["has_qualityProxy"] and stats["has_tempProxy"]):
        deck_status_rows.append({"deck": deck, "status": "temp_proxy_only"})
    # Decks with missing owned only (backward compatible name)
    elif stats["has_missingOwned"] and not stats["has_missingUnowned"]:
        deck_status_rows.append({"deck": deck, "status": "owned_proxy_only"})
    # Decks with missing unowned (backward compatible name)
    elif stats["has_missingUnowned"]:
        deck_status_rows.append({"deck": deck, "status": "unowned_proxy"})
    else:
        # Mixed proxy types not covered by above cases
        deck_status_rows.append({"deck": deck, "status": "mixed"})

pd.DataFrame(deck_status_rows).to_csv(os.path.join(OUTPUT_FOLDER, "deck_status.csv"), index=False)


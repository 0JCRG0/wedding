# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Compare final_guest_list.csv (manually assembled) against rsvp_from_email.csv
(pulled from Gmail) and flag discrepancies in food selections.
"""

import csv
import re
from collections import defaultdict

FINAL = "data/final_guest_list.csv"
EMAIL = "data/rsvp_from_email.csv"


def normalize(s):
    """Lowercase, strip accents roughly, collapse whitespace."""
    s = s.strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ü": "u",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", " ", s)
    return s


def short_food(val):
    """Normalize a food selection to a short comparable label."""
    if not val:
        return ""
    v = normalize(val)
    if "kids" in v:
        return "kids"
    if "burrata" in v:
        return "burrata"
    if "terrin" in v or "terrina" in v:
        return "salmon terrine"
    if "beef" in v or "filete de res" in v or "filete de ternera" in v or "ternera" in v:
        return "beef"
    if "salmon" in v and ("risotto" in v or "vegetable" in v or "verdura" in v):
        return "salmon risotto"
    return v


def clean_parsed_name(name):
    """Remove trailing junk from parsed names in the others field."""
    # Remove trailing noise words/chars
    name = re.sub(r"\s*[/,:.+]+\s*$", "", name)
    name = re.sub(r"\s+entrada\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s*,\s*acepta con gusto\s*$", "", name, flags=re.IGNORECASE)
    # Remove "- Burratta" etc from end
    name = re.sub(r"\s*[-–]\s*(burratt?a|salmon|terrin).*$", "", name, flags=re.IGNORECASE)
    name = name.strip(" ,-:+/")
    return name


def parse_others_field(text):
    """
    Best-effort parse of the free-text 'rsvping_for_others' field.
    Returns list of dicts with keys: name, entry, main_course (any may be empty).
    """
    if not text or text.strip().lower() in ("", "no", "tbd", "potentially", "n/a",
                                              "i am coming with evariste",
                                              "evariste's guest"):
        return []

    # Clean up <br /> tags
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")

    guests = []

    # Try numbered format: "1. Name, food & food"
    numbered = re.findall(r"\d+\.\s*(.+)", text)
    if numbered:
        lines = numbered
    else:
        # Split by newlines first
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # If single line, try splitting on / followed by capital letter
        if len(lines) == 1:
            lines = re.split(r"/\s*(?=[A-Z])", text)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip non-guest text
        if line.lower().startswith("thanks"):
            continue

        guest = {"name": "", "entry": "", "main_course": ""}

        food_keywords = [
            "burrata", "terrina", "terrine", "salmon", "filete", "beef",
            "prosciutto", "risotto", "salmón", "salm", "ternera",
        ]

        # Find where food description starts
        lower = line.lower()
        food_start = len(line)
        for kw in food_keywords:
            idx = lower.find(kw)
            if idx != -1 and idx < food_start:
                food_start = idx

        name_part = line[:food_start].strip().rstrip(":+-,. ")
        food_part = line[food_start:].strip()

        # Clean name of parenthetical notes
        name_part = re.sub(r"\(.*?\)", "", name_part).strip()
        name_part = clean_parsed_name(name_part)

        if name_part:
            guest["name"] = name_part

        # Parse food
        if food_part:
            food_lower = food_part.lower()
            if "burrata" in food_lower:
                guest["entry"] = "burrata"
            elif "terrin" in food_lower:
                guest["entry"] = "salmon terrine"

            if any(x in food_lower for x in ["filete de res", "filete de ternera", "ternera", "beef"]):
                guest["main_course"] = "beef"
            elif "salm" in food_lower and any(x in food_lower for x in ["risotto", "vegetable", "verdura"]):
                guest["main_course"] = "salmon risotto"
            # Handle short forms like "Burrata & Beef", "Burrata y Salmon"
            elif "beef" in food_lower:
                guest["main_course"] = "beef"
            elif "salmon" in food_lower or "salmón" in food_lower.replace("o", "ó"):
                # "Burrata y Salmon" = entry burrata, main salmon risotto
                if guest["entry"]:
                    guest["main_course"] = "salmon risotto"

        if guest["name"]:
            guests.append(guest)

    return guests


def load_final():
    with open(FINAL, newline="") as f:
        return list(csv.DictReader(f))


def load_email():
    with open(EMAIL, newline="") as f:
        return list(csv.DictReader(f))


def build_email_lookup(email_rows):
    """
    Build lookup: normalized name -> email data.
    Handle duplicates by keeping the most recent (first in the list).
    """
    lookup = {}
    for row in email_rows:
        name = row["name"].strip()
        nname = normalize(name)
        if nname not in lookup:
            lookup[nname] = {
                "raw_name": name,
                "entry": short_food(row["entry"]),
                "main_course": short_food(row["main_course"]),
                "date": row["date"],
                "email": row["email"],
                "rsvping_for_others": row.get("rsvping_for_others", ""),
                "allergies": row.get("allergies", ""),
            }
    return lookup


def build_others_lookup(email_rows):
    """
    Parse the 'rsvping_for_others' field and allergies (when misused)
    from all emails and build a lookup of normalized name -> guest data.
    """
    lookup = {}

    def add_guests(guests, submitted_by):
        for guest in guests:
            nname = normalize(guest["name"])
            if nname and nname not in lookup:
                lookup[nname] = {
                    "raw_name": guest["name"],
                    "entry": guest["entry"],
                    "main_course": guest["main_course"],
                    "submitted_by": submitted_by,
                }

    for row in email_rows:
        submitter = row["name"].strip()
        add_guests(parse_others_field(row.get("rsvping_for_others", "")), submitter)

        # Check allergies field for hidden guest info (e.g. Mario Reyes)
        allergy = row.get("allergies", "").strip()
        if "+" in allergy and any(kw in allergy.lower() for kw in ["burrata", "terrina", "filete", "ternera"]):
            add_guests(parse_others_field(allergy), submitter)

    return lookup


# --- Manual alias map for names that can't be fuzzy-matched ---
# final_guest_list name -> email/others name
MANUAL_ALIASES = {
    # Email submitters with different name formats
    "david alejandro tepach garcia": "david tepach",
    "rodrigo garcia duarte": "roy garcia du",
    "lilian waters": "lily waters",
    "galilea luna": "galilea luna",  # email direct (Leia Luna is different person)
    # Others field: names parsed with junk or partial
    "laura garcia rojas": "laura garcia rojas entrada",  # Hugo Alberto's submission
    "renata reyes garcia": "renata reyes garcia entrada",  # Hugo Alberto's submission
    "elizabeth laug": "elizabeth",  # Adán Reygadas' submission
    "frida reygadas": "frida valeria",  # Adán Reygadas' submission
    "lia reygadas": "lia elizabeth",  # Adán Reygadas' submission
    "adan manuel reygadas": "adan manuel",  # Adán Reygadas' submission
    "rob spoor": "robert spoor",  # Natalie Spoor's submission
    "camila gonzalez linares": "camila gonzalez linares/",  # Emiliano's submission
    "enrico casas lemus": "enrico casas.",  # Ana Sofía's submission
    "ericka limon": "ericka limon moreno , acepta con gusto",  # Marcos' submission
    "claudia bautista": "claudia carbajal",  # Diana Garcia's submission — NAME DIFFERS, flag it
    "jorge ojeda lauper": "jorge ojeda",  # Andrea Hernández's submission
    "luis luna": "luis luna /",  # Galilea Luna's submission
    "haidee torres": "haidee torres",  # Luis Enrique's submission (no food parsed)
    "maritza garcia gamboa": "maritza garcia",  # Diana Garcia's submission
}


def find_source(nmember, email_lookup, others_lookup):
    """Try to match a final guest list member to an email source."""
    # 1. Direct match in email submissions
    if nmember in email_lookup:
        return email_lookup[nmember], "direct email"

    # 2. Direct match in others submissions
    if nmember in others_lookup:
        src = others_lookup[nmember]
        return src, f"submitted by {src['submitted_by']}"

    # 3. Manual alias
    alias = MANUAL_ALIASES.get(nmember)
    if alias:
        nalias = normalize(alias)
        if nalias in email_lookup:
            src = email_lookup[nalias]
            return src, f"direct email (alias: {src['raw_name']})"
        if nalias in others_lookup:
            src = others_lookup[nalias]
            return src, f"submitted by {src['submitted_by']} (alias: {src['raw_name']})"

    # 4. Fuzzy match on email lookup
    fmatch = fuzzy_match(nmember, email_lookup)
    if fmatch:
        src = email_lookup[fmatch]
        return src, f"direct email (fuzzy: {src['raw_name']})"

    # 5. Fuzzy match on others lookup
    fmatch = fuzzy_match(nmember, others_lookup)
    if fmatch:
        src = others_lookup[fmatch]
        return src, f"submitted by {src['submitted_by']} (fuzzy: {src['raw_name']})"

    return None, None


def fuzzy_match(name, lookup):
    """
    Try to find a match requiring first name match AND strong overlap.
    """
    parts = name.split()
    best = None
    best_score = 0
    for key in lookup:
        key_parts = key.split()
        common = set(parts) & set(key_parts)
        if parts[0] == key_parts[0] and len(common) >= 2:
            score = len(common) / max(len(parts), len(key_parts))
            if score > best_score:
                best = key
                best_score = score
    if best_score >= 0.6:
        return best
    return None


def main():
    final_rows = load_final()
    email_rows = load_email()

    email_lookup = build_email_lookup(email_rows)
    others_lookup = build_others_lookup(email_rows)

    discrepancies = []
    no_email = []
    name_mismatches = []

    for row in final_rows:
        member = row["member"].strip()
        nmember = normalize(member)
        final_entry = short_food(row["entry"])
        final_main = short_food(row["main_course"])
        is_plus_one = row["is_plus_one"].strip()

        # Skip kids food
        if final_entry == "kids" or final_main == "kids":
            continue

        source, source_label = find_source(nmember, email_lookup, others_lookup)

        if not source:
            no_email.append(member)
            continue

        # Flag if alias maps to a different name (e.g. Claudia Bautista -> Claudia Carbajal)
        alias = MANUAL_ALIASES.get(nmember)
        if alias and normalize(alias) != nmember:
            raw = source.get("raw_name", alias)
            if normalize(raw) != nmember and not any(p in normalize(raw) for p in nmember.split()[:2]):
                name_mismatches.append((member, raw, source_label))

        # Compare food
        issues = []
        if source.get("entry") and final_entry and source["entry"] != final_entry:
            issues.append(f"ENTRY: final='{final_entry}' vs email='{source['entry']}'")
        if source.get("main_course") and final_main and source["main_course"] != final_main:
            issues.append(f"MAIN: final='{final_main}' vs email='{source['main_course']}'")

        if issues:
            discrepancies.append({
                "member": member,
                "plus_one_of": is_plus_one,
                "source": source_label,
                "issues": issues,
            })

    # --- Output ---
    print("=" * 70)
    print("DISCREPANCY REPORT: final_guest_list.csv vs email RSVPs")
    print("=" * 70)

    # 1. Food mismatches
    if discrepancies:
        print(f"\n## 1. FOOD SELECTION MISMATCHES ({len(discrepancies)})\n")
        for d in discrepancies:
            ctx = f" (plus one of {d['plus_one_of']})" if d["plus_one_of"] else ""
            print(f"  {d['member']}{ctx}")
            print(f"    Source: {d['source']}")
            for issue in d["issues"]:
                print(f"    ❌ {issue}")
            print()
    else:
        print("\n## 1. FOOD SELECTION MISMATCHES\n\n  ✅ None found!\n")

    # 2. Name mismatches
    if name_mismatches:
        print(f"## 2. NAME MISMATCHES ({len(name_mismatches)})")
        print("  (Final list name differs from what was submitted in email)\n")
        for final_name, email_name, src in name_mismatches:
            print(f"  ⚠️  Final: {final_name}  ←→  Email: {email_name} ({src})")
        print()

    # 3. No email RSVP
    if no_email:
        print(f"## 3. NO EMAIL RSVP FOUND ({len(no_email)})")
        print("  (Likely RSVPed via WhatsApp or added manually — verify food)\n")
        for name in no_email:
            final_row = next(r for r in final_rows if r["member"].strip() == name)
            entry = final_row["entry"]
            main = final_row["main_course"]
            po = f" (plus one of {final_row['is_plus_one']})" if final_row["is_plus_one"] else ""
            print(f"  - {name}{po}  [{entry} / {main}]")
        print()

    # 4. Duplicate submissions
    name_counts = defaultdict(list)
    for row in email_rows:
        name_counts[normalize(row["name"])].append(row)
    dupes = {k: v for k, v in name_counts.items() if len(v) > 1}
    if dupes:
        print(f"## 4. DUPLICATE EMAIL SUBMISSIONS ({len(dupes)})\n")
        for nname, rows in dupes.items():
            entries = [short_food(r["entry"]) for r in rows]
            mains = [short_food(r["main_course"]) for r in rows]
            dates = [r["date"][:16] for r in rows]
            changed = entries[0] != entries[-1] or mains[0] != mains[-1]
            flag = " ⚠️  FOOD CHANGED BETWEEN SUBMISSIONS" if changed else ""
            print(f"  {rows[0]['name']}{flag}")
            for i, r in enumerate(rows):
                print(f"    [{dates[i]}] {short_food(r['entry'])} / {short_food(r['main_course'])}")
            print()

    # 5. Allergy notes
    ignore_allergies = {"no", "no.", "none", "none.", "nel", "ninguna", "n/a",
                        "no allergies", "nooo", "sin alergias.", "no ninguna",
                        "none, ninguna", "broke men"}
    print("## 5. ALLERGY NOTES FROM EMAILS\n")
    for row in email_rows:
        allergy = row.get("allergies", "").strip()
        if allergy and allergy.lower() not in ignore_allergies:
            # Skip if it's the Mario Reyes guest-info-in-allergies case
            if "+" in allergy and any(kw in allergy.lower() for kw in ["burrata", "terrina", "filete", "ternera"]):
                continue
            print(f"  {row['name']}: {allergy}")
    print()

    # 6. Guests where email had food but we couldn't parse it (empty entry/main in others)
    print("## 6. OTHERS WITH MISSING FOOD DATA (could not parse from free text)\n")
    for nname, data in sorted(others_lookup.items()):
        if not data["entry"] and not data["main_course"]:
            print(f"  {data['raw_name']} (submitted by {data['submitted_by']}) — no food parsed")
    print()


if __name__ == "__main__":
    main()

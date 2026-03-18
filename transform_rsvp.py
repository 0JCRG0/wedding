# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas"]
# ///

import argparse
from enum import StrEnum
from io import StringIO

import pandas as pd

from import_rsvp import fetch_rsvp_data, to_csv


class RSVP(StrEnum):
    RSVPED = "RSVPed"
    DECLINED = "Declined"
    MAYBE = "Maybe"
    NO_ANSWER = "No Answer"


OUTPUT = "data/wedding_guest_list.csv"

OUTPUT_COLUMNS = ["First name", "Last name", "Family", "Who Is", "Side", "Sex", "Age", "RSVP"]


def is_empty(val):
    return pd.isna(val) or str(val).strip() in ("", "nan", "Does not apply")


def resolve_rsvp(row):
    final = str(row.get("Confirmed Final RSVP?", "")).strip()
    if final and final.lower() != "nan":
        return final


def clean(df):
    df["Group"] = df["Group"].str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["Member"].notna() & (df["Member"].str.strip() != "")]
    return df


def parse_args():
    parser = argparse.ArgumentParser(description="Transform wedding RSVP data into guest list.")
    parser.add_argument(
        "--rsvp",
        type=RSVP,
        choices=list(RSVP),
        nargs="+",
        help="Filter by RSVP status (e.g. --rsvp RSVPed Declined)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Fetch RSVP data from Google Sheets and load into DataFrame
    data = fetch_rsvp_data()
    buf = StringIO()
    to_csv(data, buf)
    buf.seek(0)
    df = pd.read_csv(buf)

    # Clean
    df = clean(df)

    # Primary guest rows
    primary = pd.DataFrame()
    primary["First name"] = df["Member"].str.strip()
    primary["Last name"] = pd.NA
    primary["Family"] = df["Group"]
    primary["RSVP"] = df.apply(resolve_rsvp, axis=1)

    # Plus-one detection
    has_name = df["If plus one, name?"].notna() & (df["If plus one, name?"].str.strip() != "")
    has_flag = df["Final Requested Plus One"] == True

    # Warn about mismatches
    flag_no_name = df[has_flag & ~has_name]
    name_no_flag = df[~has_flag & has_name]
    if not flag_no_name.empty:
        print("WARNING: Plus one requested but no name provided:")
        for _, row in flag_no_name.iterrows():
            print(f"  - {row['Member']} ({row['Group']})")
    if not name_no_flag.empty:
        print("WARNING: Plus one name provided but not flagged as requested:")
        for _, row in name_no_flag.iterrows():
            print(f"  - {row['Member']} ({row['Group']}) -> {row['If plus one, name?']}")

    # Check food selection contradictions
    rsvped = df[df["Confirmed Final RSVP?"] == RSVP.RSVPED]

    missing_entry = rsvped[rsvped["Entry selection"].apply(is_empty)]
    missing_main = rsvped[rsvped["Main Course selection"].apply(is_empty)]
    if not missing_entry.empty or not missing_main.empty:
        missing_food = pd.concat([missing_entry, missing_main]).drop_duplicates(subset="Member")
        print("WARNING: RSVPed guest missing food selection:")
        for _, row in missing_food.iterrows():
            missing = []
            if is_empty(row["Entry selection"]):
                missing.append("entry")
            if is_empty(row["Main Course selection"]):
                missing.append("main course")
            print(f"  - {row['Member']} ({row['Group']}) — missing: {', '.join(missing)}")

    plus_ones_with_food = rsvped.loc[rsvped.index.isin(df.index[has_flag & has_name])]
    missing_p1_entry = plus_ones_with_food[plus_ones_with_food["Entry selection Plus 1"].apply(is_empty)]
    missing_p1_main = plus_ones_with_food[plus_ones_with_food["Main Course selection Plus 1"].apply(is_empty)]
    if not missing_p1_entry.empty or not missing_p1_main.empty:
        missing_p1_food = pd.concat([missing_p1_entry, missing_p1_main]).drop_duplicates(subset="Member")
        print("WARNING: Plus one missing food selection:")
        for _, row in missing_p1_food.iterrows():
            missing = []
            if is_empty(row["Entry selection Plus 1"]):
                missing.append("entry")
            if is_empty(row["Main Course selection Plus 1"]):
                missing.append("main course")
            print(f"  - {row['If plus one, name?']} (plus one of {row['Member']}) — missing: {', '.join(missing)}")

    # Only include plus ones that meet both requirements
    plus_ones_mask = has_name & has_flag
    plus_ones = pd.DataFrame()
    plus_ones["First name"] = df.loc[plus_ones_mask, "If plus one, name?"].str.strip().values
    plus_ones["Last name"] = pd.NA
    plus_ones["Family"] = df.loc[plus_ones_mask, "Group"].values
    plus_ones["RSVP"] = primary.loc[plus_ones_mask, "RSVP"].values

    plus_one_count = len(plus_ones)

    # Combine and fill empty columns
    guest_list = pd.concat([primary, plus_ones], ignore_index=True)
    for col in OUTPUT_COLUMNS:
        if col not in guest_list.columns:
            guest_list[col] = ""

    guest_list = guest_list[OUTPUT_COLUMNS]

    if args.rsvp:
        rsvp_values = [r.value for r in args.rsvp]
        guest_list = guest_list[guest_list["RSVP"].isin(rsvp_values)]

    guest_list.to_csv(OUTPUT, index=False)

    print(f"Saved {OUTPUT}")
    print(f"  Primary guests: {len(primary)}")
    print(f"  Plus-ones:      {plus_one_count}")
    print(f"  Total rows:     {len(guest_list)}")


if __name__ == "__main__":
    main()

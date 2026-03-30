# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas"]
# ///

from io import StringIO

import pandas as pd

from import_rsvp import fetch_rsvp_data, to_csv
from transform_rsvp import RSVP, clean, resolve_rsvp

OUTPUT = "data/stats/final_guest_list.csv"

OUTPUT_COLUMNS = [
    "member",
    "is_plus_one",
    "entry",
    "main_course",
    "is_under_18",
    "allergies",
    "notes",
    "table_name",
]


def main():
    # Fetch RSVP data from Google Sheets and load into DataFrame
    data = fetch_rsvp_data()
    buf = StringIO()
    to_csv(data, buf)
    buf.seek(0)
    df = pd.read_csv(buf)

    # Clean
    df = clean(df)

    # Resolve RSVP and keep only RSVPed guests
    df["_rsvp"] = df.apply(resolve_rsvp, axis=1)
    df = df[df["_rsvp"] == RSVP.RSVPED]

    # Primary guest rows
    primary = pd.DataFrame()
    primary["member"] = df["Member"].str.strip().values
    primary["is_plus_one"] = ""
    primary["entry"] = df["Entry selection"].values
    primary["main_course"] = df["Main Course selection"].values
    primary["is_under_18"] = df["Under 18?"].values
    primary["allergies"] = df["Allergies"].values
    primary["notes"] = df["Notes"].values
    primary["table_name"] = df["Table name"].values

    # Plus-one rows
    has_name = df["If plus one, name?"].notna() & (df["If plus one, name?"].str.strip() != "")
    has_flag = df["Final Requested Plus One"] == True
    plus_ones_mask = has_name & has_flag

    plus_ones = pd.DataFrame()
    plus_ones["member"] = df.loc[plus_ones_mask, "If plus one, name?"].str.strip().values
    plus_ones["is_plus_one"] = df.loc[plus_ones_mask, "Member"].str.strip().values
    plus_ones["entry"] = df.loc[plus_ones_mask, "Entry selection Plus 1"].values
    plus_ones["main_course"] = df.loc[plus_ones_mask, "Main Course selection Plus 1"].values
    plus_ones["is_under_18"] = df.loc[plus_ones_mask, "Under 18?"].values
    plus_ones["allergies"] = df.loc[plus_ones_mask, "Allergies"].values
    plus_ones["notes"] = df.loc[plus_ones_mask, "Notes"].values
    plus_ones["table_name"] = df.loc[plus_ones_mask, "Table name"].values

    # Combine and save
    guest_list = pd.concat([primary, plus_ones], ignore_index=True)
    guest_list = guest_list[OUTPUT_COLUMNS]
    guest_list.to_csv(OUTPUT, index=False)

    print(f"Saved {OUTPUT}")
    print(f"  Primary guests: {len(primary)}")
    print(f"  Plus-ones:      {len(plus_ones)}")
    print(f"  Total rows:     {len(guest_list)}")


if __name__ == "__main__":
    main()

# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import csv
import json
import subprocess

SPREADSHEET_ID = "1wsk-TfDQNUttVQrk6Nl0UiiXN0dZ2lklxOMD-6pksts"
RANGE = "RSVP Tracker!B2:R140"
OUTPUT = "rsvp_tracker.csv"


def fetch_rsvp_data():
    result = subprocess.run(
        [
            "gws", "sheets", "+read",
            "--spreadsheet", SPREADSHEET_ID,
            "--range", RANGE,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # Skip the "Using keyring backend: keyring" line
    json_lines = result.stdout.splitlines()
    json_start = next(i for i, line in enumerate(json_lines) if line.strip().startswith("{"))
    return json.loads("\n".join(json_lines[json_start:]))


def to_csv(data, output):
    rows = data["values"]
    header = rows[0]
    num_cols = len(header)

    if isinstance(output, str):
        f = open(output, "w", newline="")
        should_close = True
    else:
        f = output
        should_close = False

    try:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows[1:]:
            cleaned = [cell.strip() for cell in row]
            cleaned += [""] * (num_cols - len(cleaned))
            writer.writerow(cleaned)
    finally:
        if should_close:
            f.close()

    if isinstance(output, str):
        print(f"Saved {output} ({len(rows) - 1} rows)")


def main():
    data = fetch_rsvp_data()
    to_csv(data, OUTPUT)


if __name__ == "__main__":
    main()

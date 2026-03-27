# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

"""
Fetch all RSVP form submissions from Gmail (via Squarespace) since Jan 18 2026
and build a structured guest list CSV.

Usage:
    python fetch_rsvp_emails.py
"""

import base64
import csv
import html
import json
import re
import subprocess
import sys

QUERY = "from:form-submission@squarespace.info after:2026/01/18 subject:RSVP"
OUTPUT = "data/rsvp_from_email.csv"

FIELDS = [
    "name",
    "email",
    "rsvp",
    "entry",
    "main_course",
    "rsvping_for_others",
    "allergies",
]

# Map the form labels (before the colon) to our field names
LABEL_MAP = {
    "Name / Nombre": "name",
    "Email / Correo": "email",
    "RSVP": "rsvp",
    "Entry / Entrada": "entry",
    "Main Course / Plato Fuerto": "main_course",
    "Main Course / Plato Fuerte": "main_course",
    "If you are RSVPing for others, please read below / Si está confirmando su asistencia en nombre de otras personas, lea a continuación.": "rsvping_for_others",
    "Any allergies? / Alguna alergia?": "allergies",
}


def gws_gmail(*args):
    """Run a gws gmail command and return parsed JSON."""
    result = subprocess.run(
        ["gws", "gmail", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{") or line.strip().startswith("["))
    return json.loads("\n".join(lines[json_start:]))


def list_message_ids():
    """List all RSVP message IDs matching the query."""
    all_ids = []
    page_token = None

    while True:
        params = {"userId": "me", "q": QUERY, "maxResults": 500}
        if page_token:
            params["pageToken"] = page_token

        data = gws_gmail("users", "messages", "list", "--params", json.dumps(params))
        messages = data.get("messages", [])
        all_ids.extend(m["id"] for m in messages)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_ids


def fetch_message(msg_id):
    """Fetch a single message and return its decoded HTML body."""
    data = gws_gmail(
        "users", "messages", "get",
        "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"}),
    )

    # Get date from headers
    headers = {h["name"]: h["value"] for h in data["payload"]["headers"]}
    date = headers.get("Date", "")

    # Decode body
    body_data = data["payload"]["body"].get("data", "")
    if not body_data:
        # Check parts
        for part in data["payload"].get("parts", []):
            if part.get("mimeType") == "text/html" and part["body"].get("data"):
                body_data = part["body"]["data"]
                break

    if not body_data:
        return None, date

    return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace"), date


def parse_rsvp_html(html_body):
    """
    Parse RSVP fields from the Squarespace form submission HTML.

    The HTML has fields duplicated (once in a hidden preview div, once in the
    visible body). We parse the first occurrence of each <b>Label:</b> <span>Value</span>.
    """
    # Decode HTML entities
    text = html.unescape(html_body)

    # Extract <b>...</b> followed by <span>...</span>
    pairs = re.findall(r"<b>(.*?)</b>\s*<span>(.*?)</span>", text, re.DOTALL)

    record = {}
    for label, value in pairs:
        label = label.rstrip(":").strip()
        field = LABEL_MAP.get(label)
        if field and field not in record:
            record[field] = value.strip()

    return record


def main():
    print(f"Fetching RSVP message IDs...")
    msg_ids = list_message_ids()
    print(f"Found {len(msg_ids)} emails")

    records = []
    for i, msg_id in enumerate(msg_ids, 1):
        print(f"\r  Fetching {i}/{len(msg_ids)}...", end="", flush=True)
        body, date = fetch_message(msg_id)
        if not body:
            print(f"\n  WARNING: No body for message {msg_id}, skipping")
            continue

        record = parse_rsvp_html(body)
        record["date"] = date
        record["message_id"] = msg_id
        records.append(record)

    print(f"\n  Parsed {len(records)} submissions")

    # Sort by date (most recent first)
    records.sort(key=lambda r: r.get("date", ""), reverse=True)

    # Write CSV
    all_fields = ["date", "message_id"] + FIELDS
    with open(OUTPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    print(f"\nSaved {OUTPUT} ({len(records)} rows)")

    # Summary stats
    accepts = sum(1 for r in records if "accepts" in r.get("rsvp", "").lower())
    declines = sum(1 for r in records if "declines" in r.get("rsvp", "").lower())
    other = len(records) - accepts - declines
    print(f"  Accepts:  {accepts}")
    print(f"  Declines: {declines}")
    if other:
        print(f"  Other:    {other}")


if __name__ == "__main__":
    main()

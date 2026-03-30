# /// script
# requires-python = ">=3.11"
# dependencies = ["python-dotenv"]
# ///

"""
Bulk-send wedding passes and info images to guests via Gmail.

Usage:
    uv run bulk_send_wedding_info.py                        # dry run
    uv run bulk_send_wedding_info.py --send                 # send all
    uv run bulk_send_wedding_info.py --send --email X@Y.Z   # send to one (testing)
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import defaultdict
from email.encoders import encode_base64
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from compare_rsvp import (
    build_email_lookup,
    build_others_lookup,
    find_source,
    normalize,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
FINAL_GUEST_LIST = PROJECT_DIR / "data" / "stats" / "final_guest_list.csv"
EMAIL_RSVP = PROJECT_DIR / "data" / "rsvp_from_email.csv"
APPLE_PASSES_DIR = PROJECT_DIR / "data" / "passes" / "apple"
GOOGLE_PASSES_DIR = PROJECT_DIR / "data" / "passes" / "google"
ATTACHMENTS_DIR = PROJECT_DIR / "data" / "attachments"
INFO_IMAGES = [
    ATTACHMENTS_DIR / "InfoBodaJuanMaddy_Espanol.png",
    ATTACHMENTS_DIR / "InfoWeddingJuanMaddy_English.png",
]


# ---------------------------------------------------------------------------
# Inline copies from create_passes.py (avoid import side-effects)
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Guest name -> safe filename (strip accents, lowercase, underscores)."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode()
    return ascii_name.lower().replace(" ", "_")


def table_to_image_key(table_name: str) -> str:
    """'Azul de Adonis' -> 'azul_de_adonis'"""
    key = table_name.lower().replace(" ", "_")
    return unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def resolve_passes(member, table_name):
    """Return (apple_path, google_path) for a guest. Paths may not exist."""
    table_key = table_to_image_key(table_name)
    filename = sanitize_filename(member)
    apple = APPLE_PASSES_DIR / table_key / f"{filename}.pkpass"
    google = GOOGLE_PASSES_DIR / table_key / f"{filename}.txt"
    return apple, google


def build_email_groups(final_rows, email_rows):
    """
    Map each guest to the email address that should receive their passes.

    Returns:
        email_groups: dict[email_address, list[guest_row]]
        exceptions:   list[guest_row]  (no email found)
    """
    email_lookup = build_email_lookup(email_rows)
    others_lookup = build_others_lookup(email_rows)

    # Manual overrides from MANUAL_EMAIL env var (name=email pairs, comma-separated)
    MANUAL_EMAIL = {}
    raw = os.environ.get("MANUAL_EMAIL", "")
    for pair in raw.split(","):
        if "=" in pair:
            name, email = pair.strip().rsplit("=", 1)
            MANUAL_EMAIL[normalize(name)] = email.strip()

    email_groups = defaultdict(list)
    exceptions = []

    for row in final_rows:
        member = row["member"].strip()
        nmember = normalize(member)

        # Manual override takes priority
        if nmember in MANUAL_EMAIL:
            email_groups[MANUAL_EMAIL[nmember]].append(row)
            continue

        source, label = find_source(nmember, email_lookup, others_lookup)

        if source is None:
            exceptions.append(row)
            continue

        # Direct email match — source has an "email" key
        if "email" in source:
            email_groups[source["email"]].append(row)
        # Submitted by someone else — two-hop lookup
        elif "submitted_by" in source:
            submitter_n = normalize(source["submitted_by"])
            if submitter_n in email_lookup:
                email_groups[email_lookup[submitter_n]["email"]].append(row)
            else:
                # Submitter not in email lookup (shouldn't happen)
                exceptions.append(row)
        else:
            exceptions.append(row)

    # Second pass: resolve unmatched plus-ones via their primary guest's email
    member_to_email = {}
    for email, guests in email_groups.items():
        for g in guests:
            member_to_email[normalize(g["member"])] = email

    still_exceptions = []
    for row in exceptions:
        plus_one_of = row.get("is_plus_one", "").strip()
        if plus_one_of:
            primary_n = normalize(plus_one_of)
            if primary_n in member_to_email:
                email_groups[member_to_email[primary_n]].append(row)
                continue
        still_exceptions.append(row)

    return dict(email_groups), still_exceptions


def print_send_plan(email_groups, exceptions):
    """Print the full email → guests mapping for review."""
    total_guests = sum(len(g) for g in email_groups.values())
    print("=" * 70)
    print("EMAIL SEND PLAN")
    print("=" * 70)
    print(f"\n{len(email_groups)} emails to send, covering {total_guests} guests")
    print(f"{len(exceptions)} guests with no email (exceptions)\n")

    for i, (email, guests) in enumerate(sorted(email_groups.items()), 1):
        names = [g["member"] for g in guests]
        print(f"--- [{i}] {email} ({len(guests)} guest{'s' if len(guests) > 1 else ''}) ---")
        for j, g in enumerate(guests, 1):
            apple, google = resolve_passes(g["member"], g["table_name"])
            a_ok = "OK" if apple.exists() else "MISSING"
            g_ok = "OK" if google.exists() else "MISSING"
            print(f"  {j}. {g['member']}  (table: {g['table_name']})")
            print(f"     Apple:  [{a_ok}] {apple.name}")
            print(f"     Google: [{g_ok}] {google.name}")
        print()

    if exceptions:
        print("--- EXCEPTIONS (no email found) ---")
        for g in exceptions:
            po = f"  (plus one of {g['is_plus_one']})" if g["is_plus_one"] else ""
            print(f"  - {g['member']}{po}  (table: {g['table_name']})")
        print()


# ---------------------------------------------------------------------------
# Email construction & sending
# ---------------------------------------------------------------------------
def gws_gmail(*args):
    """Run a gws gmail command and return parsed JSON."""
    result = subprocess.run(
        ["gws", "gmail", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines()
    json_start = next(
        i for i, line in enumerate(lines)
        if line.strip().startswith("{") or line.strip().startswith("[")
    )
    return json.loads("\n".join(lines[json_start:]))


def get_sender_email():
    data = gws_gmail("users", "getProfile", "--params", json.dumps({"userId": "me"}))
    return data["emailAddress"]


def build_mime_message(sender, to_email, guests):
    """Build a MIME message with passes and info images attached."""
    guest_names = [g["member"] for g in guests]
    names_str = ", ".join(guest_names)

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = "Boda Reyes Vann - Pases de entrada / Wedding Passes"

    body = f"""\
<html><body style="font-family: sans-serif; font-size: 14px; color: #222;">
<p>Hola {names_str}!</p>
<p>Adjunto encontrarán sus pases de entrada para la boda.</p>
<ul>
<li>Los archivos .pkpass son para Apple Wallet (iPhone): ábrelos directamente desde tu teléfono</li>
<li>Los archivos .txt contienen enlaces para Google Wallet (Android). Es necesario que me mandes tu cuenta de Gmail para darte acceso. Luego, abre el enlace en tu teléfono.</li>
<li>Las imágenes adjuntas tienen la información del evento</li>
</ul>
<p>¡Nos vemos el 11 de abril!</p>
<hr>
<p>Hi {names_str}!</p>
<p>Attached you'll find your wedding entry passes.</p>
<ul>
<li>The .pkpass files are for Apple Wallet (iPhone): open them directly on your phone</li>
<li>The .txt files contain links for Google Wallet (Android). It is necessary to send me your Gmail account so I can give you access. Then, open the link on your phone.</li>
<li>The attached images have the event information</li>
</ul>
<p>See you on April 11th!</p>
<p>Juan &amp; Maddy</p>
</body></html>"""
    msg.attach(MIMEText(body, "html", "utf-8"))

    # Attach info images
    for img_path in INFO_IMAGES:
        with open(img_path, "rb") as f:
            img = MIMEImage(f.read(), name=img_path.name)
            img.add_header("Content-Disposition", "attachment", filename=img_path.name)
            msg.attach(img)

    # Attach passes for each guest
    for g in guests:
        apple, google = resolve_passes(g["member"], g["table_name"])

        if apple.exists():
            part = MIMEBase("application", "vnd.apple.pkpass")
            with open(apple, "rb") as f:
                part.set_payload(f.read())
            encode_base64(part)
            part.add_header(
                "Content-Disposition", "attachment",
                filename=apple.name,
            )
            msg.attach(part)

        if google.exists():
            with open(google, "r") as f:
                txt = MIMEText(f.read(), "plain", "utf-8")
            txt.add_header(
                "Content-Disposition", "attachment",
                filename=google.name,
            )
            msg.attach(txt)

    return msg


def send_email(mime_msg):
    """Send a MIME message via the gws Gmail CLI. Returns (success, msg_id)."""
    with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
        tmp.write(mime_msg.as_bytes())
        tmp_path = tmp.name

    try:
        data = gws_gmail(
            "users", "messages", "send",
            "--params", json.dumps({"userId": "me"}),
            "--upload", tmp_path,
            "--upload-content-type", "message/rfc822",
        )
        return True, data.get("id", "?")
    except subprocess.CalledProcessError as e:
        print(f"  ERROR (return code {e.returncode}):")
        if e.stdout:
            print(f"  STDOUT: {e.stdout}")
        if e.stderr:
            print(f"  STDERR: {e.stderr}")
        return False, None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Bulk send wedding passes via Gmail")
    parser.add_argument("--send", action="store_true", help="Actually send (default is dry run)")
    parser.add_argument("--email", help="Send only to this email (for testing)")
    args = parser.parse_args()

    final_rows = load_csv(FINAL_GUEST_LIST)
    email_rows = load_csv(EMAIL_RSVP)

    email_groups, exceptions = build_email_groups(final_rows, email_rows)
    print_send_plan(email_groups, exceptions)

    if not args.send:
        print("Dry run complete. Use --send to actually send emails.")
        return

    # --- Send phase ---
    sender = get_sender_email()
    print(f"\nSending from: {sender}")

    targets = email_groups
    if args.email:
        if args.email not in email_groups:
            print(f"Email {args.email} not found in groups.")
            sys.exit(1)
        targets = {args.email: email_groups[args.email]}

    sent = 0
    failed = 0
    for i, (to_email, guests) in enumerate(sorted(targets.items()), 1):
        names = ", ".join(g["member"] for g in guests)
        mime_msg = build_mime_message(sender, to_email, guests)
        ok, msg_id = send_email(mime_msg)
        if ok:
            sent += 1
            print(f"  [{i}/{len(targets)}] Sent to {to_email} ({len(guests)} guests: {names}) — id: {msg_id}")
        else:
            failed += 1
            print(f"  [{i}/{len(targets)}] FAILED for {to_email}")
        time.sleep(0.5)

    print(f"\nDone. Sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    main()

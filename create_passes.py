# /// script
# requires-python = ">=3.11"
# dependencies = ["wallet-py3k", "Pillow", "python-dotenv"]
# ///

"""
Generate Apple Wallet (.pkpass) passes for wedding guests.

Usage:
    uv run create_passes.py --table Monarca          # One table
    uv run create_passes.py --all                    # All tables
    uv run create_passes.py --table Monarca --type google  # Google only (future)
"""

import argparse
import csv
import io
import os
import sys
import unicodedata
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from wallet.models import EventTicket, Field, Location, Pass

load_dotenv()

# ── Configuration ───────────────────────────────────────────────
PASS_TYPE_IDENTIFIER = os.environ["PASS_TYPE_IDENTIFIER"]
TEAM_IDENTIFIER = os.environ["APPLE_ISSUER_ID"]
CERT_PASSWORD = os.environ["CERT_PASSWORD"]
ORGANIZATION_NAME = "Reyes Vann"

CERT_DIR = Path("certs")
CERT_FILE = CERT_DIR / "pass_cert.pem"
KEY_FILE = CERT_DIR / "pass_key.pem"
WWDR_FILE = CERT_DIR / "wwdr.pem"

GUEST_LIST = Path("data/stats/final_guest_list.csv")
OUTPUT_BASE = Path("data/passes")
IMAGES_DIR = Path("images")

BG_COLOR = "rgb(21, 21, 21)"
FG_COLOR = "rgb(255, 255, 255)"
LABEL_COLOR = "rgb(255, 220, 180)"

# ── Event details ───────────────────────────────────────────────
VENUE_NAME = "Palacio Metropolitano"
VENUE_ADDRESS = (
    "Palacio Metropolitano, C. de Tacuba 15, Centro Historico de la "
    "Cdad. de Mexico, Centro, Cuauhtemoc, 06000 Ciudad de Mexico, CDMX"
)
VENUE_LAT = 19.4352
VENUE_LON = -99.1393
EVENT_DATE_DISPLAY = "11 de Abril de 2026"
ARRIVAL_DISPLAY = "5:00pm."
ARRIVAL_BACK = "5:00pm. Ultima entrada es a las 5:25pm."
RELEVANT_DATE = "2026-04-11T17:00:00-06:00"

# ── Back side links ─────────────────────────────────────────────
BACK_FIELDS = [
    ("venue", "Donde", VENUE_ADDRESS),
    ("arrival_info", "Llegada", ARRIVAL_BACK),
    (
        "pov_app",
        "POV app (click para unirte!)",
        "https://pov.camera/i/1818B396-FCC1-456A-A3EA-3D6000CEED51",
    ),
    (
        "maps_link",
        "Google Maps Link al salon",
        "https://share.google/FPZdT01tpp3QTF02w",
    ),
    ("website", "Sitio Web", "https://www.reyesvann.com/"),
    ("registry", "Mesa de Regalos", "https://www.reyesvann.com/registry"),
]

# ── Image specs for Apple Wallet ────────────────────────────────
# Background = full-pass butterfly (blurred by iOS)
# Logo = from images/logo.png (JC & M monogram), narrower to avoid stretching
LOGO_PATH = IMAGES_DIR / "logo.png"

ICON_SPECS = {
    "icon.png": (29, 29),
    "icon@2x.png": (58, 58),
    "icon@3x.png": (87, 87),
}

LOGO_SPECS = {
    "logo.png": (140, 50),
    "logo@2x.png": (280, 100),
}

STRIP_SPECS = {
    "strip.png": (375, 123),
    "strip@2x.png": (750, 246),
    "strip@3x.png": (1125, 369),
}


class WalletType(Enum):
    APPLE = "apple"
    GOOGLE = "google"
    BOTH = "both"


# ── Helpers ─────────────────────────────────────────────────────


def table_to_image_key(table_name: str) -> str:
    """'Azul de Adonis' -> 'azul_de_adonis'"""
    key = table_name.lower().replace(" ", "_")
    return unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()


def sanitize_filename(name: str) -> str:
    """Guest name -> safe filename (strip accents, lowercase, underscores)."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode()
    return ascii_name.lower().replace(" ", "_")


def format_food(value: str) -> str:
    """'Kids Food' -> 'Kids menu', otherwise pass through."""
    if value.strip().lower() == "kids food":
        return "Kids menu"
    return value


def load_guests(csv_path: Path) -> list[dict]:
    """Load guest list from CSV."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def guests_for_table(guests: list[dict], table_name: str) -> list[dict]:
    """Filter guests to a specific table (case-insensitive)."""
    return [g for g in guests if g["table_name"].lower() == table_name.lower()]


def _resize_image(img: Image.Image, w: int, h: int) -> bytes:
    """Center-crop and resize an image to target dimensions, return PNG bytes."""
    src_w, src_h = img.size
    target_ratio = w / h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        cropped = img.crop((offset, 0, offset + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        cropped = img.crop((0, offset, src_w, offset + new_h))

    resized = cropped.resize((w, h), Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, "PNG")
    return buf.getvalue()


def prepare_apple_images(butterfly_path: Path) -> dict[str, bytes]:
    """Build all Apple Wallet image assets.

    - icon: from butterfly
    - logo: from images/logo.png (JC & M monogram)
    - strip: from butterfly (clear, unblurred banner)

    Returns a dict of filename -> PNG bytes.
    """
    butterfly = Image.open(butterfly_path)
    logo_img = Image.open(LOGO_PATH)
    result = {}

    for filename, (w, h) in ICON_SPECS.items():
        result[filename] = _resize_image(butterfly, w, h)

    for filename, (w, h) in LOGO_SPECS.items():
        result[filename] = _resize_image(logo_img, w, h)

    for filename, (w, h) in STRIP_SPECS.items():
        result[filename] = _resize_image(butterfly, w, h)

    return result


def create_apple_pass(
    guest: dict, serial: int, images: dict[str, bytes]
) -> bytes:
    """Build and sign one .pkpass for a single guest. Returns bytes."""
    member = guest["member"]
    entry = format_food(guest["entry"])
    main_course = format_food(guest["main_course"])

    # Build event ticket fields
    event_info = EventTicket()
    event_info.addHeaderField("venue", VENUE_NAME, "LUGAR")
    event_info.addPrimaryField("guest_name", member, "INVITADO")
    event_info.addSecondaryField("date", EVENT_DATE_DISPLAY, "FECHA")
    event_info.addSecondaryField("arrival", ARRIVAL_DISPLAY, "LLEGADA")
    event_info.addAuxiliaryField("entry", entry, "ENTRADA")
    event_info.addAuxiliaryField("main_course", main_course, "PLATO FUERTE")

    for key, label, value in BACK_FIELDS:
        event_info.addBackField(key, value, label)

    # Build pass
    p = Pass(
        event_info,
        passTypeIdentifier=PASS_TYPE_IDENTIFIER,
        organizationName=ORGANIZATION_NAME,
        teamIdentifier=TEAM_IDENTIFIER,
    )
    p.serialNumber = f"wedding-{serial:03d}"
    p.description = "Boda Reyes Vann - 11 de Abril 2026"
    p.backgroundColor = BG_COLOR
    p.foregroundColor = FG_COLOR
    p.labelColor = LABEL_COLOR
    p.relevantDate = RELEVANT_DATE
    p.locations = [Location(latitude=VENUE_LAT, longitude=VENUE_LON)]

    # Add images
    for filename, data in images.items():
        p.addFile(filename, io.BytesIO(data))

    # Sign and create .pkpass
    output_buf = io.BytesIO()
    p.create(
        certificate=str(CERT_FILE),
        key=str(KEY_FILE),
        wwdr_certificate=str(WWDR_FILE),
        password=CERT_PASSWORD,
        zip_file=output_buf,
    )
    return output_buf.getvalue()


def generate_passes_for_table(
    table_name: str,
    wallet_type: WalletType = WalletType.APPLE,
) -> None:
    """Filter CSV to table, generate passes for each member."""
    guests = load_guests(GUEST_LIST)
    table_guests = guests_for_table(guests, table_name)

    if not table_guests:
        print(f"No guests found for table '{table_name}'")
        sys.exit(1)

    print(f"Table '{table_name}': {len(table_guests)} guests")

    if wallet_type in (WalletType.APPLE, WalletType.BOTH):
        _generate_apple_passes(table_name, table_guests)

    if wallet_type in (WalletType.GOOGLE, WalletType.BOTH):
        print("Google Wallet generation not yet implemented.")


def _generate_apple_passes(table_name: str, table_guests: list[dict]) -> None:
    """Generate Apple .pkpass files for a list of guests."""
    image_key = table_to_image_key(table_name)
    image_path = IMAGES_DIR / f"{image_key}.png"

    if not image_path.exists():
        print(f"Image not found: {image_path}")
        sys.exit(1)

    images = prepare_apple_images(image_path)
    output_dir = OUTPUT_BASE / "apple" / image_key
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, guest in enumerate(table_guests, start=1):
        pass_bytes = create_apple_pass(guest, serial=i, images=images)
        filename = sanitize_filename(guest["member"]) + ".pkpass"
        output_path = output_dir / filename
        output_path.write_bytes(pass_bytes)
        print(f"  {guest['member']} -> {output_path}")

    print(f"Generated {len(table_guests)} Apple Wallet passes in {output_dir}")


# ── CLI ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Generate wallet passes for wedding guests.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--table", help="Table name to generate passes for")
    group.add_argument("--all", action="store_true", help="Generate for all tables")
    parser.add_argument(
        "--type",
        choices=["apple", "google", "both"],
        default="apple",
        help="Wallet type (default: apple)",
    )
    args = parser.parse_args()

    wallet_type = WalletType(args.type)

    if args.all:
        guests = load_guests(GUEST_LIST)
        tables = sorted({g["table_name"] for g in guests})
        for table in tables:
            generate_passes_for_table(table, wallet_type)
    else:
        generate_passes_for_table(args.table, wallet_type)


if __name__ == "__main__":
    main()

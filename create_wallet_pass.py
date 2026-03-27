# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth", "requests"]
# ///

"""
Create Google Wallet passes for wedding guests.

Prerequisites
─────────────
1. Google Cloud project with the Google Wallet API enabled:
   gcloud services enable walletobjects.googleapis.com

2. Service account with permissions — add its email as a user in the
   Google Pay & Wallet Console (pay.google.com/business/console).

3. Download the service account key JSON to this directory as
   "service_account.json".

4. Copy your Issuer ID from the Wallet Console and set it below.

5. Push this repo to GitHub so the monarch image has a public raw URL,
   then update HERO_IMAGE_URL below.
"""

import json
import uuid

import google.auth.jwt
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

# ── Configuration ───────────────────────────────────────────────
SERVICE_ACCOUNT_FILE = "service_account.json"
ISSUER_ID = "<YOUR_ISSUER_ID>"
CLASS_SUFFIX = "wedding-guest-pass"
CLASS_ID = f"{ISSUER_ID}.{CLASS_SUFFIX}"

# Update after pushing repo to GitHub:
# https://raw.githubusercontent.com/<OWNER>/<REPO>/main/images/monarch.png
HERO_IMAGE_URL = "<YOUR_PUBLIC_IMAGE_URL>"

SCOPES = ["https://www.googleapis.com/auth/wallet_object.issuer"]


# ── Helpers ─────────────────────────────────────────────────────

def get_credentials():
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES,
    )


def create_class(session):
    """Create the pass class (template) if it doesn't already exist."""
    url = "https://walletobjects.googleapis.com/walletobjects/v1/genericClass"
    resp = session.get(f"{url}/{CLASS_ID}")
    if resp.status_code == 200:
        print(f"Class already exists: {CLASS_ID}")
        return

    payload = {
        "id": CLASS_ID,
        "classTemplateInfo": {
            "cardTemplateOverride": {
                "cardRowTemplateInfos": [
                    {
                        "twoItems": {
                            "startItem": {
                                "firstValue": {
                                    "fields": [
                                        {"fieldPath": "object.textModulesData['entry']"}
                                    ]
                                }
                            },
                            "endItem": {
                                "firstValue": {
                                    "fields": [
                                        {"fieldPath": "object.textModulesData['main']"}
                                    ]
                                }
                            },
                        }
                    }
                ]
            }
        },
    }

    resp = session.post(url, json=payload)
    if resp.status_code in (200, 201):
        print(f"Created class: {CLASS_ID}")
    else:
        raise RuntimeError(f"Failed to create class: {resp.status_code}\n{resp.text}")


def create_wallet_link(credentials, guest, entry, main_course):
    """Generate an 'Add to Google Wallet' save link for one guest."""
    object_id = f"{ISSUER_ID}.{uuid.uuid4().hex}"

    pass_object = {
        "id": object_id,
        "classId": CLASS_ID,
        "genericType": "GENERIC_TYPE_UNSPECIFIED",
        "hexBackgroundColor": "#6B3410",
        "logo": {
            "sourceUri": {"uri": HERO_IMAGE_URL},
            "contentDescription": {
                "defaultValue": {"language": "en", "value": "Wedding"}
            },
        },
        "heroImage": {
            "sourceUri": {"uri": HERO_IMAGE_URL},
            "contentDescription": {
                "defaultValue": {"language": "en", "value": "Wedding Invitation"}
            },
        },
        "cardTitle": {
            "defaultValue": {"language": "en", "value": "Wedding Invitation"}
        },
        "header": {
            "defaultValue": {"language": "en", "value": guest}
        },
        "textModulesData": [
            {"id": "entry", "header": "Entry", "body": entry},
            {"id": "main", "header": "Main Course", "body": main_course},
        ],
    }

    claims = {
        "iss": credentials.service_account_email,
        "aud": "google",
        "origins": [],
        "typ": "savetowallet",
        "payload": {"genericObjects": [pass_object]},
    }

    token = google.auth.jwt.encode(credentials.signer, claims)
    return f"https://pay.google.com/gp/v/save/{token.decode()}"


# ── Main ────────────────────────────────────────────────────────

def main():
    credentials = get_credentials()
    session = AuthorizedSession(credentials)

    # 1. Ensure the pass class exists
    create_class(session)

    # 2. Generate a sample pass link (trial run)
    link = create_wallet_link(
        credentials,
        guest="Juan Reyes",
        entry="Ensalada Caesar",
        main_course="Pollo al Horno",
    )
    print(f"\nAdd to Google Wallet:\n{link}\n")


if __name__ == "__main__":
    main()

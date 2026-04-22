#!/usr/bin/env python3
"""
One-time migration script: Cloudflare KV → Firestore (REST API Version)

This version uses the Cloudflare REST API directly, bypassing Wrangler CLI issues.

Usage:
  1. Generate a Cloudflare API Token with "Account.Workers KV Storage: Read" permissions.
  2. Set the environment variables:
     export CLOUDFLARE_API_TOKEN="your-token"
     export GOOGLE_APPLICATION_CREDENTIALS="path/to/sa-key.json"
  3. Run the script:
     ./.venv/bin/python migrate_kv_to_firestore.py
"""

import json
import os
import sys
import requests
from google.cloud import firestore

# --- CONFIGURATION ---
ACCOUNT_ID = "037e9c0d842b4bdab78db12c878583d6"
KV_NAMESPACE_ID = "3425d31abf8940c8b9d7b9193634960d"

def get_cloudflare_data():
    """Fetch all KV data using the Cloudflare REST API."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        print("Error: CLOUDFLARE_API_TOKEN environment variable not set.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    base_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{KV_NAMESPACE_ID}"
    
    print("Listing KV keys via API...")
    keys = []
    cursor = ""
    
    while True:
        url = f"{base_url}/keys"
        if cursor:
            url += f"?cursor={cursor}"
            
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error listing keys: {response.status_code} - {response.text}")
            sys.exit(1)
            
        data = response.json()
        if not data.get("success"):
            print(f"API Error: {data.get('errors')}")
            sys.exit(1)
            
        keys.extend(data.get("result", []))
        
        # Check for pagination
        cursor = data.get("result_info", {}).get("cursor")
        if not cursor:
            break

    print(f"Found {len(keys)} keys")

    entries = []
    for key_obj in keys:
        key_name = key_obj["name"]
        print(f"  Fetching: {key_name}")
        
        val_url = f"{base_url}/values/{key_name}"
        val_response = requests.get(val_url, headers=headers)
        
        if val_response.status_code != 200:
            print(f"    SKIP (error): {val_response.status_code}")
            continue

        try:
            value = val_response.json()
        except Exception:
            print(f"    SKIP (invalid JSON)")
            continue

        # Parse user email from key: "user@email.com:uuid"
        parts = key_name.split(":", 1)
        if len(parts) != 2:
            print(f"    SKIP (unexpected key format: {key_name})")
            continue

        user_email, scenario_uuid = parts
        entries.append({
            "user_email": user_email,
            "scenario_id": scenario_uuid,
            "value": value,
        })

    return entries


def migrate_to_firestore(entries):
    """Write KV entries to Firestore."""
    db = firestore.Client()
    batch = db.batch()

    for i, entry in enumerate(entries):
        # The document ID in Firestore is the scenario UUID
        doc_ref = db.collection("scenarios").document(entry["scenario_id"])
        
        # Structure matches our new Firestore schema
        doc_data = {
            "user_email": entry["user_email"],
            "name": entry["value"].get("name"),
            "data": entry["value"].get("data"),
            "last_modified": entry["value"].get("last_modified", 0),
        }
        batch.set(doc_ref, doc_data)
        print(f"  Staged: {entry['user_email']} / {doc_data['name']} ({entry['scenario_id']})")

        # Firestore batches limited to 500 writes
        if (i + 1) % 500 == 0:
            batch.commit()
            print(f"  Committed batch of 500")
            batch = db.batch()

    batch.commit()
    print(f"\nMigrated {len(entries)} scenarios to Firestore!")


if __name__ == "__main__":
    print("=== Cloudflare KV → Firestore Migration (REST API) ===\n")

    entries = get_cloudflare_data()
    if not entries:
        print("No entries to migrate. Check your Token permissions and IDs.")
        sys.exit(0)

    print(f"\nReady to migrate {len(entries)} scenarios to Firestore.")
    confirm = input("Proceed? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    migrate_to_firestore(entries)
    print("\nDone!")

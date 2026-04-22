#!/usr/bin/env python3
"""
One-time migration script: Cloudflare KV → Firestore

Usage:
  1. Export all KV keys from Cloudflare:
     wrangler kv:key list --namespace-id=3425d31abf8940c8b9d7b9193634960d > kv_keys.json

  2. For each key, download the value:
     wrangler kv:get <key> --namespace-id=3425d31abf8940c8b9d7b9193634960d > kv_values/<key>.json

  OR use the bulk export approach below.

  3. Run this script:
     GOOGLE_APPLICATION_CREDENTIALS=path/to/sa-key.json python migrate_kv_to_firestore.py

KV key format: "<user_email>:<scenario_uuid>"
KV value format: {"id": "...", "name": "...", "data": {...}, "last_modified": 1234567890.0}
"""

import json
import os
import subprocess
import sys

from google.cloud import firestore


KV_NAMESPACE_ID = "3425d31abf8940c8b9d7b9193634960d"
ACCOUNT_ID = "037e9c0d842b4bdab78db12c878583d6"


def export_kv_data():
    """Export all KV data using wrangler CLI."""
    print("Listing KV keys...")
    
    # Use environment variable for account ID since wrangler kv key commands 
    # often don't support it as a flag.
    env = os.environ.copy()
    if ACCOUNT_ID:
        env["CLOUDFLARE_ACCOUNT_ID"] = ACCOUNT_ID

    result = subprocess.run(
        ["npx", "wrangler", "kv", "key", "list", f"--namespace-id={KV_NAMESPACE_ID}", "--preview", "false"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__),
        env=env
    )
    if result.returncode != 0:
        print(f"Error listing keys: {result.stderr}")
        sys.exit(1)

    keys = json.loads(result.stdout)
    print(f"Found {len(keys)} keys")

    entries = []
    for key_obj in keys:
        key_name = key_obj["name"]
        print(f"  Fetching: {key_name}")
        val_result = subprocess.run(
            ["npx", "wrangler", "kv", "key", "get", f"--namespace-id={KV_NAMESPACE_ID}", "--preview", "false", key_name],
            capture_output=True, text=True, cwd=os.path.dirname(__file__),
            env=env
        )
        if val_result.returncode != 0:
            print(f"    SKIP (error): {val_result.stderr}")
            continue

        try:
            value = json.loads(val_result.stdout)
        except json.JSONDecodeError:
            print(f"    SKIP (invalid JSON)")
            continue

        # Parse user email from key: "user@email.com:uuid"
        parts = key_name.split(":", 1)
        if len(parts) != 2:
            print(f"    SKIP (unexpected key format)")
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
        doc_ref = db.collection("scenarios").document(entry["scenario_id"])
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
    print("=== Cloudflare KV → Firestore Migration ===\n")

    entries = export_kv_data()
    if not entries:
        print("No entries to migrate.")
        sys.exit(0)

    print(f"\nReady to migrate {len(entries)} scenarios to Firestore.")
    confirm = input("Proceed? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    migrate_to_firestore(entries)
    print("\nDone! You can now decommission the Cloudflare KV namespace.")

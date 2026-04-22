"""
Firebase Authentication helper for Cloud Run.

Verifies Firebase ID tokens (from Firebase Auth SDK on the frontend)
and extracts the user's email for scenario namespacing.
"""

from functools import lru_cache
from typing import Optional

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials


@lru_cache(maxsize=1)
def _init_firebase():
    """Initialise Firebase Admin SDK (once)."""
    if not firebase_admin._apps:
        # Explicit project_id helps if environment detection fails
        firebase_admin.initialize_app(options={
            'projectId': 'uk-retirement-planner'
        })


def verify_token(authorization: Optional[str]) -> Optional[dict]:
    """
    Verify a Firebase ID token from the Authorization header.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]  # Strip 'Bearer '

    try:
        _init_firebase()
        decoded = firebase_auth.verify_id_token(token)
        return decoded
    except Exception as e:
        print(f"DEBUG: Firebase Token Verification Failed: {e}")
        return None


def get_user_email(decoded_token: Optional[dict]) -> Optional[str]:
    """Extract user email from a decoded Firebase token. Used as scenario namespace key."""
    if not decoded_token:
        return None
    return decoded_token.get("email") or decoded_token.get("uid")

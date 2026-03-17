"""
Cloudflare Access JWT authentication.

When CF_ACCESS_AUD and CF_TEAM_NAME are present (i.e. deployed on Cloudflare),
every request to protected routes must carry a valid Cf-Access-Jwt-Assertion
header issued by your Access application.

When those vars are absent (local development), get_current_user returns None
and scenario routes are disabled gracefully (KV isn't available locally anyway).
"""

import json
import time
from typing import Optional

from fastapi import HTTPException, Request

try:
    import jwt
    from jwt.algorithms import RSAAlgorithm
    _JWT_AVAILABLE = True
except ImportError:
    _JWT_AVAILABLE = False

# ---------------------------------------------------------------------------
# In-process JWKS cache: { "keys": [...], "fetched_at": float }
# ---------------------------------------------------------------------------
_jwks_cache: dict = {}
_JWKS_TTL_SECONDS = 3600  # re-fetch public keys every hour


async def _fetch_jwks(team_name: str) -> list:
    """Fetch Cloudflare Access public keys (JWKS), with a simple TTL cache."""
    now = time.time()
    if _jwks_cache.get("fetched_at", 0) + _JWKS_TTL_SECONDS > now and _jwks_cache.get("keys"):
        return _jwks_cache["keys"]

    url = f"https://{team_name}.cloudflareaccess.com/cdn-cgi/access/certs"

    # In a Cloudflare Worker we use the js `fetch` global.
    # Fall back to urllib for local / test runs.
    try:
        from js import fetch as js_fetch  # type: ignore[import]
        response = await js_fetch(url)
        text = await response.text()
        jwks = json.loads(text)
    except ImportError:
        import urllib.request
        with urllib.request.urlopen(url) as resp:  # noqa: S310
            jwks = json.loads(resp.read())

    keys = jwks.get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def _get_token_from_request(request: Request) -> Optional[str]:
    """Extract the JWT from the Cf-Access-Jwt-Assertion header or CF_Authorization cookie."""
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if token:
        return token
    cookie = request.cookies.get("CF_Authorization")
    return cookie or None


async def get_current_user(request: Request) -> Optional[dict]:
    """
    FastAPI dependency.

    Returns:
        dict  — decoded JWT payload (includes 'email' and 'sub') when authenticated.
        None  — when running locally (CF_ACCESS_AUD not configured).

    Raises:
        HTTPException(401) — token missing or invalid in a deployed environment.
    """
    # Retrieve env from request state (populated by the Worker entrypoint)
    env = getattr(request.state, "env", {}) or {}
    aud = env.get("CF_ACCESS_AUD") if isinstance(env, dict) else getattr(env, "CF_ACCESS_AUD", None)
    team = env.get("CF_TEAM_NAME") if isinstance(env, dict) else getattr(env, "CF_TEAM_NAME", None)

    # Local development — auth not configured
    if not aud or not team:
        return None

    if not _JWT_AVAILABLE:
        raise HTTPException(status_code=500, detail="PyJWT not available — check dependencies.")

    token = _get_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing Cloudflare Access token.")

    try:
        jwks_keys = await _fetch_jwks(team)

        # Try each key until one validates the token
        last_error: Optional[Exception] = None
        for jwk in jwks_keys:
            try:
                public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=["RS256"],
                    audience=aud,
                    options={"verify_exp": True},
                )
                return payload  # success
            except jwt.PyJWTError as exc:
                last_error = exc
                continue

        raise HTTPException(
            status_code=401,
            detail=f"Invalid Cloudflare Access token: {last_error}",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Auth error: {exc}") from exc


def get_user_id(user: Optional[dict]) -> Optional[str]:
    """Return a stable, safe user identifier from the JWT payload (email preferred)."""
    if user is None:
        return None
    # Use email as the namespace key; fall back to sub
    return user.get("email") or user.get("sub")

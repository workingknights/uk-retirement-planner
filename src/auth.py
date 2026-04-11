"""
Cloudflare Access JWT authentication.
"""

import json
import time
from typing import Optional

# NO TOP LEVEL NATIVE IMPORTS (jwt, cryptography, etc.)

_jwks_cache: dict = {}
_JWKS_TTL_SECONDS = 3600

async def _fetch_jwks(team_name: str) -> list:
    now = time.time()
    if _jwks_cache.get("fetched_at", 0) + _JWKS_TTL_SECONDS > now and _jwks_cache.get("keys"):
        return _jwks_cache["keys"]

    url = f"https://{team_name}.cloudflareaccess.com/cdn-cgi/access/certs"
    try:
        from js import fetch as js_fetch  # type: ignore
        response = await js_fetch(url)
        text = await response.text()
        jwks = json.loads(text)
    except ImportError:
        import urllib.request
        with urllib.request.urlopen(url) as resp:
            jwks = json.loads(resp.read())

    keys = jwks.get("keys", [])
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys

def _get_token_from_request(request) -> Optional[str]:
    token = request.headers.get("Cf-Access-Jwt-Assertion")
    if token: return token
    cookie = request.cookies.get("CF_Authorization")
    return cookie or None

async def get_current_user(request) -> Optional[dict]:
    # Retrieve env from scope (passed by asgi.fetch)
    env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
    aud = env.get("CF_ACCESS_AUD") if isinstance(env, dict) else getattr(env, "CF_ACCESS_AUD", None)
    team = env.get("CF_TEAM_NAME") if isinstance(env, dict) else getattr(env, "CF_TEAM_NAME", None)

    if not aud or not team: return None

    token = _get_token_from_request(request)
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing Cloudflare Access token.")

    try:
        import jwt
        from jwt.algorithms import RSAAlgorithm
        
        jwks_keys = await _fetch_jwks(team)

        last_error = None
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
                return payload
            except jwt.PyJWTError as exc:
                last_error = exc
                continue

        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail=f"Invalid token: {last_error}")

    except Exception as exc:
        from fastapi import HTTPException
        if isinstance(exc, HTTPException): raise
        raise HTTPException(status_code=401, detail=f"Auth error: {exc}")

def get_user_id(user: Optional[dict]) -> Optional[str]:
    if user is None: return None
    return user.get("email") or user.get("sub")

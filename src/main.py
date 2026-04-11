from workers import WorkerEntrypoint
import sys
import os
import json
import traceback
import uuid
import time

# Top-level imports for snapshotting
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asgi

from models import SimulationParams
from engine import run_simulation
from auth import get_current_user, get_user_id

# Initialize FastAPI app at module scope for snapshotting
app = FastAPI(title="UK Retirement Planner API")

# --- CORS ---
# Must list origins explicitly (not "*") when allow_credentials=True,
# otherwise browsers reject the response per the CORS spec.
ALLOWED_ORIGINS = [
    "https://uk-retirement-planner.pages.dev",
    "http://localhost:5173",
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def inject_env(request: Request, call_next):
    # The 'env' object is passed in the ASGI scope by the workers-py adapter
    request.state.env = request.scope.get("env")
    return await call_next(request)

# --- ROUTES ---
@app.get("/health")
async def health_check():
    """Health check endpoint must be async to avoid threadpool usage."""
    return {"status": "ok", "message": "Backend is alive (Async)", "python": sys.version}


@app.get("/api/me")
async def me(request: Request):
    """
    Returns the current user's auth status.
    Used by the frontend to decide whether to show the login prompt.
    """
    env = getattr(request.state, "env", {}) or {}
    aud = env.get("CF_ACCESS_AUD") if isinstance(env, dict) else getattr(env, "CF_ACCESS_AUD", None)
    team = env.get("CF_TEAM_NAME") if isinstance(env, dict) else getattr(env, "CF_TEAM_NAME", None)

    if not aud or not team:
        # Local dev — auth not configured
        return {"authenticated": False, "email": None, "local": True}

    try:
        user = await get_current_user(request)
        if user is None:
            return {"authenticated": False, "email": None, "local": False}
        return {"authenticated": True, "email": user.get("email"), "local": False}
    except HTTPException:
        return {"authenticated": False, "email": None, "local": False}


from fastapi import FastAPI, HTTPException, Request, Depends, Header

# Removed login_redirect endpoint from FastAPI to evade Cloudflare snapshotting edge-cases with endpoint type inspection. It is handled directly in the WorkerEntrypoint fetch override below.


@app.post("/api/simulate")
async def simulate(params: SimulationParams):
    """Simulation endpoint — no auth required, runs for anyone."""
    try:
        result = run_simulation(params)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ScenarioSaveRequest(BaseModel):
    name: str
    data: SimulationParams


def _require_auth(user):
    """Raise 401 if running in prod but no valid user. Return user_id or None locally."""
    if user is None:
        # Running locally (auth not configured) — KV isn't available either so this
        # is a no-op; the KV check below will still raise a 500.
        return None
    uid = get_user_id(user)
    if uid is None:
        raise HTTPException(status_code=401, detail="Could not determine user identity from token.")
    return uid


def _user_key(user_id: str | None, scenario_id: str) -> str:
    """Build a namespaced KV key. Locally (no user_id) just use the bare id."""
    if user_id:
        return f"{user_id}:{scenario_id}"
    return scenario_id


@app.get("/api/scenarios")
async def list_scenarios(request: Request, user=Depends(get_current_user)):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    if not kv:
        return {"success": True, "data": [], "message": "KV not configured"}

    user_id = _require_auth(user)
    prefix = f"{user_id}:" if user_id else ""

    try:
        keys = await kv.list(prefix=prefix) if prefix else await kv.list()
        scenarios = []
        for key in keys.keys:
            val = await kv.get(key.name)
            if val:
                content = json.loads(val)
                scenarios.append({
                    "id": content.get("id"),
                    "name": content.get("name"),
                    "last_modified": content.get("last_modified", 0)
                })
        return {"success": True, "data": scenarios}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/scenarios")
async def save_scenario(req: ScenarioSaveRequest, request: Request, user=Depends(get_current_user)):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    if not kv:
        raise HTTPException(status_code=500, detail="KV not configured")

    user_id = _require_auth(user)

    scenario_id = str(uuid.uuid4())
    kv_key = _user_key(user_id, scenario_id)
    scenario_doc = {
        "id": scenario_id,
        "name": req.name,
        "data": req.data.dict(),
        "last_modified": time.time()
    }
    await kv.put(kv_key, json.dumps(scenario_doc))
    return {"success": True, "data": {"id": scenario_id}}


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    if not kv:
        raise HTTPException(status_code=500, detail="KV not configured")

    user_id = _require_auth(user)
    kv_key = _user_key(user_id, scenario_id)

    val = await kv.get(kv_key)
    if not val:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"success": True, "data": json.loads(val)}


@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    if not kv:
        raise HTTPException(status_code=500, detail="KV not configured")

    user_id = _require_auth(user)
    kv_key = _user_key(user_id, scenario_id)

    # Verify the key exists (and belongs to this user) before deleting
    val = await kv.get(kv_key)
    if not val:
        raise HTTPException(status_code=404, detail="Scenario not found")

    await kv.delete(kv_key)
    return {"success": True}


class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        try:
            req_to_use = getattr(request, "js_object", request)
            url_str = getattr(req_to_use, "url", getattr(request, "url", ""))
            
            # Intercept /api/login directly to bypass FastAPI router snapshotting issues
            if "/api/login" in url_str:
                from js import URL, Response, Object  # type: ignore
                parsed_url = URL.new(url_str)
                to_target = parsed_url.searchParams.get("to") or "https://uk-retirement-planner.pages.dev/"
                
                headers_obj = getattr(req_to_use, "headers", getattr(request, "headers", None))
                token = None
                if headers_obj and hasattr(headers_obj, "get"):
                    token = headers_obj.get("Cf-Access-Jwt-Assertion")
                    
                redirect_url = to_target
                if token:
                    delimiter = "&" if "?" in to_target else "#"
                    if "#" in to_target and delimiter == "#":
                        redirect_url = f"{to_target}&token={token}"
                    else:
                        redirect_url = f"{to_target}{delimiter}token={token}"
                        
                resp_headers = Object.fromEntries([["Location", redirect_url]])
                return Response.new("", Object.fromEntries([["status", 302], ["headers", resp_headers]]))
                
            return await asgi.fetch(app, req_to_use, env)
        except Exception as e:
            from js import Response, Object
            error_msg = f"RUNTIME ERROR:\n{str(e)}\n{traceback.format_exc()}"
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            return Response.new(json.dumps({
                "success": False,
                "error": "Runtime Error",
                "detail": error_msg
            }), Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- WORKER MODULE LOADED (WITH AUTH) ---")

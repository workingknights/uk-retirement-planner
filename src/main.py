from workers import WorkerEntrypoint
import sys
import os
import json
import traceback
import uuid
import time

# Deferred imports to avoid top-level serialization issues
import asgi

from models import SimulationParams
from engine import run_simulation
from auth import get_current_user, get_user_id

_app_instance = None

def get_app():
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    from fastapi import FastAPI, HTTPException, Request, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(title="UK Retirement Planner API")

    # --- CORS ---
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

    # --- ROUTES ---
    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Backend is alive (Lazily)", "python": sys.version}

    @app.get("/api/me")
    async def me(request: Request):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        aud = env.get("CF_ACCESS_AUD") if isinstance(env, dict) else getattr(env, "CF_ACCESS_AUD", None)
        team = env.get("CF_TEAM_NAME") if isinstance(env, dict) else getattr(env, "CF_TEAM_NAME", None)

        if not aud or not team:
            return {"authenticated": False, "email": None, "local": True}

        try:
            user = await get_current_user(request)
            if user is None:
                return {"authenticated": False, "email": None, "local": False}
            return {"authenticated": True, "email": user.get("email"), "local": False}
        except HTTPException:
            return {"authenticated": False, "email": None, "local": False}

    @app.post("/api/simulate")
    async def simulate(params: SimulationParams):
        try:
            result = run_simulation(params)
            return {"success": True, "data": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class ScenarioSaveRequest(BaseModel):
        name: str
        data: SimulationParams

    def _require_auth(user):
        if user is None: return None
        uid = get_user_id(user)
        if uid is None: raise HTTPException(status_code=401, detail="Could not determine user identity")
        return uid

    def _user_key(user_id: str | None, scenario_id: str) -> str:
        return f"{user_id}:{scenario_id}" if user_id else scenario_id

    @app.get("/api/scenarios")
    async def list_scenarios(request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: return {"success": True, "data": [], "message": "KV not configured"}

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
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/scenarios")
    async def save_scenario(req: ScenarioSaveRequest, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500, detail="KV not configured")

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
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500, detail="KV not configured")

        user_id = _require_auth(user)
        kv_key = _user_key(user_id, scenario_id)
        val = await kv.get(kv_key)
        if not val: raise HTTPException(status_code=404, detail="Scenario not found")
        return {"success": True, "data": json.loads(val)}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500, detail="KV not configured")

        user_id = _require_auth(user)
        kv_key = _user_key(user_id, scenario_id)
        val = await kv.get(kv_key)
        if not val: raise HTTPException(status_code=404, detail="Scenario not found")
        await kv.delete(kv_key)
        return {"success": True}

    _app_instance = app
    return app

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        try:
            req_to_use = getattr(request, "js_object", request)
            app = get_app()
            return await asgi.fetch(app, req_to_use, env)
        except Exception as e:
            from js import Response, Object
            error_msg = f"RUNTIME ERROR:\n{str(e)}\n{traceback.format_exc()}"
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            return Response.new(json.dumps({
                "success": False, "error": "Runtime Error", "detail": error_msg
            }), Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- WORKER MODULE LOADED (LAZY) ---")

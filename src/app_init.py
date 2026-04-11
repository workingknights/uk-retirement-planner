from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys
import json
import uuid
import time

from models import SimulationParams
from engine import run_simulation
from auth import get_current_user, get_user_id

def create_app():
    app = FastAPI(title="UK Retirement Planner API")

    # --- CORS ---
    # We still keep this here for non-OPTIONS requests
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

    def _get_env_var(env, key, default=None):
        if not env: return default
        # Cloudflare 'env' objects often don't support dict-like access
        try:
            val = getattr(env, key, None)
            if val is not None: return val
        except: pass
        
        try:
            if hasattr(env, "get"): return env.get(key, default)
        except: pass
        
        try:
            if isinstance(env, dict): return env.get(key, default)
        except: pass
        
        return default

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Backend alive (Production Fix V2)"}

    @app.get("/api/me")
    async def me(request: Request):
        # The env is injected into the scope by asgi.fetch
        env = request.scope.get("env")
        aud = _get_env_var(env, "CF_ACCESS_AUD")
        team = _get_env_var(env, "CF_TEAM_NAME")
        
        if not aud or not team:
            # Still returning some debug info in the error to help identify why it's local
            return {
                "authenticated": False, 
                "email": None, 
                "local": True,
                "debug": {
                    "env_present": env is not None,
                    "env_type": str(type(env))
                }
            }
            
        try:
            user = await get_current_user(request)
            if user is None:
                return {"authenticated": False, "email": None, "local": False}
            return {"authenticated": True, "email": user.get("email"), "local": False}
        except Exception as e:
            return {"authenticated": False, "email": None, "local": False, "error": str(e)}

    class ScenarioSaveRequest(BaseModel):
        name: str
        data: SimulationParams

    @app.get("/api/scenarios")
    async def list_scenarios(request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env")
        kv = _get_env_var(env, "SCENARIOS_KV")
        if not kv:
            # Fallback for checking KV directly on the request.state just in case
            kv = getattr(request.state, "kv", None) or getattr(request.state, "SCENARIOS_KV", None)
            
        if not kv:
            return {"success": True, "data": [], "message": "KV not configured (env missing)"}

        uid = get_user_id(user)
        if not uid:
            raise HTTPException(status_code=401, detail="User not identified")
            
        try:
            prefix = f"{uid}:"
            # Some KV versions return a list, others are async
            keys_obj = await kv.list(prefix=prefix)
            keys = getattr(keys_obj, "keys", [])
            
            scenarios = []
            for key in keys:
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
            return {"success": False, "error": f"KV error: {str(e)}"}

    @app.post("/api/scenarios")
    async def save_scenario(req: ScenarioSaveRequest, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env")
        kv = _get_env_var(env, "SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500, detail="KV not configured")

        uid = get_user_id(user)
        if not uid: raise HTTPException(status_code=401)
        
        sid = str(uuid.uuid4())
        doc = {
            "id": sid,
            "name": req.name,
            "data": req.data.dict(),
            "last_modified": time.time()
        }
        await kv.put(f"{uid}:{sid}", json.dumps(doc))
        return {"success": True, "data": {"id": sid}}

    @app.get("/api/scenarios/{scenario_id}")
    async def get_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env")
        kv = _get_env_var(env, "SCENARIOS_KV")
        uid = get_user_id(user)
        val = await kv.get(f"{uid}:{scenario_id}")
        if not val: raise HTTPException(status_code=404)
        return {"success": True, "data": json.loads(val)}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env")
        kv = _get_env_var(env, "SCENARIOS_KV")
        uid = get_user_id(user)
        await kv.delete(f"{uid}:{scenario_id}")
        return {"success": True}

    return app

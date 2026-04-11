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
    # MUST match the requesting Origin exactly in production.
    # Note: No trailing slash.
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
        if isinstance(env, dict): return env.get(key, default)
        return getattr(env, key, default)

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Backend alive (Ultimate Deferral)"}

    @app.get("/api/me")
    async def me(request: Request):
        env = request.scope.get("env")
        aud = _get_env_var(env, "CF_ACCESS_AUD")
        team = _get_env_var(env, "CF_TEAM_NAME")
        
        if not aud or not team:
            return {"authenticated": False, "email": None, "local": True}
            
        try:
            user = await get_current_user(request)
            if user is None:
                return {"authenticated": False, "email": None, "local": False}
            return {"authenticated": True, "email": user.get("email"), "local": False}
        except Exception as e:
            return {"authenticated": False, "email": None, "local": False, "error": str(e)}

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

    @app.get("/api/scenarios")
    async def list_scenarios(request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env")
        kv = _get_env_var(env, "SCENARIOS_KV")
        if not kv:
            # Still returning success: true to avoid breaking the frontend
            return {"success": True, "data": [], "message": "KV not configured (env missing)"}

        uid = get_user_id(user)
        if not uid:
            raise HTTPException(status_code=401, detail="User not identified")
            
        try:
            prefix = f"{uid}:"
            keys = await kv.list(prefix=prefix)
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

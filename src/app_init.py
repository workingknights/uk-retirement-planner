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

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "message": "Backend alive (Deferred)", "python": sys.version}

    @app.get("/api/me")
    async def me(request: Request):
        env = request.scope.get("env") or {}
        aud = env.get("CF_ACCESS_AUD")
        team = env.get("CF_TEAM_NAME")
        if not aud or not team: return {"authenticated": False, "email": None, "local": True}
        try:
            user = await get_current_user(request)
            if user is None: return {"authenticated": False, "email": None, "local": False}
            return {"authenticated": True, "email": user.get("email"), "local": False}
        except: return {"authenticated": False, "email": None, "local": False}

    @app.post("/api/simulate")
    async def simulate(params: SimulationParams):
        try: return {"success": True, "data": run_simulation(params)}
        except Exception as e: raise HTTPException(status_code=500, detail=str(e))

    class ScenarioSaveRequest(BaseModel):
        name: str
        data: SimulationParams

    @app.get("/api/scenarios")
    async def list_scenarios(request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: return {"success": True, "data": []}
        uid = get_user_id(user)
        if not uid: raise HTTPException(status_code=401)
        try:
            keys = await kv.list(prefix=f"{uid}:")
            scenarios = []
            for key in keys.keys:
                val = await kv.get(key.name)
                if val:
                    content = json.loads(val)
                    scenarios.append({"id": content.get("id"), "name": content.get("name"), "last_modified": content.get("last_modified", 0)})
            return {"success": True, "data": scenarios}
        except Exception as e: return {"success": False, "error": str(e)}

    @app.post("/api/scenarios")
    async def save_scenario(req: ScenarioSaveRequest, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500)
        uid = get_user_id(user)
        if not uid: raise HTTPException(status_code=401)
        sid = str(uuid.uuid4())
        doc = {"id": sid, "name": req.name, "data": req.data.dict(), "last_modified": time.time()}
        await kv.put(f"{uid}:{sid}", json.dumps(doc))
        return {"success": True, "data": {"id": sid}}

    @app.get("/api/scenarios/{scenario_id}")
    async def get_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or {}
        kv = env.get("SCENARIOS_KV")
        uid = get_user_id(user)
        val = await kv.get(f"{uid}:{scenario_id}")
        if not val: raise HTTPException(status_code=404)
        return {"success": True, "data": json.loads(val)}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or {}
        kv = env.get("SCENARIOS_KV")
        uid = get_user_id(user)
        await kv.delete(f"{uid}:{scenario_id}")
        return {"success": True}

    return app

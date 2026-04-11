from workers import WorkerEntrypoint
import json
import traceback

# Defer all imports to runtime
def get_app():
    global _app_instance
    if '_app_instance' in globals() and _app_instance is not None:
        return _app_instance

    from fastapi import FastAPI, HTTPException, Request, Depends
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import sys
    import os
    import uuid
    import time

    # Local deferred imports
    from models import SimulationParams
    from engine import run_simulation
    from auth import get_current_user, get_user_id

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
        return {"status": "ok", "message": "Backend alive (Strict Lazy)"}

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
        except Exception:
            return {"authenticated": False, "email": None, "local": False}

    @app.get("/api/login")
    async def login_redirect():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="https://uk-retirement-planner.pages.dev/")

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
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: return {"success": True, "data": []}

        user_id = get_user_id(user)
        if user_id is None: raise HTTPException(status_code=401)
        prefix = f"{user_id}:"

        try:
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
            return {"success": False, "error": str(e)}

    @app.post("/api/scenarios")
    async def save_scenario(req: ScenarioSaveRequest, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        if not kv: raise HTTPException(status_code=500)

        user_id = get_user_id(user)
        if user_id is None: raise HTTPException(status_code=401)
        
        # ... logic as before ...
        import uuid as uuid_mod
        scenario_id = str(uuid_mod.uuid4())
        kv_key = f"{user_id}:{scenario_id}"
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
        user_id = get_user_id(user)
        val = await kv.get(f"{user_id}:{scenario_id}")
        if not val: raise HTTPException(status_code=404)
        return {"success": True, "data": json.loads(val)}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str, request: Request, user=Depends(get_current_user)):
        env = request.scope.get("env") or getattr(request.state, "env", {}) or {}
        kv = env.get("SCENARIOS_KV")
        user_id = get_user_id(user)
        await kv.delete(f"{user_id}:{scenario_id}")
        return {"success": True}

    globals()['_app_instance'] = app
    return app

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        try:
            import asgi
            req_to_use = getattr(request, "js_object", request)
            return await asgi.fetch(get_app(), req_to_use, env)
        except Exception as e:
            from js import Response, Object
            return Response.new(json.dumps({"error": str(e)}), Object.fromEntries([["status", 500]]))

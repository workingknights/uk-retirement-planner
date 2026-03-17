from workers import WorkerEntrypoint
import sys
import os
import json
import traceback

# Cache the app at the module level
_cached_app = None
_startup_error = None

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        global _cached_app, _startup_error
        from js import Response, Object

        if _startup_error:
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(f"CACHED STARTUP ERROR:\n{_startup_error}", Object.fromEntries([["status", 500], ["headers", headers]]))

        if _cached_app is None:
            try:
                # Imports inside fetch to catch startup issues
                from fastapi import FastAPI, HTTPException, Request
                import asgi
                from fastapi.middleware.cors import CORSMiddleware
                from pydantic import BaseModel
                import uuid
                import time

                from models import SimulationParams
                from engine import run_simulation

                app = FastAPI(title="UK Retirement Planner API")
                
                # Use env for origins
                allowed_origins = str(getattr(env, "ALLOWED_ORIGINS", "*")).split(",")
                app.add_middleware(
                    CORSMiddleware,
                    allow_origins=allowed_origins,
                    allow_credentials=True,
                    allow_methods=["*"],
                    allow_headers=["*"],
                )

                @app.get("/health")
                def health_check():
                    return {"status": "ok", "message": "Backend is alive"}

                @app.post("/api/simulate")
                def simulate(params: SimulationParams):
                    result = run_simulation(params)
                    return {"success": True, "data": result}

                class ScenarioSaveRequest(BaseModel):
                    name: str
                    data: SimulationParams

                @app.get("/api/scenarios")
                async def list_scenarios(request: Request):
                    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
                    if not kv:
                        return {"success": True, "data": [], "message": "KV not configured"}
                    
                    keys = await kv.list()
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

                @app.post("/api/scenarios")
                async def save_scenario(req: ScenarioSaveRequest, request: Request):
                    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
                    if not kv:
                        raise HTTPException(status_code=500, detail="KV not configured")
                    
                    scenario_id = str(uuid.uuid4())
                    scenario_doc = {
                        "id": scenario_id,
                        "name": req.name,
                        "data": req.data.dict(),
                        "last_modified": time.time()
                    }
                    await kv.put(scenario_id, json.dumps(scenario_doc))
                    return {"success": True, "data": {"id": scenario_id}}

                @app.get("/api/scenarios/{scenario_id}")
                async def get_scenario(scenario_id: str, request: Request):
                    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
                    if not kv:
                        raise HTTPException(status_code=500, detail="KV not configured")
                    
                    val = await kv.get(scenario_id)
                    if not val:
                        raise HTTPException(status_code=404, detail="Scenario not found")
                    return {"success": True, "data": json.loads(val)}

                @app.delete("/api/scenarios/{scenario_id}")
                async def delete_scenario(scenario_id: str, request: Request):
                    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
                    if not kv:
                        raise HTTPException(status_code=500, detail="KV not configured")
                    await kv.delete(scenario_id)
                    return {"success": True}

                _cached_app = app
                print("--- FASTAPI APP INITIALIZED ---")
            except Exception as e:
                _startup_error = f"Startup Error: {str(e)}\n{traceback.format_exc()}"
                headers = Object.fromEntries([["Content-Type", "text/plain"]])
                return Response.new(f"INITIALIZATION ERROR:\n{_startup_error}", Object.fromEntries([["status", 500], ["headers", headers]]))

        try:
            import asgi
            # Use raw request if available
            req_to_use = getattr(request, "js_object", request)
            return await asgi.fetch(_cached_app, req_to_use, env)
        except Exception as e:
            error_msg = f"Runtime Error: {str(e)}\n{traceback.format_exc()}"
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(error_msg, Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- LAZY WORKER ENTRYPOINT READY ---")

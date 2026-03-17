from workers import WorkerEntrypoint
import json
import traceback
import os
import sys
import uuid
from typing import List

IMPORT_ERROR = None
app = None
SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")

try:
    from fastapi import FastAPI, HTTPException, Request
    import asgi
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    from models import SimulationParams
    from engine import run_simulation

    app = FastAPI(title="UK Retirement Planner API")
    
    # Configure CORS for frontend access
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
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
            scenarios = []
            if os.path.exists(SCENARIOS_DIR):
                for filename in os.listdir(SCENARIOS_DIR):
                    if filename.endswith(".json"):
                        with open(os.path.join(SCENARIOS_DIR, filename), "r") as f:
                            content = json.load(f)
                            scenarios.append({
                                "id": content.get("id"),
                                "name": content.get("name"),
                                "last_modified": os.path.getmtime(os.path.join(SCENARIOS_DIR, filename))
                            })
            return {"success": True, "data": scenarios}
        
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
        import time
        scenario_id = str(uuid.uuid4())
        scenario_doc = {
            "id": scenario_id,
            "name": req.name,
            "data": req.data.dict(),
            "last_modified": time.time()
        }
        if kv:
            await kv.put(scenario_id, json.dumps(scenario_doc))
        else:
            try:
                filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
                with open(filepath, "w") as f:
                    json.dump(scenario_doc, f, indent=2)
            except Exception as e:
                print(f"Error saving to disk: {e}")
        return {"success": True, "data": {"id": scenario_id}}

    @app.get("/api/scenarios/{scenario_id}")
    async def get_scenario(scenario_id: str, request: Request):
        kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
        if kv:
            val = await kv.get(scenario_id)
            if not val:
                raise HTTPException(status_code=404, detail="Scenario not found")
            return {"success": True, "data": json.loads(val)}
        else:
            filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
            if not os.path.exists(filepath):
                raise HTTPException(status_code=404, detail="Scenario not found")
            with open(filepath, "r") as f:
                return {"success": True, "data": json.load(f)}

    @app.delete("/api/scenarios/{scenario_id}")
    async def delete_scenario(scenario_id: str, request: Request):
        kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
        if kv:
            await kv.delete(scenario_id)
            return {"success": True}
        else:
            filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
            if os.path.exists(filepath):
                os.remove(filepath)
                return {"success": True}

except Exception as e:
    IMPORT_ERROR = f"Startup Error: {str(e)}\n{traceback.format_exc()}"


class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        from js import Response, Object
        if IMPORT_ERROR:
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(f"IMPORT ERROR:\n{IMPORT_ERROR}", Object.fromEntries([["status", 500], ["headers", headers]]))
        
        try:
            # Use the raw JS request object if available
            req_to_use = getattr(request, "js_object", request)
            return await asgi.fetch(app, req_to_use, env)
        except Exception as e:
            error_msg = f"Runtime Error: {str(e)}\n{traceback.format_exc()}"
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(error_msg, Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- BACKEND RESTORED AND READY ---")

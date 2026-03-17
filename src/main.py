from workers import WorkerEntrypoint
import sys
import os
import json
import traceback
import uuid
import time

# Cache at module level
_cached_app = None
_startup_error = None

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        global _cached_app, _startup_error
        
        # 1. Extremely safe JS utilities
        try:
            from js import Response, Object
            def safe_response(body, status=200, content_type="application/json"):
                try:
                    headers = Object.fromEntries([["Content-Type", content_type]])
                    return Response.new(body, Object.fromEntries([["status", status], ["headers", headers]]))
                except:
                    return str(body)
        except Exception as e:
            return f"CRITICAL: Failed to import 'js': {str(e)}"

        # 2. Handle cached initialization errors
        if _startup_error:
            return safe_response(json.dumps({
                "success": False, 
                "error": "Initialization Error", 
                "detail": _startup_error
            }), 500)

        # 3. Lazy Initialization of FastAPI
        if _cached_app is None:
            try:
                from fastapi import FastAPI, HTTPException, Request
                from fastapi.middleware.cors import CORSMiddleware
                from pydantic import BaseModel
                import asgi

                from models import SimulationParams
                from engine import run_simulation

                app = FastAPI(title="UK Retirement Planner API")
                
                # Configuration from Environment
                try:
                    origins_raw = getattr(env, "ALLOWED_ORIGINS", "*")
                    allowed_origins = str(origins_raw).split(",")
                except:
                    allowed_origins = ["*"]

                app.add_middleware(
                    CORSMiddleware,
                    allow_origins=allowed_origins,
                    allow_credentials=True,
                    allow_methods=["*"],
                    allow_headers=["*"],
                )

                # --- ROUTES ---
                @app.get("/health")
                def health_check():
                    return {"status": "ok", "message": "Backend is alive", "python": sys.version}

                @app.post("/api/simulate")
                def simulate(params: SimulationParams):
                    try:
                        result = run_simulation(params)
                        return {"success": True, "data": result}
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=str(e))

                class ScenarioSaveRequest(BaseModel):
                    name: str
                    data: SimulationParams

                @app.get("/api/scenarios")
                async def list_scenarios(request: Request):
                    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
                    if not kv:
                        return {"success": True, "data": [], "message": "KV not configured"}
                    
                    try:
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
                    except Exception as e:
                        return {"success": False, "error": str(e)}

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
                print("--- FASTAPI APP READY ---")
            except Exception as e:
                _startup_error = f"{str(e)}\n{traceback.format_exc()}"
                return safe_response(json.dumps({
                    "success": False,
                    "error": "Initialization Error",
                    "detail": _startup_error
                }), 500)

        # 4. Proxy Request to FastAPI via asgi-proxy-lib
        try:
            import asgi
            # Use raw request if available (for modern Cloudflare Workers)
            req_to_use = getattr(request, "js_object", request)
            return await asgi.fetch(_cached_app, req_to_use, env)
        except Exception as e:
            error_msg = f"RUNTIME ERROR:\n{str(e)}\n{traceback.format_exc()}"
            return safe_response(json.dumps({
                "success": False,
                "error": "Runtime Error",
                "detail": error_msg
            }), 500)

print("--- WORKER MODULE LOADED ---")

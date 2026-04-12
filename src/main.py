import json
import time
import uuid
from typing import Optional
from workers import WorkerEntrypoint
from js import Response, Object, URL

def make_resp(data, status=200):
    h = Object.fromEntries([
        ["Content-Type", "application/json"],
        ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
        ["Access-Control-Allow-Credentials", "true"],
    ])
    return Response.new(json.dumps(data), Object.fromEntries([["status", status], ["headers", h]]))


class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        real_env = env or getattr(self, "env", None)
        try:
            req_js = getattr(request, "js_object", request)
            method = getattr(req_js, "method", "GET").upper()
        except:
            method = "GET"
            req_js = request

        # -----------------------------
        # 1. Preflight OPTIONS
        # -----------------------------
        if method == "OPTIONS":
            h = Object.fromEntries([
                ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
                ["Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"],
                ["Access-Control-Allow-Headers", "Content-Type, Cf-Access-Jwt-Assertion, CF_Authorization"],
                ["Access-Control-Allow-Credentials", "true"],
                ["Access-Control-Max-Age", "86400"],
            ])
            return Response.new("", Object.fromEntries([["status", 204], ["headers", h]]))

        url_str = getattr(req_js, "url", "")
        parsed_url = URL.new(url_str)
        path = getattr(parsed_url, "pathname", "")

        
        # -----------------------------
        # 2. Extract Auth Token
        # -----------------------------
        def get_user_id() -> Optional[str]:
            token = None
            headers = req_js.headers
            if hasattr(headers, "get"):
                token = headers.get("Cf-Access-Jwt-Assertion")
                if not token:
                    c = headers.get("cookie") or ""
                    if "CF_Authorization=" in c:
                        token = c.split("CF_Authorization=")[1].split(";")[0]
            if not token:
                return None
            
            aud = None
            if real_env:
                try: aud = real_env.get("CF_ACCESS_AUD")
                except: aud = getattr(real_env, "CF_ACCESS_AUD", None)
            if not aud:
                return None
            
            try:
                import jwt
                payload = jwt.decode(token, audience=aud, options={"verify_signature": False, "verify_exp": False})
                return payload.get("email") or payload.get("sub")
            except:
                return None

        # -----------------------------
        # 3. Routes
        # -----------------------------
        try:
            if path == "/api/me" and method == "GET":
                uid = get_user_id()
                if uid: return make_resp({"authenticated": True, "email": uid, "local": False})
                return make_resp({"authenticated": False, "email": None, "local": False})

            elif path == "/api/simulate" and method == "POST":
                body_text = await req_js.text()
                data = json.loads(body_text)
                
                from models import SimulationParams
                params = SimulationParams(**data)
                
                from engine import run_simulation
                res = run_simulation(params)
                return make_resp({"success": True, "data": res})

            elif path == "/api/scenarios" and method == "GET":
                uid = get_user_id()
                if not uid: return make_resp({"error": "unauthorized"}, 401)
                
                kv = None
                if real_env:
                    try: kv = real_env.get("SCENARIOS_KV")
                    except: kv = getattr(real_env, "SCENARIOS_KV", None)
                
                if not kv: return make_resp({"success": True, "data": []})
                
                keys_obj = await kv.list(prefix=f"{uid}:")
                keys = getattr(keys_obj, "keys", [])
                scenarios = []
                for key in keys:
                    val = await kv.get(getattr(key, "name", key))
                    if val:
                        content = json.loads(val)
                        scenarios.append({
                            "id": content.get("id"), "name": content.get("name"), "last_modified": content.get("last_modified", 0)
                        })
                return make_resp({"success": True, "data": scenarios})

            elif path == "/api/scenarios" and method == "POST":
                uid = get_user_id()
                if not uid: return make_resp({"error": "unauthorized"}, 401)
                
                kv = None
                if real_env:
                    try: kv = real_env.get("SCENARIOS_KV")
                    except: kv = getattr(real_env, "SCENARIOS_KV", None)
                if not kv: return make_resp({"error": "KV missing"}, 500)
                
                body_text = await req_js.text()
                req_data = json.loads(body_text)
                sid = str(uuid.uuid4())
                doc = {
                    "id": sid,
                    "name": req_data.get("name"),
                    "data": req_data.get("data"),
                    "last_modified": time.time()
                }
                await kv.put(f"{uid}:{sid}", json.dumps(doc))
                return make_resp({"success": True, "data": {"id": sid}})

            elif path.startswith("/api/scenarios/") and method == "GET":
                uid = get_user_id()
                if not uid: return make_resp({"error": "unauthorized"}, 401)
                sid = path.split("/")[-1]
                kv = None
                if real_env:
                    try: kv = real_env.get("SCENARIOS_KV")
                    except: kv = getattr(real_env, "SCENARIOS_KV", None)
                
                val = await kv.get(f"{uid}:{sid}")
                if not val: return make_resp({"error": "not found"}, 404)
                return make_resp({"success": True, "data": json.loads(val)})


            elif path.startswith("/api/scenarios/") and method == "DELETE":
                uid = get_user_id()
                if not uid: return make_resp({"error": "unauthorized"}, 401)
                sid = path.split("/")[-1]
                kv = None
                if real_env:
                    try: kv = real_env.get("SCENARIOS_KV")
                    except: kv = getattr(real_env, "SCENARIOS_KV", None)
                
                await kv.delete(f"{uid}:{sid}")
                return make_resp({"success": True})

            # Catch-all
            return make_resp({"error": "not found"}, 404)

        except Exception as e:
            import traceback
            err_msg = f"WORKER FATAL ERROR:\n{str(e)}\n\n{traceback.format_exc()}"
            h = Object.fromEntries([
                ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
                ["Access-Control-Allow-Credentials", "true"],
                ["Content-Type", "text/plain"],
            ])
            return Response.new(err_msg, Object.fromEntries([["status", 500], ["headers", h]]))

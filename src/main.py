from workers import WorkerEntrypoint
import sys
import os
import json

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        # Inspect environment without assuming 'js' exists at top level
        info = {
            "version": sys.version,
            "path": sys.path,
            "env_keys": list(os.environ.keys()),
            "request_url": str(request.url),
            "modules": sorted(list(sys.modules.keys()))[:100] # First 100 modules for brevity
        }
        
        try:
            from js import Response, Object
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            return Response.new(json.dumps(info), Object.fromEntries([["status", 200], ["headers", headers]]))
        except Exception as e:
            # Fallback if 'js' is missing or fails
            return f"Raw Worker Alive. Python {sys.version}. Error: {str(e)}"

print(f"--- INSPECTOR LOADED: Python {sys.version} ---")

from workers import WorkerEntrypoint
import sys
import os
import json

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        info = {
            "p": sys.version,
            "path": sys.path,
            "fa": "NO"
        }
        try:
            import fastapi
            info["fa"] = "YES"
        except Exception as e:
            info["fa"] = str(e)
            
        try:
            from js import Response, Object
            return Response.new(json.dumps(info), Object.fromEntries([["status", 200]]))
        except:
            return str(info)

print("--- REVERTED TO SIMPLE INSPECTOR ---")

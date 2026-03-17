from workers import WorkerEntrypoint
import sys
import os
import json

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        from js import Response, Object
        
        def list_files(path):
            try:
                if not os.path.exists(path):
                    return f"NOT_FOUND"
                if not os.path.isdir(path):
                    return f"FILE"
                res = []
                for entry in os.listdir(path):
                    full = os.path.join(path, entry)
                    if os.path.isdir(full):
                        res.append(f"{entry}/")
                    else:
                        res.append(entry)
                return res
            except Exception as e:
                return f"ERROR: {str(e)}"

        info = {}
        try:
            info = {
                "python": sys.version,
                "path": sys.path,
                "path_ls": {p: list_files(p) for p in sys.path},
                "cwd": os.getcwd(),
                "cwd_ls": list_files(os.getcwd()),
                "fastapi": "MISSING"
            }
            try:
                import fastapi
                info["fastapi"] = f"FOUND: {fastapi.__version__}"
                info["fastapi_file"] = str(fastapi.__file__)
            except Exception as e:
                info["fastapi"] = f"IMPORT_ERROR: {str(e)}"
            
            # Specifically check python_modules if it exists
            pm_path = "/session/metadata/python_modules"
            if os.path.exists(pm_path):
                info["python_modules_ls"] = list_files(pm_path)
                
        except Exception as e:
            info["error_gathering"] = str(e)

        try:
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            return Response.new(json.dumps(info), Object.fromEntries([["status", 200], ["headers", headers]]))
        except Exception as e:
            # Absolute fallback
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(f"CRITICAL ERROR: {str(e)}\n\nPartial Info: {str(info)}", Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- BULLETPROOF INSPECTOR READY ---")

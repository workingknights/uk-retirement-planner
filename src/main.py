from workers import WorkerEntrypoint
import sys
import os
import json

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        def list_files(path):
            try:
                if not os.path.exists(path):
                    return f"{path} (Not Found)"
                res = []
                for entry in os.listdir(path):
                    full = os.path.join(path, entry)
                    if os.path.isdir(full):
                        res.append(f"{entry}/")
                    else:
                        res.append(entry)
                return res
            except Exception as e:
                return f"Error listing {path}: {str(e)}"

        path_contents = {p: list_files(p) for p in sys.path}
        
        info = {
            "version": sys.version,
            "path": sys.path,
            "path_contents": path_contents,
            "cwd": os.getcwd(),
            "ls_cwd": list_files(os.getcwd()),
            "modules_count": len(sys.modules),
            "fastapi_importable": False
        }
        
        try:
            import fastapi
            info["fastapi_importable"] = True
            info["fastapi_path"] = str(fastapi.__file__)
        except Exception as e:
            info["fastapi_import_error"] = str(e)

        try:
            from js import Response, Object
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            return Response.new(json.dumps(info), Object.fromEntries([["status", 200], ["headers", headers]]))
        except Exception as e:
            return f"Raw Worker Alive. Python {sys.version}. Info: {json.dumps(info)}"

print(f"--- INSPECTOR LOADED: Python {sys.version} ---")

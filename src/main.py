from workers import WorkerEntrypoint
import sys
import os
import traceback

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        results = ["STARTUP LOG:"]
        
        # Test 1: Simple modules
        try:
            import json
            import uuid
            results.append("JSON/UUID: OK")
        except Exception as e:
            results.append(f"JSON/UUID ERROR: {str(e)}")

        # Test 2: Project Models
        try:
            from models import SimulationParams
            results.append("MODELS: OK")
        except Exception as e:
            results.append(f"MODELS ERROR: {str(e)}\n{traceback.format_exc()}")

        # Test 3: Project Engine
        try:
            from engine import run_simulation
            results.append("ENGINE: OK")
        except Exception as e:
            results.append(f"ENGINE ERROR: {str(e)}\n{traceback.format_exc()}")

        # Test 4: Project Dependencies
        try:
            from fastapi import FastAPI
            results.append("FASTAPI: OK")
        except Exception as e:
            results.append(f"FASTAPI ERROR: {str(e)}")

        # Test 5: ASGI Bridge
        try:
            import asgi
            results.append("ASGI: OK")
        except Exception as e:
            results.append(f"ASGI ERROR: {str(e)}\n{traceback.format_exc()}")

        output = "\n".join(results)
        
        # Try to return using js.Response if available, otherwise just return string
        try:
            from js import Response, Object
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(output, Object.fromEntries([["status", 200], ["headers", headers]]))
        except:
            return output

print("--- INCREMENTAL DEBUGGER READY ---")

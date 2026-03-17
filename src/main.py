from workers import WorkerEntrypoint
import json
import traceback
import os

# from fastapi import FastAPI, HTTPException, Request
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel
# import asgi

# app = FastAPI(title="UK Retirement Planner API")

# @app.get("/health")
# def health_check():
#     return {"status": "ok", "message": "Backend is alive"}

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        try:
            from js import Response, Object
            headers = Object.fromEntries([["Content-Type", "application/json"]])
            
            # Check if it's the health endpoint manually
            url = str(request.url)
            if "/health" in url:
                return Response.new('{"status": "ok", "message": "Bypass Mode: Worker is alive"}', Object.fromEntries([["status", 200], ["headers", headers]]))
            
            return Response.new('{"error": "FastAPI is disabled for debugging"}', Object.fromEntries([["status", 503], ["headers", headers]]))
        except Exception as e:
            import traceback
            error_msg = f"Worker Error: {str(e)}\n{traceback.format_exc()}"
            from js import Response, Object
            headers = Object.fromEntries([["Content-Type", "text/plain"]])
            return Response.new(error_msg, Object.fromEntries([["status", 500], ["headers", headers]]))

print("--- BYPASS BACKEND STARTUP SEQUENCE COMPLETE ---")

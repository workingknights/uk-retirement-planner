from workers import WorkerEntrypoint

_APP_CACHE = None

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        global _APP_CACHE
        if _APP_CACHE is None:
            from app_init import create_app
            _APP_CACHE = create_app()
        
        # 1. Manual CORS handling to bypass any FastAPI/Mangum issues
        req_to_use = getattr(request, "js_object", request)
        if req_to_use.method == "OPTIONS":
            from js import Response, Object
            h = Object.fromEntries([
                ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
                ["Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"],
                ["Access-Control-Allow-Headers", "Content-Type, Cf-Access-Jwt-Assertion, CF_Authorization"],
                ["Access-Control-Allow-Credentials", "true"],
            ])
            return Response.new("", Object.fromEntries([["status", 204], ["headers", h]]))

        # 2. Redirect /api/login
        url_str = getattr(req_to_use, "url", getattr(request, "url", ""))
        if "/api/login" in url_str:
            from js import Response, Object
            h = Object.fromEntries([["Location", "https://uk-retirement-planner.pages.dev/"]])
            return Response.new("", Object.fromEntries([["status", 302], ["headers", h]]))
            
        # 3. Normal ASGI fetch
        import asgi
        return await asgi.fetch(_APP_CACHE, req_to_use, env)

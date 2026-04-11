from workers import WorkerEntrypoint

_APP_CACHE = None

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        global _APP_CACHE
        
        # 0. Get the correct env object
        # In WorkerEntrypoint, env is passed to fetch AND available as self.env
        real_env = env or getattr(self, "env", None)
        
        # 1. Manual CORS handling - ULTRABULLETPROOF
        # We use the raw JS request if possible to avoid any Python wrapper issues
        try:
            req_js = getattr(request, "js_object", request)
            method = getattr(req_js, "method", "GET").upper()
        except:
            method = "GET"
            req_js = request

        if method == "OPTIONS":
            from js import Response, Object
            h = Object.fromEntries([
                ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
                ["Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"],
                ["Access-Control-Allow-Headers", "Content-Type, Cf-Access-Jwt-Assertion, CF_Authorization"],
                ["Access-Control-Allow-Credentials", "true"],
                ["Access-Control-Max-Age", "86400"],
            ])
            return Response.new("", Object.fromEntries([["status", 204], ["headers", h]]))

        # 2. Lazy load the app
        if _APP_CACHE is None:
            # We must import inside here to escape the snapshot serialization hell
            from app_init import create_app
            _APP_CACHE = create_app()
        
        # 3. Redirect /api/login
        url_str = getattr(req_js, "url", "")
        if "/api/login" in url_str:
            from js import Response, Object
            h = Object.fromEntries([
                ["Location", "https://uk-retirement-planner.pages.dev/"],
                ["Access-Control-Allow-Origin", "https://uk-retirement-planner.pages.dev"],
                ["Access-Control-Allow-Credentials", "true"],
            ])
            return Response.new("", Object.fromEntries([["status", 302], ["headers", h]]))
            
        # 4. Normal ASGI fetch
        import asgi
        # We manually ensure real_env is passed
        return await asgi.fetch(_APP_CACHE, req_js, real_env)

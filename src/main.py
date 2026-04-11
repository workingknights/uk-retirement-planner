from workers import WorkerEntrypoint

_APP_CACHE = None

class Default(WorkerEntrypoint):
    async def fetch(self, request, env, ctx):
        global _APP_CACHE
        if _APP_CACHE is None:
            from app_init import create_app
            _APP_CACHE = create_app()
        
        import asgi
        req_to_use = getattr(request, "js_object", request)
        return await asgi.fetch(_APP_CACHE, req_to_use, env)

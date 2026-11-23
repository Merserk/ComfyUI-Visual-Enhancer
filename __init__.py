import asyncio
from aiohttp import web

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .ve_cli import browse_for_ve_cli, check_connection

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]


def _register_routes() -> None:
    try:
        import server
        prompt_server = getattr(server.PromptServer, "instance", None)
        if prompt_server is None:
            return
        routes = prompt_server.routes

        @routes.get("/visual_enhancer/status")
        async def ve_get_status(request: web.Request) -> web.Response:
            custom_path = request.rel_url.query.get("path", "").strip() or None
            force = request.rel_url.query.get("force", "0") == "1"
            status = await asyncio.to_thread(check_connection, custom_path=custom_path, force=force)
            return web.json_response(status)

        @routes.post("/visual_enhancer/set_path")
        async def ve_set_path(request: web.Request) -> web.Response:
            try:
                body = await request.json()
            except Exception:
                body = {}
            path = (body.get("path") or "").strip()
            status = await asyncio.to_thread(check_connection, custom_path=path, force=True)
            return web.json_response(status)

        @routes.post("/visual_enhancer/browse")
        async def ve_browse_path(request: web.Request) -> web.Response:
            chosen = await asyncio.to_thread(browse_for_ve_cli)
            if not chosen:
                status = await asyncio.to_thread(check_connection)
                status["cancelled"] = True
                return web.json_response(status)
            status = await asyncio.to_thread(check_connection, custom_path=chosen, force=True)
            status["cancelled"] = False
            return web.json_response(status)

    except Exception:
        pass


_register_routes()

# scripts/arcenciel_server.py

import html
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import scripts.arcenciel_download as dl
import scripts.arcenciel_api as api
import scripts.arcenciel_gui as gui
import scripts.arcenciel_paths as path_utils

route_registered = False  # A global guard so we don't define routes multiple times in the same session
last_app = None

def ensure_server_routes(app: FastAPI):
    """
    Defines all ArcEnCiel extension routes, if not already defined.
    Also includes a simple /arcenciel/ping for checking if routes exist.
    """
    global route_registered
    if route_registered:
        return  # Already set up routes in this session
    route_registered = True

    @app.get("/arcenciel/ping")
    def ping_route():
        return {"status": "ok"}

    @app.post("/arcenciel/download_with_extension")
    async def download_with_extension(request: Request):
        data = await request.json()
        model_id = data.get("model_id", "")
        version_id = data.get("version_id", "")
        model_type = data.get("model_type", "OTHER").upper()
        url = data.get("url")
        file_name = data.get("file_name", "")
        subfolder = data.get("subfolder", "").strip()

        if not url:
            return JSONResponse({"error": "No url provided."}, status_code=400)

        try:
            local_path, out_dir = path_utils.resolve_download_path(model_type, file_name, subfolder)
            os.makedirs(out_dir, exist_ok=True)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        # If it's an ArcEnCiel official route
        final_url = url
        if "arcenciel.io" in url.lower() and model_id and version_id:
            final_url = f"https://arcenciel.io/api/models/{model_id}/versions/{version_id}/download"

        dl.queue_download(model_id, version_id, final_url, local_path)
        dl.start_downloads()

        return JSONResponse(
            {"message": f"Queued download for {path_utils.safe_filename(file_name)}", "path": local_path},
            status_code=202,
        )

    @app.get("/arcenciel/model_details/{model_id}")
    def arcenciel_model_details_route(model_id: int):
        data = api.fetch_model_details(model_id)
        if "error" in data:
            return Response(content=f"<div>Error: {html.escape(str(data['error']))}</div>", media_type="text/html")
        html = gui.build_model_details_html(data)
        return Response(content=html, media_type="text/html")

    @app.get("/arcenciel/image_details/{image_id}")
    def arcenciel_image_details_route(image_id: int):
        img_data = api.fetch_image_details(image_id)
        if "error" in img_data:
            return Response(content=f"<div>Error: {html.escape(str(img_data['error']))}</div>", media_type="text/html")
        html = gui.build_image_details_html(img_data)
        return Response(content=html, media_type="text/html")

def on_app_started(demo, app: FastAPI):
    """
    Called once at full startup. We'll call ensure_server_routes here,
    so on normal runs, routes are defined initially.
    """
    global last_app
    last_app = app
    ensure_server_routes(app)


def ensure_server_routes_on_last_app():
    global route_registered
    if last_app is None:
        return False
    route_registered = False
    ensure_server_routes(last_app)
    return True

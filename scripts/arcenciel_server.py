# scripts/arcenciel_server.py

from fastapi import FastAPI, Request, Response
import scripts.arcenciel_download as dl
import scripts.arcenciel_api as api
import scripts.arcenciel_gui as gui
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_global as gl

route_registered = False  # A global guard so we don't define routes multiple times in the same session

def ensure_server_routes(app: FastAPI):
    """
    Defines all ArcEnCiel extension routes, if not already defined.
    Also includes a simple /arcenciel/ping for checking if routes exist.
    """
    global route_registered
    if route_registered:
        return  # Already set up routes in this session
    route_registered = True

    #gl.debug_print("[ArcEnCiel] ensure_server_routes => registering routes")

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
        file_name = data.get("file_name", "UnknownFile")

        #gl.debug_print(f"[ArcEnCiel] Received extension download request => {data}")

        if not url:
            return {"error": "No url provided."}

        user_paths = path_utils.load_paths()
        out_dir = user_paths.get(model_type, user_paths["OTHER"]) or "."

        safe_name = file_name.replace("/", "_").replace("\\", "_")
        local_path = f"{out_dir}/{safe_name}"

        final_url = url
        if "arcenciel.io" in url.lower() and model_id and version_id:
            final_url = f"https://arcenciel.io/api/models/{model_id}/versions/{version_id}/download"
            #gl.debug_print(f"[ArcEnCiel] Using official route => {final_url}")

        dl.queue_download(model_id, version_id, final_url, local_path)
        dl.start_downloads()

        return {"message": f"Queued download for {file_name} => {local_path}"}

    @app.get("/arcenciel/model_details/{model_id}")
    def arcenciel_model_details_route(model_id: int):
        #gl.debug_print(f"[ArcEnCiel] Fetching details for model {model_id}")
        data = api.fetch_model_details(model_id)
        if "error" in data:
            return Response(content=f"<div>Error: {data['error']}</div>", media_type="text/html")
        html = gui.build_model_details_html(data)
        return Response(content=html, media_type="text/html")

    @app.get("/arcenciel/image_details/{image_id}")
    def arcenciel_image_details_route(image_id: int):
        #gl.debug_print(f"[ArcEnCiel] Fetching details for image {image_id}")
        img_data = api.fetch_image_details(image_id)
        if "error" in img_data:
            return Response(content=f"<div>Error: {img_data['error']}</div>", media_type="text/html")
        html = gui.build_image_details_html(img_data)
        return Response(content=html, media_type="text/html")


def on_app_started(demo, app: FastAPI):
    """
    Called once at full startup. We'll call ensure_server_routes here,
    so on normal runs, routes are defined initially.
    """
    ensure_server_routes(app)

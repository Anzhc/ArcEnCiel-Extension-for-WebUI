# scripts/arcenciel_server.py

import html
import os
import sys

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import scripts.arcenciel_download as dl
import scripts.arcenciel_api as api
import scripts.arcenciel_gui as gui
import scripts.arcenciel_inventory as inventory
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_settings as settings

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

    @app.get("/arcenciel/link_status")
    def link_status_route():
        return JSONResponse(link_status())

    @app.get("/arcenciel/folders/{model_type}")
    def folders_route(model_type: str):
        try:
            return JSONResponse({"folders": inventory.list_subfolders_for_model_type(model_type)})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    @app.post("/arcenciel/inventory/scan")
    def inventory_scan_route():
        return JSONResponse({"ok": True, **inventory.scan_inventory()})

    @app.get("/arcenciel/download_status/{job_id}")
    def download_status_route(job_id: str):
        status = dl.get_download_status(job_id)
        if not status:
            return JSONResponse({"error": "Unknown download job."}, status_code=404)
        return JSONResponse(status)

    @app.get("/arcenciel/downloads")
    def downloads_route(limit: int | None = None):
        requested_limit = limit if limit and limit > 0 else settings.download_history_limit()
        return JSONResponse({"jobs": dl.list_download_statuses(requested_limit)})

    @app.post("/arcenciel/download_cancel/{job_id}")
    def download_cancel_route(job_id: str):
        status, error = dl.cancel_download(job_id)
        if not status:
            return JSONResponse({"error": error}, status_code=404)
        return JSONResponse({"job": status, "message": error or "Cancel requested."})

    @app.post("/arcenciel/download_cancel_all")
    def download_cancel_all_route():
        dl.cancel_all_downloads()
        return JSONResponse({"message": "Cancel requested for active downloads."})

    @app.post("/arcenciel/download_retry/{job_id}")
    def download_retry_route(job_id: str):
        status, error = dl.retry_download(job_id)
        if not status:
            return JSONResponse({"error": error}, status_code=404)
        if error:
            return JSONResponse({"error": error, "job": status}, status_code=409)
        dl.start_downloads()
        return JSONResponse({"job": status, "message": "Retry queued."}, status_code=202)

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

        model_data = {}
        version_data = {}
        expected_hash = ""
        try:
            if str(model_id).isdigit():
                model_data = api.fetch_model_details(model_id)
                for version in model_data.get("versions") or []:
                    if str(version.get("id")) == str(version_id):
                        version_data = version
                        break
                hashes = inventory.version_hashes(version_data)
                expected_hash = hashes[0] if hashes else ""
                installed_path = inventory.find_installed_by_hashes(hashes)
                if installed_path:
                    return JSONResponse(
                        {
                            "error": "This version is already installed.",
                            "path": installed_path,
                        },
                        status_code=409,
                    )
        except Exception as exc:
            print(f"[ArcEnCiel] metadata lookup before download failed: {exc}")

        try:
            local_path, out_dir = path_utils.resolve_download_path(model_type, file_name, subfolder)
            os.makedirs(out_dir, exist_ok=True)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        # If it's an ArcEnCiel official route
        final_url = url
        if "arcenciel.io" in url.lower() and model_id and version_id:
            final_url = f"https://arcenciel.io/api/models/{model_id}/versions/{version_id}/download"

        job = dl.queue_download(
            model_id,
            version_id,
            final_url,
            local_path,
            expected_sha256=expected_hash,
            model_data=model_data,
            version_data=version_data,
            download_preview=bool(data.get("download_preview", settings.download_preview_enabled())),
            save_html_preview=bool(data.get("save_html_preview", settings.save_html_preview_enabled())),
        )
        dl.start_downloads()

        return JSONResponse(
            {
                "message": f"Queued download for {path_utils.safe_filename(file_name)}",
                "path": job["path"],
                "job_id": job["job_id"],
            },
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


def link_status():
    loaded = any(name == "arcenciel_link" or name.startswith("arcenciel_link.") for name in sys.modules)
    running = False
    if "arcenciel_link.downloader" in sys.modules:
        try:
            running = bool(sys.modules["arcenciel_link.downloader"].RUNNING.is_set())
        except Exception:
            running = False
    return {"installed": loaded, "workerRunning": running}

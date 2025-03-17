# scripts/arcenciel_api.py
import requests
import os
import pathlib
import scripts.arcenciel_global as gl
from scripts.arcenciel_global import debug_print
import base64

ARC_API_BASE = "https://arcenciel.io/api"
# Base URL for image files (remove the "/api" part)
THUMBNAIL_BASE_URL = "https://arcenciel.io/uploads"

# Temporary directory for preview images
TEMP_PREVIEWS_DIR = pathlib.Path(__file__).resolve().parents[1] / "temp_previews"
os.makedirs(TEMP_PREVIEWS_DIR, exist_ok=True)

def request_arc_api(endpoint="", params=None):
    """Generic GET to ArcEnCiel, returns dict or error info."""
    if not params:
        params = {}
    url = f"{ARC_API_BASE}{endpoint}"
    gl.debug_print("request_arc_api ->", url, params)
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        gl.debug_print("ArcEnCiel API error:", e)
        return {"error": str(e)}

def search_models(search_term="", sort="newest", page=1, limit=12, base_model="", model_type=""):
    params = {
        "search": search_term,
        "sort": sort,
        "page": page,
        "limit": limit,
    }
    if base_model:
        params["baseModel"] = base_model
    if model_type:
        params["modelType"] = model_type

    result = request_arc_api("/models/search", params)
    return result

def get_model_versions(model_id):
    endpoint = f"/models/{model_id}/versions"
    return request_arc_api(endpoint)

def fetch_model_details(model_id):
    endpoint = f"/models/{model_id}"
    return request_arc_api(endpoint)

def get_model_gallery(model_id):
    """
    Calls GET /api/models/{id}/gallery to retrieve gallery images.
    Expected response: {"data": [ { "id":..., "filePath": ... , ... } ], ...}
    """
    endpoint = f"/models/{model_id}/gallery"
    return request_arc_api(endpoint)

def download_preview_image(model_item):
    versions = model_item.get("versions", [])
    if versions and isinstance(versions, list):
        first_version = versions[0]
        images = first_version.get("images", [])
        if images:
            first_img = images[0]
            file_path = first_img.get("filePath", "")
            if file_path:
                file_base, _ = os.path.splitext(file_path.lstrip("/"))
                thumbnail_url = f"{THUMBNAIL_BASE_URL}/{file_base}.thumbnail.webp"
                debug_print("Downloading preview from:", thumbnail_url)
                try:
                    r = requests.get(thumbnail_url, timeout=20)
                    r.raise_for_status()
                    content = r.content
                    encoded = base64.b64encode(content).decode("utf-8")
                    data_url = f"data:image/webp;base64,{encoded}"
                    debug_print("Returning data URL (length:", len(data_url), ")")
                    return data_url
                except Exception as e:
                    debug_print("Error downloading preview:", e)
    return None

def fetch_image_details(image_id):
    """
    Example call to /images/{id} or /images/info?id=..., depending on ArcEnCiel's API.
    Returns dict with image info or {"error": "..."}.
    """
    endpoint = f"/images/{image_id}/info"
    result = request_arc_api(endpoint)
    return result
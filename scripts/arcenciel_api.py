# scripts/arcenciel_api.py
import base64
import os
import urllib.parse

import requests

from scripts.arcenciel_global import debug_print

ARC_API_BASE = "https://arcenciel.io/api"
# Base URL for image files (remove the "/api" part)
THUMBNAIL_BASE_URL = "https://arcenciel.io/uploads"


def request_arc_api(endpoint="", params=None):
    """Generic GET to ArcEnCiel, returns dict or error info."""
    if not params:
        params = {}
    url = f"{ARC_API_BASE}{endpoint}"
    #gl.debug_print("request_arc_api ->", url, params)
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        #gl.debug_print("ArcEnCiel API error:", e)
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


def get_model_classes():
    result = request_arc_api("/models/classes")
    raw_classes = result.get("classes") or result.get("data") or []
    names = []
    for item in raw_classes:
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name") or item.get("label")
        else:
            name = ""
        name = str(name).strip()
        if name and name not in names:
            names.append(name)
    return names


def get_base_model_choices():
    fallback = [
        "Illustrious",
        "NoobAI Eps",
        "NoobAI V-Pred",
        "Pony",
        "Flux.1 D",
        "SDXL 1.0",
        "SD1.5",
    ]
    names = get_model_classes()
    if not names:
        names = fallback
    return ["Any"] + names


def get_model_versions(model_id):
    endpoint = f"/models/{model_id}/versions"
    return request_arc_api(endpoint)


def fetch_model_details(model_id):
    endpoint = f"/models/{model_id}"
    return request_arc_api(endpoint)


def get_model_gallery(model_id):
    """
    Calls GET /api/models/{id}/gallery to retrieve gallery images. The current
    API returns entries like {"kind": "image", "data": {...}}, while older
    responses returned image objects directly.
    """
    endpoint = f"/models/{model_id}/gallery"
    return request_arc_api(endpoint)


def unwrap_media_item(item):
    if isinstance(item, dict) and isinstance(item.get("data"), dict):
        return item["data"]
    if isinstance(item, dict):
        return item
    return {}


def normalize_gallery_items(gallery_resp):
    if not isinstance(gallery_resp, dict):
        return []
    items = gallery_resp.get("data") or gallery_resp.get("items") or []
    return [unwrap_media_item(item) for item in items if unwrap_media_item(item)]


def _uploads_url(path):
    if not path:
        return ""
    path = str(path).strip().lstrip("/")
    if path.startswith(("http://", "https://", "data:")):
        return path
    return f"{THUMBNAIL_BASE_URL}/{path}"


def _variant_url(image_item, preferred_labels):
    variants = image_item.get("variants") if isinstance(image_item, dict) else None
    if not isinstance(variants, list):
        return ""

    by_label = {}
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        label = str(variant.get("label") or "").lower()
        path = variant.get("path") or variant.get("filePath") or variant.get("url")
        if label and path:
            by_label[label] = path

    for label in preferred_labels:
        if label in by_label:
            return _uploads_url(by_label[label])

    for variant in variants:
        if not isinstance(variant, dict):
            continue
        path = variant.get("path") or variant.get("filePath") or variant.get("url")
        if path:
            return _uploads_url(path)
    return ""


def get_image_url(image_item, prefer="detail"):
    image_item = unwrap_media_item(image_item)
    if not image_item:
        return ""

    if prefer == "thumb":
        variant_url = _variant_url(image_item, ("w256", "thumbnail", "thumb", "w512"))
    elif prefer == "preview":
        variant_url = _variant_url(image_item, ("w512", "w256", "thumbnail", "thumb", "fallback"))
    else:
        variant_url = _variant_url(image_item, ("w1024", "w2048", "fallback", "w512", "w256"))
    if variant_url:
        return variant_url

    file_path = (image_item.get("filePath") or image_item.get("path") or "").lstrip("/")
    if not file_path:
        return ""
    if prefer == "thumb":
        file_base, _ = os.path.splitext(file_path)
        return _uploads_url(f"{file_base}.thumbnail.webp")
    return _uploads_url(file_path)


def iter_model_images(model_item):
    if not isinstance(model_item, dict):
        return []

    candidates = []
    for key in ("pinnedImages", "images", "gallery"):
        value = model_item.get(key)
        if isinstance(value, list):
            candidates.extend(value)

    for version in model_item.get("versions") or []:
        if not isinstance(version, dict):
            continue
        for key in ("images", "gallery", "media"):
            value = version.get(key)
            if isinstance(value, list):
                candidates.extend(value)

    return [unwrap_media_item(item) for item in candidates if unwrap_media_item(item)]


def version_is_downloadable(version):
    if not isinstance(version, dict):
        return False
    status = str(version.get("status") or "").strip().upper()
    if status in ("SCHEDULED", "UPCOMING"):
        return False
    return bool(version.get("externalDownloadUrl") or version.get("filePath"))


def version_download_url(model_id, version):
    if not version_is_downloadable(version):
        return ""
    external_url = (version.get("externalDownloadUrl") or "").strip()
    if external_url:
        return external_url
    if version.get("filePath") and model_id and version.get("id"):
        return f"https://arcenciel.io/api/models/{model_id}/versions/{version.get('id')}/download"
    return ""


def version_file_name(version):
    if not isinstance(version, dict):
        return ""
    file_name = (version.get("fileName") or version.get("originalName") or "").strip()
    if file_name:
        return file_name

    external_url = (version.get("externalDownloadUrl") or "").strip()
    if external_url:
        last_segment = external_url.rsplit("/", 1)[-1].split("?", 1)[0]
        file_name = urllib.parse.unquote(last_segment).strip()
        if file_name:
            return file_name

    file_path = (version.get("filePath") or "").strip()
    if file_path:
        return os.path.basename(file_path.replace("\\", "/"))
    return ""


def download_preview_image(model_item):
    images = iter_model_images(model_item)
    if not images:
        return None

    preview_url = get_image_url(images[0], prefer="preview")
    if not preview_url:
        return None

    try:
        r = requests.get(preview_url, timeout=20)
        r.raise_for_status()
        content_type = r.headers.get("content-type") or "image/webp"
        encoded = base64.b64encode(r.content).decode("utf-8")
        return f"data:{content_type};base64,{encoded}"
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

import html
import json
from io import BytesIO
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import scripts.arcenciel_api as api


def clean_text(value):
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    return soup.get_text("\n").strip()


def _activation_text(version):
    tags = version.get("activationTags") if isinstance(version, dict) else []
    if not isinstance(tags, list):
        return ""
    return " || ".join(str(tag) for tag in tags if tag)


def _preview_url(model_data, version):
    candidates = []
    if isinstance(version, dict):
        candidates.extend(version.get("images") or [])
        candidates.extend(version.get("gallery") or [])
    candidates.extend(api.iter_model_images(model_data))
    for item in candidates:
        url = api.get_image_url(item, prefer="preview")
        if url:
            return url

    model_id = model_data.get("id") if isinstance(model_data, dict) else None
    if model_id:
        gallery = api.normalize_gallery_items(api.get_model_gallery(model_id))
        ordered = _ordered_gallery_items(gallery, version)
        for item in ordered:
            url = api.get_image_url(item, prefer="preview")
            if url:
                return url
        for item in gallery:
            url = api.get_image_url(item, prefer="preview")
            if url:
                return url
    return ""


def _ordered_gallery_items(gallery, version):
    image_order = version.get("imageOrder") if isinstance(version, dict) else []
    if not isinstance(image_order, list) or not image_order:
        return []

    by_id = {}
    for item in gallery:
        image_id = item.get("id") if isinstance(item, dict) else None
        if image_id is not None:
            by_id[str(image_id)] = item

    ordered = []
    for image_id in image_order:
        key = str(image_id)
        if key in by_id:
            ordered.append(by_id[key])
            continue
        fetched = api.fetch_image_details(image_id)
        if isinstance(fetched, dict) and fetched.get("id"):
            ordered.append(fetched)
    return ordered


def _save_preview(preview_url, model_path):
    if not preview_url:
        return None, None

    response = requests.get(preview_url, timeout=30)
    response.raise_for_status()

    model_path = Path(model_path)
    png_path = model_path.with_suffix(".preview.png")
    cover_path = model_path.with_suffix(".png")
    try:
        from PIL import Image

        image = Image.open(BytesIO(response.content)).convert("RGBA")
        image.save(png_path, format="PNG")
        if not cover_path.exists():
            image.save(cover_path, format="PNG")
        return png_path.name, cover_path.name
    except Exception:
        content_type = (response.headers.get("content-type") or "").lower()
        suffix = ".webp" if "webp" in content_type else ".jpg"
        raw_path = model_path.with_suffix(f".preview{suffix}")
        raw_path.write_bytes(response.content)
        cover_raw_path = model_path.with_suffix(suffix)
        if not cover_raw_path.exists():
            cover_raw_path.write_bytes(response.content)
        return raw_path.name, cover_raw_path.name


def _metadata(model_data, version, model_path, sha_local, preview_name, cover_name):
    model_data = model_data if isinstance(model_data, dict) else {}
    version = version if isinstance(version, dict) else {}
    model_id = model_data.get("id") or version.get("modelId")
    version_id = version.get("id") or version.get("versionId")
    return {
        "schema": 1,
        "modelId": model_id,
        "versionId": version_id,
        "name": model_data.get("title") or version.get("modelTitle") or Path(model_path).stem,
        "versionName": version.get("versionName"),
        "type": model_data.get("type") or version.get("type"),
        "baseModel": version.get("baseModel"),
        "about": clean_text(version.get("aboutThisVersion") or version.get("about")),
        "description": clean_text(model_data.get("description") or version.get("description")),
        "activation text": _activation_text(version),
        "sha256": sha_local,
        "previewFile": preview_name,
        "coverFile": cover_name,
        "arcencielUrl": f"https://arcenciel.io/models/{model_id}" if model_id else "",
    }


def write_sidecars(model_data, version, model_path, sha_local="", download_preview=True, save_html=False):
    model_path = Path(model_path)
    preview_name = None
    cover_name = None
    if download_preview:
        try:
            preview_name, cover_name = _save_preview(_preview_url(model_data, version), model_path)
        except Exception as exc:
            print(f"[ArcEnCiel] preview sidecar failed for {model_path.name}: {exc}")

    metadata = _metadata(model_data, version, model_path, sha_local, preview_name, cover_name)
    info_path = model_path.with_suffix(".arcenciel.info")
    info_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    webui_json = {
        "description": metadata["about"] or metadata["description"],
        "sd version": metadata["baseModel"] or "unknown",
        "activation text": metadata["activation text"],
        "preferred weight": 1.0,
        "notes": metadata["arcencielUrl"],
        "sha256": metadata["sha256"],
        "modelId": metadata["modelId"],
        "modelVersionId": metadata["versionId"],
    }
    model_path.with_suffix(".json").write_text(
        json.dumps(webui_json, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if save_html:
        _write_html_preview(metadata, model_path)

    return {"info": str(info_path), "preview": preview_name}


def _write_html_preview(metadata, model_path):
    preview = metadata.get("previewFile")
    preview_html = f'<img src="{html.escape(preview, quote=True)}" alt="preview" />' if preview else ""
    tags = html.escape(metadata.get("activation text") or "")
    content = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>{html.escape(str(metadata.get("name") or "ArcEnCiel Model"))}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;line-height:1.5}}
img{{max-width:100%;border-radius:8px}}
pre{{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}}
</style>
<h1>{html.escape(str(metadata.get("name") or ""))}</h1>
{preview_html}
<h2>Activation</h2>
<pre>{tags}</pre>
<h2>Notes</h2>
<p>{html.escape(str(metadata.get("about") or metadata.get("description") or ""))}</p>
<p><a href="{html.escape(str(metadata.get("arcencielUrl") or ""), quote=True)}">ArcEnCiel model page</a></p>
</html>
"""
    Path(model_path).with_suffix(".arcenciel.html").write_text(content, encoding="utf-8")

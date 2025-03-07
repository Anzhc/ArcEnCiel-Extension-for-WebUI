import gradio as gr
import requests
import os
import re
import cgi
import urllib.parse
import concurrent.futures
import pathlib
from urllib.parse import urlparse

import modules.scripts as scripts
from modules import script_callbacks

ARCENCIEL_BASE_URL = "https://arcenciel.io"
ARCENCIEL_API_BASE = f"{ARCENCIEL_BASE_URL}/api"

PLACEHOLDER_LOCAL_PATH = os.path.join(scripts.basedir(), "placeholder_doro.png")
TEMP_IMAGES_DIR = os.path.join(scripts.basedir(), "temp_images")
os.makedirs(TEMP_IMAGES_DIR, exist_ok=True)

thumbnail_cache = {}

def find_webui_root_from_extension():
    """Walk upward from extension folder until we find the main webui root (which has 'models/')."""
    current = pathlib.Path(scripts.basedir()).resolve()
    for _ in range(5):
        if (current / "models").exists():
            return str(current)
        if current.parent == current:
            break
        current = current.parent
    return str(pathlib.Path(scripts.basedir()).resolve())

def get_folder_for_type(mtype: str) -> str:
    """Map recognized model types to subfolders under 'models/'."""
    mtype = (mtype or "").strip().lower()
    if mtype == "lora":
        return "models/lora"
    elif mtype == "checkpoint":
        return "models/Stable-diffusion"
    elif mtype == "segmentation":
        return "models/adetailer"
    elif mtype == "vae":
        return "models/VAE"
    elif mtype == "embedding":
        return "embeddings"
    return "models/Arcenciel_other_models"

MAX_VERSIONS_DISPLAY = 10

def search_models(search_query="", page=1, limit=12, sort="newest", base_model="", model_type=""):
    if base_model == "None":
        base_model = ""
    if model_type == "None":
        model_type = ""

    url = f"{ARCENCIEL_API_BASE}/models/search"
    params = {
        "search": search_query,
        "page": page,
        "limit": limit,
        "sort": sort
    }
    if base_model:
        params["baseModel"] = base_model
    if model_type:
        params["modelType"] = model_type

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[Arcenciel Extension] search_models error: {e}")
        return {
            "page": page,
            "limit": limit,
            "totalCount": 0,
            "totalPages": 0,
            "data": []
        }

def get_model_versions(model_id):
    url = f"{ARCENCIEL_API_BASE}/models/{model_id}/versions"
    try:
        resp = requests.get(url, timeout=150)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            return data["versions"]
        return []
    except Exception as e:
        print(f"[Arcenciel Extension] get_model_versions error: {e}")
        return []

def get_image_file_from_path(file_path, model_id):
    if not file_path:
        return PLACEHOLDER_LOCAL_PATH
    if file_path in thumbnail_cache:
        cached_path = thumbnail_cache[file_path]
        if os.path.exists(cached_path):
            return cached_path

    file_base, _ = os.path.splitext(file_path)
    thumbnail_url = f"{ARCENCIEL_BASE_URL}/uploads/{file_base}.thumbnail.webp"
    basename = os.path.basename(file_base)
    new_filename = f"{model_id}_{basename}.thumbnail.webp"
    local_path = os.path.join(TEMP_IMAGES_DIR, new_filename)

    try:
        resp = requests.get(thumbnail_url, timeout=150)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        thumbnail_cache[file_path] = local_path
        return local_path
    except Exception:
        thumbnail_cache[file_path] = PLACEHOLDER_LOCAL_PATH
        return PLACEHOLDER_LOCAL_PATH

def fetch_preview_from_latest_version(model_id):
    versions = get_model_versions(model_id)
    if not versions:
        return PLACEHOLDER_LOCAL_PATH

    def version_sort_key(v):
        return v.get("createdAt") or v.get("id") or 0

    sorted_versions = sorted(versions, key=version_sort_key, reverse=True)
    for v in sorted_versions:
        images = v.get("images", [])
        if images:
            first_image_file = images[0].get("filePath", "")
            if first_image_file:
                return get_image_file_from_path(first_image_file, model_id)
    return PLACEHOLDER_LOCAL_PATH

def _download_preview_worker(idx, model):
    model_id = model.get("id")
    title = model.get("title", "Untitled")
    local_preview_path = fetch_preview_from_latest_version(model_id)
    label_text = f"{title}\n(ID: {model_id})"
    return (idx, local_preview_path, label_text, model)

def fetch_models_for_gallery(search_text, page_num, limit, sort_order, base_model, model_type):
    if page_num < 1:
        page_num = 1

    items_json = search_models(
        search_query=search_text,
        page=page_num,
        limit=limit,
        sort=sort_order,
        base_model=base_model,
        model_type=model_type
    )

    total_pages = items_json.get("totalPages", 0)
    data = items_json.get("data", [])
    results_in_order = [None] * len(data)

    def _handle_completed(fut):
        idx, local_path, label_text, mod = fut.result()
        results_in_order[idx] = (local_path, label_text, mod)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        fut_map = {}
        for i, mod in enumerate(data):
            model_id = mod.get("id")
            if model_id is None:
                continue
            fut = executor.submit(_download_preview_worker, i, mod)
            fut_map[fut] = i

        for fut in concurrent.futures.as_completed(fut_map):
            try:
                _handle_completed(fut)
            except Exception as e:
                print(f"[Arcenciel Extension] Worker exception: {e}")

    gallery_items = []
    model_data_dicts = []
    for item in results_in_order:
        if item is None:
            continue
        local_path, label_text, mod = item
        gallery_items.append([local_path, label_text])
        model_data_dicts.append(mod)

    return gallery_items, model_data_dicts, total_pages

# -------------------------------------------------------------------------
# Extension DL with double-decoding for huggingface "filename*"
# -------------------------------------------------------------------------
def extension_download_cb(version_index, versions):
    """
    If a server double-encoded the filename (ex: 'filename*=UTF-8''Anzhc%2520breasts.pt'),
    we decode once, then if there's still '%2' left, we decode again.
    """
    if version_index < 0 or version_index >= len(versions):
        return "Invalid version index."

    v = versions[version_index]
    external_link = v.get("externalDownloadUrl")
    model_id = v.get("modelId") or "???"
    version_id = v.get("id") or "???"
    parent_model_type = (v.get("modelType") or "OTHER").strip().lower()

    if external_link:
        download_url = external_link
    else:
        download_url = f"{ARCENCIEL_API_BASE}/models/{model_id}/versions/{version_id}/download"

    webui_root = find_webui_root_from_extension()
    rel_folder = get_folder_for_type(parent_model_type)
    target_folder = os.path.join(webui_root, rel_folder)

    try:
        os.makedirs(target_folder, exist_ok=True)
        r = requests.get(download_url, stream=True, timeout=180)
        r.raise_for_status()

        cdisp = r.headers.get("Content-Disposition", "")
        value, params = cgi.parse_header(cdisp)

        filename_from_header = None

        # 1) if 'filename*' present => huggingface style
        if "filename*" in params:
            raw_val = params["filename*"]  # e.g. UTF-8''Anzhc%2520Breasts%2520v1.pt
            # remove leading UTF-8'' if present
            if raw_val.lower().startswith("utf-8''"):
                raw_val = raw_val[7:]
            # first decode
            raw_val = urllib.parse.unquote(raw_val)

            # check if there's STILL leftover '%2'
            while '%2' in raw_val:
                new_val = urllib.parse.unquote(raw_val)
                if new_val == raw_val:
                    break
                raw_val = new_val

            filename_from_header = raw_val
        # 2) else if 'filename' present
        elif "filename" in params:
            filename_from_header = params["filename"]

        # 3) fallback to last path
        if not filename_from_header:
            parsed = urlparse(download_url)
            filename_from_header = os.path.basename(parsed.path)

        # 4) fallback to generic
        if not filename_from_header:
            filename_from_header = "downloaded_file"

        # sanitize
        filename_from_header = re.sub(r'[\\/:*?"<>|]+', '_', filename_from_header)

        final_path = os.path.join(target_folder, filename_from_header)

        block_size = 1024 * 256
        wrote = 0
        with open(final_path, "wb") as f:
            for data in r.iter_content(block_size):
                f.write(data)
                wrote += len(data)

        size_mb = wrote / (1024 * 1024)
        return f"Downloaded '{filename_from_header}' ({size_mb:.2f} MB) → {final_path}"

    except Exception as e:
        return f"Download error: {str(e)}"

def direct_download_link_cb(version_index, versions):
    if version_index < 0 or version_index >= len(versions):
        return ""
    v = versions[version_index]
    external_link = v.get("externalDownloadUrl")
    model_id = v.get("modelId") or "???"
    version_id = v.get("id") or "???"
    if external_link:
        return external_link
    else:
        return f"{ARCENCIEL_API_BASE}/models/{model_id}/versions/{version_id}/download"

def show_model_details(model_index, stored_models):
    if model_index is None or model_index < 0 or model_index >= len(stored_models):
        return (
            gr.update(value="Select a model from the gallery."),
            gr.update(value=""),
            gr.update(value="")
        )

    model = stored_models[model_index]
    model_id = model.get("id", "N/A")
    title = model.get("title", "Untitled")
    desc = model.get("description", "No description")

    versions = get_model_versions(model_id)
    if not versions:
        version_text = "No versions found."
    else:
        lines = []
        for v in versions:
            if not isinstance(v, dict):
                continue
            version_name = v.get("versionName", "N/A")
            b_model = v.get("baseModel", "")
            about = v.get("aboutThisVersion", "")
            dl_count = v.get("downloadCount", 0)
            tags = v.get("activationTags", [])

            tags_str = ""
            if tags:
                tags_str = "Activation Tags:\n"
                for t in tags:
                    tags_str += f"  - {t}\n"

            external_link = v.get("externalDownloadUrl")
            version_id = v.get("id")
            if external_link:
                download_link = external_link
            else:
                download_link = f"{ARCENCIEL_API_BASE}/models/{model_id}/versions/{version_id}/download"

            block = (
                f"Version: {version_name}\n"
                f"Base Model: {b_model}\n"
                f"About: {about}\n"
                f"{tags_str}"
                f"Downloads: {dl_count}\n"
                f"Download link: {download_link}\n"
                "----------------------"
            )
            lines.append(block)

        version_text = "\n".join(lines) if lines else "No valid version entries found."

    return (title, desc, version_text)

def prepare_versions_for_state(model_index, stored_models):
    if model_index is None or model_index < 0 or model_index >= len(stored_models):
        return []
    parent_model = stored_models[model_index]
    model_id = parent_model.get("id")
    if not model_id:
        return []

    parent_type = parent_model.get("type", "OTHER")
    versions = get_model_versions(model_id)
    for v in versions:
        v["modelType"] = parent_type
    return versions

def build_version_ui_updates(versions):
    updates = []
    for i in range(MAX_VERSIONS_DISPLAY):
        if i < len(versions):
            v = versions[i]
            version_name = v.get("versionName", "N/A")
            base_model = v.get("baseModel", "")
            about = v.get("aboutThisVersion", "")
            dl_count = v.get("downloadCount", 0)
            tags = v.get("activationTags", [])

            tags_str = ""
            if tags:
                tags_str = "**Activation Tags**:\n"
                for t in tags:
                    tags_str += f"- {t}\n"

            vtitle = f"**Version:** {version_name} | **Base Model:** {base_model}"
            vabout = about
            vdownloads = f"**Downloads:** {dl_count}"

            updates.append(gr.update(visible=True))  
            updates.append(gr.update(value=vtitle, visible=True))  
            updates.append(gr.update(value=vabout, visible=True))  
            updates.append(gr.update(value=tags_str, visible=True))  
            updates.append(gr.update(value=vdownloads, visible=True))  
            updates.append(gr.update(value="", visible=True))  
            updates.append(gr.update(visible=True))  
            updates.append(gr.update(visible=True))  
        else:
            # Hide
            updates.append(gr.update(visible=False))
            updates.append(gr.update(value="", visible=False))
            updates.append(gr.update(value="", visible=False))
            updates.append(gr.update(value="", visible=False))
            updates.append(gr.update(value="", visible=False))
            updates.append(gr.update(value="", visible=False))
            updates.append(gr.update(visible=False))
            updates.append(gr.update(visible=False))
    return updates

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as arcenciel_interface:
        gr.Markdown("## Arcenciel.io Model Browser")

        with gr.Row():
            search_text = gr.Textbox(value="", label="Search query")
            sort_order = gr.Dropdown(choices=["newest", "oldest"], value="newest", label="Sort Order")
            base_model = gr.Dropdown(
                label="Base Model Filter",
                choices=[
                    "None","Illustrious","NoobAI Eps","NoobAI V-Pred","Pony",
                    "Flux.1 D","Flux.1 S","SDXL 1.0","SD1.5"
                ],
                value="None"
            )
            model_type = gr.Dropdown(
                label="Model Type Filter",
                choices=["None","LORA","CHECKPOINT","VAE","EMBEDDING","SEGMENTATION","OTHER"],
                value="None"
            )
            page_num = gr.Number(label="Page #", value=1, precision=0)
            limit_box = gr.Number(label="Models per page", value=12, precision=0)

        total_pages_info = gr.Markdown(value="Total pages: 0")

        with gr.Row():
            prev_button = gr.Button("Previous Page")
            next_button = gr.Button("Next Page")
            fetch_button = gr.Button("Search/Refresh")

        model_gallery = gr.Gallery(columns=6, label="Models")
        stored_models_state = gr.State([])

        with gr.Column():
            selected_model_title = gr.Markdown("Select a model from the gallery.")
            selected_model_description = gr.Markdown("")
            selected_model_versions = gr.Markdown("")

            version_boxes = []
            for i in range(MAX_VERSIONS_DISPLAY):
                with gr.Group(visible=False) as vb:
                    vtitle = gr.Markdown()
                    vabout = gr.Markdown()
                    vtags = gr.Markdown()
                    vdownloads = gr.Markdown()
                    progress_txt = gr.Markdown()
                    with gr.Row():
                        ext_dl_btn = gr.Button("Extension DL")
                        direct_dl_btn = gr.Button("Direct DL (Browser)")
                version_boxes.append((vb, vtitle, vabout, vtags, vdownloads, progress_txt, ext_dl_btn, direct_dl_btn))

        current_versions_state = gr.State([])

        def update_gallery_cb(s_text, p_num, lim, s_order, b_model, m_type):
            items, model_dicts, total_pages = fetch_models_for_gallery(
                s_text, int(p_num), int(lim), s_order, b_model, m_type
            )
            info_markdown = f"Total pages: {total_pages}"
            return [items, model_dicts, info_markdown]

        def gallery_select_cb(evt: gr.SelectData, stored_models):
            model_idx = evt.index
            versions = prepare_versions_for_state(model_idx, stored_models)

            t, d, ver_text = show_model_details(model_idx, stored_models)
            version_ui = build_version_ui_updates(versions)

            return [versions, t, d, ver_text] + version_ui

        fetch_button.click(
            fn=update_gallery_cb,
            inputs=[search_text, page_num, limit_box, sort_order, base_model, model_type],
            outputs=[model_gallery, stored_models_state, total_pages_info]
        )

        model_gallery.select(
            fn=gallery_select_cb,
            inputs=[stored_models_state],
            outputs=(
                [current_versions_state,
                 selected_model_title,
                 selected_model_description,
                 selected_model_versions]
                + [comp for row in version_boxes for comp in row]
            )
        )

        def prev_page_cb(s_text, p, lim, s_order, b_model, m_type):
            new_page = max(1, int(p) - 1)
            items, model_dicts, t_pages = fetch_models_for_gallery(
                s_text, new_page, int(lim), s_order, b_model, m_type
            )
            info_markdown = f"Total pages: {t_pages}"
            return [new_page, items, model_dicts, info_markdown]

        def next_page_cb(s_text, p, lim, s_order, b_model, m_type):
            new_page = int(p) + 1
            items, model_dicts, t_pages = fetch_models_for_gallery(
                s_text, new_page, int(lim), s_order, b_model, m_type
            )
            info_markdown = f"Total pages: {t_pages}"
            return [new_page, items, model_dicts, info_markdown]

        prev_button.click(
            fn=prev_page_cb,
            inputs=[search_text, page_num, limit_box, sort_order, base_model, model_type],
            outputs=[page_num, model_gallery, stored_models_state, total_pages_info]
        )

        next_button.click(
            fn=next_page_cb,
            inputs=[search_text, page_num, limit_box, sort_order, base_model, model_type],
            outputs=[page_num, model_gallery, stored_models_state, total_pages_info]
        )

        direct_dl_js = """
        (link) => {
            if (link) {
                window.open(link, '_blank');
            }
            return "";
        }
        """

        def make_ext_dl_callback(i):
            def _callback(versions):
                return extension_download_cb(i, versions)
            return _callback

        def make_direct_dl_py(i):
            def _callback(versions):
                return direct_download_link_cb(i, versions)
            return _callback

        for i, row in enumerate(version_boxes):
            (vb, vtitle, vabout, vtags, vdownloads, progress_txt, ext_dl_btn, direct_dl_btn) = row
            ext_dl_btn.click(
                fn=make_ext_dl_callback(i),
                inputs=[current_versions_state],
                outputs=[progress_txt],
            )
            direct_dl_btn.click(
                fn=make_direct_dl_py(i),
                inputs=[current_versions_state],
                outputs=[],
                _js=direct_dl_js
            )

    return [(arcenciel_interface, "Arcenciel Browser", "arcenciel_interface")]

script_callbacks.on_ui_tabs(on_ui_tabs)

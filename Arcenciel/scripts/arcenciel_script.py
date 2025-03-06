import gradio as gr
import requests
import os

import modules.scripts as scripts
from modules import script_callbacks

# Arcenciel.io's base API URL
ARCENCIEL_API_BASE = "https://arcenciel.io/api"

# Local placeholder image in the extension's root
PLACEHOLDER_LOCAL_PATH = os.path.join(scripts.basedir(), "placeholder_doro.png")

# Subfolder for downloaded images
TEMP_IMAGES_DIR = os.path.join(scripts.basedir(), "temp_images")
os.makedirs(TEMP_IMAGES_DIR, exist_ok=True)

def search_models(search_query="", page=1, limit=12, sort="newest", base_model="", model_type=""):
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
        print(f"[Arcenciel Extension] Error in search_models: {e}")
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
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            return data["versions"]
        print(f"[Arcenciel Extension] Unexpected structure in get_model_versions({model_id}): {data}")
        return []
    except Exception as e:
        print(f"[Arcenciel Extension] Error in get_model_versions({model_id}): {e}")
        return []

def get_image_file(image_id, model_id):
    if image_id is None:
        return PLACEHOLDER_LOCAL_PATH

    url = f"{ARCENCIEL_API_BASE}/images/{image_id}"
    filename = f"{model_id}_{image_id}.webp"
    local_path = os.path.join(TEMP_IMAGES_DIR, filename)

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(resp.content)
        return local_path
    except Exception as e:
        print(f"[Arcenciel Extension] Failed to fetch image {image_id} for model {model_id}: {e}")
        return PLACEHOLDER_LOCAL_PATH

def fetch_preview_from_latest_version(model_id):
    versions = get_model_versions(model_id)
    if not versions:
        return PLACEHOLDER_LOCAL_PATH

    def version_sort_key(v):
        return v.get("createdAt") or v.get("id") or 0

    sorted_versions = sorted(versions, key=version_sort_key, reverse=True)
    for v in sorted_versions:
        if not isinstance(v, dict):
            continue
        images = v.get("images", [])
        if images:
            first_image = images[0]
            img_id = first_image.get("id")
            local_path = get_image_file(img_id, model_id)
            return local_path

    return PLACEHOLDER_LOCAL_PATH

def fetch_models_for_gallery(search_text, page_num, limit, sort_order, base_model, model_type):
    if page_num < 1:
        page_num = 1

    results = search_models(
        search_query=search_text,
        page=page_num,
        limit=limit,
        sort=sort_order,
        base_model=base_model,
        model_type=model_type
    )

    total_pages = results.get("totalPages", 0)
    data = results.get("data", [])

    gallery_items = []
    model_data_dicts = []

    for model in data:
        model_id = model.get("id")
        if model_id is None:
            continue

        title = model.get("title", "Untitled")
        local_preview_path = fetch_preview_from_latest_version(model_id)

        label_text = f"{title}\n(ID: {model_id})"
        gallery_items.append([local_preview_path, label_text])
        model_data_dicts.append(model)

    return gallery_items, model_data_dicts, total_pages

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

            # Build a string for all activation tags, line by line
            # e.g. multiple sets might appear as:
            #    - set1
            #    - set2
            #    ...
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

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as arcenciel_interface:
        gr.Markdown("## Arcenciel.io Model Browser")

        with gr.Row():
            search_text = gr.Textbox(
                label="Search query",
                value="",
                placeholder="Type model name, description, or tag..."
            )
            sort_order = gr.Dropdown(
                choices=["newest", "oldest"],
                value="newest",
                label="Sort Order"
            )

        with gr.Row():
            base_model = gr.Textbox(
                label="Base Model Filter",
                placeholder="e.g. SD1.5"
            )
            model_type = gr.Textbox(
                label="Model Type Filter",
                placeholder="e.g. LORA, CHECKPOINT"
            )

        with gr.Row():
            page_num = gr.Number(
                label="Page #",
                value=1,
                precision=0
            )
            limit_box = gr.Number(
                label="Models per page",
                value=12,
                precision=0
            )

        total_pages_info = gr.Markdown(value="Total pages: 0")

        with gr.Row():
            prev_button = gr.Button("Previous Page")
            next_button = gr.Button("Next Page")
            fetch_button = gr.Button("Search/Refresh")

        model_gallery = gr.Gallery(
            label="Models",
            show_label=False,
            columns=4
        )
        stored_models_state = gr.State([])

        with gr.Column():
            selected_model_title = gr.Markdown("Select a model from the gallery.")
            selected_model_description = gr.Markdown("")
            selected_model_versions = gr.Markdown("")

        def update_gallery_cb(s_text, p_num, lim, s_order, b_model, m_type):
            items, model_dicts, total_pages = fetch_models_for_gallery(
                s_text, int(p_num), int(lim), s_order, b_model, m_type
            )
            info_markdown = f"Total pages: {total_pages}"
            return [items, model_dicts, info_markdown]

        def gallery_select_cb(evt: gr.SelectData, stored_models):
            index = evt.index
            return show_model_details(index, stored_models)

        fetch_button.click(
            fn=update_gallery_cb,
            inputs=[search_text, page_num, limit_box, sort_order, base_model, model_type],
            outputs=[model_gallery, stored_models_state, total_pages_info]
        )

        model_gallery.select(
            fn=gallery_select_cb,
            inputs=[stored_models_state],
            outputs=[selected_model_title, selected_model_description, selected_model_versions]
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

    return [(arcenciel_interface, "Arcenciel Browser", "arcenciel_interface")]

script_callbacks.on_ui_tabs(on_ui_tabs)

import gradio as gr
import time
import requests
from modules import shared
import os

import scripts.arcenciel_api as api
import scripts.arcenciel_global as gl
import scripts.arcenciel_paths as path_utils
from scripts.arcenciel_paths import get_paths_for_ui
import scripts.arcenciel_server as server

PLACEHOLDER_IMG = "https://via.placeholder.com/150"

already_created_tab = False

def build_image_details_html(img_data):
    if not img_data or "id" not in img_data:
        return "<div>No image data found.</div>"

    image_id = img_data.get("id", "")
    file_path = (img_data.get("filePath") or "").lstrip("/")
    full_url = f"https://arcenciel.io/uploads/{file_path}" if file_path else "https://via.placeholder.com/400"

    prompt = img_data.get("prompt", "")
    neg_prompt = img_data.get("negativePrompt", "")
    sampler = img_data.get("sampler", "")
    seed = img_data.get("seed", "")
    steps = img_data.get("steps", "")
    cfg = img_data.get("cfg", "")

    html = f"""
    <div style="padding:1em;">
      <h3>Image ID: {image_id}</h3>
      <div style="display:flex; gap:1em;">
        <div style="flex:1; min-width:200px;">
          <img src="{full_url}" style="max-width:100%; border:1px solid #444;"/>
        </div>
        <div style="flex:1; min-width:200px;">
          <div><b>Prompt:</b><br/>{prompt}</div>
          <div style="margin-top:0.5em;"><b>Negative Prompt:</b><br/>{neg_prompt}</div>
          <div style="margin-top:0.5em;"><b>Sampler:</b> {sampler}</div>
          <div style="margin-top:0.5em;"><b>Seed:</b> {seed}</div>
          <div style="margin-top:0.5em;"><b>Steps:</b> {steps}</div>
          <div style="margin-top:0.5em;"><b>CFG:</b> {cfg}</div>
        </div>
      </div>
    </div>
    """
    return html

def build_model_details_html(model_data):
    if not model_data or "id" not in model_data:
        return "<div>Empty or invalid model data.</div>"

    model_id = model_data.get("id", "")
    title = model_data.get("title", "Unknown Title")
    desc = model_data.get("description", "No description available.")
    model_type = model_data.get("type", "Unknown Type")
    tags = model_data.get("tags", [])
    uploader = model_data.get("uploader", {})
    versions = model_data.get("versions", [])

    gallery_resp = api.get_model_gallery(model_id)
    gallery_items = gallery_resp.get("data", []) or []
    if not gallery_items:
        pinned = model_data.get("pinnedImages", [])
        if pinned:
            gallery_items = pinned
    if not gallery_items and versions:
        all_ver_imgs = []
        for v in versions:
            if "images" in v:
                all_ver_imgs.extend(v["images"])
        if all_ver_imgs:
            gallery_items = all_ver_imgs

    html = """
<div class='arcen_model_detail_container' style='display:flex; gap:1em;'>
  <div style='flex:1; min-width:300px;'>
"""
    html += f"<h2>{title} (ID: {model_id})</h2>"
    html += f"<div>Type: {model_type}</div>"

    if tags:
        tag_str = ", ".join(t.get("name", "???") for t in tags)
        html += f"<div>Tags: {tag_str}</div>"

    uname = uploader.get("username", "N/A")
    html += f"<div>Uploader: {uname}</div>"
    html += f"<div class='model_description'><p>{desc}</p></div>"

    # Gallery
    html += "<h3>Gallery</h3><div class='arcen_model_gallery'>"
    if not gallery_items:
        html += "<div>No gallery images found.</div>"
    else:
        for img_item in gallery_items:
            img_id = img_item.get("id", "")
            file_path = (img_item.get("filePath") or "").lstrip("/")
            file_base, _ = os.path.splitext(file_path.lstrip("/"))
            img_url = f"https://arcenciel.io/uploads//{file_base}.thumbnail.webp" if file_path else PLACEHOLDER_IMG
            html += f"""
            <div class='arcen_gallery_item' data-image-id="{img_id}" style="cursor:pointer;">
              <img src='{img_url}' alt='gallery item' style="max-width:100px;"/>
            </div>
            """
    html += "</div>"

    # Versions
    html += "<h3>Versions</h3>"
    if not versions:
        html += "<div>No versions found for this model.</div>"
    else:
        for ver in versions:
            v_id = ver.get("id", "")
            v_name = ver.get("versionName", "Unnamed version")
            about = ver.get("aboutThisVersion", "")
            base_model = ver.get("baseModel", "Unknown base")
            activation_tags = ver.get("activationTags", [])
            file_name = ver.get("fileName", "")
            external_url = ver.get("externalDownloadUrl")

            # direct_link logic
            if external_url:
                direct_link = external_url
            else:
                direct_link = f"https://arcenciel.io/api/models/{model_id}/versions/{v_id}/download"

            if not file_name:
                if external_url:
                    import urllib.parse
                    last_segment = external_url.rsplit('/', 1)[-1]
                    last_segment = last_segment.split('?')[0]
                    file_name = urllib.parse.unquote(last_segment)
                if not file_name:
                    file_name = "Unknown file"

            html += "<div class='version_block' style='margin-bottom:1em; border:1px solid #444; padding:0.5em'>"
            html += f"<b>Version ID:</b> {v_id} | <b>Name:</b> {v_name}<br/>"
            html += f"<b>Base Model:</b> {base_model}<br/>"

            if activation_tags:
                triggers = ", ".join(activation_tags)
                html += f"<b>Trigger Words:</b> {triggers}<br/>"
            if about:
                html += f"<div><b>Notes:</b> {about}</div>"

            # Download (Browser) anchor
            html += f"""
            <a 
            href="{direct_link}" 
            target="_blank" 
            class="arcen_extension_download_btn" 
            style="margin-top:0.5em;">
                Download (Browser)
            </a>
            """

            # Download with Extension button
            html += f"""
            <button 
            class='arcen_extension_download_btn' 
            data-model-id="{model_id}"
            data-version-id="{v_id}"
            data-model-type="{model_type}"
            data-download-url="{direct_link}"
            data-file-name="{file_name}"
            style="margin-top:0.5em;">
                Download with Extension
            </button>
            """

            html += "</div>"

    # Right column placeholder for gallery image details
    html += """
  </div>
  <div style='flex:1; min-width:300px;' id='arcen_image_details_panel'>
    <div style='padding:0.5em; border:1px solid #444;'>
      <i>Select an image to see details here.</i>
    </div>
  </div>
</div>
    """
    return html

def build_gallery_html(data_list, total_pages=1, card_scale=30):
    """
    card_scale is in 'em'. We'll do height ~1.5 * width to keep 2:3 ratio.
    """
    width_em = card_scale
    height_em = round(card_scale * 1.5)

    style_override = f"""
<style>
.arcen_model_card {{
    position: relative;
    width: {width_em}em;
    height: {height_em}em;
    background: #333;
    border-radius: 8px;
    color: #fafafa;
    overflow: hidden;
    cursor: pointer;
    text-align: center;
    transition: transform 0.2s;
    box-sizing: border-box;
}}
</style>
"""
    html = style_override
    html += f"<div>Total pages: {total_pages}</div>"
    html += "<div class='arcen_model_list'>"

    for item in data_list:
        m_id = item.get("id", "N/A")
        title = item.get("title", "Untitled")
        type_ = item.get("type", "UNKNOWN")
        preview_url = item.get("preview_local") or PLACEHOLDER_IMG

        html += f"""
          <div class='arcen_model_card' data-model-id="{m_id}">
            <img class='model-bg' src="{preview_url}" alt="Preview" />
            <div class='model-info'>
              <b>{title}</b><br/>
              Type: {type_}<br/>
              ID: {m_id}
            </div>
          </div>
        """
    html += "</div>"
    return html

def do_search_and_download(query, sort_value, page, base_model, model_type, card_scale, model_limit):
    try:
        page_int = int(page)
    except:
        page_int = 1

    if base_model == "Any":
        base_model = ""
    if model_type == "Any":
        model_type = ""

    resp = api.search_models(
        search_term=query,
        sort=sort_value,
        page=page_int,
        limit=model_limit,
        base_model=base_model,
        model_type=model_type
    )
    if "data" not in resp or not resp["data"]:
        yield "<div>API error or empty data</div>"
        return

    data_list = resp["data"]
    id_to_item = {}
    for item in data_list:
        item["preview_local"] = None
        id_to_item[item["id"]] = item

    total_pages = resp.get("totalPages", 1)
    yield build_gallery_html(data_list, total_pages, card_scale)

    # Parallel downloads of previews
    unfinished = set()
    for item in data_list:
        m_id = item["id"]
        fut = gl.executor.submit(api.download_preview_image, item)
        unfinished.add((m_id, fut))

    import time
    while unfinished:
        done_this_round = []
        for (m_id, fut) in list(unfinished):
            if fut.done():
                data_url = fut.result()
                if data_url:
                    id_to_item[m_id]["preview_local"] = data_url
                done_this_round.append((m_id, fut))

        if done_this_round:
            for pair in done_this_round:
                unfinished.remove(pair)
            yield build_gallery_html(data_list, total_pages, card_scale)

        if unfinished:
            time.sleep(0.25)

def save_paths_ui(lora_path, checkpoint_path, vae_path, embedding_path, segmentation_path, other_path):
    kwargs = {
        "LORA": lora_path,
        "CHECKPOINT": checkpoint_path,
        "VAE": vae_path,
        "EMBEDDING": embedding_path,
        "SEGMENTATION": segmentation_path,
        "OTHER": other_path,
    }
    msg = path_utils.save_paths(**kwargs)
    return msg

def on_ui_tabs():
    global already_created_tab

    if not already_created_tab:
        print("[ArcEnCiel] on_ui_tabs() called first time...")
        already_created_tab = True
    else:
        print("[ArcEnCiel] on_ui_tabs() called AGAIN, skipping duplicate UI mention...")

    port = shared.cmd_opts.port or 7860
    base_url = f"http://127.0.0.1:{port}"
    ping_url = f"{base_url}/arcenciel/ping"

    try:
        r = requests.get(ping_url, timeout=2)
        if r.status_code == 200:
            print("[ArcEnCiel] /arcenciel/ping => OK, routes exist.")
        else:
            raise RuntimeError(f"Ping responded with {r.status_code}")
    except Exception as e:
        print(f"[ArcEnCiel] /arcenciel/ping failed => re-registering routes. Error: {e}")
        server.route_registered = False
        server.ensure_server_routes

    # Load path presets
    path_presets = path_utils.load_paths()
    print("[ArcEnCiel] loaded path_presets:", path_presets)

    with gr.Blocks(elem_id="arcencielTab") as arcenciel_interface:
        gr.Markdown("## ArcEnCiel Browser (Parallel Download)")

        with gr.Row():
            search_term = gr.Textbox(label="Search models", placeholder="Enter query...")
            page_box = gr.Number(label="Page #", value=1, precision=0)
            sort_box = gr.Dropdown(label="Sort", choices=["newest", "oldest"], value="newest")
            base_model_box = gr.Dropdown(
                label="Base Model",
                choices=[
                    "Any",
                    "Illustrious",
                    "NoobAI Eps",
                    "NoobAI V-Pred",
                    "Pony",
                    "Flux.1 D",
                    "Flux.1 S",
                    "SDXL 1.0",
                    "SD1.5"
                ],
                value="Any"
            )
            model_type_box = gr.Dropdown(
                label="Model Type",
                choices=[
                    "Any",
                    "LORA",
                    "CHECKPOINT",
                    "VAE",
                    "EMBEDDING",
                    "SEGMENTATION",
                    "OTHER"
                ],
                value="Any"
            )

            # The "gear" icon
            settings_button = gr.HTML(
                """<button id="arcenciel_settings_button" 
                           style="font-size:1.2em; margin-top:22px; cursor:pointer;">
                    ⚙️
                   </button>""",
                elem_id="arcenciel_settings_icon"
            )

        # Inject some CSS to style the popup
        gr.HTML("""
        <style>
        #arcenciel_settings_popup {
            display: none;  /* hidden by default */
            position: absolute;
            top: 60px;      /* adjust as needed */
            right: 10px;
            padding: 1em;
            background: #222;
            border: 1px solid #555;
            border-radius: 8px;
            z-index: 999;
            width: 280px;   /* optional width */
        }
        </style>
        """, elem_id="arcenciel_settings_popup_style_inject")

        # A Group that becomes our "popup" container
        with gr.Group(elem_id="arcenciel_settings_popup", visible=True):
            gr.Markdown("**Settings**", elem_id="arcen_settings_title")
            card_scale_slider = gr.Slider(
                label="Model Card Width (em)",
                minimum=5, maximum=50, step=1, value=30,
                elem_id="arcenciel_card_scale_slider"
            )
            model_limit_slider = gr.Slider(
                label="Models per Page",
                minimum=1, maximum=20, step=1, value=8
            )

        fetch_download_btn = gr.Button("Search & Download")

        results_html = gr.HTML("<div style='text-align:center;'>No results yet</div>",
                               elem_id="arcenciel_results_html")
        model_details_html = gr.HTML("<div>Select a card to see model details</div>",
                                     elem_id="arcenciel_model_details_html")

        # Hook up the search function
        fetch_download_btn.click(
            fn=do_search_and_download,
            inputs=[
                search_term, sort_box, page_box,
                base_model_box, model_type_box,
                card_scale_slider, model_limit_slider
            ],
            outputs=[results_html],
            queue=True
        )

        # Path Presets
        with gr.Accordion("Path Presets (for future downloads)", open=False):
            gr.Markdown("Here you can set default download paths for each model type. "
                        "They will be saved in 'save_paths.txt' so they persist across restarts.")

            lora_t = gr.Textbox(label="LORA path", value=path_presets["LORA"])
            cpt_t = gr.Textbox(label="CHECKPOINT path", value=path_presets["CHECKPOINT"])
            vae_t = gr.Textbox(label="VAE path", value=path_presets["VAE"])
            emb_t = gr.Textbox(label="EMBEDDING path", value=path_presets["EMBEDDING"])
            seg_t = gr.Textbox(label="SEGMENTATION path", value=path_presets["SEGMENTATION"])
            oth_t = gr.Textbox(label="OTHER path", value=path_presets["OTHER"])

            arcenciel_interface.load(
                fn=get_paths_for_ui,
                inputs=[],
                outputs=[lora_t, cpt_t, vae_t, emb_t, seg_t, oth_t]
            )

            save_paths_btn = gr.Button("Save Paths")
            save_status = gr.Textbox(label="Save status", value="", interactive=False)

            save_paths_btn.click(
                fn=save_paths_ui,
                inputs=[lora_t, cpt_t, vae_t, emb_t, seg_t, oth_t],
                outputs=[save_status],
                queue=False
            )

    arcenciel_interface.queue(concurrency_count=4, max_size=16)
    return [(arcenciel_interface, "ArcEnCiel Browser", "arcenciel_tab")]

import gradio as gr
import time
import requests
from modules import shared
import os

import scripts.arcenciel_api as api
import scripts.arcenciel_global as gl
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_server as server
from scripts.arcenciel_paths import get_paths_for_ui
from scripts.arcenciel_utilities import add_utilities_subtab

PLACEHOLDER_IMG = "https://via.placeholder.com/150"

already_created_tab = False


##########################
# Gather Subfolders
##########################

def gather_subfolders_recursively(base_dir):
    """
    Recursively collect all subfolder paths *relative* to base_dir.
    Returns a list of subfolder strings like "myfolder/sub1", "myfolder/sub1/sub2", etc.
    Skips the base_dir itself.
    """
    subfolders = []
    for root, dirs, files in os.walk(base_dir):
        # root is an absolute path, but we want relative path from base_dir
        rel_root = os.path.relpath(root, base_dir)
        # If rel_root == ".", it's the base dir
        if rel_root != ".":
            # Add this subfolder to the list
            subfolders.append(rel_root.replace("\\", "/"))  # ensure forward slashes

        # The 'dirs' list is updated in-place if we wanted to skip certain folders
        # but we'll just let it go.

    # Sort for consistent order
    subfolders.sort()
    return subfolders

def build_subfolder_input_html(model_type):
    """
    Build an inline HTML snippet: 
    1) A <datalist> that enumerates all subfolders under the path for `model_type`.
    2) An <input type="text" list="..."> that references it.

    If the user picks/enters "myfolder/sub2", we interpret that as a subfolder path relative to the base path for model_type.
    """
    # We map the model_type to the known path from path_utils.load_paths()
    path_presets = path_utils.load_paths()
    # The model_type might be "LORA", "CHECKPOINT", etc. Or "OTHER"
    # We'll uppercase it if needed
    # But your code typically uses uppercase strings for these paths, or you might have to map them.
    # We'll do a simple approach: 
    #   if model_type is "LORA", then path_presets["LORA"]
    #   if "checkpoint" => path_presets["CHECKPOINT"], etc.
    # But you mentioned the model_type is like "LORA" or "CHECKPOINT" in your code. 
    # We'll just do a safe .get(...) approach:
    base_dir = path_presets.get(model_type.upper())
    if not base_dir or not os.path.isdir(base_dir):
        # If path isn't valid, just return a minimal input with no datalist
        return f"""
          <input 
            type="text" 
            class="arcen_subfolder_input" 
            data-model-type="{model_type}"
            placeholder="(No valid path for {model_type}, subfolder disabled)" 
            style="margin-left:0.5em; min-width:120px;"
            disabled
          />
        """

    # Gather subfolders
    subfolders = gather_subfolders_recursively(base_dir)
    # Build <option> lines
    option_lines = ""
    for sf in subfolders:
        # We do <option value="sf" />
        option_lines += f'<option value="{sf}"/>\n'

    # We'll make a unique datalist ID per model_type
    datalist_id = f"arcen_subfolders_{model_type.lower()}"
    html = f"""
    <datalist id="{datalist_id}">
      {option_lines}
    </datalist>
    <input 
      type="text"
      list="{datalist_id}"
      class="arcen_subfolder_input"
      data-model-type="{model_type}"
      placeholder="Subfolder (optional)"
      style="margin-left:0.5em; min-width:120px;"
    />
    """
    return html


##########################
# Utility / HTML Builders
##########################

def build_image_details_html(img_data):
    """
    Renders image details in HTML, including a "Send to txt2img" button 
    that sets prompt, negative prompt, steps, sampler, seed, cfg in the txt2img UI.
    """
    if not img_data or "id" not in img_data:
        return "<div>No image data found.</div>"

    image_id = img_data.get("id", "")
    file_path = (img_data.get("filePath") or "").lstrip("/")
    if file_path:
        full_url = f"https://arcenciel.io/uploads/{file_path}"
    else:
        full_url = PLACEHOLDER_IMG

    prompt = img_data.get("prompt", "") or ""
    neg_prompt = img_data.get("negativePrompt", "") or ""
    sampler = img_data.get("sampler", "") or ""
    seed = img_data.get("seed", "") or ""
    steps = img_data.get("steps", "") or ""
    cfg = img_data.get("cfg", "") or ""

    send_btn_html = f"""
    <button 
      class="arcen_send_to_txt2img_btn"
      style="margin-top:0.5em; padding:0.4em 0.8em; cursor:pointer;"
      data-prompt="{prompt.replace('"','&quot;')}"
      data-neg-prompt="{neg_prompt.replace('"','&quot;')}"
      data-sampler="{sampler}"
      data-seed="{seed}"
      data-steps="{steps}"
      data-cfg="{cfg}"
    >
      Send to txt2img
    </button>
    """

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

          {send_btn_html}
        </div>
      </div>
    </div>
    """
    return html


def build_model_details_html(model_data):
    """
    Renders model details in a 2-column layout with gallery and version info.
    For each version, we add a new input for subfolder selection, inline with
    the two download buttons.
    """
    if not model_data or "id" not in model_data:
        return "<div>Empty or invalid model data.</div>"

    model_id = model_data.get("id", "")
    title = model_data.get("title", "Unknown Title")
    desc = model_data.get("description", "No description available.")
    model_type = model_data.get("type", "Unknown Type")
    tags = model_data.get("tags", [])
    uploader = model_data.get("uploader", {})
    versions = model_data.get("versions", [])

    # Attempt official gallery, fallback to pinned, fallback to version images...
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
        # Prepare subfolder <datalist>/<input> snippet once 
        # for the entire model_type if needed:
        # Actually, each version might be the same model_type. 
        # We'll just build it once per version, or once outside?
        # We'll do it per version for clarity.
        for ver in versions:
            v_id = ver.get("id", "")
            v_name = ver.get("versionName", "Unnamed version")
            about = ver.get("aboutThisVersion", "")
            base_model = ver.get("baseModel", "Unknown base")
            activation_tags = ver.get("activationTags", [])
            file_name = ver.get("fileName", "")
            external_url = ver.get("externalDownloadUrl")

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

            # Start a row containing:
            #   1) Download (Browser) anchor
            #   2) Download with Extension button
            #   3) Subfolder text input (with datalist)
            subfolder_html = build_subfolder_input_html(model_type)  # returns <input> + <datalist>

            html += f"""
            <div style="display:flex; align-items:center; gap:0.6em; margin-top:0.5em;">
            
              <!-- Download (Browser) anchor -->
              <a 
                href="{direct_link}" 
                target="_blank" 
                class="arcen_extension_download_btn" 
                style="margin-top:0.2em;">
                  Download (Browser)
              </a>

              <!-- Download with Extension button -->
              <button 
                class='arcen_extension_download_btn' 
                data-model-id="{model_id}"
                data-version-id="{v_id}"
                data-model-type="{model_type}"
                data-download-url="{direct_link}"
                data-file-name="{file_name}"
                style="margin-top:0.2em;">
                  Download with Extension
              </button>

              <!-- Subfolder combobox -->
              {subfolder_html}
            </div>
            """

            html += "</div>"

    # Right column placeholder
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
    Builds the main search results gallery. 
    """
    html = f"<div>Total pages: {total_pages}</div>"
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


############################
# Search & Download Workflow
############################

def do_search_and_download(query, sort_value, page, base_model, model_type, card_scale, model_limit):
    """
    Called for manual "Search" or after changing pages.
    """
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
    # yield initial HTML
    yield build_gallery_html(data_list, total_pages, card_scale)

    # Download previews in parallel
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


#################################
# Page Up / Page Down Functions
#################################

def prev_page(current_page):
    p = int(current_page)
    if p > 1:
        return p - 1
    return 1

def next_page(current_page):
    return int(current_page) + 1


###################
# Path-saving logic
###################

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


##################################
# Main UI callback
##################################

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

    path_presets = path_utils.load_paths()
    print("[ArcEnCiel] loaded path_presets:", path_presets)

    with gr.Blocks(elem_id="arcencielTab", css="style_html.css") as arcenciel_interface:
        gr.Markdown("## ArcEnCiel Browser (Parallel Download)")

        with gr.Tabs():
            # Sub-tab #1: "Browser"
            with gr.Tab("Browser"):
                with gr.Row():
                    search_term = gr.Textbox(label="Search models", placeholder="Enter query...")
                    page_box = gr.Number(label="Page #", value=1, precision=0)
                    sort_box = gr.Dropdown(label="Sort", choices=["newest", "oldest"], value="newest")
                    base_model_box = gr.Dropdown(
                        label="Base Model",
                        choices=["Any","Illustrious","NoobAI Eps","NoobAI V-Pred",
                                 "Pony","Flux.1 D","Flux.1 S","SDXL 1.0","SD1.5"],
                        value="Any"
                    )
                    model_type_box = gr.Dropdown(
                        label="Model Type",
                        choices=["Any","LORA","CHECKPOINT","VAE","EMBEDDING","SEGMENTATION","OTHER"],
                        value="Any"
                    )
                    settings_button = gr.HTML(
                        """<button id="arcenciel_settings_button" 
                                style="font-size:1.2em; margin-top:22px; cursor:pointer;">
                        ⚙️
                        </button>""",
                        elem_id="arcenciel_settings_icon"
                    )

                with gr.Row(elem_id="arcen_run_row"):
                    prev_btn = gr.Button("Previous Page", elem_id="arcen_prev_btn", variant="secondary")
                    fetch_download_btn = gr.Button("Search", concurrency_limit=20, elem_id="arcen_run_btn")
                    next_btn = gr.Button("Next Page", elem_id="arcen_next_btn", variant="secondary")

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

                results_html = gr.HTML("<div style='text-align:center;'>No results yet</div>",
                                       elem_id="arcenciel_results_html")
                model_details_html = gr.HTML("<div>Select a card to see model details</div>",
                                             elem_id="arcenciel_model_details_html")

                fetch_download_btn.click(
                    fn=do_search_and_download,
                    inputs=[search_term, sort_box, page_box,
                            base_model_box, model_type_box,
                            card_scale_slider, model_limit_slider],
                    outputs=[results_html],
                    queue=True
                )

                prev_btn.click(
                    fn=prev_page,
                    inputs=[page_box],
                    outputs=[page_box]
                ).then(
                    fn=do_search_and_download,
                    inputs=[search_term, sort_box, page_box,
                            base_model_box, model_type_box,
                            card_scale_slider, model_limit_slider],
                    outputs=[results_html],
                    queue=True
                )
                next_btn.click(
                    fn=next_page,
                    inputs=[page_box],
                    outputs=[page_box]
                ).then(
                    fn=do_search_and_download,
                    inputs=[search_term, sort_box, page_box,
                            base_model_box, model_type_box,
                            card_scale_slider, model_limit_slider],
                    outputs=[results_html],
                    queue=True
                )

                with gr.Accordion("Path Presets (for future downloads)", open=False):
                    gr.Markdown("Here you can set default download paths for each model type.")
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

            # Sub-tab #2: "Utilities"
            add_utilities_subtab()  # from your arcenciel_utilities.py

    arcenciel_interface.queue(max_size=100)
    return [(arcenciel_interface, "ArcEnCiel Browser", "arcenciel_tab")]

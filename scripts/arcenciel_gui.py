import gradio as gr
import time
import requests
from modules import shared
import os
import html

import scripts.arcenciel_api as api
import scripts.arcenciel_global as gl
import scripts.arcenciel_inventory as inventory
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_server as server
import scripts.arcenciel_download as dl  # For canceling downloads
from scripts.arcenciel_paths import get_paths_for_ui
from scripts.arcenciel_utilities import add_utilities_subtab

PLACEHOLDER_IMG = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="

already_created_tab = False


def esc(value):
    return html.escape(str(value or ""), quote=False)


def esc_attr(value):
    return html.escape(str(value or ""), quote=True)


def multiline(value):
    return esc(value).replace("\n", "<br/>")


def tag_name(tag):
    if isinstance(tag, dict):
        return tag.get("name") or tag.get("label") or "???"
    return str(tag or "???")


def format_publish_hint(version):
    status = str(version.get("status") or "").strip()
    publish_at = str(version.get("publishAt") or "").strip()
    if status == "SCHEDULED" and publish_at:
        return f"Upcoming / not downloadable yet. Scheduled for {esc(publish_at)}."
    if status:
        return f"Not downloadable yet. Status: {esc(status)}."
    return "Not downloadable yet."


def link_status_html():
    try:
        status = server.link_status()
    except Exception:
        status = {"installed": False, "workerRunning": False}
    if not status.get("installed"):
        return "<div class='arcen_link_status'>ArcEnCiel Link: not detected in this WebUI session.</div>"
    state = "worker running" if status.get("workerRunning") else "detected"
    return f"<div class='arcen_link_status'>ArcEnCiel Link: {esc(state)}.</div>"


##########################
# Gather Subfolders
##########################

def gather_subfolders_recursively(base_dir):
    subfolders = []
    for root, dirs, files in os.walk(base_dir):
        rel_root = os.path.relpath(root, base_dir)
        if rel_root != ".":
            subfolders.append(rel_root.replace("\\", "/"))
    subfolders.sort()
    return subfolders

def build_subfolder_input_html(model_type):
    path_presets = path_utils.load_paths()
    base_dir = path_presets.get(model_type.upper())
    if not base_dir or not os.path.isdir(base_dir):
        return f"""
          <input
            type="text"
            class="arcen_subfolder_input"
            data-model-type="{esc_attr(model_type)}"
            placeholder="No valid path for {esc_attr(model_type)}, subfolder disabled"
            style="margin-left:0.5em; min-width:120px;"
            disabled
          />
        """

    datalist_id = f"arcen_subfolders_{esc_attr(model_type.lower())}"
    html = f"""
    <datalist id="{datalist_id}" data-loaded="false"></datalist>
    <input
      type="text"
      list="{datalist_id}"
      class="arcen_subfolder_input"
      data-model-type="{esc_attr(model_type)}"
      placeholder="Subfolder (optional)"
      style="margin-left:0.5em; min-width:120px;"
    />
    """
    return html

##########################
# Utility / HTML Builders
##########################

def build_image_details_html(img_data):
    if not img_data or "id" not in img_data:
        return "<div>No image data found.</div>"

    image_id = img_data.get("id", "")
    full_url = api.get_image_url(img_data, prefer="detail") or PLACEHOLDER_IMG

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
      data-prompt="{esc_attr(prompt)}"
      data-neg-prompt="{esc_attr(neg_prompt)}"
      data-sampler="{esc_attr(sampler)}"
      data-seed="{esc_attr(seed)}"
      data-steps="{esc_attr(steps)}"
      data-cfg="{esc_attr(cfg)}"
    >
      Send to txt2img
    </button>
    """

    html = f"""
    <div style="padding:1em;">
      <h3>Image ID: {esc(image_id)}</h3>
      <div style="display:flex; gap:1em;">
        <div style="flex:1; min-width:200px;">
          <img src="{esc_attr(full_url)}" style="max-width:100%; border:1px solid #444;"/>
        </div>
        <div style="flex:1; min-width:200px;">
          <div><b>Prompt:</b><br/>{multiline(prompt)}</div>
          <div style="margin-top:0.5em;"><b>Negative Prompt:</b><br/>{multiline(neg_prompt)}</div>
          <div style="margin-top:0.5em;"><b>Sampler:</b> {esc(sampler)}</div>
          <div style="margin-top:0.5em;"><b>Seed:</b> {esc(seed)}</div>
          <div style="margin-top:0.5em;"><b>Steps:</b> {esc(steps)}</div>
          <div style="margin-top:0.5em;"><b>CFG:</b> {esc(cfg)}</div>

          {send_btn_html}
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
    gallery_items = api.normalize_gallery_items(gallery_resp)
    if not gallery_items:
        pinned = [api.unwrap_media_item(item) for item in model_data.get("pinnedImages", [])]
        if pinned:
            gallery_items = pinned
    if not gallery_items and versions:
        all_ver_imgs = []
        for v in versions:
            if "images" in v:
                all_ver_imgs.extend(api.unwrap_media_item(item) for item in v["images"])
        if all_ver_imgs:
            gallery_items = all_ver_imgs

    html = """
<div class='arcen_model_detail_container' style='display:flex; gap:1em;'>
  <div style='flex:1; min-width:300px;'>
"""
    html += f"<h2>{esc(title)} (ID: {esc(model_id)})</h2>"
    html += f"<div>Type: {esc(model_type)}</div>"

    if tags:
        tag_str = ", ".join(esc(tag_name(t)) for t in tags)
        html += f"<div>Tags: {tag_str}</div>"

    uname = uploader.get("username", "N/A")
    html += f"<div>Uploader: {esc(uname)}</div>"
    html += f"<div class='model_description'><p>{multiline(desc)}</p></div>"

    # Gallery
    html += "<h3>Gallery</h3><div class='arcen_model_gallery'>"
    if not gallery_items:
        html += "<div>No gallery images found.</div>"
    else:
        for img_item in gallery_items:
            img_id = img_item.get("id", "")
            img_url = api.get_image_url(img_item, prefer="thumb") or PLACEHOLDER_IMG
            html += f"""
            <div class='arcen_gallery_item' data-image-id="{esc_attr(img_id)}" style="cursor:pointer;">
              <img src='{esc_attr(img_url)}' alt='gallery item' style="max-width:100px;"/>
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
            file_name = api.version_file_name(ver)
            direct_link = api.version_download_url(model_id, ver)
            is_downloadable = api.version_is_downloadable(ver) and bool(direct_link)
            installed_path = inventory.find_installed_by_hashes(inventory.version_hashes(ver))

            html += "<div class='version_block' style='margin-bottom:1em; border:1px solid #444; padding:0.5em'>"
            html += f"<b>Version ID:</b> {esc(v_id)} | <b>Name:</b> {esc(v_name)}<br/>"
            html += f"<b>Base Model:</b> {esc(base_model)}<br/>"
            if installed_path:
                html += f"<div class='arcen_installed_notice'>Installed: {esc(installed_path)}</div>"

            if activation_tags:
                triggers = ", ".join(esc(tag) for tag in activation_tags)
                html += f"<b>Trigger Words:</b> {triggers}<br/>"
            if about:
                html += f"<div><b>Notes:</b> {multiline(about)}</div>"

            if is_downloadable:
                subfolder_html = build_subfolder_input_html(model_type)
                display_name = file_name or "ArcEnCiel-download"
                extension_button = f"""
                  <button
                    class='arcen_extension_download_btn'
                    data-model-id="{esc_attr(model_id)}"
                    data-version-id="{esc_attr(v_id)}"
                    data-model-type="{esc_attr(model_type)}"
                    data-download-url="{esc_attr(direct_link)}"
                    data-file-name="{esc_attr(display_name)}"
                    style="margin-top:0.2em;">
                      Download with Extension
                  </button>
                """
                if installed_path:
                    extension_button = """
                  <button
                    class='arcen_extension_download_btn'
                    disabled
                    style="margin-top:0.2em;">
                      Already installed
                  </button>
                """
                html += f"""
                <div style="display:flex; align-items:center; gap:0.6em; margin-top:0.5em; flex-wrap:wrap;">
                  <a
                    href="{esc_attr(direct_link)}"
                    target="_blank"
                    class="arcen_browser_download_btn"
                    style="margin-top:0.2em;">
                      Download (Browser)
                  </a>

                  {extension_button}

                  {subfolder_html}
                  <span class="arcen_download_status" aria-live="polite"></span>
                </div>
                """
            else:
                html += f"""
                <div class="arcen_upcoming_notice" style="margin-top:0.5em; color:#f0c36d;">
                  {format_publish_hint(ver)}
                </div>
                """

            html += "</div>"

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
    html = f"<div>Total pages: {esc(total_pages)}</div>"
    html += "<div class='arcen_model_list'>"

    for item in data_list:
        m_id = item.get("id", "N/A")
        title = item.get("title", "Untitled")
        type_ = item.get("type", "UNKNOWN")
        preview_url = item.get("preview_local") or PLACEHOLDER_IMG
        install_state = inventory.model_install_state(item)
        badge_html = ""
        if install_state == "installed":
            badge_html = "<div class='arcen_card_badge installed'>Installed</div>"
        elif install_state == "partial":
            badge_html = "<div class='arcen_card_badge partial'>Partial</div>"

        html += f"""
          <div class='arcen_model_card' data-model-id="{esc_attr(m_id)}">
            <img class='model-bg' src="{esc_attr(preview_url)}" alt="Preview" />
            {badge_html}
            <div class='model-info'>
              <b>{esc(title)}</b><br/>
              Type: {esc(type_)}<br/>
              ID: {esc(m_id)}
            </div>
          </div>
        """
    html += "</div>"
    return html

############################
# Search & Download Workflow
############################

def do_search_and_download(query, sort_value, page, base_model, model_type, card_scale, model_limit):
    try:
        page_int = int(page)
    except Exception:
        page_int = 1
    try:
        limit_int = max(1, int(model_limit))
    except Exception:
        limit_int = 8

    if base_model == "Any":
        base_model = ""
    if model_type == "Any":
        model_type = ""

    resp = api.search_models(
        search_term=query,
        sort=sort_value,
        page=page_int,
        limit=limit_int,
        base_model=base_model,
        model_type=model_type
    )
    if "data" not in resp or not resp["data"]:
        error = resp.get("error") if isinstance(resp, dict) else ""
        yield f"<div>{esc(error) if error else 'No models found.'}</div>"
        return

    data_list = resp["data"]
    id_to_item = {}
    for item in data_list:
        item["preview_local"] = None
        id_to_item[item["id"]] = item

    total_pages = resp.get("totalPages", 1)
    yield build_gallery_html(data_list, total_pages, card_scale)

    # parallel preview downloads
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
                try:
                    data_url = fut.result()
                except Exception as e:
                    gl.debug_print("Preview download failed:", e)
                    data_url = None
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
# Cancel downloads
##################################

def cancel_downloads_ui():
    """
    A simple Gradio callback function that calls dl.cancel_all_downloads().
    Returns a message string for the UI.
    """
    dl.cancel_all_downloads()
    return "All queued (and ongoing) downloads have been canceled."

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
        if not server.ensure_server_routes_on_last_app():
            print("[ArcEnCiel] no FastAPI app available yet; app_started will register routes.")

    path_presets = path_utils.load_paths()
    base_model_choices = api.get_base_model_choices()
    print("[ArcEnCiel] loaded path_presets:", path_presets)

    with gr.Blocks(elem_id="arcencielTab", css="style_html.css") as arcenciel_interface:
        gr.Markdown("## ArcEnCiel Browser (Parallel Download)")
        link_status = gr.HTML(link_status_html(), elem_id="arcenciel_link_status")
        arcenciel_interface.load(fn=link_status_html, inputs=[], outputs=[link_status])

        with gr.Tabs():
            # Sub-tab #1: "Browser"
            with gr.Tab("Browser"):
                # Row of main controls: search, page, sort, base_model, etc.
                with gr.Row():
                    search_term = gr.Textbox(label="Search models", placeholder="Enter query...")
                    page_box = gr.Number(label="Page #", value=1, precision=0)
                    sort_box = gr.Dropdown(label="Sort", choices=["newest", "oldest"], value="newest")
                    base_model_box = gr.Dropdown(
                        label="Base Model",
                        choices=base_model_choices,
                        value="Any"
                    )
                    model_type_box = gr.Dropdown(
                        label="Model Type",
                        choices=["Any","LORA","CHECKPOINT","VAE","EMBEDDING","SEGMENTATION","OTHER"],
                        value="Any"
                    )

                    # Cancel All Downloads button
                    cancel_btn = gr.Button(
                        value="Cancel All Downloads",
                        variant="stop",  # "stop" or "danger"
                        elem_id="arcenciel_cancel_downloads_btn",
                        # style as you like, or rely on default
                    )
                    settings_button = gr.HTML(
                        """<button id="arcenciel_settings_button"
                                style="font-size:1.2em; margin-top:6px; cursor:pointer;">
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

                # Cancel output label
                cancel_status_label = gr.Textbox(label="Cancel Status", value="", interactive=False)

                # Search button => do_search_and_download
                fetch_download_btn.click(
                    fn=do_search_and_download,
                    inputs=[search_term, sort_box, page_box,
                            base_model_box, model_type_box,
                            card_scale_slider, model_limit_slider],
                    outputs=[results_html],
                    queue=True
                )

                # Prev => do_search
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

                # Next => do_search
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

                # Cancel downloads => calls cancel_downloads_ui
                cancel_status_label = gr.Textbox(
                    label="Cancel Status",
                    value="",
                    interactive=False
                )
                cancel_btn.click(
                    fn=cancel_downloads_ui,
                    inputs=[],
                    outputs=[cancel_status_label],
                    queue=False
                )

                # Path Presets accordion
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
            add_utilities_subtab()

    arcenciel_interface.queue(max_size=100)
    return [(arcenciel_interface, "ArcEnCiel Browser", "arcenciel_tab")]

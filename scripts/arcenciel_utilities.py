import os
import re
import json
import base64
import html
import gradio as gr
from bs4 import BeautifulSoup
from modules.hashes import calculate_sha256

import scripts.arcenciel_api as api
import scripts.arcenciel_inventory as inventory
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_sidecars as sidecars


def esc(value):
    return html.escape(str(value or ""), quote=False)


def clean_description(desc: str) -> str:
    """
    Gracefully convert HTML/Markdown-like description into readable plain text,
    preserving paragraphs and spacing via BeautifulSoup.
    """
    if not desc:
        return ""

    soup = BeautifulSoup(desc, "html.parser")
    text = soup.get_text("\n")  # block elements => newlines

    # Condense multiple blank lines into one
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


def gather_files_recursive(dir_path, exts):
    """
    Recursively scan 'dir_path' for files whose extension is in 'exts'
    and return a list of full file paths.
    """
    matched = []
    for root, dirs, files in os.walk(dir_path):
        for fname in files:
            if fname.lower().endswith(exts):
                matched.append(os.path.join(root, fname))
    return matched


def create_jsons_for_models(
    lora_sel, cpt_sel, vae_sel, emb_sel, seg_sel, oth_sel,
    overwrite_json, download_preview
):
    """
    Generator function that:
      - Loads path presets, scans selected dirs (recursively) for model files.
      - For each file:
         * If user wants JSON and none exists (or Overwrite is on), create/update JSON.
         * If user wants preview image and none exists, download it.
         * If both are satisfied already, skip the file.
      - Yields streaming progress lines to a Gradio HTML component.
    """

    paths_dict = path_utils.load_paths()

    # Determine which categories are selected
    selected_keys = []
    if lora_sel: selected_keys.append("LORA")
    if cpt_sel:  selected_keys.append("CHECKPOINT")
    if vae_sel:  selected_keys.append("VAE")
    if emb_sel:  selected_keys.append("EMBEDDING")
    if seg_sel:  selected_keys.append("SEGMENTATION")
    if oth_sel:  selected_keys.append("OTHER")

    if not selected_keys:
        yield "<p style='color:red;'>No categories selected. Aborting.</p>"
        return

    # Recursively gather model files
    exts = (".safetensors", ".ckpt", ".bin", ".pt")
    model_files = []
    for key in selected_keys:
        p = paths_dict.get(key)
        if not p or not os.path.isdir(p):
            yield f"<p style='color:orange;'>Path for {esc(key)} is not set or invalid: {esc(p)}</p>"
            continue
        model_files.extend(gather_files_recursive(p, exts))

    total_count = len(model_files)
    if total_count == 0:
        yield "<p>No model files found in the selected categories.</p>"
        return

    yield f"<p>Found {total_count} model files. Beginning checks...</p>"

    for idx, fpath in enumerate(model_files, start=1):
        fname = os.path.basename(fpath)
        yield f"<p>[{idx}/{total_count}] Checking: {esc(fname)}</p>"

        base_no_ext, _ = os.path.splitext(fpath)
        json_path = base_no_ext + ".json"
        preview_path = base_no_ext + ".png"

        need_json = overwrite_json or not os.path.exists(json_path)
        need_preview = download_preview and not os.path.exists(preview_path)

        if not need_json and not need_preview:
            yield f"<p style='color:blue;'>Nothing to do for {esc(fname)}, skipping.</p>"
            continue

        try:
            sha_val = calculate_sha256(fpath)
        except Exception as e:
            yield f"<p style='color:red;'>Error hashing {esc(fname)}: {esc(e)}</p>"
            continue

        resp = api.search_models(search_term=sha_val, limit=5)
        if not resp or "data" not in resp or not resp["data"]:
            yield f"<p>No ArcEnCiel match => skipping {esc(fname)}.</p>"
            continue

        matched_model = None
        matched_version = None
        for m in resp["data"]:
            for ver in m.get("versions", []):
                if ver.get("sha256") == sha_val or ver.get("sha256webui") == sha_val:
                    matched_model = m
                    matched_version = ver
                    break
            if matched_model:
                break

        if not matched_model or not matched_version:
            yield f"<p>Found models, but none had a matching version => skipping {esc(fname)}.</p>"
            continue

        try:
            sidecars.write_sidecars(
                matched_model,
                matched_version,
                fpath,
                sha_local=sha_val,
                download_preview=need_preview,
            )
            inventory.update_cached_hash(fpath, sha_val)
            if need_json:
                yield f"<p style='color:green;'>Wrote JSON/info sidecars => {esc(os.path.basename(json_path))}</p>"
            if need_preview:
                yield f"<p style='color:green;'>Downloaded preview sidecar for {esc(fname)}.</p>"
        except Exception as e:
            yield f"<p style='color:red;'>Error writing sidecars for {esc(fname)}: {esc(e)}</p>"

    yield "<p>Done processing all models in selected categories.</p>"


def scan_inventory_ui():
    try:
        result = inventory.scan_inventory()
        return (
            f"<p style='color:green;'>Inventory scan complete: "
            f"{esc(result.get('files'))} files, {esc(result.get('hashes'))} hashes.</p>"
        )
    except Exception as e:
        return f"<p style='color:red;'>Inventory scan failed: {esc(e)}</p>"


def add_utilities_subtab():
    """
    Creates the 'Utilities' sub-tab for ArcEnCiel, with a 3-column layout:
      - Column A: Create JSON for models
      - Column B/C: placeholders
    """
    with gr.Tab("Utilities"):
        gr.Markdown("### ArcEnCiel Utilities")

        with gr.Row():
            # Column A: Main utility
            with gr.Box():
                gr.Markdown("**Create JSON for Models**")
                gr.Markdown("Select which categories to process:")
                with gr.Row():
                    check_lora = gr.Checkbox(value=True, label="LORA")
                    check_cpt = gr.Checkbox(value=True, label="CHECKPOINT")
                    check_vae = gr.Checkbox(value=True, label="VAE")
                    check_emb = gr.Checkbox(value=True, label="EMBEDDING")
                    check_seg = gr.Checkbox(value=True, label="SEGMENTATION")
                    check_oth = gr.Checkbox(value=True, label="OTHER")

                gr.Markdown("Additional Options:")
                with gr.Row():
                    check_overwrite = gr.Checkbox(value=False, label="Overwrite existing JSON")
                    check_download_preview = gr.Checkbox(value=False, label="Download preview image")

                generate_json_btn = gr.Button("Create JSON for Models")
                scan_inventory_btn = gr.Button("Scan Installed Models")
                progress_html = gr.HTML(
                    "No progress yet.",
                    elem_id="arcenciel_utilities_progress"
                )

                generate_json_btn.click(
                    fn=create_jsons_for_models,
                    inputs=[
                        check_lora,
                        check_cpt,
                        check_vae,
                        check_emb,
                        check_seg,
                        check_oth,
                        check_overwrite,
                        check_download_preview
                    ],
                    outputs=[progress_html],
                    queue=True
                )
                scan_inventory_btn.click(
                    fn=scan_inventory_ui,
                    inputs=[],
                    outputs=[progress_html],
                    queue=True
                )

            # Column B: Placeholder
            with gr.Box():
                gr.Markdown("**Placeholder #2**")
                gr.Markdown("Add future utilities here...")

            # Column C: Placeholder
            with gr.Box():
                gr.Markdown("**Placeholder #3**")
                gr.Markdown("Add future utilities here as well...")

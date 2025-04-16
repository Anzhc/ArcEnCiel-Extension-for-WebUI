import os
import re
import json
import base64
import gradio as gr
from bs4 import BeautifulSoup
from modules.hashes import calculate_sha256

import scripts.arcenciel_api as api
import scripts.arcenciel_paths as path_utils
import scripts.arcenciel_global as gl

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
                fpath = os.path.join(root, fname)
                matched.append(fpath)
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

    # We gather model files by scanning each directory (and its subfolders) 
    # for recognized file extensions.
    exts = (".safetensors", ".ckpt", ".bin", ".pt")
    model_files = []
    for key in selected_keys:
        p = paths_dict.get(key)
        if not p or not os.path.isdir(p):
            yield f"<p style='color:orange;'>Path for {key} is not set or invalid: {p}</p>"
            continue

        # Recursively gather .safetensors, .ckpt, .bin, .pt
        found_in_path = gather_files_recursive(p, exts)
        model_files.extend(found_in_path)

    total_count = len(model_files)
    if total_count == 0:
        yield "<p>No model files found in the selected categories.</p>"
        return

    yield f"<p>Found {total_count} model files. Beginning checks...</p>"

    for idx, fpath in enumerate(model_files, start=1):
        fname = os.path.basename(fpath)
        yield f"<p>[{idx}/{total_count}] Checking: {fname}</p>"

        # Determine if we need JSON or preview
        base_no_ext, _ = os.path.splitext(fpath)
        json_path = base_no_ext + ".json"
        preview_path = base_no_ext + ".png"

        # Do we need to create or overwrite JSON?
        need_json = False
        if overwrite_json:
            need_json = True
        else:
            need_json = not os.path.exists(json_path)

        # Do we need to download preview?
        need_preview = (download_preview and not os.path.exists(preview_path))

        # If we need neither, skip
        if not need_json and not need_preview:
            yield f"<p style='color:blue;'>Nothing to do for {fname}, skipping.</p>"
            continue

        # OK, compute SHA + search ArcEnCiel
        try:
            sha_val = calculate_sha256(fpath)
        except Exception as e:
            yield f"<p style='color:red;'>Error hashing {fname}: {e}</p>"
            continue

        resp = api.search_models(search_term=sha_val, limit=5)
        if not resp or "data" not in resp or not resp["data"]:
            yield f"<p>No ArcEnCiel match => skipping {fname}.</p>"
            continue

        # Among returned models, find version with exact matching sha
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
            yield f"<p>Found models, but none had a matching version => skipping {fname}.</p>"
            continue

        # If needed, create/update JSON
        if need_json:
            model_id = matched_model.get("id", 0)
            raw_desc = matched_model.get("description", "No description")
            desc_text = clean_description(raw_desc)

            base_model_str = matched_version.get("baseModel", "Other")
            version_id = matched_version.get("id", 0)
            activation_tags = matched_version.get("activationTags", [])
            activation_text = "\n\n".join(activation_tags)

            json_data = {
                "sha256": sha_val,
                "modelId": model_id,
                "modelVersionId": version_id,
                "activation text": activation_text,
                "description": desc_text,
                "sd version": base_model_str,
            }

            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(json_data, f, indent=2)
                yield f"<p style='color:green;'>Wrote JSON => {os.path.basename(json_path)}</p>"
            except Exception as e:
                yield f"<p style='color:red;'>Error writing JSON {os.path.basename(json_path)}: {e}</p>"

        # If needed, download preview
        if need_preview:
            fake_item = {"versions": [matched_version]}
            data_url = api.download_preview_image(fake_item)
            if data_url:
                try:
                    raw_b64 = data_url.split(",", 1)[1]
                    raw_data = base64.b64decode(raw_b64)
                    with open(preview_path, "wb") as imgf:
                        imgf.write(raw_data)
                    yield f"<p style='color:green;'>Downloaded preview => {os.path.basename(preview_path)}</p>"
                except Exception as e:
                    yield f"<p style='color:red;'>Error saving preview for {fname}: {e}</p>"
            else:
                yield f"<p style='color:orange;'>No preview available for {fname}.</p>"

    yield "<p>Done processing all models in selected categories.</p>"


def add_utilities_subtab():
    """
    Creates the 'Utilities' sub-tab for ArcEnCiel, with a row of 3 columns:

      [Column A]: Our "Create JSON for Models" feature
      [Column B]: Placeholder for future features
      [Column C]: Another placeholder

    Each column is in a 'Box' or 'Group' for visual separation.
    """
    with gr.Tab("Utilities"):
        gr.Markdown("### ArcEnCiel Utilities")

        with gr.Row():
            # Column A: Our main JSON/preview utility
            with gr.Box():
                gr.Markdown("**Create JSON for Models**")

                gr.Markdown("Select which categories to process:")
                with gr.Row():
                    check_lora = gr.Checkbox(value=True,  label="LORA")
                    check_cpt  = gr.Checkbox(value=True,  label="CHECKPOINT")
                    check_vae  = gr.Checkbox(value=True,  label="VAE")
                    check_emb  = gr.Checkbox(value=True,  label="EMBEDDING")
                    check_seg  = gr.Checkbox(value=True,  label="SEGMENTATION")
                    check_oth  = gr.Checkbox(value=True,  label="OTHER")

                gr.Markdown("Additional Options:")
                with gr.Row():
                    check_overwrite = gr.Checkbox(value=False, label="Overwrite existing JSON")
                    check_download_preview = gr.Checkbox(value=False, label="Download preview image")

                generate_json_btn = gr.Button("Create JSON for Models")
                progress_html = gr.HTML("No progress yet.")

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

                # This is where the progress text goes:
                progress_html.style(height=250, overflow="auto")

            # Column B: Placeholder
            with gr.Box():
                gr.Markdown("**Placeholder #2**")
                gr.Markdown("Add future utilities here...")

            # Column C: Placeholder
            with gr.Box():
                gr.Markdown("**Placeholder #3**")
                gr.Markdown("Add future utilities here as well...")

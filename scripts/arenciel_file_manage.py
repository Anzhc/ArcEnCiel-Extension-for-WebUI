# scripts/arcenciel_file_manage.py
import os
import hashlib
import json
import scripts.arcenciel_global as gl

def make_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def gen_sha256(file_path):
    """Compute sha256 of file_path if it exists."""
    sha = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
    except:
        return None

def save_model_info(model_id, version_id, local_json_path, extra_data=None):
    """Store metadata in a local .json sidecar."""
    data = {
        "model_id": model_id,
        "version_id": version_id,
    }
    if extra_data:
        data.update(extra_data)
    try:
        with open(local_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        #gl.debug_print(f"Saved model info: {local_json_path}")
    except Exception as e:
        gl.debug_print(f"Could not save model info: {e}")

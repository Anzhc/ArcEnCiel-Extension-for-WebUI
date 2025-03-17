import os
from pathlib import Path

SAVED_PATHS_FILE = Path(__file__).parent.parent / "save_paths.txt"
# ^ This places save_paths.txt in the extension root folder

# The known model types we want to handle
KNOWN_TYPES = ["LORA", "CHECKPOINT", "VAE", "EMBEDDING", "SEGMENTATION", "OTHER"]

def load_paths():
    """
    Load path presets from save_paths.txt (line-based key=value).
    If file doesn't exist, create it with placeholder paths.
    Return a dict { "LORA": "...", "CHECKPOINT": "...", ... }
    """
    #print("[ArcEnCiel] load_paths() reading from:", SAVED_PATHS_FILE)
    default_dict = {t: f"C:\\myModels\\{t.lower()}" for t in KNOWN_TYPES}
    # This is our fallback if the file doesn't exist or is incomplete

    if not SAVED_PATHS_FILE.exists():
        # Create it with the defaults
        _save_paths(default_dict)
        return default_dict

    # Otherwise, parse the file line by line
    loaded_dict = dict(default_dict)  # start with defaults
    with open(SAVED_PATHS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip().upper()
            val = val.strip()
            if key in KNOWN_TYPES:
                loaded_dict[key] = val
    return loaded_dict

def _save_paths(paths_dict):
    """
    Internal helper that overwrites save_paths.txt with lines in key=value format.
    """
    with open(SAVED_PATHS_FILE, "w", encoding="utf-8") as f:
        for k, v in paths_dict.items():
            f.write(f"{k}={v}\n")

def save_paths(**kwargs):
    """
    Public function for UI usage. The UI will pass each known type's path as argument.
    We gather them into a dict and write them.
    """
    new_paths = {}
    for t in KNOWN_TYPES:
        if t in kwargs:
            new_paths[t] = kwargs[t]
    _save_paths(new_paths)
    return "Paths saved successfully."

def get_paths_for_ui():
    paths = load_paths()
    return (
        paths["LORA"],
        paths["CHECKPOINT"],
        paths["VAE"],
        paths["EMBEDDING"],
        paths["SEGMENTATION"],
        paths["OTHER"],
    )

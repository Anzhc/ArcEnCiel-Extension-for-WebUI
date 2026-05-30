import os
import re
from pathlib import PurePosixPath
from pathlib import Path

SAVED_PATHS_FILE = Path(__file__).parent.parent / "save_paths.txt"
# ^ This places save_paths.txt in the extension root folder

# The known model types we want to handle
KNOWN_TYPES = ["LORA", "CHECKPOINT", "VAE", "EMBEDDING", "SEGMENTATION", "OTHER"]
DEFAULT_RELATIVE_PATHS = {
    "LORA": "models/Lora",
    "CHECKPOINT": "models/Stable-diffusion",
    "VAE": "models/VAE",
    "EMBEDDING": "embeddings",
    "SEGMENTATION": "models/Segmentation",
    "OTHER": "models/ArcEnCiel",
}
_LEGACY_WINDOWS_DEFAULTS = {t: f"C:\\myModels\\{t.lower()}" for t in KNOWN_TYPES}
_SAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f<>:\"|?*]")


def webui_root():
    try:
        from modules import paths_internal

        return Path(paths_internal.script_path).expanduser().resolve()
    except Exception:
        return Path.cwd().expanduser().resolve()


def default_paths(raw=False):
    if raw:
        return dict(DEFAULT_RELATIVE_PATHS)
    root = webui_root()
    return {key: str((root / value).resolve()) for key, value in DEFAULT_RELATIVE_PATHS.items()}


def _is_legacy_windows_placeholder(model_type, value):
    expected = _LEGACY_WINDOWS_DEFAULTS.get(model_type, "")
    return os.name != "nt" and str(value).strip().lower() == expected.lower()


def resolve_path_value(value, model_type=None):
    value = str(value or "").strip()
    defaults = default_paths()
    if not value:
        return defaults.get(model_type, str(webui_root()))
    if model_type and _is_legacy_windows_placeholder(model_type, value):
        return defaults.get(model_type, str(webui_root()))

    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if expanded.is_absolute():
        return str(expanded.resolve())
    return str((webui_root() / expanded).resolve())

def load_paths():
    """
    Load path presets from save_paths.txt (line-based key=value).
    If file doesn't exist, create it with portable WebUI-relative paths.
    Return a dict { "LORA": "...", "CHECKPOINT": "...", ... }
    """
    print("[ArcEnCiel] load_paths() reading from:", SAVED_PATHS_FILE)
    raw_defaults = default_paths(raw=True)

    if not SAVED_PATHS_FILE.exists():
        # Create it with the defaults
        _save_paths(raw_defaults)
        return default_paths()

    # Otherwise, parse the file line by line
    loaded_dict = dict(raw_defaults)  # start with defaults
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
    return {key: resolve_path_value(value, key) for key, value in loaded_dict.items()}

def _save_paths(paths_dict):
    """
    Internal helper that overwrites save_paths.txt with lines in key=value format.
    """
    with open(SAVED_PATHS_FILE, "w", encoding="utf-8") as f:
        for k in KNOWN_TYPES:
            v = paths_dict.get(k, "")
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


def sanitize_subfolder(subfolder):
    raw = str(subfolder or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("Subfolder must be relative.")

    path = PurePosixPath(raw)
    parts = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("Subfolder cannot contain '..'.")
        if _SAFE_FILENAME_CHARS.search(part):
            raise ValueError("Subfolder contains control characters.")
        parts.append(part)
    return "/".join(parts)


def safe_filename(file_name, fallback="ArcEnCiel-download"):
    raw = str(file_name or "").strip().replace("\\", "/")
    name = raw.rsplit("/", 1)[-1]
    name = _SAFE_FILENAME_CHARS.sub("", name).strip()
    if not name or name in (".", ".."):
        name = fallback
    return name[:180]


def resolve_download_path(model_type, file_name, subfolder=""):
    paths = load_paths()
    model_type = str(model_type or "OTHER").upper()
    base_dir = Path(paths.get(model_type) or paths.get("OTHER") or webui_root()).resolve()
    safe_subfolder = sanitize_subfolder(subfolder)
    out_dir = base_dir / safe_subfolder if safe_subfolder else base_dir
    out_dir = out_dir.resolve()

    try:
        out_dir.relative_to(base_dir)
    except ValueError as exc:
        raise ValueError("Download path escapes the configured base directory.") from exc

    return str(out_dir / safe_filename(file_name)), str(out_dir)

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

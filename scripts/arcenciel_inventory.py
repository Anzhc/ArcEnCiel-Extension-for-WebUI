import argparse
import glob
import json
import os
import shlex
import threading
from pathlib import Path

import scripts.arcenciel_paths as path_utils

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_FILE = CACHE_DIR / "hashes.json"
MODEL_EXTS = {".safetensors", ".ckpt", ".pt", ".bin"}
HASH_FIELDS = ("sha256", "sha256webui", "hash")

_CACHE_LOCK = threading.Lock()
_CACHE_DATA = None


def _hash_file(path):
    import hashlib

    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def sha256_of_file(path):
    return _hash_file(path)


def _load_cache():
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_cache(data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _cache():
    global _CACHE_DATA
    if _CACHE_DATA is None:
        _CACHE_DATA = _load_cache()
    return _CACHE_DATA


def _file_signature(path):
    stat = path.stat()
    return {
        "mtime_ns": getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)),
        "size": stat.st_size,
    }


def _commandline_opts():
    opts = {"ckpt_dir": None, "lora_dir": None, "vae_dir": None, "embeddings_dir": None}
    try:
        from modules import shared

        for key in opts:
            value = getattr(shared.cmd_opts, key, None)
            if value:
                opts[key] = value
    except Exception:
        pass

    if not any(opts.values()) and os.getenv("COMMANDLINE_ARGS"):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--ckpt-dir")
        parser.add_argument("--lora-dir")
        parser.add_argument("--vae-dir")
        parser.add_argument("--embeddings-dir")
        args, _ = parser.parse_known_args(shlex.split(os.getenv("COMMANDLINE_ARGS", "")))
        for key, value in vars(args).items():
            if value:
                opts[key] = value
    return opts


def model_dirs():
    paths = path_utils.load_paths()
    opts = _commandline_opts()
    if opts["ckpt_dir"]:
        paths["CHECKPOINT"] = path_utils.resolve_path_value(opts["ckpt_dir"], "CHECKPOINT")
    if opts["lora_dir"]:
        paths["LORA"] = path_utils.resolve_path_value(opts["lora_dir"], "LORA")
    if opts["vae_dir"]:
        paths["VAE"] = path_utils.resolve_path_value(opts["vae_dir"], "VAE")
    if opts["embeddings_dir"]:
        paths["EMBEDDING"] = path_utils.resolve_path_value(opts["embeddings_dir"], "EMBEDDING")
    return {key: Path(value).resolve() for key, value in paths.items() if value}


def _iter_model_files(selected_types=None):
    selected = {str(item).upper() for item in selected_types or [] if item}
    for model_type, root in model_dirs().items():
        if selected and model_type not in selected:
            continue
        if not root.exists():
            continue
        pattern = str(root / "**" / "*")
        for file_name in glob.glob(pattern, recursive=True):
            path = Path(file_name)
            if path.is_file() and path.suffix.lower() in MODEL_EXTS:
                yield model_type, path


def _normalize_hash(value):
    text = str(value or "").strip().lower()
    if len(text) == 64 and all(char in "0123456789abcdef" for char in text):
        return text
    return ""


def version_hashes(version):
    if not isinstance(version, dict):
        return []
    hashes = []
    for field in HASH_FIELDS:
        value = _normalize_hash(version.get(field))
        if value and value not in hashes:
            hashes.append(value)
    nested = version.get("hashes")
    if isinstance(nested, dict):
        for value in nested.values():
            normalized = _normalize_hash(value)
            if normalized and normalized not in hashes:
                hashes.append(normalized)
    return hashes


def get_cached_hashes():
    with _CACHE_LOCK:
        cache = _cache()
        return {
            str(entry.get("hash", "")).lower()
            for entry in cache.values()
            if entry.get("hash")
        }


def get_cached_entries():
    with _CACHE_LOCK:
        return dict(_cache())


def find_installed_by_hashes(hashes):
    wanted = {_normalize_hash(value) for value in hashes}
    wanted.discard("")
    if not wanted:
        return None
    with _CACHE_LOCK:
        for path, entry in _cache().items():
            if str(entry.get("hash", "")).lower() in wanted and Path(path).exists():
                return path
    return None


def is_version_installed(version):
    return bool(find_installed_by_hashes(version_hashes(version)))


def model_install_state(model_item):
    versions = model_item.get("versions") if isinstance(model_item, dict) else []
    if not versions:
        return "unknown"
    downloadable_versions = [v for v in versions if version_hashes(v)]
    if not downloadable_versions:
        return "unknown"
    installed = [is_version_installed(v) for v in downloadable_versions]
    if all(installed):
        return "installed"
    if any(installed):
        return "partial"
    return "missing"


def scan_inventory(selected_types=None):
    scanned = 0
    updated = False
    with _CACHE_LOCK:
        cache = _cache()
        seen_paths = set()
        for _model_type, path in _iter_model_files(selected_types):
            resolved = str(path.resolve())
            seen_paths.add(resolved)
            signature = _file_signature(path)
            entry = cache.get(resolved)
            if (
                entry
                and entry.get("mtime_ns") == signature["mtime_ns"]
                and entry.get("size") == signature["size"]
                and entry.get("hash")
            ):
                scanned += 1
                continue
            digest = _hash_file(path)
            cache[resolved] = {**signature, "hash": digest}
            scanned += 1
            updated = True

        orphaned = [path for path in cache if not Path(path).exists()]
        for path in orphaned:
            del cache[path]
            updated = True
        if updated:
            _save_cache(cache)

        hashes = {
            str(entry.get("hash", "")).lower()
            for entry in cache.values()
            if entry.get("hash")
        }
    return {"files": scanned, "hashes": len(hashes), "cacheFile": str(CACHE_FILE)}


def update_cached_hash(path, hash_value):
    normalized = _normalize_hash(hash_value)
    if not normalized:
        return
    resolved = Path(path).resolve()
    if not resolved.exists():
        return
    signature = _file_signature(resolved)
    with _CACHE_LOCK:
        cache = _cache()
        cache[str(resolved)] = {**signature, "hash": normalized}
        _save_cache(cache)


def list_subfolders_for_model_type(model_type):
    model_type = str(model_type or "OTHER").upper()
    paths = model_dirs()
    root = paths.get(model_type) or paths.get("OTHER")
    if not root or not root.exists():
        return []
    folders = []
    for path in root.rglob("*"):
        if path.is_dir() and not path.name.startswith("."):
            rel = path.relative_to(root).as_posix()
            if rel:
                folders.append(rel)
    return sorted(folders)

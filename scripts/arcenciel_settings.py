import os

try:
    from modules import shared
except Exception:
    shared = None


SECTION = ("arcenciel", "ArcEnCiel")

PATH_OPTION_NAMES = {
    "LORA": "arcenciel_path_lora",
    "CHECKPOINT": "arcenciel_path_checkpoint",
    "VAE": "arcenciel_path_vae",
    "EMBEDDING": "arcenciel_path_embedding",
    "SEGMENTATION": "arcenciel_path_segmentation",
    "OTHER": "arcenciel_path_other",
}

DEFAULTS = {
    "arcenciel_min_free_mb": int(os.getenv("ARCENCIEL_MIN_FREE_MB", "2048")),
    "arcenciel_max_retries": int(os.getenv("ARCENCIEL_MAX_RETRIES", "5")),
    "arcenciel_backoff_base": int(os.getenv("ARCENCIEL_BACKOFF_BASE", "2")),
    "arcenciel_download_preview": True,
    "arcenciel_save_html_preview": False,
    "arcenciel_download_history_limit": 50,
    "arcenciel_debug_logging": bool(os.getenv("ARCENCIEL_DEBUG")),
}


def _opts_data():
    try:
        if shared is not None and getattr(shared, "opts", None) is not None:
            return shared.opts.data
    except Exception:
        pass
    return {}


def get_option(name, default=None):
    return _opts_data().get(name, default)


def get_int(name, default, minimum=None, maximum=None):
    value = get_option(name, default)
    try:
        value = int(value)
    except Exception:
        value = int(default)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_bool(name, default=False):
    value = get_option(name, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def min_free_mb():
    return get_int(
        "arcenciel_min_free_mb",
        DEFAULTS["arcenciel_min_free_mb"],
        minimum=0,
    )


def max_retries():
    return get_int(
        "arcenciel_max_retries",
        DEFAULTS["arcenciel_max_retries"],
        minimum=1,
        maximum=20,
    )


def backoff_base():
    return get_int(
        "arcenciel_backoff_base",
        DEFAULTS["arcenciel_backoff_base"],
        minimum=1,
        maximum=10,
    )


def download_preview_enabled():
    return get_bool("arcenciel_download_preview", DEFAULTS["arcenciel_download_preview"])


def save_html_preview_enabled():
    return get_bool("arcenciel_save_html_preview", DEFAULTS["arcenciel_save_html_preview"])


def download_history_limit():
    return get_int(
        "arcenciel_download_history_limit",
        DEFAULTS["arcenciel_download_history_limit"],
        minimum=1,
        maximum=500,
    )


def debug_logging_enabled():
    return get_bool("arcenciel_debug_logging", DEFAULTS["arcenciel_debug_logging"])


def path_override(model_type):
    option_name = PATH_OPTION_NAMES.get(str(model_type or "").upper())
    if not option_name:
        return ""
    return str(get_option(option_name, "") or "").strip()


def _add_option(name, info):
    try:
        data_labels = getattr(shared.opts, "data_labels", {})
        if name not in data_labels:
            shared.opts.add_option(name, info)
    except Exception:
        pass


def on_ui_settings():
    if shared is None:
        return

    option_info = shared.OptionInfo
    _add_option(
        "arcenciel_min_free_mb",
        option_info(
            DEFAULTS["arcenciel_min_free_mb"],
            "Minimum free space before download (MB)",
            section=SECTION,
        ),
    )
    _add_option(
        "arcenciel_max_retries",
        option_info(DEFAULTS["arcenciel_max_retries"], "Download retry attempts", section=SECTION),
    )
    _add_option(
        "arcenciel_backoff_base",
        option_info(DEFAULTS["arcenciel_backoff_base"], "Download retry backoff base", section=SECTION),
    )
    _add_option(
        "arcenciel_download_preview",
        option_info(
            DEFAULTS["arcenciel_download_preview"],
            "Download preview sidecar images",
            section=SECTION,
        ),
    )
    _add_option(
        "arcenciel_save_html_preview",
        option_info(
            DEFAULTS["arcenciel_save_html_preview"],
            "Write ArcEnCiel HTML preview sidecars",
            section=SECTION,
        ),
    )
    _add_option(
        "arcenciel_download_history_limit",
        option_info(
            DEFAULTS["arcenciel_download_history_limit"],
            "Download history entries to keep visible",
            section=SECTION,
        ),
    )
    _add_option(
        "arcenciel_debug_logging",
        option_info(DEFAULTS["arcenciel_debug_logging"], "Enable ArcEnCiel debug logging", section=SECTION),
    )

    for model_type, option_name in PATH_OPTION_NAMES.items():
        _add_option(
            option_name,
            option_info(
                "",
                f"{model_type} path override (empty = Path Presets/default)",
                section=SECTION,
            ),
        )

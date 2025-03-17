#scripts/callbacks.py

from modules import script_callbacks
from scripts.arcenciel_gui import on_ui_tabs
from scripts.arcenciel_server import on_app_started

# Register the route on app start
script_callbacks.on_app_started(on_app_started)

# Make sure there's no second on_ui_tabs() in any other file
script_callbacks.on_ui_tabs(on_ui_tabs)

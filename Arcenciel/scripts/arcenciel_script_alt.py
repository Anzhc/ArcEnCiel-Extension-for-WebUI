import gradio as gr
from modules import script_callbacks

EXTERNAL_SITE_URL = "https://arcenciel.io"

def on_ui_tabs():
    with gr.Blocks(analytics_enabled=False) as demo:
        gr.Markdown("## Arc En Ciel")

        # Subtract some offset so we don't overflow too badly.
        # e.g. 160px for top bars, etc. Tweak as needed.
        iframe_html = f"""
        <iframe 
            src="{EXTERNAL_SITE_URL}" 
            width="100%" 
            style="border: none; height: calc(100vh - 160px);"
        >
        </iframe>
        """

        gr.HTML(iframe_html)

    return [(demo, "ArcEnCiel Browser", "embedded_website_tab")]

script_callbacks.on_ui_tabs(on_ui_tabs)
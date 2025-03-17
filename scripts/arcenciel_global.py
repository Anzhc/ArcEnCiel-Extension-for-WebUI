# scripts/arcenciel_global.py
from concurrent.futures import ThreadPoolExecutor

do_debug_print = True

def debug_print(*args):
    if do_debug_print:
        print("[ArcEnCiel DEBUG]:", *args)

# Shared state
json_data = None
url_list = {}
previous_inputs = None
cancel_status = False
download_queue = []
isDownloading = False

# (Add these lines)
executor = ThreadPoolExecutor(max_workers=4)  # up to 4 parallel downloads
futures_map = {}  # key: model_id, value: Future object

def init():
    global json_data, url_list, previous_inputs
    global cancel_status, download_queue, isDownloading
    global futures_map
    json_data = None
    url_list.clear()
    previous_inputs = None
    cancel_status = False
    download_queue.clear()
    isDownloading = False
    futures_map.clear()

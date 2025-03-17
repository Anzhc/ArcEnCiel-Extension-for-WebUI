# scripts/arcenciel_download.py

import os
import time
import threading
import requests
import tqdm
import scripts.arcenciel_global as gl
from threading import Lock

# We'll store a reference to the queue-level tqdm bar in a global var.
queue_pbar = None
queue_pbar_lock = Lock()

def queue_download(model_id, version_id, file_url, filename):
    """
    Adds an item to the global download_queue.
    Increments the queue_pbar total if it exists.
    """
    item = {
        "model_id": model_id,
        "version_id": version_id,
        "file_url": file_url,
        "filename": filename,
    }
    gl.download_queue.append(item)
    gl.debug_print(f"Queued download: {item}")

    # If we already have a queue_pbar, increment its total by 1
    with queue_pbar_lock:
        if queue_pbar is not None:
            queue_pbar.total += 1
            queue_pbar.refresh()

def start_downloads():
    """
    Start a background thread that processes gl.download_queue items dynamically.
    If already in progress, do nothing.
    """
    if gl.isDownloading:
        return  # already in progress

    gl.isDownloading = True

    def download_worker():
        global queue_pbar
        gl.debug_print("Starting dynamic queue downloader.")

        # We'll create the queue-level TQDM with a 0 initial total.
        # dynamic_ncols=True can help TQDM properly size columns.
        with tqdm.tqdm(
            total=0,
            desc="Queue",
            ascii=True,
            position=0,
            dynamic_ncols=True
        ) as pbar:
            # store in global so queue_download can update it
            with queue_pbar_lock:
                queue_pbar = pbar

            # Now loop while queue has items or we haven't been canceled
            while True:
                if gl.cancel_status:
                    gl.debug_print("Download canceled globally.")
                    break

                # If queue is empty, check if we might be done
                if not gl.download_queue:
                    # small sleep to see if new items come in
                    time.sleep(0.2)
                    # If still empty, maybe we are done
                    if not gl.download_queue and not gl.cancel_status:
                        # no more items arrived
                        break
                    continue

                # Pop the first item
                item = gl.download_queue.pop(0)
                do_download(item)

                # once file finishes, increment queue bar
                pbar.update(1)

            # end while
            gl.debug_print("All downloads finished or canceled.")
            gl.isDownloading = False
            # Reset queue_pbar to None
            with queue_pbar_lock:
                queue_pbar = None

    t = threading.Thread(target=download_worker, daemon=True)
    t.start()

def do_download(item):
    """
    Download one file with a file-level tqdm bar that shows bytes progress.
    """
    url = item["file_url"]
    filename = item["filename"]
    gl.debug_print(f"Downloading from {url} -> {filename}")

    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()

        total_size = int(r.headers.get('content-length', 0))
        chunk_size = 4096

        # ensure output folder
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

        # file-level bar
        with open(filename, "wb") as f, tqdm.tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            desc=os.path.basename(filename),
            ascii=True,
            position=1,
            dynamic_ncols=True
        ) as pbar:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if gl.cancel_status:
                    gl.debug_print("Download canceled mid-file.")
                    return
                f.write(chunk)
                pbar.update(len(chunk))

        gl.debug_print(f"Download completed: {filename}")
    except Exception as e:
        gl.debug_print(f"Failed to download {filename}: {e}")

def cancel_all_downloads():
    """
    Set cancel_status, empty the queue, so we stop everything.
    """
    gl.debug_print("Canceling all downloads.")
    gl.cancel_status = True
    gl.download_queue.clear()

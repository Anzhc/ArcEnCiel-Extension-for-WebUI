# scripts/arcenciel_download.py

import queue
import random
import shutil
import threading
import time
import uuid
from pathlib import Path

import requests

try:
    import tqdm
except ModuleNotFoundError:
    class _NoopProgress:
        def __init__(self, *args, **kwargs):
            self.total = kwargs.get("total", 0)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, *_args, **_kwargs):
            return None

        def refresh(self):
            return None

    class tqdm:
        tqdm = _NoopProgress

import scripts.arcenciel_global as gl
import scripts.arcenciel_inventory as inventory
import scripts.arcenciel_settings as settings
import scripts.arcenciel_sidecars as sidecars

CHUNK_SIZE = 1024 * 1024

_download_queue = queue.Queue()
_jobs = {}
_jobs_lock = threading.Lock()
_worker_lock = threading.Lock()
_worker_running = False


def _unique_path(path):
    path = Path(path)
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    candidate = path
    idx = 1
    while candidate.exists() or Path(str(candidate) + ".part").exists():
        candidate = parent / f"{stem}_{idx}{suffix}"
        idx += 1
    return candidate


def _set_job(job_id, **updates):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        updates.setdefault("updated_at", time.time())
        job.update(updates)


def _snapshot_job(job):
    return {
        "job_id": job["job_id"],
        "model_id": job.get("model_id"),
        "version_id": job.get("version_id"),
        "state": job.get("state"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "path": str(job.get("target_path", "")),
        "file_name": Path(job.get("target_path", "")).name if job.get("target_path") else "",
        "sha256": job.get("sha256", ""),
        "created_at": job.get("created_at", 0),
        "updated_at": job.get("updated_at", job.get("created_at", 0)),
        "retry_count": job.get("retry_count", 0),
    }


def get_download_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        return _snapshot_job(job) if job else None


def list_download_statuses(limit=None):
    if limit is None:
        limit = settings.download_history_limit()
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda item: item.get("created_at", 0), reverse=True)[
            :limit
        ]
        return [_snapshot_job(job) for job in jobs]


def queue_download(
    model_id,
    version_id,
    file_url,
    filename,
    *,
    expected_sha256="",
    model_data=None,
    version_data=None,
    download_preview=True,
    save_html_preview=False,
):
    target_path = _unique_path(filename)
    job_id = uuid.uuid4().hex[:12]
    now = time.time()
    job = {
        "job_id": job_id,
        "model_id": model_id,
        "version_id": version_id,
        "file_url": file_url,
        "target_path": str(target_path),
        "expected_sha256": str(expected_sha256 or "").lower(),
        "model_data": model_data,
        "version_data": version_data,
        "download_preview": download_preview,
        "save_html_preview": save_html_preview,
        "state": "QUEUED",
        "progress": 0,
        "message": "Queued",
        "created_at": now,
        "updated_at": now,
        "retry_count": 0,
        "cancel_requested": False,
    }
    with _jobs_lock:
        _jobs[job_id] = job
    _download_queue.put(job)
    return _snapshot_job(job)


def start_downloads():
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        gl.isDownloading = True
        threading.Thread(target=_download_worker, daemon=True).start()


def _download_worker():
    global _worker_running
    try:
        with tqdm.tqdm(total=0, desc="Queue", ascii=True, position=0, dynamic_ncols=True) as pbar:
            while True:
                if gl.cancel_status:
                    _cancel_queued_jobs()
                    break
                try:
                    job = _download_queue.get(timeout=0.25)
                except queue.Empty:
                    break
                pbar.total += 1
                pbar.refresh()
                _run_job(job)
                pbar.update(1)
                _download_queue.task_done()
    finally:
        gl.isDownloading = False
        gl.cancel_status = False
        with _worker_lock:
            _worker_running = False


def _cancel_queued_jobs():
    while True:
        try:
            job = _download_queue.get_nowait()
        except queue.Empty:
            break
        _set_job(job["job_id"], state="CANCELED", message="Canceled before start")
        _download_queue.task_done()


def _run_job(job):
    job_id = job["job_id"]
    label = Path(job["target_path"]).name
    try:
        if job.get("cancel_requested"):
            _set_job(job_id, state="CANCELED", progress=0, message="Canceled before start")
            return
        _set_job(job_id, state="DOWNLOADING", progress=0, message="Starting download")
        digest = _download_with_retry(job)
        _set_job(job_id, state="SIDECARS", progress=98, message="Writing sidecars")
        inventory.update_cached_hash(job["target_path"], digest)
        if job.get("model_data") and job.get("version_data"):
            sidecars.write_sidecars(
                job["model_data"],
                job["version_data"],
                job["target_path"],
                sha_local=digest,
                download_preview=job.get("download_preview", True),
                save_html=job.get("save_html_preview", False),
            )
        _set_job(
            job_id,
            state="DONE",
            progress=100,
            message=f"Downloaded {label}",
            sha256=digest,
        )
    except Exception as exc:
        if gl.cancel_status or job.get("cancel_requested"):
            _set_job(job_id, state="CANCELED", message="Download canceled")
        else:
            _set_job(job_id, state="ERROR", message=str(exc))
            gl.debug_print(f"Failed to download {label}: {exc}")


def _download_with_retry(job):
    last_error = None
    max_retries = settings.max_retries()
    for attempt in range(1, max_retries + 1):
        try:
            return _download_once(job)
        except Exception as exc:
            last_error = exc
            _cleanup_part(job["target_path"])
            if gl.cancel_status or job.get("cancel_requested"):
                raise RuntimeError("Download canceled") from exc
            if attempt >= max_retries:
                break
            wait = min(30, settings.backoff_base() ** attempt + random.uniform(0, 1))
            _set_job(
                job["job_id"],
                state="RETRYING",
                message=f"{exc}; retrying in {wait:.1f}s",
            )
            time.sleep(wait)
    raise last_error


def _download_once(job):
    target_path = Path(job["target_path"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if not _enough_free_space(target_path.parent):
        raise RuntimeError(f"Less than {settings.min_free_mb()} MB free in {target_path.parent}")
    if job.get("cancel_requested"):
        raise RuntimeError("Download canceled")

    tmp_path = Path(str(target_path) + ".part")
    url = job["file_url"]
    expected_sha = str(job.get("expected_sha256") or "").lower()
    session = requests.Session()

    with session.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0) or 0)
        done = 0
        with open(tmp_path, "wb") as handle, tqdm.tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            desc=target_path.name,
            ascii=True,
            position=1,
            dynamic_ncols=True,
        ) as progress_bar:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if gl.cancel_status or job.get("cancel_requested"):
                    raise RuntimeError("Download canceled")
                if not chunk:
                    continue
                handle.write(chunk)
                done += len(chunk)
                progress_bar.update(len(chunk))
                if total:
                    _set_job(job["job_id"], progress=max(0, min(97, int(done / total * 97))))

    digest = inventory.sha256_of_file(tmp_path)
    if expected_sha and digest.lower() != expected_sha:
        raise RuntimeError("SHA-256 mismatch")
    tmp_path.replace(target_path)
    return digest.lower()


def _cleanup_part(path):
    try:
        Path(str(path) + ".part").unlink(missing_ok=True)
    except Exception:
        pass


def _enough_free_space(path):
    free_mb = shutil.disk_usage(path).free // (1024 * 1024)
    return free_mb >= settings.min_free_mb()


def cancel_all_downloads():
    should_cancel_worker = False
    with _jobs_lock:
        for job in _jobs.values():
            if job.get("state") in {"QUEUED", "DOWNLOADING", "RETRYING"}:
                should_cancel_worker = True
                job["cancel_requested"] = True
                job["updated_at"] = time.time()
    gl.cancel_status = should_cancel_worker
    _cancel_queued_jobs()


def cancel_download(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None, "Unknown download job."
        if job.get("state") in {"DONE", "ERROR", "CANCELED"}:
            return _snapshot_job(job), "Job is already finished."
        job["cancel_requested"] = True
        job["updated_at"] = time.time()
        if job.get("state") == "QUEUED":
            job["state"] = "CANCELED"
            job["message"] = "Canceled"
        else:
            job["message"] = "Cancel requested"
        return _snapshot_job(job), ""


def retry_download(job_id):
    with _jobs_lock:
        old_job = _jobs.get(job_id)
        if not old_job:
            return None, "Unknown download job."
        if old_job.get("state") not in {"ERROR", "CANCELED"}:
            return _snapshot_job(old_job), "Only failed or canceled jobs can be retried."
        retry_count = int(old_job.get("retry_count", 0)) + 1
        retry_source = {
            "model_id": old_job.get("model_id"),
            "version_id": old_job.get("version_id"),
            "file_url": old_job.get("file_url"),
            "target_path": old_job.get("target_path"),
            "expected_sha256": old_job.get("expected_sha256", ""),
            "model_data": old_job.get("model_data"),
            "version_data": old_job.get("version_data"),
            "download_preview": old_job.get("download_preview", True),
            "save_html_preview": old_job.get("save_html_preview", False),
        }

    snapshot = queue_download(
        retry_source["model_id"],
        retry_source["version_id"],
        retry_source["file_url"],
        retry_source["target_path"],
        expected_sha256=retry_source["expected_sha256"],
        model_data=retry_source["model_data"],
        version_data=retry_source["version_data"],
        download_preview=retry_source["download_preview"],
        save_html_preview=retry_source["save_html_preview"],
    )
    _set_job(snapshot["job_id"], retry_count=retry_count, message="Queued for retry")
    return get_download_status(snapshot["job_id"]), ""

"""
upload_from_url.py — process all pending jobs from the download queue.

Supports every URL type that the frontend can submit:
  ① Google Drive FOLDER link   → lists all files in the folder, downloads each
  ② Google Drive FILE  link    → downloads the single file
  ③ YouTube URL                → downloads via yt-dlp
  ④ HLS / m3u8 stream          → downloads via FFmpeg
  ⑤ Standard direct-download   → streamed HTTP download
"""

import os
import re
import traceback

from direct_download import download_from_url
from uploader import upload_file
from drive import list_files, download_file

from firebase_db import (
    get_pending_jobs,
    update_download_job,
)


# ── URL classification helpers ────────────────────────────────────────────────

_GDRIVE_FOLDER_RE = re.compile(
    r"drive\.google\.com/.*/folders/",
    re.I,
)
_GDRIVE_FILE_RE = re.compile(
    r"drive\.google\.com/(?:file/d/|open\?id=|uc\?)",
    re.I,
)


def _is_gdrive_folder(url: str) -> bool:
    return bool(_GDRIVE_FOLDER_RE.search(url))


def _is_gdrive_file(url: str) -> bool:
    return bool(_GDRIVE_FILE_RE.search(url))


def _gdrive_file_id(url: str) -> str | None:
    """Extract the file ID from a GDrive file URL."""
    # /file/d/<id>/
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # open?id=<id>  or  uc?id=<id>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


# ── per-job handlers ──────────────────────────────────────────────────────────

def _handle_gdrive_folder(url: str, dest_folder_id: str | None) -> None:
    """Download every file in the GDrive folder and upload them."""
    print(f"\n[GDrive Folder] Listing files in: {url}")
    files = list_files(url)           # drive.py accepts URLs or raw IDs
    print(f"Found {len(files)} file(s) in folder.\n")

    for idx, gfile in enumerate(files, 1):
        print(f"  [{idx}/{len(files)}] {gfile['name']}")
        temp_path = None
        try:
            temp_path = download_file(gfile)
            upload_file(temp_path, dest_folder_id)
        except Exception:
            traceback.print_exc()
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)


def _handle_gdrive_file(url: str, dest_folder_id: str | None) -> None:
    """Download a single GDrive file and upload it."""
    file_id = _gdrive_file_id(url)
    if not file_id:
        raise ValueError(f"Could not extract file ID from GDrive URL: {url}")

    print(f"\n[GDrive File] file_id={file_id}")
    # Build a minimal file dict that drive.download_file() expects
    gfile = {"id": file_id, "name": f"gdrive_{file_id}"}
    temp_path = download_file(gfile)
    try:
        upload_file(temp_path, dest_folder_id)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _handle_generic_url(url: str, dest_folder_id: str | None) -> None:
    """
    Route to the appropriate downloader (YouTube, HLS, standard HTTP).
    direct_download.download_from_url() handles all three cases internally.
    """
    temp_path = download_from_url(url)
    try:
        upload_file(temp_path, dest_folder_id)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    jobs = get_pending_jobs()

    if not jobs:
        print("\nNo pending download jobs.\n")
        return

    print(f"\n{'=' * 70}")
    print(f"Found {len(jobs)} pending job(s).")
    print(f"{'=' * 70}\n")

    for index, job in enumerate(jobs, 1):
        job_id        = job["jobId"]
        url           = job["url"]
        dest_folder   = job.get("folderId")   # Firestore folder doc ID or None

        print("=" * 70)
        print(f"[{index}/{len(jobs)}]  {url}")
        if dest_folder:
            print(f"  → destination folder: {dest_folder}")
        print("=" * 70)

        update_download_job(job_id, {"status": "downloading"})

        try:
            if _is_gdrive_folder(url):
                _handle_gdrive_folder(url, dest_folder)

            elif _is_gdrive_file(url):
                _handle_gdrive_file(url, dest_folder)

            else:
                # YouTube / HLS / standard HTTP — all handled by direct_download
                update_download_job(job_id, {"status": "downloading"})
                _handle_generic_url(url, dest_folder)

            update_download_job(job_id, {"status": "completed"})
            print(f"\n✅ Job {job_id} completed.\n")

        except Exception:
            traceback.print_exc()
            update_download_job(job_id, {"status": "failed"})
            print(f"\n❌ Job {job_id} failed.\n")


if __name__ == "__main__":
    main()

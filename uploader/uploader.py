"""
uploader.py — PW file uploader, logic mirrored from cloud-pro's uploadService.js.

Key behaviour (matching cloud-pro):
  - Files <= MULTIPART_LIMIT → single POST
  - Files >  MULTIPART_LIMIT → split into CHUNK_SIZE parts,
    each part uploaded individually.
  - Chunk names: `<filename>.part<NNNN>of<TTTT>`  (zero-padded 4 digits)
  - Each upload POSTs to /v1/files with field name "image".
  - Session tracking is kept in Firestore (firebase_db) so runs can resume.
  - Final file metadata is stored via add_file() once all parts succeed.
"""

import os
import mimetypes
import math
import tempfile
import time

import requests
from tqdm import tqdm
from requests_toolbelt.multipart.encoder import (
    MultipartEncoder,
    MultipartEncoderMonitor,
)

from config import (
    UPLOAD_URL,
    HEADERS,
    CHUNK_SIZE,
    MULTIPART_LIMIT,
    UPLOAD_RETRY_COUNT,
)
from firebase_db import add_file
from session_manager import (
    load_or_create_session,
    save_uploaded_part,
    finish_session,
    uploaded_bytes,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _split_file(file_path: str, chunk_size: int = CHUNK_SIZE) -> list[dict]:
    """
    Split *file_path* into in-memory temporary files.
    Naming matches cloud-pro: `<basename>.part<NNNN>of<TTTT>`.
    Returns a list of dicts: {index, name, path, size}.
    """
    file_size    = os.path.getsize(file_path)
    total_chunks = math.ceil(file_size / chunk_size)
    base_name    = os.path.basename(file_path)
    chunks       = []

    with open(file_path, "rb") as fp:
        for index in range(total_chunks):
            data      = fp.read(chunk_size)
            part_no   = str(index + 1).zfill(4)
            total_no  = str(total_chunks).zfill(4)
            part_name = f"{base_name}.part{part_no}of{total_no}"

            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".part")
            tmp.write(data)
            tmp.close()

            chunks.append({
                "index": index,
                "name":  part_name,
                "path":  tmp.name,
                "size":  len(data),
            })

    return chunks


# ── core upload ───────────────────────────────────────────────────────────────

def _upload_single_part(
    path: str,
    upload_name: str,
    progress_callback=None,
) -> dict:
    """
    POST a single file/part to the PW API.
    Returns: {_id, url, createdAt}
    """
    with open(path, "rb") as fp:
        encoder = MultipartEncoder(
            fields={
                "image": (upload_name, fp, _mime(upload_name))
            }
        )

        started = time.time()

        def _cb(monitor):
            if progress_callback is None:
                return
            elapsed = max(time.time() - started, 0.001)
            loaded  = monitor.bytes_read
            total   = encoder.len
            speed   = loaded / elapsed
            eta     = (total - loaded) / speed if speed else 0
            progress_callback(loaded, total, speed, eta)

        monitor  = MultipartEncoderMonitor(encoder, _cb)
        hdrs     = {**HEADERS, "Content-Type": monitor.content_type}
        response = requests.post(
            UPLOAD_URL,
            headers=hdrs,
            data=monitor,
            timeout=None,
        )

    response.raise_for_status()
    data = response.json()["data"]
    return {
        "_id":       data["_id"],
        "url":       data["baseUrl"] + data["key"],
        "createdAt": data["createdAt"],
    }


# ── public entry point ────────────────────────────────────────────────────────

def upload_file(file_path: str, folder_id: str | None = None) -> None:
    """
    Upload *file_path* to PW storage, storing metadata in Firestore.
    *folder_id* is the Firestore folder document ID (may be None for root).
    """
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    # ── single-part upload ────────────────────────────────────────────────
    if file_size <= MULTIPART_LIMIT:
        session = load_or_create_session(
            file_path,
            [{"size": file_size}],
            multipart=False,
        )

        bar      = tqdm(total=file_size, unit="B", unit_scale=True, desc=f"↑ {file_name}")
        previous = 0

        def _single_progress(loaded, total, speed, eta):
            nonlocal previous
            bar.update(loaded - previous)
            previous = loaded
            bar.set_postfix(
                speed=f"{speed / 1024 / 1024:.2f} MB/s",
                eta=f"{eta:.0f}s",
            )

        result = _upload_single_part(file_path, file_name, _single_progress)
        bar.close()

        add_file({
            "id":        result["_id"],
            "_id":       result["_id"],
            "multipart": False,
            "folderId":  folder_id,
            "name":      file_name,
            "url":       result["url"],
            "createdAt": result["createdAt"],
            "size":      file_size,
            "type":      _mime(file_name),
        })

        finish_session(session)
        return

    # ── multipart upload ──────────────────────────────────────────────────
    chunks  = _split_file(file_path)
    session = load_or_create_session(file_path, chunks, multipart=True)

    done_bytes = uploaded_bytes(session)
    overall    = tqdm(
        total=file_size,
        initial=done_bytes,
        unit="B",
        unit_scale=True,
        desc=file_name,
    )
    started = time.time()

    for i in range(session["nextChunk"], len(chunks)):
        chunk = chunks[i]
        retry = 0

        while True:
            try:
                previous = 0

                def _chunk_progress(loaded, total, speed, eta):
                    nonlocal previous, done_bytes
                    overall.update(loaded - previous)
                    previous      = loaded
                    uploaded_now  = done_bytes + loaded
                    elapsed       = max(time.time() - started, 0.001)
                    overall_speed = uploaded_now / elapsed
                    remaining     = file_size - uploaded_now
                    overall_eta   = remaining / overall_speed if overall_speed else 0
                    overall.set_postfix(
                        speed=f"{overall_speed / 1024 / 1024:.2f} MB/s",
                        eta=f"{overall_eta:.0f}s",
                    )

                result = _upload_single_part(
                    chunk["path"],
                    chunk["name"],
                    _chunk_progress,
                )

                done_bytes += chunk["size"]
                save_uploaded_part(session, i, result["_id"], result["url"], chunk["size"])
                break

            except Exception:
                retry += 1
                if retry > UPLOAD_RETRY_COUNT:
                    raise

        os.remove(chunk["path"])

    overall.close()

    add_file({
        "id":        "virtual-" + session["sessionId"],
        "multipart": True,
        "folderId":  folder_id,
        "name":      file_name,
        "size":      file_size,
        "type":      _mime(file_name),
        "createdAt": session["createdAt"],
        "parts":     session["parts"],
    })

    finish_session(session)

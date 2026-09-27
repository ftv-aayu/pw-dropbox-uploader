"""
drive.py — Google Drive helpers.

list_files(folder_id)  →  list files in a GDrive folder.
download_file(file)    →  download a single GDrive file to a temp path.
"""

import os
import re
import tempfile

import requests
from tqdm import tqdm

from config import GDRIVE_API_KEY


def _extract_folder_id(url_or_id: str) -> str:
    """
    Accept either a raw folder ID or any of the common GDrive folder URL forms:
      - https://drive.google.com/drive/folders/<id>
      - https://drive.google.com/drive/u/0/folders/<id>
      - https://drive.google.com/open?id=<id>
    Falls back to treating the string as a raw ID.
    """
    # folders/<id>  form
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)

    # ?id=<id>  form
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)

    # Assume it's already a raw ID
    return url_or_id.strip()


def list_files(folder_id: str) -> list[dict]:
    """Return all non-trashed files directly inside *folder_id*."""
    fid    = _extract_folder_id(folder_id)
    files  = []
    page_token = None

    while True:
        params = {
            "q":         f"'{fid}' in parents and trashed=false",
            "fields":    "nextPageToken,files(id,name,mimeType,size)",
            "pageSize":  1000,
            "key":       GDRIVE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(
            "https://www.googleapis.com/drive/v3/files",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        files.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return files


def download_file(file: dict) -> str:
    """Download a single GDrive *file* dict and return its temp path."""
    url = (
        f"https://www.googleapis.com/drive/v3/files/{file['id']}"
        f"?alt=media&key={GDRIVE_API_KEY}"
    )
    response = requests.get(url, stream=True)
    response.raise_for_status()

    suffix = os.path.splitext(file["name"])[1]
    tmp    = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    total = int(response.headers.get("content-length", 0))
    with open(tmp.name, "wb") as fp, tqdm(
        total=total,
        unit="B",
        unit_scale=True,
        desc=f"↓ {file['name']}",
    ) as bar:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                fp.write(chunk)
                bar.update(len(chunk))

    return tmp.name

import os

PW_TOKEN        = os.environ["PW_TOKEN"]
GDRIVE_API_KEY  = os.environ["GDRIVE_API_KEY"]

FIREBASE_CREDENTIALS = "firebase.json"

UPLOAD_URL = "https://api.penpencil.co/v1/files"

# ── Chunk / multipart settings ──────────────────────────────────────────────
# PW API accepts a maximum of 100 MB per part upload request.
# Files larger than MULTIPART_LIMIT are split into CHUNK_SIZE pieces.
# Both are capped at 100 MB to match the server limit.
CHUNK_SIZE      = 100 * 1024 * 1024   # 100 MB
MULTIPART_LIMIT = 100 * 1024 * 1024   # 100 MB  (single-part threshold)

UPLOAD_RETRY_COUNT = 3

HEADERS = {
    "authorization": f"Bearer {PW_TOKEN}",
    "client-type":   "web",
    "X-SDK-Version": "0.0.13-alpha.10",
    "client-id":     "5eb393ee95fab7468a79d189"
}

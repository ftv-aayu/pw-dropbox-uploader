import os

PW_TOKEN = os.environ["PW_TOKEN"]

GDRIVE_API_KEY = os.environ["GDRIVE_API_KEY"]

FIREBASE_CREDENTIALS = "firebase.json"

UPLOAD_URL = "https://api.penpencil.co/v1/files"

FOLDER_ID = "1csUkT15QFnIWxT5Ys03QhXX-_hSHBhIo"

CHUNK_SIZE = 100 * 1024 * 1024

MULTIPART_LIMIT = 100 * 1024 * 1024

UPLOAD_RETRY_COUNT = 3


HEADERS = {

    "authorization": f"Bearer {PW_TOKEN}",

    "client-type": "web",

    "X-SDK-Version": "0.0.13-alpha.10",

    "client-id": "5eb393ee95fab7468a79d189"

}

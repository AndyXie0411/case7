import os
import datetime
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
from azure.storage.blob import BlobServiceClient, ContentSettings
from werkzeug.utils import secure_filename


# --- Configuration ---
CONTAINER_NAME = os.getenv("IMAGES_CONTAINER", "lanternfly-images")
CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")

# Initialize Blob Service Client
if CONNECTION_STRING:
    bsc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
else:
    # For App Service, typically only account URL + managed identity or env key is used
    bsc = BlobServiceClient(account_url=ACCOUNT_URL)

cc = bsc.get_container_client(CONTAINER_NAME)

# Create container if it doesn't exist
try:
    cc.create_container(public_access="blob")
except Exception:
    pass  # already exists

# --- Flask App ---
app = Flask(__name__)

MAX_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# --- Routes ---

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/v1/upload")
def upload():
    if "file" not in request.files:
        return jsonify(ok=False, error="Missing file field"), 400

    f = request.files["file"]

    # Validate file type
    if f.mimetype not in ALLOWED_TYPES:
        return jsonify(ok=False, error="Unsupported file type"), 415

    # Validate file size
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > MAX_SIZE:
        return jsonify(ok=False, error="File too large (max 10MB)"), 413

    # Sanitize and timestamp filename
    safe_name = secure_filename(f.filename)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    blob_name = f"{timestamp}-{safe_name}"

    try:
        blob_client = cc.get_blob_client(blob_name)
        blob_client.upload_blob(
            f,
            overwrite=True,
            content_settings=ContentSettings(content_type=f.mimetype),
        )
        url = f"{cc.url}/{blob_name}"
        app.logger.info(f"Uploaded: {url}")
        return jsonify(ok=True, url=url)
    except Exception as e:
        app.logger.error(f"Upload failed: {e}")
        return jsonify(ok=False, error=str(e)), 500


@app.get("/api/v1/gallery")
def gallery():
    try:
        blobs = list(cc.list_blobs())
        urls = [f"{cc.url}/{b.name}" for b in blobs]
        return jsonify(ok=True, gallery=urls)
    except Exception as e:
        app.logger.error(f"Gallery error: {e}")
        return jsonify(ok=False, error=str(e)), 500


@app.get("/health")
def health():
    return jsonify(status="ok"), 200


# --- Run local dev server ---
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

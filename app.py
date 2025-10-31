import os
import datetime
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("IMAGES_CONTAINER", "lanternfly-images")
ACCOUNT_URL = os.getenv("STORAGE_ACCOUNT_URL")

# --- Azure Blob Service Setup ---
bsc = BlobServiceClient.from_connection_string(CONNECTION_STRING)
cc = bsc.get_container_client(CONTAINER_NAME)

# Create container if not exists
try:
    cc.create_container(public_access="container")
except Exception:
    pass  # ignore if container already exists

# --- Flask app ---
app = Flask(__name__)

# --- Utility ---
def allowed_file(content_type):
    """Allow only image/* types."""
    return content_type.startswith("image/")

# --- API Endpoints ---

@app.post("/api/v1/upload")
def upload():
    if "file" not in request.files:
        return jsonify(ok=False, error="Missing file field"), 400

    file = request.files["file"]

    if not allowed_file(file.content_type):
        return jsonify(ok=False, error="Invalid file type. Must be image/*"), 400

    if len(file.read()) > 10 * 1024 * 1024:  # 10 MB limit
        return jsonify(ok=False, error="File too large (>10MB)"), 400
    file.seek(0)  # reset pointer

    safe_name = secure_filename(file.filename)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    blob_name = f"{timestamp}-{safe_name}"

    try:
        cc.upload_blob(
            name=blob_name,
            data=file,
            overwrite=True,
            content_settings=ContentSettings(content_type=file.content_type)
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
        blobs = cc.list_blobs()
        urls = [f"{cc.url}/{b.name}" for b in blobs]
        return jsonify(ok=True, gallery=urls)
    except Exception as e:
        app.logger.error(f"Gallery error: {e}")
        return jsonify(ok=False, error=str(e)), 500


@app.get("/api/v1/health")
def health():
    return "OK", 200


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

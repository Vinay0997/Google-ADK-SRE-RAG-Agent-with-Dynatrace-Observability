import os

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token

app = Flask(__name__, static_folder="static/assets", static_url_path="/assets")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")


@app.get("/health")
def health():
    return jsonify(status="ready")


@app.post("/api/ask")
def ask():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="A JSON object is required."), 400

    question = body.get("question")
    if not isinstance(question, str) or not 3 <= len(question) <= 4000:
        return jsonify(error="Question must contain 3 to 4000 characters."), 400

    payload = {
        "question": question,
        "user_id": "cloudrun-ui-demo",
        "role": "viewer",
    }
    if isinstance(body.get("session_id"), str):
        payload["session_id"] = body["session_id"]

    try:
        token = fetch_id_token(Request(), BACKEND_URL)
        upstream = requests.post(
            f"{BACKEND_URL}/ask",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 270),
            allow_redirects=False,
        )
        return Response(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get(
                "Content-Type", "application/json"
            ),
        )
    except requests.Timeout:
        return jsonify(error="Backend request timed out."), 504
    except Exception:
        app.logger.exception("Backend invocation failed")
        return jsonify(error="Backend invocation failed; inspect frontend logs."), 502


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/<path:path>")
def static_files(path):
    full_path = os.path.join(app.root_path, "static", path)
    if os.path.isfile(full_path):
        return send_from_directory("static", path)
    if path.startswith(("api/", "assets/")):
        return jsonify(error="Not found"), 404
    return send_from_directory("static", "index.html")

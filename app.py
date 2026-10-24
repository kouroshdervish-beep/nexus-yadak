from flask import Flask, send_from_directory
from pathlib import Path

app = Flask(__name__, static_folder=None)
BASE_DIR = Path(__file__).resolve().parent

@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")

@app.get("/<path:path>")
def static_files(path):
    # Serve local assets if any are added later; prevent path traversal.
    target = (BASE_DIR / path).resolve()
    if BASE_DIR.resolve() not in target.parents and target != BASE_DIR.resolve():
        return ("Not found", 404)
    if target.is_file():
        return send_from_directory(BASE_DIR, path)
    return ("Not found", 404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

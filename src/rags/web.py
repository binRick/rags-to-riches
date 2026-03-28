import json
import queue
import threading
import webbrowser
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, stream_with_context

from . import cache, github

app = Flask(__name__, template_folder="templates")
app.config["JSON_SORT_KEYS"] = False

_refresh_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/repos")
def get_repos():
    repos, timestamp = cache.load()
    if repos is None:
        return jsonify({"repos": [], "cached_at": None, "count": 0})
    return jsonify({"repos": repos, "cached_at": timestamp, "count": len(repos)})


@app.route("/api/refresh")
def refresh():
    """SSE endpoint — streams progress events then emits done/error."""

    def generate():
        token = github.get_token()
        if not token:
            yield _event({"type": "error", "message": "No GitHub token found. Set GITHUB_TOKEN env var."})
            return

        q: queue.Queue = queue.Queue()

        def fetch():
            try:
                def on_page(page: int, total: int) -> None:
                    q.put({"type": "progress", "page": page, "total": total})

                repos = github.fetch_starred(token, on_page=on_page)
                cache.save(repos)
                q.put({"type": "done", "count": len(repos), "cached_at": __import__("time").time()})
            except Exception as exc:
                q.put({"type": "error", "message": str(exc)})

        threading.Thread(target=fetch, daemon=True).start()

        while True:
            try:
                msg = q.get(timeout=60)
                yield _event(msg)
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield _event({"type": "ping"})

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def run(port: int = 5123) -> None:
    url = f"http://localhost:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"  Web app running at {url}")
    app.run(port=port, debug=False, use_reloader=False)

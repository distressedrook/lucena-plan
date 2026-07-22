"""review_server — serves experiments/reports/ as static files (the
benchmark HTML tables live there) PLUS a tiny JSON API so the page's
checkbox/notes state persists to an actual file on disk, not just browser
storage:

  GET  /api/review        -> the whole review-state JSON {id: {checked, notes}}
  POST /api/review        -> body is a partial {id: {checked, notes}, ...};
                              merged into the on-disk state and saved
                              (atomic write: tmp file + rename)

State file: experiments/reports/benchmark_review.json — plain JSON,
inspectable, git-diffable, safe to hand-edit. This script itself lives in
experiments/tools/ (2026-07-22 reorg) — DIR points at reports/ explicitly,
not at the script's own directory, since what's served is the generated
output, not the tool that generates it.

Run: python3 experiments/tools/review_server.py [port]   (default 8900)
"""
from __future__ import annotations

import http.server
import json
import os
import sys
import threading

DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "reports"))
STATE_PATH = os.path.join(DIR, "benchmark_review.json")
_lock = threading.Lock()


def _load() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(state: dict) -> None:
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE_PATH)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    def log_message(self, fmt, *args):
        pass   # keep the terminal quiet; errors still raise

    def end_headers(self):
        # No caching, ever — this data gets regenerated in place under the
        # same filename, and a stale browser cache showing old facts next
        # to fresh ones is a much worse bug than a few extra requests.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/review":
            with _lock:
                body = json.dumps(_load()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/api/review":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            patch = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "bad JSON")
            return
        with _lock:
            state = _load()
            for k, v in patch.items():
                state.setdefault(k, {}).update(v)
            _save(state)
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8900
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"serving {DIR} + /api/review on http://127.0.0.1:{port}  "
          f"(state -> {STATE_PATH})")
    srv.serve_forever()

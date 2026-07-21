"""Tiny live status dashboard for corpus runs — http://127.0.0.1:8899

Shows: shard progress of the current/last calibration run (lift_shards/),
row counts, freshness, and the latest lift_report.txt. Auto-refreshes.
Run: nohup python experiments/status_server.py &
"""
from __future__ import annotations

import glob
import html
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE = "/Users/avismara/Development/chess-plans/experiments"
SHARDS = f"{BASE}/lift_shards"
REPORT = f"{BASE}/lift_report.txt"
EXPECTED_SHARDS = 68          # ceil(33769 / 500)
PORT = 8899


def shard_stats():
    files = sorted(glob.glob(f"{SHARDS}/shard_*.jsonl"))
    rows = 0
    latest = 0.0
    for p in files:
        try:
            with open(p) as f:
                rows += sum(1 for _ in f)
            latest = max(latest, os.path.getmtime(p))
        except OSError:
            pass
    return len(files), rows, latest


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        n, rows, latest = shard_stats()
        pct = 100 * n / EXPECTED_SHARDS
        age = time.time() - latest if latest else None
        state = ("RUNNING" if age is not None and age < 120
                 else "COMPLETE" if n >= EXPECTED_SHARDS else "IDLE/STALLED")
        try:
            report = open(REPORT).read()
        except OSError:
            report = "(no report yet)"
        body = f"""<!doctype html><html><head><meta charset='utf-8'>
<meta http-equiv='refresh' content='5'>
<title>chess-plans runs</title>
<style>body{{font-family:ui-monospace,monospace;background:#101418;color:#d8dee6;
margin:2rem}} .bar{{background:#232b33;border-radius:6px;height:22px;width:60%}}
.fill{{background:#4c9e57;height:22px;border-radius:6px;width:{pct:.1f}%}}
pre{{background:#161c22;padding:1rem;border-radius:8px;overflow-x:auto;
font-size:12px;line-height:1.35}} .s{{color:#8b98a5}}
h1{{font-size:18px}} .{state.split('/')[0]}{{color:{'#7bd88f' if state=='RUNNING' else '#e8c264' if state!='COMPLETE' else '#6cb2e8'}}}</style>
</head><body>
<h1>chess-plans corpus calibration <span class='{state.split('/')[0]}'>[{state}]</span></h1>
<div class='bar'><div class='fill'></div></div>
<p>shards {n}/{EXPECTED_SHARDS} ({pct:.0f}%) &middot; anchor rows {rows:,}
&middot; <span class='s'>last shard write {f'{age:.0f}s ago' if age is not None else 'never'}</span></p>
<h1>latest lift report</h1>
<pre>{html.escape(report)}</pre>
</body></html>"""
        data = body.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()

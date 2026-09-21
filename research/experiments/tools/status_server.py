"""Tiny live status dashboard for corpus runs — http://127.0.0.1:8899

Shows: shard progress of the current/last calibration run (lift_shards/),
row counts, freshness, and the latest lift_report.txt. Auto-refreshes.
Run: nohup python research/experiments/status_server.py &
"""
from __future__ import annotations

import glob
import html
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import kstudy_reduce

BASE = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments"
SHARDS = f"{BASE}/maia_shards"
REPORT = f"{BASE}/lift_report.txt"
KREPORT = f"{BASE}/kstudy_report.txt"
EXPECTED_SHARDS = 64          # 40 argmax + 12 ksample + 12 k-extension
PORT = 8899

# lazily re-reduce the k-study whenever a new ksample shard has landed;
# the reduce is cheap (<0.1s for 12 shards) and only runs on count change.
_last_kreduced = -1


def kstudy_panel() -> str:
    """Return the current k-study report text, re-reducing if a ksample shard
    appeared since the last reduce. Never raises into the request path."""
    global _last_kreduced
    ndone = len([p for p in glob.glob(f"{SHARDS}/ksample_*.jsonl")])
    if ndone != _last_kreduced:
        try:
            kstudy_reduce.main()
            _last_kreduced = ndone
        except Exception as e:                       # keep the page alive
            return f"(k-study reduce failed: {e})"
    try:
        return open(KREPORT).read()
    except OSError:
        return "(k-study not reduced yet — no ksample shards)"


def shard_stats():
    files = sorted(glob.glob(f"{SHARDS}/*.jsonl"))
    for tmp in glob.glob(f"{SHARDS}/*.tmp"):
        try:
            latest_tmp = os.path.getmtime(tmp)
        except OSError:
            continue
    rows = 0
    latest = 0.0
    for p in files:
        try:
            with open(p) as f:
                rows += sum(1 for _ in f)
            latest = max(latest, os.path.getmtime(p))
        except OSError:
            pass
    for tmp in glob.glob(f"{SHARDS}/*.tmp"):
        try:
            latest = max(latest, os.path.getmtime(tmp))
        except OSError:
            pass
    n_argmax = len(glob.glob(f"{SHARDS}/argmax_*.jsonl"))
    n_ksample = len(glob.glob(f"{SHARDS}/ksample_*.jsonl"))
    return len(files), rows, latest, n_argmax, n_ksample


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        n, rows, latest, n_argmax, n_ksample = shard_stats()
        kreport = kstudy_panel()
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
<h1>chess-plans overnight Maia calibration <span class='{state.split('/')[0]}'>[{state}]</span></h1>
<div class='bar'><div class='fill'></div></div>
<p>shards {n}/{EXPECTED_SHARDS} ({pct:.0f}%) &middot;
<span class='s'>argmax {n_argmax}/40 &middot; ksample {n_ksample}/24 (12 base + 12 ext->K=16)</span> &middot;
anchor rows {rows:,} &middot;
<span class='s'>last shard write {f'{age:.0f}s ago' if age is not None else 'never'}</span></p>
<h1>k-study result <span class='s'>(rollouts-to-stability &middot; Maia VERIFY-tier contract)</span></h1>
<pre>{html.escape(kreport)}</pre>
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

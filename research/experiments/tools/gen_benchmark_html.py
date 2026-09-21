"""gen_benchmark_html — render the 4,000-position benchmark as an HTML
table: fen | lichess analysis link | fact sheet.

Run: python3 research/experiments/gen_benchmark_html.py
Output: research/experiments/benchmark_sheets.html
"""
from __future__ import annotations

import html
import json
import sys
import time
import urllib.parse
from multiprocessing import Pool

sys.path.insert(0, "/Users/avismara/Projects/active/lucena/lucena-plans/src")

BENCH = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/benchmark_v1.jsonl"
OUT = "/Users/avismara/Projects/active/lucena/lucena-plans/research/experiments/reports/benchmark_sheets.html"
WORKERS = 8

HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>chess-plans benchmark_v1 — 4000 fact sheets</title>
<style>
  body { font-family: -apple-system, sans-serif; margin: 0; padding: 16px; }
  table { border-collapse: collapse; width: 100%; table-layout: fixed; }
  th, td { border: 1px solid #ccc; padding: 6px 8px; vertical-align: top; text-align: left; }
  th { background: #eee; position: sticky; top: 0; z-index: 1; }
  td.chk { width: 3%; text-align: center; }
  td.fen { width: 19%; font-family: monospace; font-size: 12px; word-break: break-all; }
  td.link { width: 7%; }
  td.sheet { width: 46%; }
  td.notes { width: 25%; }
  pre.sheet { white-space: pre-wrap; font-family: -apple-system, sans-serif; margin: 0 0 6px 0; font-size: 13px; max-height: 260px; overflow-y: auto; }
  #search { margin-bottom: 10px; padding: 6px; width: 320px; }
  .id { color: #888; font-size: 11px; }
  .copybtn { font-size: 11px; padding: 2px 8px; cursor: pointer; }
  .copybtn.copied { background: #dfd; }
  textarea.notes { width: 100%; box-sizing: border-box; min-height: 60px; font-family: -apple-system, sans-serif; font-size: 12px; resize: vertical; }
  tr.reviewed td.sheet, tr.reviewed td.fen { background: #f3fbf3; }
  input[type=checkbox] { width: 18px; height: 18px; cursor: pointer; }
  #status { color: #888; font-size: 12px; margin-left: 12px; }
</style>
</head><body>
<h2>chess-plans benchmark_v1 — 4000 positions</h2>
<input id="search" placeholder="filter by id or fen substring...">
<span id="status"></span>
<table id="tbl"><thead><tr><th>reviewed</th><th>FEN</th><th>lichess</th><th>fact sheet (POSITION READ / STRUCTURE / WEAKNESSES / PLAN, prompt+preamble stripped)</th><th>notes</th></tr></thead><tbody>
"""

FOOT = """</tbody></table>
<script>
var API = '/api/review';
var state = {};   // id -> {checked, notes}
var saveTimer = null;
var pending = {};

function setStatus(s) { document.getElementById('status').textContent = s; }

function applyRow(row, id) {
  var s = state[id] || {};
  var cb = row.querySelector('input.reviewedbox');
  var nt = row.querySelector('textarea.notes');
  cb.checked = !!s.checked;
  nt.value = s.notes || '';
  row.classList.toggle('reviewed', !!s.checked);
}

function scheduleSave() {
  clearTimeout(saveTimer);
  setStatus('saving...');
  saveTimer = setTimeout(function() {
    var body = JSON.stringify(pending);
    pending = {};
    fetch(API, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body})
      .then(function(r) { if (!r.ok) throw new Error('save failed'); setStatus('saved'); })
      .catch(function() { setStatus('SAVE FAILED — is the review server running?'); });
  }, 500);
}

document.addEventListener('DOMContentLoaded', function() {
  fetch(API).then(function(r) { return r.json(); }).then(function(data) {
    state = data || {};
    document.querySelectorAll('#tbl tbody tr').forEach(function(row) {
      applyRow(row, row.dataset.id);
    });
    var n = Object.keys(state).filter(function(k) { return state[k].checked; }).length;
    setStatus(n + ' reviewed');
  }).catch(function() {
    setStatus('review server not reachable — checkbox/notes will not persist');
  });
});

document.getElementById('tbl').addEventListener('change', function(e) {
  if (e.target.classList.contains('reviewedbox')) {
    var row = e.target.closest('tr');
    var id = row.dataset.id;
    state[id] = state[id] || {};
    state[id].checked = e.target.checked;
    row.classList.toggle('reviewed', e.target.checked);
    pending[id] = state[id];
    scheduleSave();
  }
});

document.getElementById('tbl').addEventListener('input', function(e) {
  if (e.target.classList.contains('notes')) {
    var row = e.target.closest('tr');
    var id = row.dataset.id;
    state[id] = state[id] || {};
    state[id].notes = e.target.value;
    pending[id] = state[id];
    scheduleSave();
  }
});

document.getElementById('tbl').addEventListener('click', function(e) {
  if (e.target.classList.contains('copybtn')) {
    var row = e.target.closest('tr');
    var text = row.querySelector('pre.sheet').textContent;
    navigator.clipboard.writeText(text).then(function() {
      e.target.classList.add('copied');
      var old = e.target.textContent;
      e.target.textContent = 'copied!';
      setTimeout(function() { e.target.classList.remove('copied'); e.target.textContent = old; }, 1200);
    });
  }
});

document.getElementById('search').addEventListener('input', function(e) {
  var q = e.target.value.toLowerCase();
  document.querySelectorAll('#tbl tbody tr').forEach(function(row) {
    row.style.display = row.dataset.k.includes(q) ? '' : 'none';
  });
});
</script>
</body></html>
"""


def lichess_link(fen: str) -> str:
    return "https://lichess.org/analysis/" + urllib.parse.quote(fen.replace(" ", "_"))


def render_row(r: dict) -> str:
    from fact_sheet import build_fact_sheet   # imported per worker process
    fen = r["fen"]
    try:
        body, pid = build_fact_sheet(fen)
    except Exception as e:
        body = f"[ERROR building sheet: {e}]"
    k = (r["id"] + " " + fen).lower()
    rid = html.escape(r["id"], quote=True)
    return (
        f'<tr data-k="{html.escape(k)}" data-id="{rid}">'
        f'<td class="chk"><input type="checkbox" class="reviewedbox"></td>'
        f'<td class="fen"><span class="id">{html.escape(r["id"])}</span><br>'
        f'{html.escape(fen)}</td>'
        f'<td class="link"><a href="{lichess_link(fen)}" target="_blank">'
        f'analyze</a></td>'
        f'<td class="sheet">'
        f'<button type="button" class="copybtn">copy sheet</button>'
        f'<pre class="sheet">{html.escape(body)}</pre></td>'
        f'<td class="notes"><textarea class="notes" '
        f'placeholder="notes..."></textarea></td>'
        f'</tr>\n'
    )


if __name__ == "__main__":
    rows = [json.loads(l) for l in open(BENCH)]
    n = len(rows)
    t0 = time.time()
    errs = 0
    with open(OUT, "w") as f:
        f.write(HEAD)
        with Pool(WORKERS) as pool:
            for i, row_html in enumerate(pool.imap(render_row, rows,
                                                    chunksize=10)):
                if "[ERROR" in row_html:
                    errs += 1
                f.write(row_html)
                if (i + 1) % 200 == 0:
                    elapsed = time.time() - t0
                    print(f"  {i+1}/{n} ({elapsed:.0f}s, "
                          f"{elapsed/(i+1)*1000:.0f}ms/pos, "
                          f"eta {elapsed/(i+1)*(n-i-1):.0f}s)",
                          file=sys.stderr, flush=True)
        f.write(FOOT)
    print(f"done: {n} positions, {errs} errors, {time.time()-t0:.0f}s -> {OUT}")

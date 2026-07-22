"""gen_agreement_html — render agreement_benchmark.json (the parallel
build's output) as a designed HTML report: one row per plan family, with
engine-confirm / floor / discrimination / Maia-typical, tiered by
discrimination ratio, with witness positions linked to Lichess.

Run: python3 experiments/gen_agreement_html.py
Output: experiments/agreement_report.html
"""
from __future__ import annotations

import html
import json
import sys
import urllib.parse

sys.path.insert(0, "/Users/avismara/Development/lucena/lucena-plans")
from suggest import CANDIDATE_FAMILIES

IN = "/Users/avismara/Development/lucena/lucena-plans/experiments/agreement_benchmark.json"
BENCH = "/Users/avismara/Development/lucena/lucena-plans/experiments/benchmark_v1.jsonl"
OUT = "/Users/avismara/Development/lucena/lucena-plans/experiments/reports/agreement_report.html"
MIN_N = 6

# family key -> display label, reversed from suggest.py's CANDIDATE_FAMILIES
LABEL = {}
for _disp, _keys in CANDIDATE_FAMILIES.items():
    for _k in _keys:
        LABEL.setdefault(_k, _disp.title())


def lichess_link(fen: str) -> str:
    return "https://lichess.org/analysis/" + urllib.parse.quote(fen.replace(" ", "_"))


def tier(ratio: float | None, n: int) -> tuple[str, str]:
    """(tier-key, tier-label) purely from the measured discrimination
    ratio — no hardcoded family lists, the data decides."""
    if ratio is None or n < MIN_N:
        return "none", "no signal"
    if ratio >= 3:
        return "strong", "strong signal"
    if ratio >= 1.5:
        return "solid", "solid signal"
    return "weak", "weak / anti-signal" if ratio < 1 else "marginal"


HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>chess-plans — plan-family agreement benchmark</title>
<style>
:root {
  --bg: #f7f5f0; --panel: #ffffff; --border: #ddd7c9; --border-soft: #e8e3d6;
  --text: #23211c; --text-dim: #6b6656; --accent: #8a6a2f; --accent-soft: #c9a15a;
  --good: #3f7d55; --good-bg: #e6f0e8; --bad: #9c4a34; --bad-bg: #f5e7e2;
  --chip: #efece2;
  --radius: 3px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14171c; --panel: #1a1e25; --border: #2c313c; --border-soft: #23272f;
    --text: #e8e6e0; --text-dim: #9aa0ab; --accent: #c9a15a; --accent-soft: #c9a15a;
    --good: #6fc48a; --good-bg: #1c2a20; --bad: #d97a5f; --bad-bg: #2c1f1c;
    --chip: #20242c;
  }
}
:root[data-theme="dark"] {
  --bg: #14171c; --panel: #1a1e25; --border: #2c313c; --border-soft: #23272f;
  --text: #e8e6e0; --text-dim: #9aa0ab; --accent: #c9a15a; --accent-soft: #c9a15a;
  --good: #6fc48a; --good-bg: #1c2a20; --bad: #d97a5f; --bad-bg: #2c1f1c;
  --chip: #20242c;
}
:root[data-theme="light"] {
  --bg: #f7f5f0; --panel: #ffffff; --border: #ddd7c9; --border-soft: #e8e3d6;
  --text: #23211c; --text-dim: #6b6656; --accent: #8a6a2f; --accent-soft: #c9a15a;
  --good: #3f7d55; --good-bg: #e6f0e8; --bad: #9c4a34; --bad-bg: #f5e7e2;
  --chip: #efece2;
}
* { box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text); margin: 0;
  font-family: ui-sans-serif, -apple-system, "Segoe UI", sans-serif;
  padding: 0 0 60px 0;
}
header {
  padding: 40px 32px 28px; border-bottom: 1px solid var(--border);
  background: var(--panel);
}
h1 {
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  font-weight: 600; font-size: 28px; margin: 0 0 6px 0; text-wrap: balance;
  letter-spacing: -0.01em;
}
header p.sub { margin: 0; color: var(--text-dim); font-size: 14px; max-width: 62ch; }
.meta { display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; }
.stat {
  background: var(--chip); border: 1px solid var(--border-soft);
  border-radius: var(--radius); padding: 10px 14px; min-width: 120px;
}
.stat .n { font-variant-numeric: tabular-nums; font-size: 20px; font-weight: 600; }
.stat .l { font-size: 11px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 0.04em; margin-top: 2px; }
main { max-width: 1080px; margin: 0 auto; padding: 32px; }
section.tier { margin-bottom: 36px; }
section.tier h2 {
  font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-dim); font-weight: 600; margin: 0 0 4px 0;
  display: flex; align-items: center; gap: 8px;
}
section.tier .count { font-weight: 400; color: var(--text-dim); }
section.tier p.desc { margin: 0 0 14px 0; color: var(--text-dim); font-size: 13px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.strong { background: var(--good); }
.dot.solid { background: var(--accent-soft); }
.dot.weak { background: var(--bad); }
.dot.none { background: var(--text-dim); }
.card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 8px; overflow: hidden;
}
.row {
  display: grid;
  grid-template-columns: 210px 90px 1fr 1fr 90px 32px;
  gap: 14px; align-items: center; padding: 12px 16px; cursor: pointer;
}
.row:hover { background: var(--border-soft); }
.famname { font-weight: 600; font-size: 14px; }
.famkey { font-family: ui-monospace, monospace; font-size: 11px; color: var(--text-dim); }
.n { font-variant-numeric: tabular-nums; font-size: 12px; color: var(--text-dim); text-align: right; }
.barwrap { display: flex; flex-direction: column; gap: 3px; }
.barlabel { display: flex; justify-content: space-between; font-size: 11px;
  color: var(--text-dim); font-variant-numeric: tabular-nums; }
.bar { height: 6px; background: var(--border-soft); border-radius: 3px; overflow: hidden; }
.bar > span { display: block; height: 100%; }
.bar.eng > span { background: var(--good); }
.bar.floor > span { background: var(--bad); opacity: 0.7; }
.bar.maia > span { background: var(--accent-soft); }
.ratio { font-variant-numeric: tabular-nums; text-align: right; font-size: 13px; font-weight: 600; }
.expand { text-align: center; color: var(--text-dim); font-size: 12px; transition: transform 0.15s; }
.card.open .expand { transform: rotate(90deg); }
.detail { display: none; padding: 0 16px 14px 16px; border-top: 1px solid var(--border-soft); }
.card.open .detail { display: block; }
.witnesses { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.witnesses a {
  font-size: 11px; font-family: ui-monospace, monospace; color: var(--accent);
  text-decoration: none; background: var(--chip); padding: 3px 7px;
  border-radius: var(--radius); border: 1px solid var(--border-soft);
}
.witnesses a:hover { border-color: var(--accent); }
.detail h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--text-dim); margin: 12px 0 0 0; }
.colhead {
  display: grid; grid-template-columns: 210px 90px 1fr 1fr 90px 32px; gap: 14px;
  padding: 0 16px 6px 16px; font-size: 11px; color: var(--text-dim);
  text-transform: uppercase; letter-spacing: 0.04em;
}
footer { max-width: 1080px; margin: 0 auto; padding: 0 32px; color: var(--text-dim); font-size: 12px; }
a.plain { color: var(--accent); }
</style>
</head><body>
"""

FOOT = """
<script>
document.querySelectorAll('.row').forEach(function(row) {
  row.addEventListener('click', function() {
    row.closest('.card').classList.toggle('open');
  });
});
</script>
</body></html>
"""


def bar(pct: float, cls: str) -> str:
    pct = max(0, min(100, pct))
    return f'<div class="bar {cls}"><span style="width:{pct:.1f}%"></span></div>'


def row_html(fam: str, v: dict, id2fen: dict) -> str:
    tot_e, conf, conf_r = v["tot_e"], v["conf"], v["conf_r"]
    tot_m, typ = v["tot_m"], v["typ"]
    ce = 100 * conf / tot_e if tot_e >= MIN_N else None
    fl = 100 * conf_r / tot_e if tot_e >= MIN_N else None
    cm = 100 * typ / tot_m if tot_m >= MIN_N else None
    ratio = (conf / conf_r) if (tot_e >= MIN_N and conf_r > 0) else (
        float("inf") if (tot_e >= MIN_N and conf > 0) else None)
    tkey, _ = tier(ratio, tot_e)
    ratio_txt = ("&infin;&times;" if ratio == float("inf") else
                f"{ratio:.1f}&times;" if ratio is not None else "&mdash;")
    label = LABEL.get(fam, fam.replace("_", " ").title())

    eng_bar = (bar(ce, "eng") + f'<div class="barlabel"><span>engine</span>'
              f'<span>{ce:.0f}%</span></div>'
              + bar(fl, "floor") + f'<div class="barlabel"><span>floor</span>'
              f'<span>{fl:.0f}%</span></div>') if ce is not None else \
        '<div class="barlabel"><span>not enough data</span></div>'
    maia_bar = (bar(cm, "maia") + f'<div class="barlabel"><span>maia typical</span>'
               f'<span>{cm:.0f}% ({tot_m})</span></div>') if cm is not None else \
        '<div class="barlabel"><span>&mdash;</span></div>'

    def wlist(ids):
        return "".join(
            f'<a href="{lichess_link(id2fen[i])}" target="_blank">{html.escape(i)}</a>'
            for i in ids if i in id2fen)

    detail = ""
    if v["eng_witnesses"] or v["maia_witnesses"]:
        detail = '<div class="detail">'
        if v["eng_witnesses"]:
            detail += (f'<h4>engine-confirmed witnesses '
                      f'({len(v["eng_witnesses"])} shown)</h4>'
                      f'<div class="witnesses">{wlist(v["eng_witnesses"])}</div>')
        if v["maia_witnesses"]:
            detail += (f'<h4>maia-typical witnesses '
                      f'({len(v["maia_witnesses"])} shown)</h4>'
                      f'<div class="witnesses">{wlist(v["maia_witnesses"])}</div>')
        detail += "</div>"

    return (
        f'<div class="card" data-tier="{tkey}">'
        f'<div class="row">'
        f'<div><div class="famname">{html.escape(label)}</div>'
        f'<div class="famkey">{html.escape(fam)}</div></div>'
        f'<div class="n">n={tot_e or tot_m}</div>'
        f'<div class="barwrap">{eng_bar}</div>'
        f'<div class="barwrap">{maia_bar}</div>'
        f'<div class="ratio">{ratio_txt}</div>'
        f'<div class="expand">&#9656;</div>'
        f'</div>{detail}</div>\n'
    )


if __name__ == "__main__":
    data = json.load(open(IN))
    meta, families = data["meta"], data["families"]
    id2fen = {json.loads(l)["id"]: json.loads(l)["fen"] for l in open(BENCH)}

    tiers = {"strong": [], "solid": [], "weak": [], "none": []}
    for fam, v in families.items():
        tot_e = v["tot_e"]
        ratio = (v["conf"] / v["conf_r"]) if (tot_e >= MIN_N and v["conf_r"] > 0) else (
            float("inf") if (tot_e >= MIN_N and v["conf"] > 0) else None)
        tkey, _ = tier(ratio, tot_e)
        tiers[tkey].append((fam, v, ratio, tot_e))

    for k in tiers:
        tiers[k].sort(key=lambda t: -(t[3] or 0))

    TIER_META = {
        "strong": ("Strong signal", "&ge;3&times; the random floor — "
                  "engine-confirmed play discriminates this family cleanly "
                  "from chance.", "dot strong"),
        "solid": ("Solid signal", "1.5&ndash;3&times; the random floor — "
                  "real discrimination, weaker margin.", "dot solid"),
        "weak": ("Weak or anti-signal", "Below 1.5&times; the floor (or "
                "under it) — candidate-tier or retired families; kept "
                "for the record, not for recommendation.", "dot weak"),
        "none": ("No signal yet", "Fewer than 6 qualifying positions in "
                "this 4,000-position benchmark.", "dot none"),
    }

    out = [HEAD]
    out.append(
        f'<header><h1>Plan-family agreement benchmark</h1>'
        f'<p class="sub">Every named plan family, checked against '
        f'{meta["positions"]:,} frozen GM positions: does the family '
        f'appear in an eval-equal engine line (vs. a random-line floor), '
        f'and is it typical of strong human play (Maia-2400 rollouts)? '
        f'Built from <code>benchmark_v1</code>.</p>'
        f'<div class="meta">'
        f'<div class="stat"><div class="n">{meta["positions"]:,}</div>'
        f'<div class="l">positions</div></div>'
        f'<div class="stat"><div class="n">{meta["engine_leg"]:,}</div>'
        f'<div class="l">engine leg</div></div>'
        f'<div class="stat"><div class="n">{meta["maia_leg"]:,}</div>'
        f'<div class="l">maia leg</div></div>'
        f'<div class="stat"><div class="n">{meta["mean_equal_lines"]:.1f}</div>'
        f'<div class="l">mean equal lines/pos</div></div>'
        f'<div class="stat"><div class="n">{meta["generated_in_s"]:.0f}s</div>'
        f'<div class="l">build time (8 workers)</div></div>'
        f'</div></header><main>'
    )

    for key in ("strong", "solid", "weak", "none"):
        rows = tiers[key]
        if not rows:
            continue
        title, desc, dotcls = TIER_META[key]
        out.append(
            f'<section class="tier"><h2><span class="{dotcls}"></span>'
            f'{title} <span class="count">({len(rows)} families)</span></h2>'
            f'<p class="desc">{desc}</p>'
            f'<div class="colhead"><div>family</div><div>n</div>'
            f'<div>engine vs floor</div><div>maia</div>'
            f'<div>discrimination</div><div></div></div>'
        )
        for fam, v, ratio, tot_e in rows:
            out.append(row_html(fam, v, id2fen))
        out.append("</section>")

    out.append("</main>")
    out.append(FOOT)
    with open(OUT, "w") as f:
        f.write("".join(out))
    print(f"-> {OUT}")

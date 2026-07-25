#!/usr/bin/env python3
"""Generate a self-contained correctness-review HTML for the 207 fired
compensation reads: board + our read + engine eval/lines + Lichess link +
per-position verdict marking (localStorage, exportable)."""
import os, sys, json, html
STUDY = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(STUDY, "../../../.."))
sys.path.insert(0, os.path.join(ROOT, "src"))
import chess
from initiative import initiative as _initiative

bench = [json.loads(l) for l in open(os.path.join(STUDY, "imbalance_benchmark.jsonl"))]
cache = {r["fen"]: r for r in (json.loads(l)
         for l in open(os.path.join(STUDY, "labeled_cache.jsonl")))}
# only the GENUINELY-POSITIONAL reads to audit — only-moves are a separate
# tactical/drill family (owner 2026-07-25: "remove all these from the queue").
fired = [r for r in bench if r.get("read") and r["read"]["primary"] != "only_move"]
print("positional reads to review (only-moves excluded):", len(fired))

from lucena_core import positional as _P
from lucena_core.board import Board as _LB

def _king_why(fen):
    """Named evidence behind each king's danger number (the term already
    computes it — zone_attackers/open files/shield/storm/line_pressure)."""
    try:
        kf = _P.analyze_positional(_LB(fen))["terms"]["king_safety"]["features"]
    except Exception:
        return None
    out = {}
    for s in ("white", "black"):
        f = kf[s]
        bits = []
        if f["zone_attackers"]:
            bits.append("attackers: " + ", ".join(f["zone_attackers"][:3]))
        if f["open_files_nearby"]:
            bits.append("open " + "/".join(f["open_files_nearby"]) + "-file beside king")
        if f["shield_pawns"] == 0:
            bits.append("no pawn shield")
        if f.get("storm"):
            bits.append(f"pawn storm {f['storm']}")
        if f.get("line_pressure"):
            bits.append(f"heavies on king's lines {f['line_pressure']}")
        out[s] = {"danger": f["danger_bounded"], "why": bits}
    return out

def san_line(fen, ucis, n=8):
    b = chess.Board(fen)
    out = []
    for u in ucis[:n]:
        try:
            mv = chess.Move.from_uci(u)
            out.append(b.san(mv)); b.push(mv)
        except Exception:
            break
    return out

data = []
for r in fired:
    fen = r["fen"]
    pvs = (cache.get(fen) or {}).get("pvs") or []
    lines = []
    for pv in pvs[:3]:
        san = san_line(fen, pv.get("ucis") or [])
        if san:
            lines.append({"cp": pv.get("cp"), "san": " ".join(san)})
    rd = r["read"]
    data.append({
        "fen": fen,
        "type": r["type"],
        "cp": r["engine_cp"],          # +White
        "naive": r["naive_cp"],
        "side": rd["side"],
        "deficit": rd["deficit_cp"],
        "comp": rd["comp_cp"],
        "mag": rd["magnitude"],
        "primary": rd["primary"],
        "kind": rd.get("concrete_kind"),
        "only_move": rd.get("only_move"),
        "sharpness": r.get("sharpness"),
        # PRODUCT OUTPUT, verbatim from the frozen sheet blocks — the page
        # computes nothing itself, so ✓/✗ verifies the product.
        "evidence": rd.get("evidence") or [],
        "initiative": (lambda iv: None if not iv else {
            "w": iv["white"]["score"], "b": iv["black"]["score"],
            "leader": iv["leader"], "resolves": iv.get("resolves"),
            "mechanism": iv.get("mechanism"), "deferred": iv.get("deferred"),
            "why": {s: {**iv[s]["why"],
                        "forcing": iv[s].get("forcing_moves") or [],
                        "frac": iv[s].get("forcing_frac")}
                    for s in ("white", "black")}})(r.get("initiative")),
        "king_why": r.get("king_why"),
        "summary": rd["summary"],
        "lines": lines,
        "turn": "White" if fen.split()[1] == "w" else "Black",
    })

# STABLE ids: assigned by a fixed sort (fen) so a card's id never changes even
# if the display order or benchmark is regenerated — these are the handles to
# talk about a position by.
for i, d in enumerate(sorted(data, key=lambda x: x["fen"])):
    d["id"] = f"P{i+1:03d}"

# display sort: static forms first, then concrete by kind, so like-with-like review
order = {"attack": 0, "activity": 1, "space": 2, "concrete": 3}
data.sort(key=lambda d: (order.get(d["primary"], 9), d["kind"] or "", d["type"]))

# sidecar index (id -> position + read) so the assistant can look up any id
idx = [{"id": d["id"], "fen": d["fen"], "type": d["type"], "primary": d["primary"],
        "kind": d["kind"], "cp": d["cp"], "summary": d["summary"],
        "initiative": d["initiative"]}
       for d in sorted(data, key=lambda x: x["id"])]
with open(os.path.join(STUDY, "review_index.json"), "w") as f:
    json.dump(idx, f, indent=1)

blob = json.dumps(data).replace("</", "<\\/")

HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compensation read — correctness review (207)</title>
<style>
 :root{--paper:#F1EDE3;--ink:#2b2b2b;--line:#d9d2c2;--ok:#2e7d32;--bad:#c62828;--maybe:#b58900;}
 *{box-sizing:border-box}
 body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--paper)}
 header{position:sticky;top:0;z-index:5;background:var(--paper);border-bottom:1px solid var(--line);padding:10px 16px}
 h1{font:600 17px/1.2 Georgia,serif;margin:0 0 6px}
 .bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;font-size:13px}
 .bar select,.bar button{font:13px inherit;padding:4px 8px;border:1px solid var(--line);background:#fff;border-radius:6px;cursor:pointer}
 .tally b{font-variant-numeric:tabular-nums}
 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:14px;padding:16px}
 .card{border:1px solid var(--line);border-radius:10px;background:#fff;padding:12px;display:flex;gap:12px}
 .card.correct{border-color:var(--ok);box-shadow:0 0 0 2px #2e7d3222}
 .card.wrong{border-color:var(--bad);box-shadow:0 0 0 2px #c6282822}
 .card.unsure{border-color:var(--maybe)}
 .board{width:200px;flex:0 0 200px}
 .board table{border-collapse:collapse;width:200px;height:200px}
 .board td{width:25px;height:25px;text-align:center;font-size:20px;line-height:25px;padding:0}
 .lt{background:#f0d9b5}.dk{background:#b58863}
 .wp{color:#fff;text-shadow:0 0 1px #000,0 0 1px #000,0 0 2px #000}
 .bp{color:#111}
 .meta{flex:1;min-width:0}
 .tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:6px}
 .tag{font:11px/1 inherit;padding:3px 6px;border-radius:20px;background:#efe9db;border:1px solid var(--line)}
 .tag.f{background:#e3edf7}.tag.k{background:#f7efe3}
 .read{font:500 14px/1.35 Georgia,serif;margin:6px 0;padding:8px;background:#faf7ef;border-left:3px solid #8a7a55;border-radius:0 6px 6px 0}
 .eval{font-variant-numeric:tabular-nums;font-weight:600}
 .lines{font:12px/1.5 Menlo,monospace;color:#555;margin:4px 0}
 .lines div{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 a.li{font-size:12px;text-decoration:none;color:#2b6cb0}
 .marks{display:flex;gap:6px;margin-top:8px}
 .marks button{flex:1;padding:5px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer;font-size:14px}
 .marks button.on-ok{background:var(--ok);color:#fff;border-color:var(--ok)}
 .marks button.on-bad{background:var(--bad);color:#fff;border-color:var(--bad)}
 .marks button.on-maybe{background:var(--maybe);color:#fff;border-color:var(--maybe)}
 .idx{color:#999;font-size:11px}
 .pid{font:600 13px Menlo,monospace;background:#8a7a55;color:#fff;padding:2px 7px;border-radius:6px;cursor:pointer;user-select:all}
 .pid:hover{background:#6f6244}
 .pid.copied{background:#2e7d32}
 .om{font:600 11px/1 inherit;padding:3px 6px;border-radius:20px;background:#3b2f2f;color:#ffd7a8;border:1px solid #6b4f3a}
 .om.razor{background:#5a1f1f;color:#ffcaca;border-color:#8a3a3a}
 .sharp{font:600 11px/1 inherit;padding:3px 6px;border-radius:20px;border:1px solid var(--line)}
 .sharp.DEAD,.sharp.QUIET{background:#eef1ee;color:#5a6b5a}
 .sharp.DYNAMIC{background:#eef3fb;color:#375a86}
 .sharp.SHARP{background:#fbf0e3;color:#8a5a1f}
 .sharp.RAZOR{background:#fbe3e3;color:#8a1f1f}
 .init{font:600 11px/1 Menlo,monospace;padding:3px 6px;border-radius:20px;background:#eee9f5;color:#4a3a6b;border:1px solid #cfc4e0}
 .why{font:11px/1.5 Menlo,monospace;color:#555;margin:4px 0}
 .why summary{cursor:pointer;color:#8a7a55;font-family:inherit}
 .why div{margin:2px 0 2px 8px}
 .ev{font:11.5px/1.5 Menlo,monospace;color:#4a5a3a;background:#f3f6ec;border-left:3px solid #7a8a55;padding:5px 8px;border-radius:0 6px 6px 0;margin:4px 0}
 .hidden{display:none}
</style></head><body>
<header>
 <h1>Compensation read — correctness review</h1>
 <div class="bar">
  <span class="tally" id="tally"></span>
  <label>id <input id="fId" size="6" placeholder="P042" style="font:13px Menlo,monospace;padding:4px 6px;border:1px solid var(--line);border-radius:6px"></label>
  <label>form <select id="fForm"><option value="">all</option></select></label>
  <label>kind <select id="fKind"><option value="">all</option></select></label>
  <label>sharpness <select id="fSharp"><option value="">all</option></select></label>
  <label>type <select id="fType"><option value="">all</option></select></label>
  <label><input type="checkbox" id="fUn"> only unmarked</label>
  <button id="export">Export verdicts</button>
  <button id="reset" style="color:#c62828">Reset marks</button>
 </div>
</header>
<div class="grid" id="grid"></div>
<script>
const DATA = __BLOB__;
const KEY = f => "imbrev::"+f;
const G = {P:"\\u265F",N:"\\u265E",B:"\\u265D",R:"\\u265C",Q:"\\u265B",K:"\\u265A"};
function boardHTML(fen){
 const rows = fen.split(" ")[0].split("/");
 let h = "<table>";
 for(let r=0;r<8;r++){ h+="<tr>"; let f=0;
  for(const ch of rows[r]){
   if(/\\d/.test(ch)){ for(let k=0;k<+ch;k++){ const dk=(r+f)%2; h+=`<td class="${dk?'dk':'lt'}"></td>`; f++; } }
   else { const dk=(r+f)%2; const white=ch===ch.toUpperCase();
    h+=`<td class="${dk?'dk':'lt'}"><span class="${white?'wp':'bp'}">${G[ch.toUpperCase()]}</span></td>`; f++; }
  } h+="</tr>";
 } return h+"</table>";
}
function evalStr(cp){ const s=(cp>0?"+":"")+(cp/100).toFixed(2); return s+" (White)"; }
function whyHTML(d){
 let h="";
 if(d.initiative&&d.initiative.why){
  for(const s of ["white","black"]){
   const w=d.initiative.why[s]; const bits=[];
   if(w.checks&&w.checks.length)bits.push("checks: "+w.checks.slice(0,4).join(", "));
   if(w.captures&&w.captures.length)bits.push("sound captures: "+w.captures.slice(0,4).join(", "));
   if(w.loose&&w.loose.length)bits.push("loose: "+w.loose.slice(0,3).join(", "));
   if(w.attacked&&w.attacked.length)bits.push("attacks: "+w.attacked.slice(0,3).join(", "));
   if(w.forcing&&w.forcing.length)bits.push(`keeps forcing (${Math.round((w.frac||0)*100)}%): `+w.forcing.slice(0,4).join(", "));
   h+=`<div><b>init ${s[0].toUpperCase()}</b> ${d.initiative[s==="white"?"w":"b"].toFixed(2)} — ${bits.join("; ")||"no forcing resources"}</div>`;
  }
 }
 if(d.king_why){
  for(const s of ["white","black"]){
   const k=d.king_why[s];
   h+=`<div><b>king ${s[0].toUpperCase()}</b> ${k.danger.toFixed(2)} — ${k.why.join("; ")||"quiet"}</div>`;
  }
 }
 return h;
}
function card(d,i){
 const el=document.createElement("div"); el.className="card"; el.dataset.fen=d.fen;
 el.dataset.form=d.primary; el.dataset.kind=d.kind||""; el.dataset.type=d.type; el.dataset.id=d.id; el.dataset.sharp=d.sharpness||"";
 const li="https://lichess.org/analysis/"+d.fen.replace(/ /g,"_");
 const lines=d.lines.map(l=>`<div>${(l.cp>0?"+":"")+(l.cp/100).toFixed(2)}  ${l.san}</div>`).join("");
 el.innerHTML=`
  <div class="board">${boardHTML(d.fen)}<div class="idx">${d.turn} to move</div></div>
  <div class="meta">
   <div class="tags">
    <span class="pid" title="click to copy">${d.id}</span>
    ${d.sharpness?`<span class="sharp ${d.sharpness}" title="sharpness (dynamism bucket)">${d.sharpness}</span>`:""}
    ${d.initiative?`<span class="init" title="initiative: engine MultiPV-spread verdict; geometry says why. 'unclear' = strong but unexplained; 'resolves' = imbalance evens out in the line">init W ${d.initiative.w.toFixed(2)} B ${d.initiative.b.toFixed(2)} → ${d.initiative.resolves?"resolves ("+d.initiative.resolves+")":(d.initiative.leader||"balanced")}${d.initiative.mechanism&&d.initiative.mechanism.length?" via "+d.initiative.mechanism.join("+"):""}${d.initiative.deferred?" · "+d.initiative.deferred+"?":""}</span>`:""}
    ${d.only_move?`<span class="om ${d.only_move.razor?'razor':''}">${d.only_move.razor?'RAZOR only-move':'only-move'} ${d.only_move.move} Δ${(d.only_move.gap_cp/100).toFixed(1)}</span>`:""}
    <span class="tag f">${d.primary}${d.kind?":"+d.kind:""}</span>
    <span class="tag">${d.type}</span>
    <span class="tag">${d.mag}</span>
    <span class="tag eval">${evalStr(d.cp)}</span>
    <span class="tag">down ${(d.deficit/100).toFixed(1)} · comp ${(d.comp/100).toFixed(1)}</span>
   </div>
   <div class="read">${d.summary}</div>
   ${d.evidence&&d.evidence.length?`<div class="ev">${d.evidence.map(e=>"&#8226; "+e).join("<br>")}</div>`:""}
   <div class="lines">${lines||"<i>no lines</i>"}</div>
   <details class="why"><summary>why (evidence)</summary>${whyHTML(d)}</details>
   <a class="li" href="${li}" target="_blank" rel="noopener">Open in Lichess &#9654;</a>
   <div class="marks">
    <button data-v="correct">&#10003; correct</button>
    <button data-v="wrong">&#10007; wrong</button>
    <button data-v="unsure">? unsure</button>
   </div>
  </div>`;
 const pid=el.querySelector(".pid");
 pid.onclick=()=>{ navigator.clipboard&&navigator.clipboard.writeText(d.id);
  pid.classList.add("copied"); setTimeout(()=>pid.classList.remove("copied"),700); };
 const v=localStorage.getItem(KEY(d.fen));
 applyMark(el,v);
 el.querySelectorAll(".marks button").forEach(b=>b.onclick=()=>{
  const nv=b.dataset.v; const cur=localStorage.getItem(KEY(d.fen));
  if(cur===nv){localStorage.removeItem(KEY(d.fen)); applyMark(el,null);}
  else {localStorage.setItem(KEY(d.fen),nv); applyMark(el,nv);}
  tally(); filter();
 });
 return el;
}
function applyMark(el,v){
 el.classList.remove("correct","wrong","unsure");
 el.querySelectorAll(".marks button").forEach(b=>b.classList.remove("on-ok","on-bad","on-maybe"));
 if(!v)return; el.classList.add(v);
 const map={correct:"on-ok",wrong:"on-bad",unsure:"on-maybe"};
 const b=el.querySelector(`.marks button[data-v="${v}"]`); if(b)b.classList.add(map[v]);
}
function tally(){
 let c=0,w=0,u=0; DATA.forEach(d=>{const v=localStorage.getItem(KEY(d.fen)); if(v==="correct")c++;else if(v==="wrong")w++;else if(v==="unsure")u++;});
 const done=c+w+u;
 document.getElementById("tally").innerHTML=
  `<b>${DATA.length}</b> total · <b style="color:#2e7d32">${c}</b> correct · <b style="color:#c62828">${w}</b> wrong · <b style="color:#b58900">${u}</b> unsure · <b>${DATA.length-done}</b> unmarked`+
  (done?` · correctness so far <b>${c+w?Math.round(100*c/(c+w)):0}%</b> (of judged)`:"");
}
function filter(){
 const ff=fForm.value,fk=fKind.value,ft=fType.value,un=fUn.checked,fi=fId.value.trim().toUpperCase(),fs=fSharp.value;
 document.querySelectorAll(".card").forEach(el=>{
  const v=localStorage.getItem(el.dataset.fen? "imbrev::"+el.dataset.fen : "");
  let show=(!ff||el.dataset.form===ff)&&(!fk||el.dataset.kind===fk)&&(!ft||el.dataset.type===ft)&&(!un|| !v)&&(!fi||el.dataset.id.includes(fi))&&(!fs||el.dataset.sharp===fs);
  el.classList.toggle("hidden",!show);
 });
}
const grid=document.getElementById("grid");
DATA.forEach((d,i)=>grid.appendChild(card(d,i)));
// populate filters
const fForm=document.getElementById("fForm"),fKind=document.getElementById("fKind"),fType=document.getElementById("fType"),fUn=document.getElementById("fUn"),fSharp=document.getElementById("fSharp");
[...new Set(DATA.map(d=>d.primary))].sort().forEach(v=>fForm.add(new Option(v,v)));
[...new Set(DATA.map(d=>d.kind).filter(Boolean))].sort().forEach(v=>fKind.add(new Option(v,v)));
[...new Set(DATA.map(d=>d.type))].sort().forEach(v=>fType.add(new Option(v,v)));
const SH=["DEAD","QUIET","DYNAMIC","SHARP","RAZOR"];
[...new Set(DATA.map(d=>d.sharpness).filter(Boolean))].sort((a,b)=>SH.indexOf(a)-SH.indexOf(b)).forEach(v=>fSharp.add(new Option(v,v)));
const fId=document.getElementById("fId");
[fForm,fKind,fType,fSharp].forEach(s=>s.onchange=filter); fUn.onchange=filter; fId.oninput=filter;
document.getElementById("export").onclick=()=>{
 const out=DATA.map(d=>({id:d.id,fen:d.fen,type:d.type,primary:d.primary,kind:d.kind,summary:d.summary,verdict:localStorage.getItem(KEY(d.fen))||null}));
 const blob=new Blob([JSON.stringify(out,null,2)],{type:"application/json"});
 const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="compensation_verdicts.json"; a.click();
};
document.getElementById("reset").onclick=()=>{ if(confirm("Clear all marks?")){DATA.forEach(d=>localStorage.removeItem(KEY(d.fen))); document.querySelectorAll(".card").forEach(el=>applyMark(el,null)); tally(); filter();} };
tally();
</script></body></html>"""

out = HTML.replace("__BLOB__", blob)
path = os.path.join(STUDY, "review.html")
with open(path, "w") as f:
    f.write(out)
print("wrote", path, f"({len(out)//1024} KB)")

"""Offline HTML report with embedded data and optional local image assets."""
from __future__ import annotations

import html
import json
from typing import List

from .resolve import COMPLETE, MISSING, NO_ROMS, ONLY_SHARED, PARTIAL

STATUS_ORDER = [COMPLETE, PARTIAL, ONLY_SHARED, MISSING, NO_ROMS]


def rows(rep: dict) -> List[dict]:
    v = rep.get("verify")
    verify = {}
    if v is not None:
        verify.update({p: "ok" for p in v["ok"]})
        verify.update({p: "no_md5" for p in v["no_md5"]})
        verify.update({pr["path"]: pr["status"] for pr in v["problems"]})

    out = []
    for status in STATUS_ORDER:
        for m in rep.get(status, []):
            out.append({
                "n": m["name"] or m["path"].rsplit("/", 1)[-1][:-4],
                "p": m["path"],
                "s": m["setname"],
                "c": m["rbf"],
                "st": status,
                "v": verify.get(m["path"], ""),
                "z": m["zips"],
                "m": [[x["name"], x["crc"], x["zip"]] for x in m.get("missing", [])],
                "f": m.get("found", []),
                "a": "/_alternatives/" in m["path"],
                "sel": m.get("selected"),
                "art": rep.get("artwork", {}).get(m["setname"].lower(), {}),
            })
    out.sort(key=lambda r: r["n"].lower())
    return out


def render(rep: dict) -> str:
    data = {
        "summary": rep["summary"],
        "dry_run": rep["dry_run"],
        "verified": rep.get("verify") is not None,
        "one_per_game": rep.get("one_per_game") is not None,
        "rows": rows(rep),
        "wanted": rep.get("most_wanted", []),
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload).replace(
        "__TITLE__", html.escape("MiSTer arcade report" + (" (dry run)" if rep["dry_run"] else "")))


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f7f7f5; --panel: #ffffff; --text: #1d1d1b; --muted: #6b6b66; --line: #e3e3de;
  --ok: #1f7a3d; --ok-bg: #e3f4e8; --warn: #8a5a00; --warn-bg: #fbefd5;
  --bad: #a32020; --bad-bg: #fbe3e3; --info: #2b5c9e; --info-bg: #e2ecf8; --dim-bg: #ececea;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #161615; --panel: #1f1f1d; --text: #ececea; --muted: #9a9a94; --line: #33332f;
    --ok: #7fd49a; --ok-bg: #1d3a26; --warn: #f0c26a; --warn-bg: #3d3018;
    --bad: #f19a9a; --bad-bg: #432222; --info: #9cc0f0; --info-bg: #1e2f47; --dim-bg: #2a2a27;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1200px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 22px; margin: 0 0 4px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 20px; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px;
  cursor: pointer; text-align: left; color: inherit; font: inherit; }
.card:hover { border-color: var(--muted); }
.card.on { outline: 2px solid var(--info); }
.card b { display: block; font-size: 24px; font-variant-numeric: tabular-nums; }
.card span { color: var(--muted); font-size: 12px; }
.bar { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; align-items: center; }
input, select { font: inherit; color: var(--text); background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 7px 10px; }
input[type=search] { flex: 1 1 260px; min-width: 0; }
label.chk { display: flex; gap: 6px; align-items: center; color: var(--muted); }
.count { color: var(--muted); margin-left: auto; font-variant-numeric: tabular-nums; }
.wrap { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { position: sticky; top: 0; background: var(--panel); font-size: 12px; color: var(--muted);
  cursor: pointer; user-select: none; white-space: nowrap; }
th.sorted::after { content: " \2193"; } th.sorted.asc::after { content: " \2191"; }
tr.row { cursor: pointer; } tr.row:hover td { background: var(--dim-bg); }
td.name { min-width: 260px; } .alt { color: var(--muted); font-size: 12px; }
.chosen { color: var(--info); font-size: 12px; font-weight: 600; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; white-space: nowrap; }
.b-complete, .b-ok { background: var(--ok-bg); color: var(--ok); }
.b-partial { background: var(--warn-bg); color: var(--warn); }
.b-only_shared, .b-no_md5, .b-no_roms { background: var(--dim-bg); color: var(--muted); }
.b-missing, .b-md5_mismatch, .b-file_not_found { background: var(--bad-bg); color: var(--bad); }
.b-none { color: var(--muted); }
tr.detail td { background: var(--bg); }
.detail ul { margin: 4px 0 0; padding-left: 18px; }
details { margin-top: 24px; } summary { cursor: pointer; font-weight: 600; }
.note { color: var(--muted); font-size: 12px; margin-top: 8px; }
.game-heading { display: flex; gap: 10px; align-items: center; }
.thumb { width: 80px; height: 60px; object-fit: contain; background: var(--bg); border-radius: 4px; }
.gallery { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0; }
.gallery figure { margin: 0; }
.gallery img { width: 220px; height: 170px; object-fit: contain; background: var(--panel); }
.gallery figcaption, .game-info { color: var(--muted); font-size: 12px; }
a { color: var(--info); }
</style>
</head>
<body>
<main>
<h1>MiSTer arcade report</h1>
<p class="sub" id="sub"></p>
<div class="cards" id="cards"></div>
<div class="bar">
  <input type="search" id="q" placeholder="Search name, setname, core or zip">
  <select id="fv"><option value="">Any verification</option></select>
  <select id="fc"><option value="">All cores</option></select>
  <label class="chk"><input type="checkbox" id="fa" checked> alternatives</label>
  <label class="chk" id="fsl" hidden><input type="checkbox" id="fs"> only the one chosen per game</label>
  <span class="count" id="count"></span>
</div>
<div class="wrap"><table>
  <thead><tr>
    <th data-k="n">Game</th><th data-k="c">Core</th><th data-k="s">Setname</th>
    <th data-k="st">Status</th><th data-k="v">md5 check</th><th data-k="mc">Missing</th>
  </tr></thead>
  <tbody id="tb"></tbody>
</table></div>
<p class="note">Click a row for its zips and missing files. "only shared" = the only files found are ones many
games use (BIOS, sound chips), so the game itself is not in the collection.</p>
<details id="wanted"><summary>Most wanted files</summary><div class="wrap" style="margin-top:8px"><table>
  <thead><tr><th>CRC</th><th>Name</th><th>Needed by</th><th>Only missing file for</th></tr></thead>
  <tbody id="wb"></tbody></table></div></details>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const ST = {complete: 'complete', partial: 'partial', only_shared: 'only shared', missing: 'missing', no_roms: 'no ROMs needed'};
const VF = {ok: 'md5 ok', no_md5: 'no md5', md5_mismatch: 'md5 different', file_not_found: 'file not found'};
const ORDER = ['complete', 'partial', 'only_shared', 'missing', 'no_roms'];
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
D.rows.forEach(r => { r.mc = r.m.length; r.key = (r.n + ' ' + r.s + ' ' + r.c + ' ' + r.z.join(' ')).toLowerCase(); });

let state = {st: '', q: '', v: '', c: '', alt: true, sel: false, sort: 'n', asc: true, open: new Set()};
try { Object.assign(state, JSON.parse(localStorage.getItem('mab-filters') || '{}'), {open: new Set()}); } catch (e) {}
const save = () => { try { const {open, ...s} = state; localStorage.setItem('mab-filters', JSON.stringify(s)); } catch (e) {} };

const s = D.summary;
document.getElementById('sub').textContent =
  `${s.mra_total} .mra · ${s.input_files} input files · ` +
  (D.verified ? 'md5 checked with --verify' : 'run with --verify to check md5') + (D.dry_run ? ' · dry run' : '');

const cards = document.getElementById('cards');
[['', 'all .mra', s.mra_total]].concat(ORDER.map(k => [k, ST[k], s[k]])).forEach(([k, label, n]) => {
  const b = document.createElement('button');
  b.className = 'card'; b.dataset.st = k;
  b.innerHTML = `<b>${n}</b><span>${esc(label)}</span>`;
  b.onclick = () => { state.st = k; render(); };
  cards.appendChild(b);
});

const fv = document.getElementById('fv'), fc = document.getElementById('fc');
Object.entries(VF).forEach(([k, l]) => fv.add(new Option(l, k)));
fv.add(new Option('not checked', '-'));
[...new Set(D.rows.map(r => r.c))].sort((a, b) => a.localeCompare(b)).forEach(c => fc.add(new Option(c || '?', c)));
const q = document.getElementById('q'), fa = document.getElementById('fa');
q.value = state.q; fv.value = state.v; fc.value = state.c; fa.checked = state.alt;
const fs = document.getElementById('fs');
if (D.one_per_game) { document.getElementById('fsl').hidden = false; fs.checked = state.sel; } else { state.sel = false; }
fs.onchange = () => { state.sel = fs.checked; render(); };
q.oninput = () => { state.q = q.value; render(); };
fv.onchange = () => { state.v = fv.value; render(); };
fc.onchange = () => { state.c = fc.value; render(); };
fa.onchange = () => { state.alt = fa.checked; render(); };
document.querySelectorAll('th[data-k]').forEach(th => th.onclick = () => {
  const k = th.dataset.k; state.asc = state.sort === k ? !state.asc : true; state.sort = k; render();
});

function cmp(a, b) {
  const k = state.sort; let x = a[k], y = b[k];
  if (k === 'st') { x = ORDER.indexOf(x); y = ORDER.indexOf(y); }
  const r = typeof x === 'number' ? x - y : String(x).localeCompare(String(y));
  return (state.asc ? r : -r) || a.n.localeCompare(b.n);
}

function detail(r) {
  let h = `<div class="mono">${esc(r.p)}</div><div>zips: <span class="mono">${esc(r.z.join(', ') || '-')}</span></div>`;
  const art = r.art || {};
  if (art.source) {
    h += `<div>${gameInfo(art)} · <a href="${esc(art.source)}" target="_blank" rel="noopener noreferrer">Information and images: MDK</a></div>`;
    h += `<div class="gallery">${(art.images || []).map(im => `<figure><a href="${esc(im.path)}" target="_blank" rel="noopener"><img src="${esc(im.path)}" alt="${esc(r.n + ' — ' + im.label)}" loading="lazy"></a><figcaption>${esc(im.label)}</figcaption></figure>`).join('')}</div>`;
    if (!(art.images || []).length) h += '<div class="note">No images available</div>';
  }
  if (r.m.length) h += `<div>missing:</div><ul>${r.m.map(([n, c, z]) =>
    `<li class="mono">${esc(z)}: ${esc(n)} &nbsp;crc ${esc(c)}</li>`).join('')}</ul>`;
  if (r.f.length) h += `<div>found only shared files: <span class="mono">${esc(r.f.join(', '))}</span></div>`;
  return h;
}

function gameInfo(art) {
  return [art.year, art.genre, art.manufacturer].filter(x => x && x !== 'N/A').map(esc).join(' · ');
}

function gameHeading(r) {
  const art = r.art || {}, images = art.images || [];
  const im = images.find(i => i.label === 'In-game') || images[0];
  return `<div class="game-heading">${im ? `<img class="thumb" src="${esc(im.path)}" alt="${esc(r.n)}" loading="lazy">` : ''}<div>${esc(r.n)}${r.a ? ' <span class="alt">alternative</span>' : ''}${r.sel ? ' <span class="chosen">chosen</span>' : ''}<div class="game-info">${gameInfo(art)}</div></div></div>`;
}

function render() {
  save();
  cards.querySelectorAll('.card').forEach(c => c.classList.toggle('on', c.dataset.st === state.st));
  document.querySelectorAll('th[data-k]').forEach(th => {
    th.classList.toggle('sorted', th.dataset.k === state.sort); th.classList.toggle('asc', state.asc);
  });
  const needle = state.q.trim().toLowerCase();
  const list = D.rows.filter(r =>
    (!state.st || r.st === state.st) && (state.alt || !r.a) && (!state.sel || r.sel) && (!state.c || r.c === state.c) &&
    (!state.v || (state.v === '-' ? !r.v : r.v === state.v)) && (!needle || r.key.includes(needle))
  ).sort(cmp);
  document.getElementById('count').textContent = `${list.length} shown`;
  document.getElementById('tb').innerHTML = list.map(r => {
    const id = r.p, open = state.open.has(id);
    const v = r.v ? `<span class="badge b-${r.v}">${VF[r.v]}</span>` : '<span class="b-none">-</span>';
    return `<tr class="row" data-id="${esc(id)}">
      <td class="name">${gameHeading(r)}</td>
      <td>${esc(r.c)}</td><td class="mono">${esc(r.s)}</td>
      <td><span class="badge b-${r.st}">${ST[r.st]}</span></td><td>${v}</td>
      <td>${r.mc || ''}</td></tr>` + (open ? `<tr class="detail"><td colspan="6">${detail(r)}</td></tr>` : '');
  }).join('');
}

document.getElementById('tb').onclick = e => {
  const tr = e.target.closest('tr.row'); if (!tr) return;
  const id = tr.dataset.id; state.open.has(id) ? state.open.delete(id) : state.open.add(id); render();
};

document.getElementById('wb').innerHTML = D.wanted.map(w =>
  `<tr><td class="mono">${esc(w.crc)}</td><td class="mono">${esc(w.name)}</td><td>${w.mra_count}</td><td>${w.last_missing_for}</td></tr>`
).join('');
if (!D.wanted.length) document.getElementById('wanted').hidden = true;
render();
</script>
</body>
</html>
"""

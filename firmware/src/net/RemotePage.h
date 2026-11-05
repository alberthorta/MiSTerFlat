#pragma once

// The virtual display page, served at "/". The screen arrives on /ws as binary frames:
// 'F', flags (bit 0: backlight on), width and height (16-bit little-endian), then the RGB565
// pixels (big-endian) run-length coded as RemoteView.cpp describes. Touches go back as text:
// "d x y", "m x y", "u", in screen pixels.
static const char kRemotePage[] = R"HTML(<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b0d11">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="MiSTerLily">
<title>MiSTerLily</title>
<style>
:root { color-scheme: dark; --bg: #0b0d11; --bezel: #1a1d24; --edge: #2a2f3a; --text: #d9dde4; --muted: #7d8594; --ok: #3ccf8e; --warn: #f5a623; }
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
body { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
  padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left));
  -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; }
.bezel { width: 100%; max-width: min(720px, calc((100vh - 120px) * 4 / 3)); padding: 14px; background: var(--bezel);
  border: 1px solid var(--edge); border-radius: 18px; box-shadow: 0 20px 60px rgba(0,0,0,.5), inset 0 1px 0 rgba(255,255,255,.04); }
.screen { position: relative; aspect-ratio: 4 / 3; background: #000; border-radius: 4px; overflow: hidden; }
canvas { display: block; width: 100%; height: 100%; image-rendering: pixelated; touch-action: none; cursor: pointer; transition: opacity .3s; }
.asleep canvas { opacity: .25; }
.note { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; text-align: center;
  padding: 16px; color: var(--muted); pointer-events: none; }
.note[hidden] { display: none; }
.bar { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--warn); }
.live .dot { background: var(--ok); }
</style>
</head>
<body>
<div class="bezel"><div class="screen" id="screen">
  <canvas id="c" width="320" height="240" aria-label="MiSTerLily display"></canvas>
  <div class="note" id="note">Connecting…</div>
</div></div>
<div class="bar" id="bar"><span class="dot"></span><span id="state">Connecting</span></div>
<script>
'use strict';
const c = document.getElementById('c'), g = c.getContext('2d'), note = document.getElementById('note');
const bar = document.getElementById('bar'), state = document.getElementById('state'), screen = document.getElementById('screen');
let ws = null, img = null, down = false, last = null, repeat = null;

function show(text, live) {
  state.textContent = text;
  bar.classList.toggle('live', live);
}
function draw(buf) {
  const b = new Uint8Array(buf);
  if (b[0] !== 70) return;
  const light = b[1] & 1, w = b[2] | b[3] << 8, h = b[4] | b[5] << 8;
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; img = null; }
  if (!img) img = g.createImageData(w, h);
  const px = img.data;
  let i = 6, o = 0;
  const put = (hi, lo) => {
    const v = hi << 8 | lo;
    px[o] = (v >> 11) * 255 / 31; px[o + 1] = (v >> 5 & 63) * 255 / 63; px[o + 2] = (v & 31) * 255 / 31; px[o + 3] = 255;
    o += 4;
  };
  while (i < b.length && o < px.length) {
    const t = b[i++];
    if (t & 128) { const hi = b[i], lo = b[i + 1]; i += 2; for (let n = (t & 127) + 1; n--;) put(hi, lo); }
    else { for (let n = t + 1; n--; i += 2) put(b[i], b[i + 1]); }
  }
  g.putImageData(img, 0, 0);
  screen.classList.toggle('asleep', !light);
  note.hidden = !!light;
  note.textContent = 'The display is asleep. Tap to wake it.';
}
function connect() {
  ws = new WebSocket('ws://' + location.host + '/ws');
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => show('Live', true);
  ws.onmessage = e => draw(e.data);
  ws.onclose = () => {
    show('Reconnecting', false);
    note.hidden = false; note.textContent = 'Reconnecting…';
    setTimeout(connect, 1500);
  };
}
function send(text) { if (ws && ws.readyState === 1) ws.send(text); }
function point(e) {
  const r = c.getBoundingClientRect();
  return [Math.round((e.clientX - r.left) * c.width / r.width), Math.round((e.clientY - r.top) * c.height / r.height)];
}
c.addEventListener('pointerdown', e => {
  c.setPointerCapture(e.pointerId);
  down = true; last = point(e);
  send('d ' + last.join(' '));
  // A finger held still must stay down: the board lifts it after 2.5 s of silence.
  repeat = setInterval(() => send('d ' + last.join(' ')), 1000);
  e.preventDefault();
});
c.addEventListener('pointermove', e => { if (down) { last = point(e); send('m ' + last.join(' ')); } });
const up = () => { if (!down) return; down = false; clearInterval(repeat); send('u'); };
c.addEventListener('pointerup', up);
c.addEventListener('pointercancel', up);
document.addEventListener('visibilitychange', () => { if (document.hidden) up(); });
connect();
</script>
</body>
</html>
)HTML";

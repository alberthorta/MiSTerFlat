'use strict';
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmtBytes = b => b == null ? '–' : b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : (b / 1e6).toFixed(0) + ' MB';
const fmtUptime = s => {
  if (s == null) return '–';
  s = Math.floor(s);
  const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return d ? d + 'd ' + h + 'h' : h ? h + 'h ' + m + 'm' : m + ' min';
};
const fmtDate = t => new Date(t * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
const artUrl = art => '/art/' + art.split('/').map(encodeURIComponent).join('/');
const icon = name => '<svg><use href="#i-' + name + '"/></svg>';

function toast(msg, error) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.toggle('error', !!error);
  t.classList.add('show');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), error ? 4000 : 2500);
}
const fail = e => toast(e.message || String(e), true);

async function api(path, body) {
  const r = await fetch(path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

async function upload(path, file) {
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

/* ---------- Routing: #now, #games, #games/<system>, #cores, #saves, #display, #settings ---------- */
const VIEWS = ['now', 'games', 'cores', 'saves', 'display', 'settings'];
const TITLES = {now: 'Now', games: 'Games', cores: 'Core options', saves: 'Saves', display: 'Display', settings: 'Settings'};
let view = '';

function route() {
  const [name, arg] = location.hash.replace(/^#/, '').split('/');
  const next = VIEWS.includes(name) ? name : 'now';
  if (next === 'games') {
    const sys = arg ? decodeURIComponent(arg) : '';
    if (sys !== system) { system = sys; paintSystems(); }
    $('q').placeholder = system && names[system] ? 'Search ' + names[system] : 'Search all games';
  }
  const changed = next !== view;
  view = next;
  for (const v of VIEWS) $('view-' + v).hidden = v !== view;
  for (const a of document.querySelectorAll('[data-nav]')) {
    const on = a.dataset.nav === view;
    a.classList.toggle('on', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  $('title').textContent = TITLES[view];
  if (changed) window.scrollTo(0, 0);
  loaders[view](arg ? decodeURIComponent(arg) : '');
}
window.addEventListener('hashchange', route);

const loaders = {
  now() { recent(); pads().catch(() => {}); },
  games() { games(); },
  cores(arg) { coreList(arg).catch(fail); },
  saves() { cards().catch(fail); },
  display() { lily().catch(fail); },
  settings() { settings().catch(fail); },
};

/* ---------- Status: top strip, hero, vitals ---------- */
let wasScanning = false, heroKey = null, scanning = false;

async function status() {
  let s;
  try { s = await api('/api/status'); }
  catch (e) {
    $('dot').className = 'dot off';
    document.body.classList.add('offline');
    $('now-text').textContent = 'Not answering';
    paintHero(null);
    return;
  }
  scanning = s.scanning;
  const now = s.now, inMenu = !now.core || now.core.toUpperCase() === 'MENU';
  $('dot').className = 'dot' + (scanning ? ' busy' : '');
  document.body.classList.remove('offline');
  $('now-text').textContent = inMenu ? 'In the menu' : (now.game || now.core);
  paintHero(now);
  paintVitals(s.system);
  if (wasScanning && !scanning) { systems().then(games); recent(); toast('Library updated'); }
  wasScanning = scanning;
  $('rescan').disabled = scanning;
  $('rescan').innerHTML = icon('refresh') + (scanning ? 'Scanning…' : 'Rescan');
  $('library-sub').textContent = scanning ? 'Reading the SD card. The page updates when it ends.'
    : s.indexed ? 'Indexed ' + fmtDate(s.indexed) + '.' : 'Not indexed yet.';
}

function paintHero(now) {
  const key = now ? (now.core || '') + '|' + (now.game || '') + '|' + (now.art || '') : 'offline';
  if (key === heroKey) return;
  heroKey = key;
  const hero = $('hero'), cover = $('hero-cover'), actions = $('hero-actions');
  const inMenu = !now || !now.core || now.core.toUpperCase() === 'MENU';
  hero.classList.toggle('has-art', !!(now && now.art));
  $('hero-bg').style.backgroundImage = now && now.art ? 'url("' + artUrl(now.art) + '")' : '';
  if (now && now.art) {
    const img = new Image();
    img.alt = '';
    img.src = artUrl(now.art);
    img.onload = () => img.classList.add('loaded');
    img.onerror = () => { cover.innerHTML = '<svg class="mark-big"><use href="#i-mark"/></svg>'; hero.classList.remove('has-art'); };
    cover.replaceChildren(img);
  } else {
    cover.innerHTML = '<svg class="mark-big"><use href="#i-mark"/></svg>';
  }
  if (!now) {
    $('hero-kicker').textContent = 'MiSTer is not answering';
    $('hero-title').textContent = 'Offline';
    actions.innerHTML = '';
    return;
  }
  if (inMenu) {
    $('hero-kicker').textContent = 'In the menu';
    $('hero-title').textContent = 'Nothing is running';
    actions.innerHTML = '<a class="btn primary" href="#games">' + icon('games') + 'Browse games</a>';
  } else {
    $('hero-kicker').textContent = now.game ? 'Playing on ' + (names[now.system] || now.core) : 'Running';
    $('hero-title').textContent = now.game || now.core;
    actions.innerHTML = '<button class="btn" id="menu">' + icon('menu') + 'Back to menu</button>';
    $('menu').onclick = async ev => {
      ev.currentTarget.disabled = true;
      try { await api('/api/menu', {}); toast('Back to the menu'); setTimeout(status, 1500); } catch (e) { fail(e); }
    };
  }
}

function vital(label, value, extra, pct) {
  return '<div class="vital"><span>' + label + '</span><strong>' + esc(value) + (extra ? ' <em>' + esc(extra) + '</em>' : '') + '</strong>'
    + (pct != null ? '<div class="meter"><i class="' + (pct > 90 ? 'high' : '') + '" style="width:' + pct.toFixed(0) + '%"></i></div>' : '') + '</div>';
}

function paintVitals(sys) {
  const used = sys.mem.total - sys.mem.available, memPct = used / sys.mem.total * 100;
  const disk = sys.disk, diskPct = disk ? (disk.total - disk.free) / disk.total * 100 : null;
  const wifi = sys.wifi;
  const signal = !wifi ? '' : wifi.level >= -60 ? 'good' : wifi.level >= -70 ? 'ok' : 'weak';
  $('vitals').innerHTML = [
    vital('CPU', sys.cpu == null ? (sys.load ? sys.load[0] : '–') : sys.cpu + ' %', sys.cpu == null && sys.load ? 'load' : ''),
    vital('Memory', fmtBytes(used), 'of ' + fmtBytes(sys.mem.total), memPct),
    vital('SD card', disk ? fmtBytes(disk.free) : '–', disk ? 'free' : '', diskPct),
    vital('Uptime', fmtUptime(sys.uptime)),
    vital('Address', sys.ip || '–'),
    vital('Wi-Fi', wifi ? (wifi.ssid || wifi.iface) : 'Cable', wifi ? signal + ', ' + Math.round(wifi.level) + ' dBm' : ''),
  ].join('');
  $('nav-foot').textContent = (sys.ip || '') + (sys.kernel ? '\n' + sys.kernel : '');
}

/* ---------- Games: cards, systems, search, sheet ---------- */
let system = '', names = {}, timer = null, listKey = null, sheetGame = null;
const byKey = new Map();

function card(g, sub) {
  const key = g.system + '\n' + g.path;
  byKey.set(key, g);
  const b = document.createElement('button');
  b.className = 'card';
  b.type = 'button';
  b.dataset.key = key;
  const cover = g.art ? '<img loading="lazy" alt="" src="' + artUrl(g.art) + '">' : '<span class="noart">' + esc(names[g.system] || g.system) + '</span>';
  b.innerHTML = '<div class="cover">' + cover + '<span class="play">' + icon('play') + '</span></div><div class="name">' + esc(g.name) + '</div>'
    + (sub ? '<div class="sub">' + esc(sub) + '</div>' : '');
  return b;
}

function onImageError(ev) {
  const img = ev.target;
  if (img.tagName !== 'IMG' || !img.closest('.cover')) return;
  const b = img.closest('.card'), g = b && byKey.get(b.dataset.key);
  const cover = img.parentNode;
  img.remove();
  if (g) cover.insertAdjacentHTML('afterbegin', '<span class="noart">' + esc(names[g.system] || g.system) + '</span>');
}
document.addEventListener('error', onImageError, true);

function onCardClick(ev) {
  const b = ev.target.closest('.card');
  if (b) openSheet(byKey.get(b.dataset.key));
}
$('games').addEventListener('click', onCardClick);
$('recent').addEventListener('click', onCardClick);

function openSheet(g) {
  if (!g) return;
  sheetGame = g;
  $('sheet-cover').innerHTML = g.art ? '<img alt="" src="' + artUrl(g.art) + '">' : '';
  $('sheet-name').textContent = g.name;
  $('sheet-sub').textContent = [names[g.system] || g.system, g.alt ? 'other version' : '', g.discs ? g.discs + ' discs' : ''].filter(Boolean).join(', ');
  $('sheet-play').disabled = false;
  $('sheet').showModal();
  $('sheet-play').focus({preventScroll: true});
}
$('sheet-close').onclick = () => $('sheet').close();
$('sheet').onclick = ev => { if (ev.target === $('sheet')) $('sheet').close(); };
$('sheet-play').onclick = async () => {
  const g = sheetGame;
  $('sheet-play').disabled = true;
  try {
    await api('/api/launch', {system: g.system, path: g.path});
    $('sheet').close();
    toast('Loading ' + g.name);
    setTimeout(() => { status(); recent(); }, 1500);
  } catch (e) { fail(e); $('sheet-play').disabled = false; }
};

async function recent() {
  const list = await api('/api/recent').catch(() => []);
  $('recentbox').hidden = !list.length;
  $('recent').replaceChildren(...list.slice(0, 10).map(g => card(g, names[g.system] || g.system)));
}

let systemList = [];
async function systems() {
  systemList = await api('/api/systems');
  names = Object.fromEntries(systemList.map(s => [s.id, s.name]));
  paintSystems();
  if (!systemList.length) $('hint').textContent = 'No games found yet. The first scan can take a minute.';
  if (view === 'games' && system) $('q').placeholder = 'Search ' + (names[system] || system);
}

function paintSystems() {
  const box = $('systems');
  const all = {id: '', name: 'All', count: systemList.reduce((n, s) => n + s.count, 0)};
  box.replaceChildren(...[all, ...systemList].map(s => {
    const a = document.createElement('a');
    a.className = 'chip' + (s.id === system ? ' on' : '');
    a.href = s.id ? '#games/' + encodeURIComponent(s.id) : '#games';
    a.setAttribute('role', 'tab');
    a.setAttribute('aria-selected', s.id === system ? 'true' : 'false');
    a.innerHTML = esc(s.name) + '<small>' + s.count + '</small>';
    return a;
  }));
  const on = box.querySelector('.on');
  if (on && box.scrollWidth > box.clientWidth) on.scrollIntoView({block: 'nearest', inline: 'center'});
}

async function games() {
  const q = $('q').value.trim(), alt = $('alt').getAttribute('aria-pressed') === 'true';
  const key = system + '\n' + q + '\n' + alt;
  if (key === listKey) return;
  listKey = key;
  if (!system && !q) {
    $('games').replaceChildren();
    $('listtitle').textContent = 'Games';
    $('listcount').textContent = '';
    $('hint').textContent = 'Pick a system or type a name.';
    $('hint').hidden = false;
    return;
  }
  const list = await api('/api/games?' + new URLSearchParams({system, q, alt: alt ? '1' : '0'}));
  if (key !== listKey) return;
  $('listtitle').textContent = (system ? names[system] || system : 'All systems') + (q ? ': “' + q + '”' : '');
  $('listcount').textContent = list.length >= 500 ? 'first 500' : list.length + (list.length === 1 ? ' game' : ' games');
  const frag = document.createDocumentFragment();
  for (const g of list) frag.append(card(g, [system ? '' : names[g.system], g.alt ? 'other version' : '', g.discs ? g.discs + ' discs' : ''].filter(Boolean).join(', ')));
  $('games').replaceChildren(frag);
  $('hint').hidden = list.length > 0 && list.length < 500;
  $('hint').textContent = list.length ? 'Showing the first 500. Type to narrow the list.' : 'No match.';
}

$('q').oninput = () => { clearTimeout(timer); timer = setTimeout(games, 250); };
$('alt').onclick = () => { $('alt').setAttribute('aria-pressed', $('alt').getAttribute('aria-pressed') === 'true' ? 'false' : 'true'); games(); };

/* ---------- Now: controllers ---------- */
async function pads() {
  const c = await api('/api/controllers');
  $('motion').checked = c.block_motion_sensors;
  const box = $('pads');
  if (!c.devices.length) { box.innerHTML = '<p class="help" style="padding-top:14px">No controllers connected.</p>'; return; }
  box.replaceChildren(...c.devices.map(d => {
    const div = document.createElement('div');
    div.className = 'pad';
    const tags = [];
    if (d.ignored) tags.push('<span class="tag off">Ignored' + (d.offline ? ', not connected' : '') + '</span>');
    for (const p of d.parts) tags.push('<span class="tag">' + esc(p.kind) + (p.blocked ? ', held' : '') + '</span>');
    const meta = [d.bus, d.id, d.address].filter(Boolean).map(esc).join(' ');
    div.innerHTML = icon('pad') + '<div class="row-text"><span>' + esc(d.name) + '</span>'
      + '<span class="meta">' + (d.battery != null ? '<span class="battery"><i><b class="' + (d.battery <= 20 ? 'low' : '') + '" style="width:' + Math.max(2, d.battery * .18) + 'px"></b></i>'
        + d.battery + ' %' + (d.charging ? ', charging' : '') + '</span>' : '') + tags.join('') + (meta ? '<span>' + meta + '</span>' : '') + '</span></div>';
    if (d.address) {
      const b = document.createElement('button');
      b.className = 'btn small';
      b.textContent = d.ignored ? 'Stop ignoring' : 'Ignore';
      b.onclick = async () => {
        if (!d.ignored && !confirm('Ignore ' + d.name + '? MiSTer will not get its input, and Bluetooth devices are blocked.')) return;
        try { await api('/api/controllers/ignore', {address: d.address, name: d.name, ignore: !d.ignored}); setTimeout(pads, 3500); }
        catch (e) { fail(e); }
      };
      div.append(b);
    }
    return div;
  }));
}
$('motion').onchange = async () => {
  try { await api('/api/controllers/motion', {enabled: $('motion').checked}); setTimeout(pads, 3500); }
  catch (e) { fail(e); }
};
$('rescan').onclick = async () => {
  try { await api('/api/rescan', {}); wasScanning = true; status(); } catch (e) { fail(e); }
};

/* ---------- Settings ---------- */
let options = null, custom = {};

function fill(sel, values, current, extra) {
  sel.replaceChildren();
  const groups = {};
  for (const v of (extra || []).concat(values)) {
    const slash = v.lastIndexOf('/');
    const g = slash < 0 ? '' : v.slice(0, slash);
    (groups[g] = groups[g] || []).push(v);
  }
  for (const [g, list] of Object.entries(groups)) {
    const parent = g ? Object.assign(document.createElement('optgroup'), {label: g}) : sel;
    for (const v of list) parent.append(new Option(v === '' ? (sel.dataset.empty || 'None') : g ? v.slice(g.length + 1).replace(/\.txt$/, '') : v, v));
    if (g) sel.append(parent);
  }
  if (current && ![...sel.options].some(o => o.value === current)) sel.append(new Option(current + ' (missing)', current));
  sel.value = current || '';
}

async function settings() {
  if (!options) options = await api('/api/settings/options');
  const s = await api('/api/settings');
  custom = s.custom;
  $('vol').value = s.volume.level;
  $('volval').textContent = s.volume.muted ? 'muted' : s.volume.level + ' / 7';
  $('mute').textContent = s.volume.muted ? 'Unmute' : 'Mute';
  $('mute').dataset.muted = s.volume.muted ? '1' : '';
  const vs = $('vscale');
  vs.replaceChildren(...Object.entries(options.vscale_modes).map(([k, v]) => new Option(v, k)));
  vs.value = s.ini.vscale_mode;
  for (const [id, list, cur] of [['vmode', options.video_modes, s.ini.video_mode], ['dvi', options.dvi_modes, s.ini.dvi_mode]]) {
    const sel = $(id);
    sel.replaceChildren(...Object.entries(list).map(([k, v]) => new Option(v, k)));
    if (cur && !(cur in list)) sel.append(new Option(cur + ' (set by hand)', cur));
    sel.value = cur;
  }
  for (const sec of ['MiSTer', 'arcade', 'arcade_vertical'])
    fill($('p-' + sec), options.presets, s.ini.preset_default[sec], ['']);
  const presetNames = Object.keys(custom);
  $('custombox').hidden = !presetNames.length;
  if (presetNames.length) {
    const keep = $('cp-name').value;
    fill($('cp-name'), presetNames, presetNames.includes(keep) ? keep : presetNames[0]);
    showPreset();
  }
}

function showPreset() {
  const p = custom[$('cp-name').value] || {};
  fill($('cp-hfilter'), options.filters, p.hfilter);
  fill($('cp-vfilter'), options.filters, p.vfilter, ['same']);
  fill($('cp-gamma'), options.gamma, p.gamma, ['off']);
  fill($('cp-mask'), options.masks, p.mask, ['']);
  fill($('cp-maskmode'), options.maskmodes, p.maskmode || 'off');
}

async function setIni(section, key, value) {
  try { await api('/api/settings/ini', {section, key, value}); toast('Saved. Applies on the next core load.'); }
  catch (e) { fail(e); settings(); }
}

$('vol').oninput = () => { $('volval').textContent = $('vol').value + ' / 7'; };
$('vol').onchange = async () => { try { await api('/api/settings/volume', {level: +$('vol').value}); } catch (e) { fail(e); } };
$('mute').onclick = async () => {
  const mute = !$('mute').dataset.muted;
  try { await api('/api/settings/volume', {mute}); setTimeout(settings, 1500); } catch (e) { fail(e); }
};
$('vscale').onchange = () => setIni('MiSTer', 'vscale_mode', $('vscale').value);
$('vmode').onchange = () => setIni('MiSTer', 'video_mode', $('vmode').value);
$('dvi').onchange = () => setIni('MiSTer', 'dvi_mode', $('dvi').value);
for (const sec of ['MiSTer', 'arcade', 'arcade_vertical'])
  $('p-' + sec).onchange = ev => setIni(sec, 'preset_default', ev.target.value);
$('cp-name').onchange = showPreset;
$('cp-save').onclick = async () => {
  const fields = Object.fromEntries(['hfilter', 'vfilter', 'gamma', 'mask', 'maskmode'].map(k => [k, $('cp-' + k).value]));
  fields.sfilter = (custom[$('cp-name').value] || {}).sfilter || 'same';
  try { await api('/api/settings/preset', {name: $('cp-name').value, fields}); toast('Preset saved. Applies on the next core load.'); settings(); }
  catch (e) { fail(e); }
};
/* ---------- Power sheet: rail button (desktop) and header icon (phone) ---------- */
// The sheet is the first step; the chosen action asks for a second tap, so a stray tap does nothing.
let powerArmed = null, powerArmTimer = null;
function powerDisarm() {
  powerArmed = null; clearTimeout(powerArmTimer);
  for (const id of ['reboot', 'poweroff']) $(id).classList.remove('armed');
  $('power-confirm').hidden = true;
}
async function openPower() {
  powerDisarm();
  $('power').showModal();
  $('power-title').focus({preventScroll: true});
  try { $('poweroff').hidden = !(await api('/api/lily')).power_off; } catch (e) { $('poweroff').hidden = true; }
}
async function powerAction(id) {
  if (powerArmed !== id) {
    powerDisarm();
    powerArmed = id;
    $(id).classList.add('armed');
    $('power-confirm').textContent = id === 'reboot' ? 'Tap Reboot again to reboot now.' : 'Tap Power off again to switch the MiSTer off.';
    $('power-confirm').hidden = false;
    powerArmTimer = setTimeout(powerDisarm, 4000);
    return;
  }
  powerDisarm();
  try {
    await api(id === 'reboot' ? '/api/reboot' : '/api/poweroff', {});
    $('power').close();
    toast(id === 'reboot' ? 'Rebooting…' : 'Shutting down…');
  } catch (e) { fail(e); }
}
$('nav-power').onclick = openPower;
$('top-power').onclick = openPower;
$('power-close').onclick = () => $('power').close();
$('power').onclose = powerDisarm;
$('power').onclick = e => { if (e.target === $('power')) $('power').close(); };
$('reboot').onclick = () => powerAction('reboot');
$('poweroff').onclick = () => powerAction('poweroff');

/* ---------- Display: MiSTerLily ---------- */
let lilyTimer = null;
const FONT_LABELS = {c64: 'Commodore 64', '7seg': 'Seven segments', big: 'Big digits', sans: 'Sans',
  orbitron: 'Orbitron', serif: 'Serif', mono: 'Typewriter', retro16: 'Retro thin'};
const fontLabel = n => FONT_LABELS[n] || n;

async function lily(refresh) {
  const l = await api('/api/lily' + (refresh ? '?refresh=1' : ''));
  $('lily-panel').hidden = !l.installed;
  $('lily-none').hidden = l.installed;
  if (!l.installed) return l;
  const job = l.job, running = !!(job && job.running);
  $('lily-model').textContent = l.board ? (l.model || 'MiSTerLily display') : 'Display not connected';
  $('lily-conn').textContent = l.board ? 'Connected over USB.' : 'Check the USB cable, then press Check again.';
  $('lily-fw').textContent = l.board ? 'Installed v' + l.board : 'Installed version unknown';
  $('lily-state').textContent = l.latest ? 'Latest release v' + l.latest + (l.latest === l.board ? ', up to date.' : '.') : (l.error || '');
  $('lily-latest').textContent = !l.latest ? 'Update firmware' : l.latest === l.board ? 'Reinstall v' + l.latest : 'Update to v' + l.latest;
  $('lily-latest').disabled = running || !l.latest || !l.board;
  $('lily-file').disabled = running || !l.board;
  $('lily-job').hidden = !job;
  const d = l.display;
  $('lily-display').hidden = !d;
  $('lily-nodisplay').hidden = !!d;
  // Not while the user moves the slider or has the list open: a refresh would undo the choice.
  if (d && document.activeElement !== $('lily-bright') && document.activeElement !== $('lily-font')) {
    $('lily-bright').max = d.brightness_max;
    $('lily-bright').value = d.brightness;
    $('lily-brightval').textContent = d.brightness + ' / ' + d.brightness_max;
    const sel = $('lily-font');
    if (sel.options.length !== d.clockfonts.length)
      sel.replaceChildren(...d.clockfonts.map((n, i) => new Option(fontLabel(n), i)));
    sel.value = d.clockfont;
  }
  if (job) {
    $('lily-progress').value = job.progress;
    $('lily-step').textContent = job.error ? 'Error: ' + job.error
      : job.done ? 'Done: the display runs v' + job.done + '.' : job.step;
  }
  clearTimeout(lilyTimer);
  if (running) lilyTimer = setTimeout(() => lily().catch(() => {}), 1000);
  return l;
}

async function lilySet(setting, value) {
  try { await api('/api/lily/display', {setting, value}); } catch (e) { fail(e); }
}
$('lily-bright').oninput = () => { $('lily-brightval').textContent = $('lily-bright').value + ' / ' + $('lily-bright').max; };
$('lily-bright').onchange = () => lilySet('brightness', +$('lily-bright').value);
$('lily-font').onchange = () => lilySet('clockfont', +$('lily-font').value);
$('lily-latest').onclick = async () => {
  if (!confirm($('lily-latest').textContent + ' on the MiSTerLily display? Do not unplug it while it runs.')) return;
  try { await api('/api/lily/flash', {}); lily(); } catch (e) { fail(e); }
};
$('lily-file').onclick = () => { $('lily-input').value = ''; $('lily-input').click(); };
$('lily-input').onchange = async () => {
  const file = $('lily-input').files[0];
  if (!file || !confirm('Flash ' + file.name + ' on the MiSTerLily display? The file is checked before the display is touched.')) return;
  try { await upload('/api/lily/upload', file); lily(); } catch (e) { fail(e); }
};
$('lily-check').onclick = async () => {
  const b = $('lily-check');
  b.disabled = true; b.textContent = 'Checking…';
  try {
    const l = await lily(true);
    toast(l.error ? l.error : !l.latest ? 'No release found'
      : l.latest === l.board ? 'Up to date: v' + l.latest : 'v' + l.latest + ' is available');
  } catch (e) { fail(e); }
  b.disabled = false; b.textContent = 'Check again';
};

/* ---------- Saves: PlayStation memory cards ---------- */
let uploadTarget = null;

async function cards() {
  const c = await api('/api/psx/cards');
  $('cardwarn').hidden = !c.psx_running;
  if (!c.cards.length) { $('cards').innerHTML = '<p class="empty">No PlayStation games in the library.</p>'; return; }
  $('cards').replaceChildren(...c.cards.map(cardInfo => {
    const div = document.createElement('div');
    div.className = 'save';
    const n = cardInfo.saves.length;
    const state = !cardInfo.exists ? 'No card yet. Upload one, or the core makes it the first time you save.'
      : cardInfo.error ? cardInfo.error : n ? n + (n === 1 ? ' save' : ' saves') : 'Card is empty.';
    const list = n ? '<ul>' + cardInfo.saves.map(s => '<li><span>' + esc(s.title || s.code) + '</span><code>' + esc(s.code) + ', '
      + s.blocks + ' block' + (s.blocks > 1 ? 's' : '') + '</code></li>').join('') + '</ul>' : '';
    div.innerHTML = '<h3>' + esc(cardInfo.game) + '</h3><p class="state' + (n ? ' has' : '') + '">' + esc(state) + '</p>' + list
      + (cardInfo.exists ? '<p class="file">' + esc(cardInfo.file) + ', ' + fmtDate(cardInfo.modified) + '</p>' : '')
      + '<div class="acts"></div>';
    const acts = div.querySelector('.acts');
    if (cardInfo.exists) {
      const a = document.createElement('a');
      a.className = 'btn';
      a.href = '/api/psx/cards/download?' + new URLSearchParams({file: cardInfo.file});
      a.innerHTML = icon('download') + 'Download';
      acts.append(a);
    }
    const up = document.createElement('button');
    up.className = 'btn';
    up.innerHTML = icon('upload') + (cardInfo.exists ? 'Replace…' : 'Upload…');
    up.onclick = () => { uploadTarget = cardInfo; $('cardfile').value = ''; $('cardfile').click(); };
    acts.append(up);
    return div;
  }));
}

$('cardfile').onchange = async () => {
  const file = $('cardfile').files[0];
  if (!file || !uploadTarget) return;
  if (uploadTarget.exists && !confirm('Replace the card of ' + uploadTarget.game + ' with ' + file.name + '? The current card is backed up.')) return;
  try {
    const data = await upload('/api/psx/cards/upload?' + new URLSearchParams({file: uploadTarget.file}), file);
    toast('Card saved: ' + data.saves.length + ' save(s)');
    if (data.psx_running && confirm('The PlayStation core is running. Reload the game now so it reads the new card?')) {
      const r2 = await api('/api/psx/reload', {});
      toast('Reloading ' + r2.game);
    }
    cards();
  } catch (e) { fail(e); }
};

/* ---------- Cores: OSD options ---------- */
let coreData = null;

async function coreList(wanted) {
  const list = await api('/api/cores');
  const sel = $('core'), keep = wanted || sel.value;
  sel.replaceChildren(new Option('Pick a core…', ''), ...list.map(c => new Option(c.id, c.id)));
  sel.value = list.some(c => c.id === keep) ? keep : '';
  if (sel.value) coreShow();
  else {
    $('coreopts').replaceChildren();
    $('coresave').hidden = true;
    $('corerun').hidden = true;
    $('corenote').textContent = list.length + ' cores. The options are the ones of the core\'s OSD menu.';
  }
}

async function coreShow() {
  const id = $('core').value;
  if (!id) { $('coreopts').replaceChildren(); $('coresave').hidden = true; $('corerun').hidden = true; return; }
  coreData = await api('/api/cores/options?' + new URLSearchParams({core: id}));
  $('corenote').textContent = 'Saved in config/' + coreData.cfg + (coreData.saved ? '' : ' (not saved yet: defaults shown)')
    + '. Applies the next time the core loads.';
  $('corerun').hidden = !coreData.running;
  const pages = {};
  for (const o of coreData.options) (pages[o.page || 'Main'] = pages[o.page || 'Main'] || []).push(o);
  const frag = document.createDocumentFragment();
  for (const [title, opts] of Object.entries(pages)) {
    const head = document.createElement('div');
    head.className = 'block-head';
    head.innerHTML = '<h2>' + esc(title) + '</h2>';
    const group = document.createElement('div');
    group.className = 'group';
    for (const o of opts) {
      const row = document.createElement('div');
      row.className = 'row stack';
      const label = document.createElement('label');
      label.className = 'row-text';
      label.textContent = o.label;
      label.htmlFor = 'opt-' + o.id;
      const sel = document.createElement('select');
      sel.id = 'opt-' + o.id;
      sel.dataset.opt = o.id;
      o.values.forEach((v, i) => sel.append(new Option(v, i)));
      if (o.value >= o.values.length) sel.append(new Option('(value ' + o.value + ')', o.value));
      sel.value = o.value;
      row.append(label, sel);
      group.append(row);
    }
    frag.append(head, group);
  }
  $('coreopts').replaceChildren(frag);
  coreDirty();
}

function coreChanges() {
  const values = {};
  for (const sel of $('coreopts').querySelectorAll('select')) {
    const o = coreData.options[+sel.dataset.opt];
    const changed = +sel.value !== o.value;
    sel.closest('.row').classList.toggle('changed', changed);
    if (changed) values[o.id] = +sel.value;
  }
  return values;
}

function coreDirty() {
  const n = Object.keys(coreChanges()).length;
  $('coresave').hidden = !n;
  $('corecount').textContent = n === 1 ? '1 change' : n + ' changes';
}
$('coreopts').addEventListener('change', coreDirty);
$('core').onchange = () => { history.replaceState(null, '', $('core').value ? '#cores/' + encodeURIComponent($('core').value) : '#cores'); coreShow().catch(fail); };
$('core-save').onclick = async () => {
  const values = coreChanges();
  if (!Object.keys(values).length) { toast('Nothing changed'); return; }
  $('core-save').disabled = true;
  try { await api('/api/cores/options', {core: coreData.id, values}); toast('Saved. Applies the next time the core loads.'); await coreShow(); }
  catch (e) { fail(e); }
  $('core-save').disabled = false;
};

/* ---------- Start ---------- */
status();
systems().catch(() => {}).then(route);
setInterval(status, 5000);

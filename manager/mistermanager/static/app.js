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
const fmtSize = b => b >= 1048576 ? (b / 1048576).toFixed(1).replace(/\.0$/, '') + ' MB' : b >= 1024 ? Math.round(b / 1024) + ' KB' : b + ' bytes';
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

/* ---------- Routing: #now, #games, #games/<system>, #quick, #quick/<system>, #cores, #cores/<core>, #display, #settings ---------- */
const VIEWS = ['now', 'games', 'quick', 'cores', 'display', 'settings'];
const TITLES = {now: 'Now', games: 'Games', quick: 'Systems', cores: 'Cores', display: 'Display', settings: 'Settings'};
let view = '';

function route() {
  // Saves used to be a section of its own; old links land on the PlayStation core.
  if (location.hash === '#saves') { location.replace('#cores/PSX'); return; }
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
  quick(arg) { (arg ? quickSystem(arg) : quickHome()).catch(fail); },
  cores(arg) { coreList(arg).catch(fail); },
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
const verCmp = (a, b) => {
  const x = a.split('.').map(Number), y = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0) ? 1 : -1;
  return 0;
};
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
  const cmp = l.latest && l.board ? verCmp(l.board, l.latest) : -1;
  $('lily-state').textContent = !l.latest ? (l.error || '') : 'Latest release v' + l.latest
    + (cmp === 0 ? ', up to date.' : cmp > 0 ? '. The installed one is newer.' : '.');
  $('lily-latest').textContent = !l.latest ? 'Update firmware' : cmp === 0 ? 'Reinstall v' + l.latest
    : cmp > 0 ? 'Install v' + l.latest : 'Update to v' + l.latest;
  $('lily-latest').disabled = running || !l.latest || !l.board;
  $('lily-file').disabled = running || !l.board;
  $('lily-restart').hidden = !l.board;
  $('lily-restart').disabled = running;
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
  paintStation(l.station);
  if (job) {
    $('lily-progress').value = job.progress;
    $('lily-step').textContent = job.error ? 'Error: ' + job.error
      : job.done ? 'Done: the display runs v' + job.done + '.' : job.step;
  }
  clearTimeout(lilyTimer);
  const sta = l.station, busy = sta && (sta.scanning || sta.state === 'connecting' || staWaiting);
  if (running || (busy && view === 'display')) lilyTimer = setTimeout(() => lily().catch(() => {}), running ? 1000 : 2000);
  return l;
}

/* Display Wi-Fi: the display board's own network, for the virtual display. */
let staPick = null, staWaiting = false;
const signal = rssi => rssi >= -60 ? 'strong' : rssi >= -72 ? 'good' : 'weak';
function paintStation(s) {
  $('sta-panel').hidden = !s;
  if (!s) return;
  const ok = s.state === 'ok';
  if (s.scanning || s.networks.length) staWaiting = false;
  $('sta-title').textContent = ok ? 'Connected to ' + s.ssid
    : s.state === 'connecting' ? 'Joining ' + (s.ssid || 'the network') + '…' : 'Not connected';
  $('sta-sub').textContent = ok ? s.ip + ' · signal ' + signal(s.rssi) + ' (' + s.rssi + ' dBm) · also http://misterlily.local/'
    : 'The display joins a network of its own and shows its screen at an address of its own, also while the MiSTer is off.';
  $('sta-open').hidden = !ok;
  if (ok) $('sta-open').href = 'http://' + s.ip + '/';
  $('sta-error').hidden = !s.error;
  $('sta-error').textContent = s.error;
  $('sta-forget').hidden = !s.ssid;
  const m = s.mister, same = m && ok && m.ssid === s.ssid;
  $('sta-mister').hidden = !m || same;
  if (m && !same) {
    $('sta-mister-title').textContent = 'The MiSTer is on ' + m.ssid;
    $('sta-mister-sub').textContent = m.ok ? 'The display can join the same network with the password the MiSTer has saved.' : m.reason;
    $('sta-copy').disabled = !m.ok;
  }
  $('sta-scan').disabled = s.scanning || staWaiting;
  $('sta-scan').innerHTML = icon('search') + (s.scanning || staWaiting ? 'Looking…' : 'Find networks');
  const list = $('sta-list');
  list.hidden = !s.networks.length;
  list.replaceChildren(...s.networks.map(n => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'sta-net' + (ok && n.ssid === s.ssid ? ' on' : '') + (staPick && staPick.ssid === n.ssid ? ' picked' : '');
    b.innerHTML = '<span>' + esc(n.ssid) + '</span><small>' + (n.mister ? 'MiSTer is on it · ' : n.known ? 'saved on the MiSTer · ' : '')
      + (n.secure ? 'secured · ' : 'open · ') + signal(n.rssi) + '</small>';
    b.onclick = () => staChoose(n);
    return b;
  }));
}
async function staSend(body) {
  await api('/api/lily/wifi', body);
  staWaiting = true;
  setTimeout(() => lily().catch(() => {}), 1500);
}
function staChoose(n) {
  staPick = n;
  // Open, or the MiSTer has its password: join at once.
  if (!n.secure || n.known) { staJoin(''); return; }
  $('sta-join').hidden = false;
  $('sta-join-name').textContent = n.ssid;
  $('sta-pass').value = '';
  $('sta-pass').focus();
  for (const b of $('sta-list').children) b.classList.toggle('picked', b.querySelector('span').textContent === n.ssid);
}
async function staJoin(password) {
  if (!staPick) return;
  try {
    await api('/api/lily/wifi', {action: 'join', ssid: staPick.ssid, password});
    toast('Joining ' + staPick.ssid + '. It takes up to 20 s.');
    $('sta-join').hidden = true;
    $('sta-pass').value = '';
    staPick = null;
    setTimeout(() => lily().catch(() => {}), 2500);
  } catch (e) { fail(e); }
}
$('sta-join').onsubmit = e => { e.preventDefault(); staJoin($('sta-pass').value); };
$('sta-scan').onclick = () => staSend({action: 'scan'}).catch(fail);
$('sta-copy').onclick = async () => {
  try {
    await api('/api/lily/wifi', {action: 'copy'});
    toast('Joining the MiSTer\'s network. It takes up to 20 s.');
    setTimeout(() => lily().catch(() => {}), 2500);
  } catch (e) { fail(e); }
};
armed($('sta-forget'), 'Tap again to forget', async () => {
  await api('/api/lily/wifi', {action: 'forget'});
  toast('The display left the network.');
  $('sta-forget').disabled = false;
  $('sta-forget').classList.remove('armed');
  $('sta-forget').innerHTML = icon('close') + 'Forget network';
  setTimeout(() => lily().catch(() => {}), 2500);
});

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
// The board starts again in a few seconds, its Wi-Fi too; the MiSTer keeps running.
armed($('lily-restart'), 'Tap again to restart', async () => {
  await api('/api/lily/restart', {});
  toast('Restarting the display');
  $('lily-restart').classList.remove('armed');
  $('lily-restart').disabled = false;
  $('lily-restart').textContent = 'Restart';
  setTimeout(() => lily().catch(() => {}), 8000);
});
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

/* ---------- Cores: saves and save states ---------- */
// Delete asks for a second tap on the same button, like the power sheet.
function armed(btn, label, action) {
  const idle = btn.innerHTML;
  let timer = null;
  btn.onclick = async () => {
    if (!btn.classList.contains('armed')) {
      btn.classList.add('armed');
      btn.textContent = label;
      timer = setTimeout(() => { btn.classList.remove('armed'); btn.innerHTML = idle; }, 4000);
      return;
    }
    clearTimeout(timer);
    btn.disabled = true;
    try { await action(); } catch (e) { fail(e); btn.disabled = false; btn.classList.remove('armed'); btn.innerHTML = idle; }
  };
}
function saveItem(title, lines, list) {
  const div = document.createElement('div');
  div.className = 'save';
  div.innerHTML = '<h3>' + esc(title) + '</h3>' + lines.map(l => '<p class="' + l[0] + '">' + esc(l[1]) + '</p>').join('')
    + (list || '') + '<div class="acts"></div>';
  return div;
}
function dlButton(href) {
  const a = document.createElement('a');
  a.className = 'btn';
  a.href = href;
  a.innerHTML = icon('download') + 'Download';
  return a;
}
function delButton(core, kind, file, what) {
  const b = document.createElement('button');
  b.className = 'btn danger-quiet';
  b.innerHTML = icon('close') + 'Delete';
  armed(b, 'Tap again to delete', async () => {
    await api('/api/saves/delete', {core, kind, file});
    toast(what + ' deleted. A backup is kept.');
    coreSaves();
  });
  return b;
}
const savesHref = (core, kind, file) => '/api/saves/download?' + new URLSearchParams({core, kind, file});

let uploadTarget = null, saveTarget = null;

async function coreSaves() {
  const item = coreItem(), box = $('coresaves');
  if (!item || !item.folder) { box.replaceChildren(); return; }
  const core = item.folder;
  const [s, c] = await Promise.all([api('/api/saves?' + new URLSearchParams({core})).catch(() => null),
    core === 'PSX' ? api('/api/psx/cards') : null]);
  if (coreItem() !== item) return;  // another core was picked meanwhile
  const frag = document.createDocumentFragment();
  const head = (title, n) => {
    const d = document.createElement('div');
    d.className = 'block-head';
    d.innerHTML = '<h2>' + esc(title) + '</h2>' + (n ? '<span class="list-count">' + n + '</span>' : '');
    return d;
  };
  if (s && s.running) {
    const p = document.createElement('p');
    p.className = 'banner warn';
    p.innerHTML = icon('alert') + '<span>' + (core === 'PSX'
      ? 'The PlayStation core is running. It reads a card only when a disc loads. After an upload, let the page reload the game and do not open the OSD before that.'
      : 'This core is running and can write its saves again at any time. Load another core before you replace or delete a save.') + '</span>';
    frag.append(p);
  }

  const list = document.createElement('div');
  list.className = 'stack-list';
  if (c) {
    frag.append(head('Memory cards', c.cards.filter(x => x.exists).length));
    for (const card of c.cards) {
      const n = card.saves.length;
      const state = !card.exists ? 'No card yet. Upload one, or the core makes it the first time you save.'
        : card.error ? card.error : n ? n + (n === 1 ? ' save' : ' saves') : 'Card is empty.';
      const inner = n ? '<ul>' + card.saves.map(x => '<li><span>' + esc(x.title || x.code) + '</span><code>' + esc(x.code) + ', '
        + x.blocks + ' block' + (x.blocks > 1 ? 's' : '') + '</code></li>').join('') + '</ul>' : '';
      const lines = [['state' + (n ? ' has' : ''), state]];
      if (card.exists) lines.push(['file', card.file + ' · ' + fmtDate(card.modified)]);
      const div = saveItem(card.game, lines, inner);
      const acts = div.querySelector('.acts');
      if (card.exists) acts.append(dlButton('/api/psx/cards/download?' + new URLSearchParams({file: card.file})));
      const up = document.createElement('button');
      up.className = 'btn';
      up.innerHTML = icon('upload') + (card.exists ? 'Replace…' : 'Upload…');
      up.onclick = () => { uploadTarget = card; $('cardfile').value = ''; $('cardfile').click(); };
      acts.append(up);
      if (card.exists) acts.append(delButton('PSX', 'saves', card.file, 'Card'));
      list.append(div);
    }
    const more = document.createElement('details');
    more.className = 'more';
    more.innerHTML = '<summary>How cards work</summary><p>One card per game folder in <code>saves/PSX</code>. Download gives a <code>.mcd</code> file that PC tools and emulators read. Upload takes <code>.mcd</code>, <code>.mcr</code>, <code>.sav</code>, <code>.gme</code> or <code>.vmp</code>; the old card is backed up first.</p>'
      + '<p>In the game, save to the card in slot 1. MiSTer writes the card to the SD when you use “Save Memory Card” in the OSD, or on its own with Autosave.</p>';
    frag.append(list, more);
  } else if (s) {
    frag.append(head('Saves', s.saves.length));
    for (const x of s.saves) {
      const div = saveItem(x.game, [['file', x.file + ' · ' + fmtSize(x.size) + ' · ' + fmtDate(x.modified)]]);
      const up = document.createElement('button');
      up.className = 'btn';
      up.innerHTML = icon('upload') + 'Replace…';
      up.onclick = () => { saveTarget = x; $('savefile').value = ''; $('savefile').click(); };
      div.querySelector('.acts').append(dlButton(savesHref(core, 'saves', x.file)), up, delButton(core, 'saves', x.file, 'Save'));
      list.append(div);
    }
    if (!s.saves.length) list.innerHTML = '<p class="help">No saves yet. The core makes one the first time a game saves.</p>';
    frag.append(list);
  }

  if (s && s.states.length) {
    frag.append(head('Save states', s.states.length));
    const states = document.createElement('div');
    states.className = 'stack-list';
    for (const x of s.states) {
      const div = saveItem(x.game, [['file', (x.slot ? 'Slot ' + x.slot + ' · ' : '') + fmtSize(x.size) + ' · ' + fmtDate(x.modified)]]);
      div.querySelector('.acts').append(dlButton(savesHref(core, 'states', x.file)), delButton(core, 'states', x.file, 'Save state'));
      states.append(div);
    }
    const note = document.createElement('p');
    note.className = 'more';
    note.textContent = 'A save state only works with the same core version that made it, so there is no upload here.';
    frag.append(states, note);
  }
  box.replaceChildren(frag);
}

$('savefile').onchange = async () => {
  const file = $('savefile').files[0], item = coreItem();
  if (!file || !saveTarget || !item) return;
  if (!confirm('Replace the save of ' + saveTarget.game + ' with ' + file.name + '? The current save is backed up.')) return;
  try {
    await upload('/api/saves/upload?' + new URLSearchParams({core: item.folder, file: saveTarget.file}), file);
    toast('Save replaced. A backup is kept.');
    coreSaves();
  } catch (e) { fail(e); }
};

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
    coreSaves();
  } catch (e) { fail(e); }
};

/* ---------- Cores: OSD options ---------- */
let coreData = null, coreItems = {}, coreTab = 'options';
const coreItem = () => coreItems[$('core').value];
// Options and Saves are two tabs: a core can have 50 options, and its saves must not sit under them.
function coreTabs() {
  const item = coreItem();
  const hasOpts = !!(item && item.options), hasSaves = !!(item && item.folder);
  const tab = !hasOpts ? 'saves' : !hasSaves ? 'options' : coreTab;
  $('coretabs').hidden = !(hasOpts && hasSaves);
  const n = item ? item.saves + item.states : 0;
  $('tab-savecount').textContent = n ? ' ' + n : '';
  for (const b of $('coretabs').querySelectorAll('button')) b.setAttribute('aria-selected', b.dataset.tab === tab);
  $('coreopts').hidden = tab !== 'options';
  $('coresaves').hidden = tab !== 'saves';
  $('corerun').classList.toggle('off-tab', tab !== 'options');
  $('coresave').classList.toggle('off-tab', tab !== 'options');
}
$('coretabs').onclick = e => {
  const b = e.target.closest('button[data-tab]');
  if (!b) return;
  coreTab = b.dataset.tab;
  coreTabs();
};
function coreLabel(c) {
  const n = c.saves + c.states;
  return c.id + (n ? ' · ' + n + (n === 1 ? ' save' : ' saves') : '');
}

async function coreList(wanted) {
  const list = await api('/api/cores');
  coreItems = Object.fromEntries(list.map(c => [c.id, c]));
  const sel = $('core'), keep = wanted || sel.value;
  sel.replaceChildren(new Option('Pick a core…', ''), ...list.map(c => new Option(coreLabel(c), c.id)));
  sel.value = list.some(c => c.id === keep) ? keep : '';
  if (sel.value) coreShow();
  else {
    $('coreopts').replaceChildren();
    $('coresaves').replaceChildren();
    $('coretabs').hidden = true;
    $('coresave').hidden = true;
    $('corerun').hidden = true;
    $('corenote').textContent = list.length + ' cores. Each one has its OSD options and its saves.';
  }
}

async function coreShow() {
  const id = $('core').value;
  if (!id) { $('coreopts').replaceChildren(); $('coresaves').replaceChildren(); $('coretabs').hidden = true; $('coresave').hidden = true; $('corerun').hidden = true; return; }
  coreSaves().catch(fail);
  coreTabs();
  const item = coreItem();
  if (item && !item.options) {
    coreData = null;
    $('corenote').textContent = 'This core has no options here, only its saves.';
    $('corerun').hidden = true;
    $('coreopts').replaceChildren();
    $('coresave').hidden = true;
    return;
  }
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

/* ---------- Systems: the quick launch games of the touch display ---------- */
let quickKey = '', quickData = null, coverGame = null;
const sysCoverUrl = d => '/api/quick/syscover?' + new URLSearchParams({system: d.id, v: d.cover_crc || 'art'});
const quickCover = g => '/api/quick/cover?' + new URLSearchParams({system: quickKey, game: g.id, v: g.crc});

async function quickHome() {
  quickKey = '';
  $('quick-home').hidden = false;
  $('quick-system').hidden = true;
  $('title').textContent = 'Systems';
  const list = await api('/api/quick');
  $('quick-systems').replaceChildren(...list.map(s => {
    const a = document.createElement('a');
    a.className = 'row qsys';
    a.href = '#quick/' + encodeURIComponent(s.id);
    const count = s.count ? s.count + (s.count === 1 ? ' game' : ' games') : 'No games';
    const note = !s.installed ? '<small>Core not on the SD card</small>'
      : s.label !== s.name ? '<small class="renamed">“' + esc(s.label) + '” on the display</small>' : '';
    a.innerHTML = '<span class="row-text">' + esc(s.name) + note + '</span>'
      + '<span class="count' + (s.count ? ' has' : '') + '">' + count + '</span>' + icon('down').replace('<svg>', '<svg style="transform:rotate(-90deg)">');
    return a;
  }));
}

async function quickSystem(key) {
  quickKey = key;
  $('quick-home').hidden = true;
  $('quick-system').hidden = false;
  const [data, list] = await Promise.all([api('/api/quick/games?' + new URLSearchParams({system: key})), api('/api/quick')]);
  if (quickKey !== key) return;
  quickData = data;
  const info = list.find(s => s.id === key) || {};
  $('title').textContent = data.name;
  $('quick-name').textContent = data.name;
  $('quick-count').textContent = data.games.length + ' / ' + data.max;
  $('quick-add').disabled = data.games.length >= data.max;
  $('quick-nocore').hidden = info.installed !== false;
  $('quick-label').textContent = data.label;
  $('quick-syscover').innerHTML = data.has_cover ? '<img alt="" src="' + sysCoverUrl(data) + '">' : '';
  const box = $('quick-games');
  if (!data.games.length) {
    box.innerHTML = '<p class="help">No games yet. Add a few with “Add game”: they show on the display in this order.</p>';
    return;
  }
  box.replaceChildren(...data.games.map((g, i) => {
    const row = document.createElement('div');
    row.className = 'qgame';
    row.innerHTML = '<button class="qthumb" type="button" aria-label="Cover of ' + esc(g.name) + '">'
      + (g.cover ? '<img alt="" src="' + quickCover(g) + '">' : icon('image')) + '</button>'
      + '<div class="qtext"><h3>' + esc(g.name) + '</h3><p' + (g.missing ? ' class="warn">The file is not on the SD card any more' : '>'
      + esc(g.path.split('/').pop())) + '</p></div><div class="qacts"></div>';
    row.querySelector('.qthumb').onclick = () => openCover(g);
    const acts = row.querySelector('.qacts');
    const btn = (name, label, fn, disabled) => {
      const b = document.createElement('button');
      b.className = 'icon-btn';
      b.type = 'button';
      b.setAttribute('aria-label', label);
      b.innerHTML = icon(name);
      b.disabled = !!disabled;
      if (fn) b.onclick = fn;
      acts.append(b);
      return b;
    };
    btn('up', 'Move up', () => quickMove(g, -1), i === 0);
    btn('down', 'Move down', () => quickMove(g, 1), i === data.games.length - 1);
    const del = btn('close', 'Remove ' + g.name);
    armed(del, '', async () => {
      await api('/api/quick/remove', {system: key, game: g.id});
      toast(g.name + ' removed');
      quickSystem(key);
    });
    del.addEventListener('click', () => { if (del.classList.contains('armed')) del.innerHTML = icon('check'); });
    return row;
  }));
}

async function quickMove(g, delta) {
  try {
    await api('/api/quick/move', {system: quickKey, game: g.id, delta});
    quickSystem(quickKey);
  } catch (e) { fail(e); }
}

// Add: the games of this system on the SD card, searched like the Games page.
let addTimer = null;
$('quick-add').onclick = () => {
  $('qadd-sub').textContent = quickData ? quickData.name : '';
  $('qadd-q').value = '';
  $('qadd').showModal();
  quickAddList();
  $('qadd-q').focus();
};
$('qadd-close').onclick = () => $('qadd').close();
$('qadd').onclick = ev => { if (ev.target === $('qadd')) $('qadd').close(); };
$('qadd-q').oninput = () => { clearTimeout(addTimer); addTimer = setTimeout(quickAddList, 200); };

async function quickAddList() {
  if (!quickData) return;
  const q = $('qadd-q').value.trim();
  const list = await api('/api/games?' + new URLSearchParams({system: quickData.system, q})).catch(() => []);
  if ($('qadd-q').value.trim() !== q) return;
  const have = new Set(quickData.games.map(g => g.path));
  const box = $('qadd-list');
  if (!list.length) { box.innerHTML = '<p class="help">' + (q ? 'No game matches.' : 'No games of this system on the SD card.') + '</p>'; return; }
  box.replaceChildren(...list.slice(0, 200).map(g => {
    const b = document.createElement('button');
    b.className = 'qadd-item';
    b.type = 'button';
    b.disabled = have.has(g.path);
    b.innerHTML = '<span class="qthumb">' + (g.art ? '<img loading="lazy" alt="" src="' + artUrl(g.art) + '">' : '') + '</span>'
      + '<span>' + esc(g.name) + '</span>' + (b.disabled ? '<small>In the list</small>' : '');
    b.onclick = () => quickAdd(g, b);
    return b;
  }));
}

async function quickAdd(g, b) {
  b.disabled = true;
  try {
    const entry = await api('/api/quick/add', {system: quickKey, path: g.path});
    $('qadd').close();
    toast(entry.name + ' added. Pick its cover.');
    await quickSystem(quickKey);
    openCover(Object.assign({cover: false, crc: 0}, entry));
  } catch (e) { fail(e); b.disabled = false; }
}

// Covers: made here as a JPEG of at most 320 px on the long side, in the shape of the picture
// (box art is wide for the SNES and tall for the Mega Drive; the display keeps that shape).
async function makeCover(src) {
  const img = new Image();
  img.src = src;
  await img.decode();
  const scale = Math.min(1, 320 / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(img.naturalWidth * scale));
  c.height = Math.max(1, Math.round(img.naturalHeight * scale));
  const g = c.getContext('2d');
  g.fillStyle = '#000';
  g.fillRect(0, 0, c.width, c.height);
  g.imageSmoothingQuality = 'high';
  g.drawImage(img, 0, 0, c.width, c.height);
  return new Promise(ok => c.toBlob(ok, 'image/jpeg', 0.88));
}

async function saveCover(g, src) {
  const blob = await makeCover(src);
  await upload('/api/quick/cover?' + new URLSearchParams({system: quickKey, game: g.id}), blob);
}

// The cover picker: every picture we can find for the game, to tap one.
function coverTile(src, label, g) {
  const b = document.createElement('button');
  b.type = 'button';
  b.innerHTML = '<img loading="lazy" alt="" src="' + src + '"><span>' + esc(label) + '</span>';
  b.onclick = () => coverDone(saveCover(g, src), 'Cover saved');
  return b;
}
function coverSection(title) {
  const h = document.createElement('h3');
  h.textContent = title;
  const grid = document.createElement('div');
  grid.className = 'qcover-grid';
  return [h, grid];
}

async function openCover(g) {
  coverGame = g;
  $('qcover-title').textContent = g.name;
  $('qname').value = g.name;
  $('qcover-sub').textContent = g.cover ? 'Cover on the display' : 'No cover yet';
  $('qcover-now').innerHTML = g.cover ? '<img alt="" src="' + quickCover(g) + '">' : '';
  $('qcover-remove').hidden = !g.cover;
  const list = $('qcover-list');
  const [sdHead, sdGrid] = coverSection('On the SD card');
  const [webHead, webGrid] = coverSection('Online (libretro thumbnails)');
  const webNote = document.createElement('p');
  webNote.className = 'help';
  webNote.textContent = 'Searching… The first search of a system takes a few seconds.';
  list.replaceChildren(sdHead, sdGrid, webHead, webNote, webGrid);
  if (!$('qcover').open) $('qcover').showModal();
  const params = new URLSearchParams({system: quickKey, game: g.id});
  api('/api/quick/pictures?' + params).then(({sd}) => {
    if (coverGame !== g) return;
    if (!sd.length) { sdGrid.replaceWith(Object.assign(document.createElement('p'), {className: 'help', textContent: 'No pictures for this game on the SD card.'})); return; }
    sdGrid.replaceChildren(...sd.map(p => coverTile(artUrl(p.art), p.kind, g)));
  }).catch(e => { sdGrid.textContent = e.message; });
  api('/api/quick/boxart/search?' + params).then(({names}) => {
    if (coverGame !== g) return;
    webNote.textContent = names.length ? '' : 'Nothing found online for this name.';
    webNote.hidden = !!names.length;
    webGrid.replaceChildren(...names.map(name => coverTile('/api/quick/boxart?' + new URLSearchParams({system: quickKey, name}), name, g)));
  }).catch(e => { webNote.textContent = e.message; });
}
$('qcover-close').onclick = () => $('qcover').close();
$('qcover').onclick = ev => { if (ev.target === $('qcover')) $('qcover').close(); };
$('qcover').addEventListener('close', () => { coverGame = null; });

async function coverDone(promise, what) {
  try {
    await promise;
    $('qcover').close();
    toast(what);
    quickSystem(quickKey);
  } catch (e) { fail(e); }
}
$('qcover-upload').onclick = () => { $('quick-file').value = ''; $('quick-file').click(); };
$('quick-file').onchange = () => {
  const file = $('quick-file').files[0];
  if (!file || !coverGame) return;
  const url = URL.createObjectURL(file);
  coverDone(saveCover(coverGame, url).finally(() => URL.revokeObjectURL(url)), 'Cover saved');
};
$('qcover-remove').onclick = () => coverDone(api('/api/quick/cover/delete', {system: quickKey, game: coverGame.id}), 'Cover removed');

$('qname-form').onsubmit = async ev => {
  ev.preventDefault();
  const g = coverGame;
  if (!g) return;
  try {
    const {name} = await api('/api/quick/rename', {system: quickKey, game: g.id, name: $('qname').value});
    g.name = name;
    $('qcover-title').textContent = name;
    toast('Name saved');
    quickSystem(quickKey);
  } catch (e) { fail(e); }
};

// The system itself on the display: its name and its picture (a 4:3 screen, like the core
// pictures of MiSTerLily: the picture fits inside it on black).
async function makeSystemCover(src) {
  const img = new Image();
  img.src = src;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = 320; c.height = 240;
  const g = c.getContext('2d');
  g.fillStyle = '#000';
  g.fillRect(0, 0, 320, 240);
  const s = Math.min(320 / img.naturalWidth, 240 / img.naturalHeight);
  const w = img.naturalWidth * s, h = img.naturalHeight * s;
  g.imageSmoothingQuality = 'high';
  g.drawImage(img, (320 - w) / 2, (240 - h) / 2, w, h);
  return new Promise(ok => c.toBlob(ok, 'image/jpeg', 0.9));
}
function paintSysSheet() {
  const d = quickData;
  $('qsys-sub').textContent = d.name;
  $('qsys-name').value = d.label;
  $('qsys-name').placeholder = d.default_label;
  $('qsys-cover').innerHTML = d.has_cover ? '<img alt="" src="' + sysCoverUrl(d) + '">' : '';
  $('qsys-default').hidden = !d.custom_cover;
}
async function sysChanged(what) {
  toast(what);
  await quickSystem(quickKey);
  if ($('qsys').open) paintSysSheet();
}
$('quick-syscard').onclick = () => { if (!quickData) return; paintSysSheet(); $('qsys').showModal(); };
$('qsys-close').onclick = () => $('qsys').close();
$('qsys').onclick = ev => { if (ev.target === $('qsys')) $('qsys').close(); };
$('qsys-form').onsubmit = async ev => {
  ev.preventDefault();
  try {
    await api('/api/quick/system', {system: quickKey, name: $('qsys-name').value});
    await sysChanged('Name saved');
  } catch (e) { fail(e); }
};
$('qsys-upload').onclick = () => { $('quick-sysfile').value = ''; $('quick-sysfile').click(); };
$('quick-sysfile').onchange = async () => {
  const file = $('quick-sysfile').files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  try {
    const blob = await makeSystemCover(url);
    await upload('/api/quick/syscover?' + new URLSearchParams({system: quickKey}), blob);
    await sysChanged('Picture saved');
  } catch (e) { fail(e); } finally { URL.revokeObjectURL(url); }
};
$('qsys-default').onclick = async () => {
  try {
    await api('/api/quick/syscover/delete', {system: quickKey});
    await sysChanged('Back to the default picture');
  } catch (e) { fail(e); }
};

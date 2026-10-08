import { $, getJSON, fmtPct, addExcess, relMonth, esc, VERDICTS } from './util.js';
import { state } from './state.js';
import { map, render, setHandlers, flyToVenue, flyToOverview } from './map.js';
import { moveNow } from './charts.js';
import { renderList, renderLeagueChips, renderCard, renderCompare, renderPooled } from './views.js';

const titlesFor = (v) => {
  const list = state.titleData?.[v.id] || [];
  return list.map((q) => { const [y, m] = q.split('-').map(Number); return (y - v.opened_year) * 12 + (m - v.opened_month); });
};

// ---------- URL state (shareable links; ignored where the host forbids it) ----------
function syncUrl() {
  try {
    const p = new URLSearchParams();
    if (state.view === 'pooled') p.set('view', 'pooled');
    else if (state.sel) { p.set('venue', state.sel.id); p.set('t', state.t); }
    history.replaceState(null, '', `${location.pathname}?${p}`);
  } catch { /* sandboxed frame */ }
}

// ---------- timeline ----------
function setT(t, fromUser = false) {
  const d = state.data; if (!d) return;
  state.t = Math.max(0, Math.min(d.quarters.length - 1, t));
  $('#scrub').value = state.t;
  const rel = relMonth(d, state.t), [y, m] = d.quarters[state.t].split('-').map(Number), yrs = rel / 12;
  $('#time-label').innerHTML = `<b>Q${Math.ceil(m / 3)} ${y}</b> · ${rel < 0 ? Math.abs(yrs).toFixed(1) + ' yr before' : yrs < 0.05 ? 'opening' : yrs.toFixed(1) + ' yr after'}`;
  if (fromUser) pause();
  if (state.sel) moveNow($('#chart') || document, state.sel, rel);
  render(); syncUrl();
}
function play() {
  if (!state.data) return;
  if (state.t >= state.data.quarters.length - 1) state.t = 0;
  state.playing = true; $('#play').textContent = '❚❚'; $('#play').setAttribute('aria-label', 'Pause timeline');
  state.timer = setInterval(() => { if (state.t >= state.data.quarters.length - 1) return pause(); setT(state.t + 1); }, 320);
}
function pause() { state.playing = false; clearInterval(state.timer); $('#play').textContent = '▶'; $('#play').setAttribute('aria-label', 'Play timeline'); }

// ---------- views ----------
function setView(view) {
  state.view = view; pause();
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === view)));
  $('#timeline').hidden = view === 'pooled' || !state.data; $('#legend').hidden = view === 'pooled';
  if (view === 'pooled') { renderPooled(select); flyToOverview(); } else if (state.sel) { renderCard({ titles: titlesFor(state.sel) }); flyToVenue(state.sel); }
  renderList(); render(); syncUrl();
}

async function select(id, { focusZip = null, autoplay = true } = {}) {
  pause();
  const v = state.venues.find((x) => x.id === id); if (!v) return;
  state.view = 'venues'; state.sel = v; state.data = null; state.polys = []; state.zipIndex = {}; state.focusZip = focusZip; state.compare = null;
  document.querySelectorAll('.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === 'venues')));
  $('#legend').hidden = false;
  renderList(); renderCard({ titles: titlesFor(v) }); render(); flyToVenue(v);
  try {
    const [d, shapes] = await Promise.all([getJSON(`data/venues/${id}.json`), getJSON(`data/venues/${id}.shapes.json`).catch(() => null)]);
    if (state.sel?.id !== id) return;
    if (v.chart) addExcess(d, v);
    state.data = d; state.zipIndex = Object.fromEntries(d.zips.map((z) => [z.zip, z]));
    state.polys = shapes ? Object.entries(shapes).flatMap(([zip, polys]) => polys.map((polygon) => ({ zip, polygon }))).filter((p) => state.zipIndex[p.zip]) : [];
    const sc = $('#scrub'); sc.max = d.quarters.length - 1;
    const oi = d.quarters.findIndex((q) => q >= d.opened), frac = Math.max(0, oi) / (d.quarters.length - 1);
    $('#timeline').hidden = false;
    $('#open-tick').style.left = `${8 + frac * (sc.clientWidth - 16)}px`;
    const wanted = Number(new URLSearchParams(location.search).get('t'));
    setT(focusZip ? d.quarters.length - 1 : (Number.isFinite(wanted) && wanted > 0 && state.firstLoad ? wanted : 0));
    state.firstLoad = false;
    if (autoplay && !focusZip && !(wanted > 0)) setTimeout(() => state.sel?.id === id && play(), 1800);
  } catch { $('#time-label').textContent = 'No ZIP-level data for this venue'; $('#timeline').hidden = false; }
}

// ---------- find my ZIP ----------
async function lookupZip(raw) {
  const out = $('#zip-out'), zip = raw.trim().padStart(5, '0');
  if (!/^\d{5}$/.test(zip)) { out.textContent = 'Enter a 5-digit ZIP code.'; return; }
  out.textContent = 'Searching…';
  if (!state.allSeries) {
    state.allSeries = {};
    await Promise.all(state.venues.filter((v) => v.sc).map(async (v) => { try { state.allSeries[v.id] = await getJSON(`data/venues/${v.id}.json`); } catch { /* skip */ } }));
  }
  let best = null;
  for (const [id, s] of Object.entries(state.allSeries)) { const z = s.zips.find((q) => q.zip === zip); if (z && (!best || z.dist < best.z.dist)) best = { id, z }; }
  if (!best) { out.textContent = `ZIP ${zip} is not within 15 miles of a scored venue.`; return; }
  await select(best.id, { focusZip: zip });
  const z = state.zipIndex[zip], v = state.sel, last = state.data.quarters.length - 1;
  out.innerHTML = z ? `<b>${zip}</b> is ${z.dist.toFixed(1)} mi from ${esc(v.name)}. Three years after opening it was <b>${fmtPct(z.exc[last])}</b> vs. its synthetic twin (${fmtPct(z.pct[last])} since before opening).` : '';
}

// ---------- ask the data ----------
async function onAsk(e) {
  e.preventDefault();
  const q = $('#ask-q').value.trim(), out = $('#ask-out'), btn = $('#ask-go');
  if (!q) return;
  btn.disabled = true; out.textContent = 'Thinking…';
  try {
    const res = await fetch('api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.error || (res.status === 404 || res.status === 405 ? 'The question box needs the Python server: run `atlas serve`.' : `Error ${res.status}`));
    const chips = (body.venue_ids || []).map((id) => state.venues.find((v) => v.id === id)).filter(Boolean).map((v) => `<button type="button" data-id="${v.id}">${esc(v.name)}</button>`).join('');
    out.innerHTML = `<div>${esc(body.answer)}</div>${chips ? `<div class="chips">${chips}</div>` : ''}`;
  } catch (err) { out.innerHTML = `<span class="err">${esc(err.message)}</span>`; } finally { btn.disabled = false; }
}
const SUGGESTED = ['Which venue had the biggest effect?', 'Which results should I not trust, and why?', 'Did any venue make home values grow more slowly?', 'How did the NFL stadiums do compared with MLB parks?'];

// ---------- boot ----------
async function boot() {
  const [venues, pooled, states, titles] = await Promise.all([getJSON('data/venues.json'), getJSON('data/pooled.json').catch(() => null),
    getJSON('data/states.json').catch(() => null), getJSON('data/titles.json').catch(() => null)]);
  Object.assign(state, { venues, pooled, states, titleData: titles, firstLoad: true });
  setHandlers({ select });
  renderLeagueChips(); renderList(); renderCard(); render();
  $('#suggested').innerHTML = SUGGESTED.map((q) => `<button type="button">${esc(q)}</button>`).join('');
  $('#suggested').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) { $('#ask-q').value = b.textContent; $('#ask').requestSubmit(); } });
  $('#venue-list').addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (b) select(b.dataset.id); });
  $('#league-chips').addEventListener('click', (e) => { const b = e.target.closest('button[data-league]'); if (!b) return; state.league = b.dataset.league; renderLeagueChips(); renderList(); if (state.view === 'pooled') renderPooled(select); render(); });
  document.querySelectorAll('.sort button').forEach((b) => b.addEventListener('click', () => { state.sort = b.dataset.sort; document.querySelectorAll('.sort button').forEach((x) => x.classList.toggle('on', x === b)); renderList(); }));
  document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
  $('#scrub').addEventListener('input', (e) => setT(Number(e.target.value), true));
  $('#play').addEventListener('click', () => (state.playing ? pause() : play()));
  $('#about-btn').addEventListener('click', () => $('#about').showModal());
  $('#card').addEventListener('change', (e) => { if (e.target.id === 'cmp') { state.compare = e.target.value || null; renderCompare(); } });
  $('#card').addEventListener('click', (e) => {
    if (e.target.id !== 'share') return;
    const done = () => { e.target.textContent = 'Link copied'; setTimeout(() => (e.target.textContent = 'Copy link'), 1800); };
    navigator.clipboard?.writeText(location.href).then(done).catch(() => { e.target.textContent = location.href; });
  });
  $('#zip-form').addEventListener('submit', (e) => { e.preventDefault(); lookupZip($('#zip-q').value); });
  if (window.__NO_ASK__ || location.hostname.endsWith('github.io')) $('#ask').hidden = true;
  $('#ask').addEventListener('submit', onAsk);
  $('#ask-out').addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (b) select(b.dataset.id); });

  const qs = new URLSearchParams(location.search), wanted = qs.get('venue');
  if (qs.get('view') === 'pooled') setView('pooled');
  else if (wanted && venues.some((v) => v.id === wanted)) select(wanted);
  else { const first = venues.find((v) => v.verdict === 'signal') || venues.find((v) => v.sc); if (first) select(first.id); }
}
map.on('load', boot);
window.__atlas = { state, select, setT, setView };

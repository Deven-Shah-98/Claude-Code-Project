import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { ColumnLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';

const CARTO = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const BLANK = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0f0f0e' } }] };
const MILE = 1609.34;
const RINGS = [1.5, 3, 5, 15];
const HEIGHT_M_PER_K = 0.9;   // metres of column per $1k of home value

const VERDICTS = {
  signal:       { icon: '●', label: 'Statistically distinct', short: 'distinct' },
  suggestive:   { icon: '◐', label: 'Suggestive', short: 'suggestive' },
  inconclusive: { icon: '○', label: 'Inconclusive', short: 'inconclusive' },
  confounded:   { icon: '⚠', label: 'Pandemic-confounded', short: 'confounded' },
  'no-data':    { icon: '–', label: 'Not enough data', short: 'no data' },
};

const state = { venues: [], sel: null, data: null, t: 0, playing: false, sort: 'effect', timer: null };
const $ = (s) => document.querySelector(s);
const fmtPct = (x, d = 1) => (x == null ? '–' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d)}%`);

// ---------- colour: diverging blue (gain) <-> red (loss) through neutral gray ----------
const STOPS = [[-30, [230, 103, 103]], [-10, [156, 74, 74]], [0, [56, 56, 53]], [10, [37, 106, 191]], [30, [109, 167, 236]]];
function colorFor(pct, alpha = 235) {
  const v = Math.max(-30, Math.min(30, pct));
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [a, ca] = STOPS[i], [b, cb] = STOPS[i + 1];
    if (v <= b) { const k = (v - a) / (b - a); return [0, 1, 2].map((j) => Math.round(ca[j] + (cb[j] - ca[j]) * k)).concat(alpha); }
  }
  return [...STOPS.at(-1)[1], alpha];
}

// ---------- map ----------
let fellBack = false;
const map = new maplibregl.Map({ container: 'map', style: CARTO, center: [-96, 38], zoom: 3.4, pitch: 0, attributionControl: { compact: true }, maxPitch: 75 });
map.on('error', () => { if (!fellBack && !map.isStyleLoaded()) { fellBack = true; map.setStyle(BLANK); } });
const overlay = new MapboxOverlay({ layers: [] });
map.addControl(overlay);
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');

function verdictColor(v) { return { signal: [57, 135, 229], suggestive: [110, 150, 200], confounded: [200, 160, 60], inconclusive: [130, 130, 120], 'no-data': [90, 90, 85] }[v] || [130, 130, 120]; }

function render() {
  const layers = [];
  const v = state.sel;
  if (!v) {
    layers.push(new ScatterplotLayer({ id: 'venues', data: state.venues, pickable: true, getPosition: (d) => [d.lon, d.lat],
      getFillColor: (d) => [...verdictColor(d.verdict), 230], getRadius: 9, radiusUnits: 'pixels', stroked: true, getLineColor: [255, 255, 255, 120], lineWidthMinPixels: 1,
      onClick: ({ object }) => object && select(object.id) }));
  } else {
    const t = state.t, d = state.data;
    layers.push(new ScatterplotLayer({ id: 'rings', data: RINGS.map((r) => ({ r })), getPosition: () => [v.lon, v.lat], getRadius: (x) => x.r * MILE,
      radiusUnits: 'meters', stroked: true, filled: false, getLineColor: [255, 255, 255, 45], lineWidthMinPixels: 1 }));
    if (d) {
      layers.push(new ColumnLayer({ id: 'zips', data: d.zips, pickable: true, diskResolution: 6, radius: 340, extruded: true, getPosition: (z) => [z.lon, z.lat],
        getElevation: (z) => z.value_k[t] * HEIGHT_M_PER_K, getFillColor: (z) => colorFor(z.exc[t]), material: { ambient: 0.5, diffuse: 0.7, shininess: 24 },
        transitions: { getElevation: 220, getFillColor: 220 }, updateTriggers: { getElevation: [t], getFillColor: [t] },
        onHover: onHover }));
    }
    layers.push(new ScatterplotLayer({ id: 'venue-glow', data: [v], getPosition: (x) => [x.lon, x.lat], getRadius: 14, radiusUnits: 'pixels', getFillColor: [255, 255, 255, 255], stroked: true, getLineColor: [57, 135, 229, 255], lineWidthMinPixels: 3, parameters: { depthTest: false } }));
    layers.push(new TextLayer({ id: 'venue-label', data: [v], getPosition: (x) => [x.lon, x.lat], getText: (x) => x.name, getSize: 14, getColor: [255, 255, 255, 255], getPixelOffset: [0, -26], fontWeight: 700, outlineWidth: 4, outlineColor: [15, 15, 14, 255], fontSettings: { sdf: true }, parameters: { depthTest: false } }));
  }
  overlay.setProps({ layers });
}

function onHover(info) {
  const tip = $('#tooltip');
  if (!info.object) { tip.style.display = 'none'; return; }
  const z = info.object, t = state.t;
  tip.innerHTML = `<b>ZIP ${z.zip}</b><br>${z.dist.toFixed(1)} mi from venue<br>$${Math.round(z.value_k[t])}k · ${fmtPct(z.pct[t])} since pre-opening<br><b>${fmtPct(z.exc[t])}</b> vs. synthetic twin`;
  tip.style.display = 'block';
  tip.style.left = `${info.x + 14}px`; tip.style.top = `${info.y + 14}px`;
}

// ---------- sidebar ----------
function renderList() {
  const rows = [...state.venues].sort((a, b) => state.sort === 'year' ? a.opened_year - b.opened_year
    : (b.sc?.effect_pct ?? -1e9) - (a.sc?.effect_pct ?? -1e9));
  $('#venue-list').innerHTML = rows.map((v) => `<li><button data-id="${v.id}" ${state.sel?.id === v.id ? 'aria-current="true"' : ''}>
    <span class="v-name">${v.name}</span><span class="v-eff">${v.sc ? fmtPct(v.sc.effect_pct) : '–'}</span>
    <span class="v-meta">${v.city}, ${v.state} · opened ${v.opened_year}</span><span class="v-tag">${VERDICTS[v.verdict].icon} ${VERDICTS[v.verdict].short}</span></button></li>`).join('');
}

// ---------- card + chart ----------
function renderCard() {
  const v = state.sel, c = $('#card');
  if (!v) { c.innerHTML = `<div class="eyebrow">Pick a venue</div><p class="pval">Choose a stadium or arena to fly there and watch home values change around it.</p>`; return; }
  const V = VERDICTS[v.verdict], sc = v.sc;
  const p = sc?.p_value;
  c.innerHTML = `
    <div class="eyebrow">${v.league} · opened ${v.opened_year}</div>
    <h2>${v.name}</h2><p class="where">${v.team} · ${v.city}, ${v.state}</p>
    ${sc ? `<div class="hero"><span class="num">${fmtPct(sc.effect_pct)}</span><span class="cap">vs. synthetic twin,<br>3 years after opening</span></div>
    <span class="chip ${v.verdict === 'signal' ? 'signal' : ''}"><i>${V.icon}</i> ${V.label}</span>
    <p class="pval">Placebo p = <b>${p.toFixed(3)}</b> — about ${Math.max(1, Math.round(p * sc.n_placebos))} in ${sc.n_placebos} random areas with no venue looked this extreme. Pre-opening fit error ${(sc.pre_rmspe * 100).toFixed(2)}%, ${sc.n_treated} ZIPs treated.</p>
    ${v.robustness ? `<p class="pval">Robustness check — density-matched donors: <b>${fmtPct(v.robustness.effect_pct)}</b> (placebo p = ${v.robustness.p_value.toFixed(3)}, ${v.robustness.n_donors.toLocaleString()} donors). The estimate moves with the comparison pool.</p>` : ''}
    <div class="chart" id="chart"></div>`
    : `<span class="chip"><i>${V.icon}</i> ${V.label}</span><p class="pval">${v.error || ''}</p>`}
    ${v.caveats.length ? `<ul class="caveats">${v.caveats.map((x) => `<li>${x}</li>`).join('')}</ul>` : ''}
    ${sc ? `<details><summary>Show data table</summary><div id="tbl"></div></details>` : ''}`;
  if (sc) { drawChart(); drawTable(); }
}

function relMonthNow() {
  const d = state.data; if (!d) return 0;
  const [y, m] = d.quarters[state.t].split('-').map(Number), [oy, om] = d.opened.split('-').map(Number);
  return (y - oy) * 12 + (m - om);
}

function drawChart() {
  const v = state.sel; if (!v?.chart) return;
  const { months, actual, synthetic } = v.chart;
  const W = 440, H = 240, m = { l: 40, r: 74, t: 14, b: 28 };
  const all = actual.concat(synthetic), lo = Math.floor(Math.min(...all) / 10) * 10, hi = Math.ceil(Math.max(...all) / 10) * 10;
  const x = (mo) => m.l + ((mo - months[0]) / (months.at(-1) - months[0])) * (W - m.l - m.r);
  const y = (val) => m.t + (1 - (val - lo) / (hi - lo)) * (H - m.t - m.b);
  const line = (arr) => arr.map((val, i) => `${i ? 'L' : 'M'}${x(months[i]).toFixed(1)},${y(val).toFixed(1)}`).join('');
  const ticks = []; for (let t = lo; t <= hi; t += (hi - lo > 60 ? 20 : 10)) ticks.push(t);
  const xt = months.filter((mo) => mo % 12 === 0);
  const iEnd = months.length - 1;
  $('#chart').innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Home value index: actual versus synthetic counterfactual">
    ${ticks.map((t) => `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join('')}
    ${xt.map((mo) => `<text x="${x(mo)}" y="${H - 8}" text-anchor="middle">${mo === 0 ? 'opens' : (mo / 12 > 0 ? '+' : '') + mo / 12 + 'y'}</text>`).join('')}
    <line x1="${x(0)}" x2="${x(0)}" y1="${m.t}" y2="${H - m.b}" stroke="#8d8c82" stroke-dasharray="4 4"/>
    <path d="${line(synthetic)}" fill="none" stroke="var(--series-synth)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${line(actual)}" fill="none" stroke="var(--series-actual)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <text class="lbl" x="${W - m.r + 6}" y="${y(actual[iEnd]) + 4}" style="fill:var(--text-primary)">Actual</text>
    <text class="lbl" x="${W - m.r + 6}" y="${y(synthetic[iEnd]) + 4 + (Math.abs(y(actual[iEnd]) - y(synthetic[iEnd])) < 14 ? 14 : 0)}" style="fill:var(--text-secondary)">Twin</text>
    <circle id="now-a" r="4.5" fill="var(--series-actual)" stroke="var(--surface-1)" stroke-width="2"/>
    <line id="now-line" y1="${m.t}" y2="${H - m.b}" stroke="#ffffff" stroke-opacity=".35"/>
    <rect id="hit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>
    <div class="chart-tip" id="ctip"></div>
    <div style="display:flex;gap:14px;font-size:12px;color:var(--text-secondary);margin-top:4px">
      <span><span style="display:inline-block;width:14px;height:3px;background:var(--series-actual);vertical-align:middle;margin-right:6px"></span>Actual neighborhood (index 100 = pre-opening)</span>
      <span><span style="display:inline-block;width:14px;height:3px;background:var(--series-synth);vertical-align:middle;margin-right:6px"></span>Synthetic twin</span></div>`;
  const hit = $('#hit'), tip = $('#ctip'), svg = $('#chart svg');
  hit.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    const mo = months[0] + ((px - m.l) / (W - m.l - m.r)) * (months.at(-1) - months[0]);
    let i = 0; months.forEach((mm, k) => { if (Math.abs(mm - mo) < Math.abs(months[i] - mo)) i = k; });
    const gap = (actual[i] / synthetic[i] - 1) * 100;
    tip.style.display = 'block'; tip.style.left = `${(x(months[i]) / W) * r.width}px`; tip.style.top = `${(y(actual[i]) / H) * r.height}px`;
    tip.innerHTML = `<b>${months[i] === 0 ? 'Opening' : (months[i] / 12).toFixed(1).replace('.0', '') + ' yr ' + (months[i] < 0 ? 'before' : 'after')}</b><br>Actual ${actual[i].toFixed(1)}<br>Twin ${synthetic[i].toFixed(1)}<br>Gap ${fmtPct(gap)}`;
  });
  hit.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
  moveNow();
  svg._scale = { x, y };
}
function moveNow() {
  const v = state.sel, svg = $('#chart svg'); if (!svg || !v?.chart) return;
  const { months, actual } = v.chart, mo = Math.max(months[0], Math.min(months.at(-1), relMonthNow()));
  let i = 0; months.forEach((mm, k) => { if (Math.abs(mm - mo) < Math.abs(months[i] - mo)) i = k; });
  const W = 440, m = { l: 40, r: 74, t: 14, b: 28 }, H = 240;
  const all = actual.concat(v.chart.synthetic), lo = Math.floor(Math.min(...all) / 10) * 10, hi = Math.ceil(Math.max(...all) / 10) * 10;
  const xx = m.l + ((months[i] - months[0]) / (months.at(-1) - months[0])) * (W - m.l - m.r);
  const yy = m.t + (1 - (actual[i] - lo) / (hi - lo)) * (H - m.t - m.b);
  $('#now-a').setAttribute('cx', xx); $('#now-a').setAttribute('cy', yy);
  $('#now-line').setAttribute('x1', xx); $('#now-line').setAttribute('x2', xx);
}
function drawTable() {
  const v = state.sel, el = $('#tbl'); if (!el || !v?.chart) return;
  const { months, actual, synthetic } = v.chart;
  const rows = months.map((mo, i) => [mo, actual[i], synthetic[i]]).filter(([mo]) => mo % 12 === 0);
  el.innerHTML = `<table><tr><th>Years from opening</th><th>Actual</th><th>Twin</th><th>Gap</th></tr>${rows.map(([mo, a, s]) =>
    `<tr><td>${mo / 12}</td><td>${a.toFixed(1)}</td><td>${s.toFixed(1)}</td><td>${fmtPct((a / s - 1) * 100)}</td></tr>`).join('')}</table>`;
}

// ---------- timeline ----------
function setT(t, fromUser = false) {
  const d = state.data; if (!d) return;
  state.t = Math.max(0, Math.min(d.quarters.length - 1, t));
  $('#scrub').value = state.t;
  const rel = relMonthNow(), [y, m] = d.quarters[state.t].split('-').map(Number);
  const qn = Math.ceil(m / 3), yrs = (rel / 12);
  $('#time-label').innerHTML = `<b>Q${qn} ${y}</b> · ${rel < 0 ? Math.abs(yrs).toFixed(1) + ' yr before' : yrs < 0.05 ? 'opening' : yrs.toFixed(1) + ' yr after'}`;
  if (fromUser) pause();
  moveNow(); render();
}
function play() {
  if (!state.data) return;
  if (state.t >= state.data.quarters.length - 1) state.t = 0;
  state.playing = true; $('#play').textContent = '❚❚'; $('#play').setAttribute('aria-label', 'Pause timeline');
  state.timer = setInterval(() => { if (state.t >= state.data.quarters.length - 1) return pause(); setT(state.t + 1); }, 320);
}
function pause() { state.playing = false; clearInterval(state.timer); $('#play').textContent = '▶'; $('#play').setAttribute('aria-label', 'Play timeline'); }

// ---------- growth relative to the synthetic twin ----------
function interp(xs, ys, x) {
  if (x <= xs[0]) return ys[0]; if (x >= xs.at(-1)) return ys.at(-1);
  let i = 0; while (xs[i + 1] < x) i++;
  return ys[i] + ((ys[i + 1] - ys[i]) * (x - xs[i])) / (xs[i + 1] - xs[i]);
}
function addExcess(d, v) {
  const [oy, om] = d.opened.split('-').map(Number), { months, synthetic } = v.chart;
  const s0 = interp(months, synthetic, -6.5);   // matches the 12-month pre-opening baseline used for ZIPs
  const twin = d.quarters.map((q) => { const [y, m] = q.split('-').map(Number); return interp(months, synthetic, (y - oy) * 12 + (m - om)) / s0; });
  d.zips.forEach((z) => { z.exc = z.pct.map((p, t) => ((1 + p / 100) / twin[t] - 1) * 100); });
}

// ---------- selection ----------
async function select(id) {
  pause();
  const v = state.venues.find((x) => x.id === id); state.sel = v; state.data = null; renderList(); renderCard(); render();
  const wide = window.innerWidth > 900;
  map.flyTo({ center: [v.lon, v.lat], zoom: wide ? 10.6 : 10, pitch: 58, bearing: -18, duration: 2200, essential: true,
    padding: wide ? { right: 420, bottom: 70, top: 0, left: 0 } : { bottom: 360, top: 0, left: 0, right: 0 } });
  try {
    const res = await fetch(`data/venues/${id}.json`);
    if (!res.ok) throw new Error(res.status);
    const d = await res.json(); if (state.sel?.id !== id) return;
    state.data = d; addExcess(d, v);
    const sc = $('#scrub'); sc.max = d.quarters.length - 1;
    const oi = d.quarters.findIndex((q) => q >= d.opened); const frac = Math.max(0, oi) / (d.quarters.length - 1);
    $('#open-tick').style.left = `calc(${frac * 100}% * (1 - 16px / 100%) + 8px)`;
    $('#open-tick').style.left = `${8 + frac * (sc.clientWidth - 16)}px`;
    setT(0); setTimeout(() => state.sel?.id === id && play(), 1800);
  } catch { $('#time-label').textContent = 'No ZIP-level data for this venue'; }
}

// ---------- boot ----------
async function boot() {
  state.venues = await (await fetch('data/venues.json')).json();
  renderList(); renderCard(); render();
  $('#venue-list').addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (b) select(b.dataset.id); });
  document.querySelectorAll('.sort button').forEach((b) => b.addEventListener('click', () => {
    state.sort = b.dataset.sort; document.querySelectorAll('.sort button').forEach((x) => x.classList.toggle('on', x === b)); renderList(); }));
  $('#scrub').addEventListener('input', (e) => setT(Number(e.target.value), true));
  $('#play').addEventListener('click', () => (state.playing ? pause() : play()));
  $('#about-btn').addEventListener('click', () => $('#about').showModal());
  const first = state.venues.find((v) => v.verdict === 'signal') || state.venues.find((v) => v.sc);
  const wanted = new URLSearchParams(location.search).get('venue');
  if (wanted && state.venues.some((v) => v.id === wanted)) select(wanted); else if (first) select(first.id);
}
map.on('load', boot);
window.__atlas = { state, select, setT };

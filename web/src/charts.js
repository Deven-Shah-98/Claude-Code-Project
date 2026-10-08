import { $, esc, fmtPct } from './util.js';

const scale = (d0, d1, r0, r1) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
const niceTicks = (lo, hi, step) => { const out = []; for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) out.push(t); return out; };

// ---- counterfactual: actual neighborhood vs. synthetic twin ------------------------------------
const TW = { W: 440, H: 240, l: 40, r: 74, t: 14, b: 28 };

function twinScales(v) {
  const { months, actual, synthetic } = v.chart, all = actual.concat(synthetic);
  const lo = Math.floor(Math.min(...all) / 10) * 10, hi = Math.ceil(Math.max(...all) / 10) * 10;
  return { months, actual, synthetic, lo, hi,
    x: scale(months[0], months.at(-1), TW.l, TW.W - TW.r), y: scale(lo, hi, TW.H - TW.b, TW.t) };
}

export function drawTwinChart(el, v, titles = []) {
  const { months, actual, synthetic, lo, hi, x, y } = twinScales(v);
  const line = (arr) => arr.map((val, i) => `${i ? 'L' : 'M'}${x(months[i]).toFixed(1)},${y(val).toFixed(1)}`).join('');
  const ticks = niceTicks(lo, hi, hi - lo > 60 ? 20 : 10), xt = months.filter((mo) => mo % 12 === 0), iEnd = months.length - 1;
  const tm = titles.filter((m) => m >= months[0] && m <= months.at(-1));
  el.innerHTML = `<svg viewBox="0 0 ${TW.W} ${TW.H}" role="img" aria-label="Home value index: actual versus synthetic counterfactual">
    ${ticks.map((t) => `<line class="grid" x1="${TW.l}" x2="${TW.W - TW.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${TW.l - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join('')}
    ${xt.map((mo) => `<text x="${x(mo)}" y="${TW.H - 8}" text-anchor="middle">${mo === 0 ? 'opens' : (mo > 0 ? '+' : '') + mo / 12 + 'y'}</text>`).join('')}
    <line x1="${x(0)}" x2="${x(0)}" y1="${TW.t}" y2="${TW.H - TW.b}" stroke="#8d8c82" stroke-dasharray="4 4"/>
    <path d="${line(synthetic)}" fill="none" stroke="var(--series-synth)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="${line(actual)}" fill="none" stroke="var(--series-actual)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    ${tm.map((m) => `<path d="M${x(m)},${TW.H - TW.b - 2} l-4,-8 h8 z" fill="var(--text-primary)" opacity=".85"><title>Team won a championship (${(m / 12 > 0 ? '+' : '') + (m / 12).toFixed(1)} yr)</title></path>`).join('')}
    <text class="lbl" x="${TW.W - TW.r + 6}" y="${y(actual[iEnd]) + 4}" style="fill:var(--text-primary)">Actual</text>
    <text class="lbl" x="${TW.W - TW.r + 6}" y="${y(synthetic[iEnd]) + 4 + (Math.abs(y(actual[iEnd]) - y(synthetic[iEnd])) < 14 ? 14 : 0)}" style="fill:var(--text-secondary)">Twin</text>
    <circle id="now-a" r="4.5" fill="var(--series-actual)" stroke="var(--surface-1)" stroke-width="2"/>
    <line id="now-line" y1="${TW.t}" y2="${TW.H - TW.b}" stroke="#ffffff" stroke-opacity=".35"/>
    <rect id="hit" x="${TW.l}" y="${TW.t}" width="${TW.W - TW.l - TW.r}" height="${TW.H - TW.t - TW.b}" fill="transparent"/></svg>
    <div class="chart-tip" id="ctip"></div>
    <div class="legend-row">
      <span><i style="background:var(--series-actual)"></i>Actual neighborhood (100 = pre-opening average)</span>
      <span><i style="background:var(--series-synth)"></i>Synthetic twin</span>${tm.length ? '<span><b class="tri">▲</b>Championship</span>' : ''}</div>`;
  const hit = $('#hit', el), tip = $('#ctip', el), svg = $('svg', el);
  hit.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * TW.W;
    const mo = months[0] + ((px - TW.l) / (TW.W - TW.l - TW.r)) * (months.at(-1) - months[0]);
    let i = 0; months.forEach((mm, k) => { if (Math.abs(mm - mo) < Math.abs(months[i] - mo)) i = k; });
    const gap = (actual[i] / synthetic[i] - 1) * 100;
    tip.style.display = 'block'; tip.style.left = `${(x(months[i]) / TW.W) * r.width}px`; tip.style.top = `${(y(actual[i]) / TW.H) * r.height}px`;
    tip.innerHTML = `<b>${months[i] === 0 ? 'Opening' : (Math.abs(months[i]) / 12).toFixed(1).replace('.0', '') + ' yr ' + (months[i] < 0 ? 'before' : 'after')}</b><br>Actual ${actual[i].toFixed(1)}<br>Twin ${synthetic[i].toFixed(1)}<br>Gap ${fmtPct(gap)}`;
  });
  hit.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
}

export function moveNow(el, v, month) {
  if (!$('#now-a', el)) return;
  const { months, actual, x, y } = twinScales(v), mo = Math.max(months[0], Math.min(months.at(-1), month));
  let i = 0; months.forEach((mm, k) => { if (Math.abs(mm - mo) < Math.abs(months[i] - mo)) i = k; });
  $('#now-a', el).setAttribute('cx', x(months[i])); $('#now-a', el).setAttribute('cy', y(actual[i]));
  $('#now-line', el).setAttribute('x1', x(months[i])); $('#now-line', el).setAttribute('x2', x(months[i]));
}

// ---- compare two venues: gap vs. synthetic twin over time --------------------------------------
export function drawGapChart(el, list) {
  const W = 440, H = 200, m = { l: 40, r: 10, t: 12, b: 26 };
  const months = list[0].months, all = list.flatMap((s) => s.gap);
  const lo = Math.floor(Math.min(0, ...all) / 10) * 10, hi = Math.ceil(Math.max(0, ...all) / 10) * 10 || 10;
  const x = scale(months[0], months.at(-1), m.l, W - m.r), y = scale(lo, hi, H - m.b, m.t);
  const path = (s) => s.gap.map((g, i) => `${i ? 'L' : 'M'}${x(s.months[i]).toFixed(1)},${y(g).toFixed(1)}`).join('');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gap versus synthetic twin for two venues">
    ${niceTicks(lo, hi, hi - lo > 60 ? 20 : 10).map((t) => `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}"/><text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${t > 0 ? '+' : ''}${t}%</text>`).join('')}
    ${months.filter((mo) => mo % 12 === 0).map((mo) => `<text x="${x(mo)}" y="${H - 8}" text-anchor="middle">${mo === 0 ? 'opens' : (mo > 0 ? '+' : '') + mo / 12 + 'y'}</text>`).join('')}
    <line x1="${x(0)}" x2="${x(0)}" y1="${m.t}" y2="${H - m.b}" stroke="#8d8c82" stroke-dasharray="4 4"/>
    ${list.map((s) => `<path d="${path(s)}" fill="none" stroke="${s.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`).join('')}
    <rect id="ghit" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/></svg>
    <div class="chart-tip" id="gtip"></div>
    <div class="legend-row">${list.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}</div>`;
  const hit = $('#ghit', el), tip = $('#gtip', el), svg = $('svg', el);
  hit.addEventListener('pointermove', (e) => {
    const r = svg.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    const mo = months[0] + ((px - m.l) / (W - m.l - m.r)) * (months.at(-1) - months[0]);
    let i = 0; months.forEach((mm, k) => { if (Math.abs(mm - mo) < Math.abs(months[i] - mo)) i = k; });
    tip.style.display = 'block'; tip.style.left = `${(x(months[i]) / W) * r.width}px`; tip.style.top = `${(y(Math.max(...list.map((s) => s.gap[i]))) / H) * r.height}px`;
    tip.innerHTML = `<b>${months[i] === 0 ? 'Opening' : (Math.abs(months[i]) / 12).toFixed(1).replace('.0', '') + ' yr ' + (months[i] < 0 ? 'before' : 'after')}</b>${list.map((s) => `<br>${esc(s.name)} ${fmtPct(s.gap[i])}`).join('')}`;
  });
  hit.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
}

// ---- forest plot: each venue's effect with its placebo-based band ------------------------------
export function drawForest(el, rows, onPick) {
  const W = 440, rowH = 21, m = { l: 138, r: 50, t: 8, b: 30 }, H = m.t + rows.length * rowH + m.b;
  const lo = Math.max(-60, Math.floor(Math.min(0, ...rows.map((r) => r.band_pct[0])) / 10) * 10);
  const hi = Math.min(90, Math.ceil(Math.max(0, ...rows.map((r) => r.band_pct[1])) / 10) * 10);
  const x = scale(lo, hi, m.l, W - m.r), cl = (v) => Math.max(lo, Math.min(hi, v));
  const body = rows.map((r, i) => {
    const cy = m.t + i * rowH + rowH / 2, cx = x(cl(r.effect_pct)), sig = r.verdict === 'signal';
    const mark = r.verdict === 'confounded'
      ? `<path d="M${cx},${cy - 5.5} l5.5,5.5 l-5.5,5.5 l-5.5,-5.5 z" fill="var(--surface-1)" stroke="var(--text-secondary)" stroke-width="1.6"/>`
      : `<circle cx="${cx}" cy="${cy}" r="${sig ? 5.5 : 4.5}" fill="${sig ? 'var(--series-actual)' : r.verdict === 'suggestive' ? '#6e96c8' : 'var(--surface-1)'}" stroke="${sig ? '#fff' : 'var(--text-secondary)'}" stroke-width="${sig ? 1.5 : 1.4}"/>`;
    return `<g class="frow" data-id="${r.id}" tabindex="0" role="button" aria-label="${esc(r.name)} ${fmtPct(r.effect_pct)}">
      <rect x="0" y="${cy - rowH / 2}" width="${W}" height="${rowH}" fill="transparent"/>
      <text x="${m.l - 8}" y="${cy + 4}" text-anchor="end" style="fill:var(--text-secondary)">${esc(r.name.length > 22 ? r.name.slice(0, 21) + '…' : r.name)}</text>
      <line x1="${x(cl(r.band_pct[0]))}" x2="${x(cl(r.band_pct[1]))}" y1="${cy}" y2="${cy}" stroke="var(--text-muted)" stroke-width="1.6" stroke-linecap="round"/>
      ${mark}<text x="${W - m.r + 6}" y="${cy + 4}" style="fill:var(--text-primary)">${fmtPct(r.effect_pct, 0)}</text></g>`;
  }).join('');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Estimated effect for each venue">
    ${niceTicks(lo, hi, hi - lo > 80 ? 20 : 10).map((t) => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${m.t}" y2="${H - m.b}" ${t === 0 ? 'stroke="#8d8c82" stroke-dasharray="4 4"' : ''}/><text x="${x(t)}" y="${H - 12}" text-anchor="middle">${t > 0 ? '+' : ''}${t}%</text>`).join('')}
    ${body}</svg>
    <div class="legend-row"><span><b class="dot full">●</b>Statistically distinct</span><span><b class="dot half">●</b>Suggestive</span><span><b class="dot hollow">○</b>Inconclusive</span><span><b class="dot hollow">◇</b>Pandemic-confounded</span></div>`;
  el.querySelectorAll('.frow').forEach((g) => {
    g.addEventListener('click', () => onPick(g.dataset.id));
    g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(g.dataset.id); } });
  });
}

// ---- robustness: every alternative specification, one dot each ---------------------------------
export function drawSpecStrip(el, grid, primary) {
  const rows = grid.rows; if (!rows.length) { el.innerHTML = ''; return; }
  const W = 440, H = 96, m = { l: 14, r: 14, t: 10, b: 26 };
  const vals = rows.map((r) => r.effect_pct).concat(primary);
  const lo = Math.floor(Math.min(0, ...vals) / 10) * 10, hi = Math.ceil(Math.max(0, ...vals) / 10) * 10 || 10;
  const x = scale(lo, hi, m.l, W - m.r), lanes = 3, laneH = (H - m.t - m.b) / lanes;
  const sorted = [...rows].sort((a, b) => a.effect_pct - b.effect_pct);
  const dots = sorted.map((r, i) => `<circle cx="${x(r.effect_pct)}" cy="${m.t + laneH * (i % lanes) + laneH / 2}" r="4.5" fill="var(--text-secondary)" fill-opacity=".55" stroke="var(--surface-1)" stroke-width="1"><title>${esc(r.spec)}: ${fmtPct(r.effect_pct)}</title></circle>`).join('');
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Estimates under alternative specifications">
    ${niceTicks(lo, hi, hi - lo > 60 ? 20 : 10).map((t) => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${m.t}" y2="${H - m.b}" ${t === 0 ? 'stroke="#8d8c82" stroke-dasharray="4 4"' : ''}/><text x="${x(t)}" y="${H - 8}" text-anchor="middle">${t > 0 ? '+' : ''}${t}%</text>`).join('')}
    ${dots}
    <line x1="${x(primary)}" x2="${x(primary)}" y1="${m.t - 4}" y2="${H - m.b + 2}" stroke="var(--series-actual)" stroke-width="2.5"/></svg>
    <div class="legend-row"><span><i style="background:var(--series-actual)"></i>Main estimate</span><span><b class="dot half">●</b>Alternative specification (hover for details)</span></div>`;
}

import { $, esc, fmtPct, VERDICTS } from './util.js';
import { state } from './state.js';
import { drawTwinChart, drawGapChart, drawForest, drawSpecStrip } from './charts.js';

const LEAGUES = ['all', 'MLB', 'NFL', 'NBA', 'NHL'];

export function renderLeagueChips() {
  $('#league-chips').innerHTML = LEAGUES.map((l) => `<button data-league="${l}" class="${state.league === l ? 'on' : ''}">${l === 'all' ? 'All' : l}</button>`).join('');
}

export function renderList() {
  const rows = state.venues.filter((v) => state.league === 'all' || v.league === state.league).sort((a, b) =>
    state.sort === 'year' ? a.opened_year - b.opened_year : (b.sc?.effect_pct ?? -1e9) - (a.sc?.effect_pct ?? -1e9));
  $('#venue-list').innerHTML = rows.map((v) => `<li><button data-id="${v.id}" ${state.sel?.id === v.id && state.view === 'venues' ? 'aria-current="true"' : ''}>
    <span class="v-name">${esc(v.name)}</span><span class="v-eff">${v.sc ? fmtPct(v.sc.effect_pct) : '–'}</span>
    <span class="v-meta">${esc(v.city)}, ${v.state} · ${v.league} · ${v.opened_year}</span><span class="v-tag">${VERDICTS[v.verdict].icon} ${VERDICTS[v.verdict].short}</span></button></li>`).join('');
}

const pText = (p, n) => `${p.toFixed(3)}</b> — about ${Math.max(1, Math.round(p * n))} in ${n}`;

export function renderCard({ titles = [] } = {}) {
  const v = state.sel, c = $('#card');
  if (!v) { c.innerHTML = `<div class="eyebrow">Pick a venue</div><p class="pval">Choose a stadium or arena to fly there and watch home values change around it.</p>`; return; }
  const V = VERDICTS[v.verdict], sc = v.sc, g = v.grid, rb = v.robustness;
  const others = state.venues.filter((x) => x.sc && x.id !== v.id).sort((a, b) => a.name.localeCompare(b.name));
  c.innerHTML = `
    <div class="eyebrow">${v.league} · opened ${v.opened_year}</div>
    <div class="titlerow"><h2>${esc(v.name)}</h2><button id="share" class="link" title="Copy a link to this venue and time">Copy link</button></div>
    <p class="where">${esc(v.team)} · ${esc(v.city)}, ${v.state}</p>
    ${sc ? `<div class="hero"><span class="num">${fmtPct(sc.effect_pct)}</span><span class="cap">vs. synthetic twin,<br>3 years after opening</span></div>
    <span class="chip ${v.verdict === 'signal' ? 'signal' : ''}"><i>${V.icon}</i> ${V.label}</span>
    <p class="pval">Placebo p = <b>${pText(sc.p_value, sc.n_placebos)} random areas with no venue looked this extreme. Pre-opening fit error ${(sc.pre_rmspe * 100).toFixed(2)}%, ${sc.n_treated} ZIPs within ${sc.treated_radius ?? 3} mi.
      ${sc.p_value_dense != null ? `<br>Among similarly sized ZIPs, p = <b>${sc.p_value_dense.toFixed(3)}</b>.` : ''}</p>
    <div class="chart" id="chart"></div>
    ${g?.rows?.length ? `<h3>Does it hold up?</h3>
      <p class="pval">${g.summary.share_same_sign === 1 ? `All ${g.summary.n}` : `${Math.round(g.summary.share_same_sign * g.summary.n)} of ${g.summary.n}`} alternative setups (treated radius, time window, dropping top donors) keep the same direction; they range from ${fmtPct(g.summary.min, 0)} to ${fmtPct(g.summary.max, 0)}.
      ${rb ? `With density-matched donors: <b>${fmtPct(rb.effect_pct)}</b> (placebo p = ${rb.p_value.toFixed(3)}).` : ''}</p>
      <div class="chart" id="spec"></div>` : ''}
    <h3>Compare</h3>
    <label class="cmp"><span class="eyebrow">With another venue</span>
      <select id="cmp"><option value="">Choose a venue…</option>${others.map((o) => `<option value="${o.id}" ${state.compare === o.id ? 'selected' : ''}>${esc(o.name)} (${fmtPct(o.sc.effect_pct, 0)})</option>`).join('')}</select></label>
    <div class="chart" id="cmpchart"></div>`
    : `<span class="chip"><i>${V.icon}</i> ${V.label}</span><p class="pval">${esc(v.error || '')}</p>`}
    ${v.caveats.length ? `<ul class="caveats">${v.caveats.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
    ${sc ? `<details><summary>Show data table</summary><div id="tbl"></div></details>` : ''}`;
  if (sc) {
    drawTwinChart($('#chart'), v, titles);
    if (g?.rows?.length) drawSpecStrip($('#spec'), g, sc.effect_pct);
    drawTable(v); renderCompare();
  }
}

export function renderCompare() {
  const el = $('#cmpchart'), v = state.sel, o = state.venues.find((x) => x.id === state.compare);
  if (!el) return;
  if (!o || !v?.chart) { el.innerHTML = ''; return; }
  const gap = (x) => x.chart.actual.map((a, i) => (a / x.chart.synthetic[i] - 1) * 100);
  drawGapChart(el, [
    { name: v.name, color: 'var(--series-actual)', months: v.chart.months, gap: gap(v) },
    { name: o.name, color: 'var(--series-synth)', months: o.chart.months, gap: gap(o) },
  ]);
}

function drawTable(v) {
  const el = $('#tbl'); if (!el || !v?.chart) return;
  const { months, actual, synthetic } = v.chart;
  const rows = months.map((mo, i) => [mo, actual[i], synthetic[i]]).filter(([mo]) => mo % 12 === 0);
  el.innerHTML = `<table><tr><th>Years from opening</th><th>Actual</th><th>Twin</th><th>Gap</th></tr>${rows.map(([mo, a, s]) =>
    `<tr><td>${mo / 12}</td><td>${a.toFixed(1)}</td><td>${s.toFixed(1)}</td><td>${fmtPct((a / s - 1) * 100)}</td></tr>`).join('')}</table>`;
}

// ---- pooled "big picture" ------------------------------------------------------------------------
const groupRows = (g) => Object.entries(g || {}).map(([k, r]) => `<tr><td>${k}</td><td>${r.n}</td><td>${fmtPct(r.mean_pct)}</td><td>${fmtPct(r.ci_pct[0], 0)} to ${fmtPct(r.ci_pct[1], 0)}</td></tr>`).join('');
const excludesZero = (ci) => ci[0] > 0 || ci[1] < 0;

export function renderPooled(onPick) {
  const P = state.pooled, c = $('#card');
  if (!P || !P.all || P.all.error) { c.innerHTML = `<div class="eyebrow">Big picture</div><p class="pval">Pooled results are not available in this data export.</p>`; return; }
  const a = P.all, d = P.dense_null, dir = a.mean_pct > 0 ? 'faster' : 'slower';
  const headline = excludesZero(a.ci_pct) ? `${dir[0].toUpperCase()}${dir.slice(1)} growth near new venues, on average`
    : (excludesZero(a.random_effects_ci_pct) || a.placebo_p < 0.05) ? `Modestly ${dir} growth on average, not conclusive` : 'No clear average effect';
  const rows = [...P.forest].sort((x, y) => y.effect_pct - x.effect_pct).filter((r) => state.league === 'all' || r.league === state.league);
  const pw = P.pandemic_window, yrs = P.forest.filter((r) => r.verdict !== 'confounded').map((r) => r.year).sort();
  const eras = Object.entries(P.by_era || {}).filter(([, r]) => excludesZero(r.ci_pct));
  const eraNote = eras.length ? `Clearest in the ${eras.map(([k, r]) => `${k} venues (${fmtPct(r.mean_pct)}, 95% CI ${fmtPct(r.ci_pct[0], 0)} to ${fmtPct(r.ci_pct[1], 0)})`).join(' and ')}.` : '';
  c.innerHTML = `
    <div class="eyebrow">Big picture · ${a.n} venues opened ${yrs[0]}–${yrs.at(-1)}</div>
    <h2>${headline}</h2>
    <div class="hero"><span class="num">${fmtPct(a.mean_pct)}</span><span class="cap">average effect vs. synthetic twins<br>95% CI ${fmtPct(a.ci_pct[0])} to ${fmtPct(a.ci_pct[1])}</span></div>
    <p class="pval">Three ways of testing agree on the direction but not on certainty: the interval across venues ${excludesZero(a.ci_pct) ? 'excludes' : 'just includes'} zero;
      a random-effects model gives ${fmtPct(a.random_effects_pct)} (${fmtPct(a.random_effects_ci_pct[0])} to ${fmtPct(a.random_effects_ci_pct[1])});
      the pooled placebo test gives p = <b>${a.placebo_p.toFixed(3)}</b>${d && !d.error ? ` (<b>${d.placebo_p.toFixed(3)}</b> against similarly sized ZIPs)` : ''}.
      Venues differ a lot (I² = ${(a.i2 * 100).toFixed(0)}%): ${Math.round(a.share_positive * a.n)} of ${a.n} are positive (sign test p = ${a.sign_test_p.toFixed(2)}), and only a few stand out on their own. ${eraNote}</p>
    <p class="pval faint">Association, not proof of causation: venues are usually built as part of larger redevelopment, which this method cannot separate from the venue itself. Placebo p-values are approximate (slightly liberal in simulation); the interval is a t-interval over venues.</p>
    <h3>Every venue</h3>
    <div class="chart" id="forest"></div>
    ${P.by_era ? `<h3>By opening era <span class="faint">(exploratory)</span></h3><table class="tbl"><tr><th>Opened</th><th>Venues</th><th>Mean</th><th>95% CI</th></tr>${groupRows(P.by_era)}</table>
      <p class="pval faint">Venues opened 2006–09 had post-opening windows inside the 2008–11 housing bust, which hit metros unevenly.</p>` : ''}
    ${P.by_league ? `<h3>By league <span class="faint">(exploratory)</span></h3><table class="tbl"><tr><th>League</th><th>Venues</th><th>Mean</th><th>95% CI</th></tr>${groupRows(P.by_league)}</table>` : ''}
    ${pw && pw.n ? `<h3>Opened 2019–20</h3><p class="pval">${pw.n} venues overlap the pandemic window${pw.mean_pct != null ? `; their average is ${fmtPct(pw.mean_pct)}` : ''}. They are kept out of the pooled estimate above.</p>` : ''}`;
  drawForest($('#forest'), rows, onPick);
}

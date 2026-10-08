export const $ = (s, root = document) => root.querySelector(s);
export const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
export const fmtPct = (x, d = 1) => (x == null || Number.isNaN(x) ? '–' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d)}%`);

export const VERDICTS = {
  signal:       { icon: '●', label: 'Statistically distinct', short: 'distinct' },
  suggestive:   { icon: '◐', label: 'Suggestive', short: 'suggestive' },
  inconclusive: { icon: '○', label: 'Inconclusive', short: 'inconclusive' },
  confounded:   { icon: '⚠', label: 'Pandemic-confounded', short: 'confounded' },
  'no-data':    { icon: '–', label: 'Not enough data', short: 'no data' },
};

// Diverging scale: red (slower than the synthetic twin) <-> gray <-> blue (faster).
const STOPS = [[-30, [230, 103, 103]], [-10, [156, 74, 74]], [0, [56, 56, 53]], [10, [37, 106, 191]], [30, [109, 167, 236]]];
export function colorFor(pct, alpha = 235) {
  const v = Math.max(-30, Math.min(30, pct));
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [a, ca] = STOPS[i], [b, cb] = STOPS[i + 1];
    if (v <= b) { const k = (v - a) / (b - a); return [0, 1, 2].map((j) => Math.round(ca[j] + (cb[j] - ca[j]) * k)).concat(alpha); }
  }
  return [...STOPS.at(-1)[1], alpha];
}

export function interp(xs, ys, x) {
  if (x <= xs[0]) return ys[0];
  if (x >= xs.at(-1)) return ys.at(-1);
  let i = 0; while (xs[i + 1] < x) i++;
  return ys[i] + ((ys[i + 1] - ys[i]) * (x - xs[i])) / (xs[i + 1] - xs[i]);
}

// Growth of each ZIP relative to the synthetic twin, per quarter ("excess" growth, in %).
export function addExcess(d, v) {
  const [oy, om] = d.opened.split('-').map(Number), { months, synthetic } = v.chart;
  const s0 = interp(months, synthetic, -6.5);   // matches the 12-month pre-opening baseline used for ZIPs
  const twin = d.quarters.map((q) => { const [y, m] = q.split('-').map(Number); return interp(months, synthetic, (y - oy) * 12 + (m - om)) / s0; });
  d.zips.forEach((z) => { z.exc = z.pct.map((p, t) => ((1 + p / 100) / twin[t] - 1) * 100); });
}

export function relMonth(d, t) {
  const [y, m] = d.quarters[t].split('-').map(Number), [oy, om] = d.opened.split('-').map(Number);
  return (y - oy) * 12 + (m - om);
}

export async function getJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

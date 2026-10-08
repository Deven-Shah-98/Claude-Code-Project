import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { MapboxOverlay } from '@deck.gl/mapbox';
import { PolygonLayer, ScatterplotLayer, TextLayer, PathLayer } from '@deck.gl/layers';
import { colorFor, fmtPct, $ } from './util.js';
import { state } from './state.js';

const CARTO = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const BLANK = { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#0f0f0e' } }] };
const MILE = 1609.34, RINGS = [1.5, 3, 5, 15], HEIGHT_M_PER_K = 0.9, LABEL_ZOOM = 10.2;

let fellBack = false, overlay, handlers = {};
export const map = new maplibregl.Map({ container: 'map', style: CARTO, center: [-96, 38], zoom: 3.4, pitch: 0, attributionControl: { compact: true }, maxPitch: 75 });
map.on('error', () => { if (!fellBack && !map.isStyleLoaded()) { fellBack = true; map.setStyle(BLANK); } });
overlay = new MapboxOverlay({ layers: [] });
map.addControl(overlay);
map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');
map.on('zoomend', () => render());

export function setHandlers(h) { handlers = h; }

const verdictColor = (v) => ({ signal: [57, 135, 229], suggestive: [110, 150, 200], confounded: [200, 160, 60], inconclusive: [130, 130, 120], 'no-data': [90, 90, 85] }[v] || [130, 130, 120]);

function onHover(info) {
  const tip = $('#tooltip');
  if (!info.object) { tip.style.display = 'none'; return; }
  const o = info.object, t = state.t;
  if (o.zip) {
    const z = state.zipIndex[o.zip];
    tip.innerHTML = `<b>ZIP ${z.zip}</b><br>${z.dist.toFixed(1)} mi from venue<br>$${Math.round(z.value_k[t])}k · ${fmtPct(z.pct[t])} since pre-opening<br><b>${fmtPct(z.exc[t])}</b> vs. synthetic twin`;
  } else {
    tip.innerHTML = `<b>${o.name}</b><br>${o.team} · opened ${o.opened_year}<br>${o.sc ? `<b>${fmtPct(o.sc.effect_pct)}</b> vs. synthetic twin` : 'no estimate'}`;
  }
  tip.style.display = 'block';
  tip.style.left = `${info.x + 14}px`; tip.style.top = `${info.y + 14}px`;
}

const ringLabels = (v) => RINGS.map((r) => ({ text: `${r} mi`, pos: [v.lon, v.lat + r / 69.05] }));

export function render() {
  const layers = [];
  const v = state.sel;
  const overview = state.view === 'pooled' || !v;
  if (overview) {
    if (state.states) {
      layers.push(new PathLayer({ id: 'states', data: state.states.flatMap((s) => s.polys.flatMap((p) => p.map((ring) => ({ path: ring })))),
        getPath: (d) => d.path, getColor: [255, 255, 255, 55], widthMinPixels: 1, pickable: false }));
    }
    const scored = state.venues.filter((x) => state.league === 'all' || x.league === state.league);
    layers.push(new ScatterplotLayer({ id: 'venues', data: scored, pickable: true, getPosition: (d) => [d.lon, d.lat],
      getFillColor: (d) => (d.sc ? colorFor(d.sc.effect_pct, 230) : [...verdictColor(d.verdict), 200]),
      getRadius: (d) => (d.verdict === 'confounded' ? 7 : 9), radiusUnits: 'pixels', stroked: true,
      getLineColor: (d) => (d.verdict === 'signal' ? [255, 255, 255, 255] : d.verdict === 'confounded' ? [200, 160, 60, 255] : [255, 255, 255, 90]),
      getLineWidth: (d) => (d.verdict === 'signal' ? 3 : 1.5), lineWidthUnits: 'pixels',
      onClick: ({ object }) => object && handlers.select?.(object.id), onHover }));
  } else {
    const t = state.t, zoomed = map.getZoom() >= LABEL_ZOOM;
    layers.push(new ScatterplotLayer({ id: 'rings', data: RINGS.map((r) => ({ r })), getPosition: () => [v.lon, v.lat], getRadius: (x) => x.r * MILE,
      radiusUnits: 'meters', stroked: true, filled: false, getLineColor: [255, 255, 255, 45], lineWidthMinPixels: 1 }));
    layers.push(new TextLayer({ id: 'ring-labels', data: ringLabels(v), getPosition: (d) => d.pos, getText: (d) => d.text, getSize: 11,
      getColor: [200, 200, 190, 170], outlineWidth: 3, outlineColor: [15, 15, 14, 255], fontSettings: { sdf: true }, parameters: { depthTest: false } }));
    if (state.polys.length) {
      layers.push(new PolygonLayer({ id: 'zips', data: state.polys, pickable: true, extruded: true, wireframe: false, stroked: false,
        getPolygon: (d) => d.polygon, getElevation: (d) => state.zipIndex[d.zip].value_k[t] * HEIGHT_M_PER_K,
        getFillColor: (d) => (d.zip === state.focusZip ? [255, 255, 255, 245] : colorFor(state.zipIndex[d.zip].exc[t])),
        material: { ambient: 0.55, diffuse: 0.65, shininess: 20 },
        transitions: { getElevation: 220, getFillColor: 220 }, updateTriggers: { getElevation: [t], getFillColor: [t, state.focusZip] }, onHover }));
      if (zoomed) {
        const labelled = Object.values(state.zipIndex).filter((z) => z.dist <= 6 || z.zip === state.focusZip);
        layers.push(new TextLayer({ id: 'zip-labels', data: labelled, getPosition: (z) => [z.lon, z.lat, z.value_k[t] * HEIGHT_M_PER_K + 40],
          getText: (z) => z.zip, getSize: 11, getColor: [235, 235, 225, 235], outlineWidth: 3, outlineColor: [15, 15, 14, 255],
          fontSettings: { sdf: true }, parameters: { depthTest: false }, updateTriggers: { getPosition: [t] } }));
      }
    }
    layers.push(new ScatterplotLayer({ id: 'venue-glow', data: [v], getPosition: (x) => [x.lon, x.lat], getRadius: 14, radiusUnits: 'pixels', getFillColor: [255, 255, 255, 255], stroked: true, getLineColor: [57, 135, 229, 255], lineWidthMinPixels: 3, parameters: { depthTest: false } }));
    layers.push(new TextLayer({ id: 'venue-label', data: [v], getPosition: (x) => [x.lon, x.lat], getText: (x) => x.name, getSize: 14, getColor: [255, 255, 255, 255], getPixelOffset: [0, -26], fontWeight: 700, outlineWidth: 4, outlineColor: [15, 15, 14, 255], fontSettings: { sdf: true }, parameters: { depthTest: false } }));
  }
  overlay.setProps({ layers });
}

export function flyToVenue(v) {
  const wide = window.innerWidth > 900;
  map.flyTo({ center: [v.lon, v.lat], zoom: wide ? 10.6 : 10, pitch: 58, bearing: -18, duration: 2200, essential: true,
    padding: wide ? { right: 420, bottom: 70, top: 0, left: 0 } : { bottom: 360, top: 0, left: 0, right: 0 } });
}

export function flyToOverview() {
  const wide = window.innerWidth > 900;
  map.flyTo({ center: [-96, 38.5], zoom: wide ? 3.5 : 2.6, pitch: 0, bearing: 0, duration: 1500, essential: true,
    padding: wide ? { right: 440, bottom: 0, top: 0, left: 0 } : { bottom: 300, top: 0, left: 0, right: 0 } });
}

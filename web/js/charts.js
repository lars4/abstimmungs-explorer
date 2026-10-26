// Dependency-free SVG charts.
import { TILE_GRID, yesColor, textOn, niceTicks, dateToYear, fmtPct, armsUrl } from './lib.js';

const NS = 'http://www.w3.org/2000/svg';
export const SERIES_COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#E69F00', '#56B4E9'];

export function svg(tag, attrs = {}, children = []) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  for (const c of [].concat(children)) el.append(c);
  return el;
}

let tipEl;
export function tooltip() {
  if (!tipEl) {
    tipEl = document.createElement('div');
    tipEl.className = 'tip';
    tipEl.setAttribute('role', 'tooltip');
    document.body.append(tipEl);
  }
  return {
    show(html, x, y) {
      tipEl.innerHTML = html;
      tipEl.style.display = 'block';
      const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
      tipEl.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14)) + 'px';
      tipEl.style.top = Math.min(window.innerHeight - h - 8, Math.max(8, y + 14)) + 'px';
    },
    hide() { tipEl.style.display = 'none'; },
  };
}

/** Canton tile map. values: {code: {yes, turnout}}; opts: {names, onSelect, selected, tipHtml} */
export function tileMap(container, values, opts = {}) {
  const size = 62, gap = 5, cols = 7, rows = 6;
  const W = cols * (size + gap) + gap, H = rows * (size + gap) + gap;
  const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'tilemap', role: 'img',
    'aria-label': opts.label || 'Kantonskarte' });
  const tip = tooltip();
  for (const [code, [c, r]] of Object.entries(TILE_GRID)) {
    const v = values[code];
    const x = gap + c * (size + gap), y = gap + r * (size + gap);
    const g = svg('g', { class: 'tile' + (opts.selected === code ? ' sel' : ''), tabindex: opts.onSelect ? 0 : null,
      role: opts.onSelect ? 'button' : null, 'aria-label': `${opts.names?.[code] || code}: ${v ? fmtPct(v.yes) : 'keine Daten'}` });
    const fill = yesColor(v?.yes);
    g.append(svg('rect', { x, y, width: size, height: size, rx: 7, fill }));
    const aw = 22, ah = aw * 493 / 406;
    g.append(svg('image', { href: armsUrl(code), x: x + (size - aw) / 2, y: y + 3, width: aw, height: ah, class: 't-arms' }));
    g.append(svg('text', { x: x + size / 2, y: y + 43, class: 't-code', fill: textOn(v?.yes) }, [document.createTextNode(code)]));
    g.append(svg('text', { x: x + size / 2, y: y + 57, class: 't-val', fill: textOn(v?.yes) },
      [document.createTextNode(v ? v.yes.toFixed(1).replace('.', ',') : '–')]));
    g.addEventListener('mousemove', (e) => tip.show(opts.tipHtml ? opts.tipHtml(code, v) : `<b>${opts.names?.[code] || code}</b><br>${v ? fmtPct(v.yes) : '–'}`, e.clientX, e.clientY));
    g.addEventListener('mouseleave', tip.hide);
    if (opts.onSelect) {
      g.addEventListener('click', () => opts.onSelect(code));
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opts.onSelect(code); } });
    }
    root.append(g);
  }
  container.replaceChildren(root);
}

/**
 * Multi-series line chart over time.
 * series: [{name, color, points:[{date, value, id, title}]}]
 * opts: {yDomain:[min,max], ref:50, yFormat, onPick(point, series), tipHtml}
 */
export function lineChart(container, series, opts = {}) {
  const W = 880, H = 340, m = { l: 48, r: 16, t: 14, b: 30 };
  const all = series.flatMap((s) => s.points);
  const root = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'linechart', role: 'img', 'aria-label': opts.label || 'Verlauf' });
  if (!all.length) {
    root.append(svg('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'empty' }, [document.createTextNode(opts.empty || 'Keine Daten')]));
    container.replaceChildren(root);
    return;
  }
  const xs = all.map((p) => dateToYear(p.date));
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const vals = all.map((p) => p.value);
  let [yMin, yMax] = opts.yDomain || [Math.min(...vals), Math.max(...vals)];
  if (!opts.yDomain) { const pad = (yMax - yMin) * 0.08 || 5; yMin -= pad; yMax += pad; }
  const X = (d) => m.l + ((dateToYear(d) - xMin) / (xMax - xMin || 1)) * (W - m.l - m.r);
  const Y = (v) => H - m.b - ((v - yMin) / (yMax - yMin || 1)) * (H - m.t - m.b);
  const fmtY = opts.yFormat || ((v) => v.toFixed(0));

  for (const t of niceTicks(yMin, yMax, 5)) {
    root.append(svg('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: 'grid' }));
    root.append(svg('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'axis' }, [document.createTextNode(fmtY(t))]));
  }
  const y0 = Math.floor(xMin), y1 = Math.ceil(xMax);
  const step = Math.max(1, Math.round((y1 - y0) / 9));
  for (let y = y0; y <= y1; y += step) {
    const x = m.l + ((y - xMin) / (xMax - xMin || 1)) * (W - m.l - m.r);
    if (x < m.l - 1 || x > W - m.r + 1) continue;
    root.append(svg('text', { x, y: H - 8, 'text-anchor': 'middle', class: 'axis' }, [document.createTextNode(String(y))]));
  }
  if (opts.ref != null && opts.ref > yMin && opts.ref < yMax) {
    root.append(svg('line', { x1: m.l, x2: W - m.r, y1: Y(opts.ref), y2: Y(opts.ref), class: 'ref' }));
  }
  series.forEach((s, i) => {
    const color = s.color || SERIES_COLORS[i % SERIES_COLORS.length];
    const d = s.points.map((p, j) => `${j ? 'L' : 'M'}${X(p.date).toFixed(1)},${Y(p.value).toFixed(1)}`).join('');
    root.append(svg('path', { d, fill: 'none', stroke: color, 'stroke-width': s.thin ? 1 : 2.2, 'stroke-linejoin': 'round', opacity: s.thin ? 0.55 : 1 }));
    if (!s.noDots) for (const p of s.points) root.append(svg('circle', { cx: X(p.date), cy: Y(p.value), r: 2.6, fill: color, class: 'dot' }));
  });

  // hover: nearest point by x over all series
  const flat = series.flatMap((s, si) => s.points.map((p) => ({ p, s, si })));
  const cross = svg('line', { y1: m.t, y2: H - m.b, class: 'cross', style: 'display:none' });
  const mark = svg('circle', { r: 5, class: 'mark', style: 'display:none' });
  root.append(cross, mark);
  const tip = tooltip();
  const overlay = svg('rect', { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: 'transparent', style: 'cursor:crosshair' });
  const nearest = (evt) => {
    const r = root.getBoundingClientRect();
    const sx = ((evt.clientX - r.left) / r.width) * W, sy = ((evt.clientY - r.top) / r.height) * H;
    let best = null, bd = Infinity;
    for (const f of flat) {
      const d = Math.hypot(X(f.p.date) - sx, (Y(f.p.value) - sy) * 0.6);
      if (d < bd) { bd = d; best = f; }
    }
    return best;
  };
  overlay.addEventListener('mousemove', (e) => {
    const f = nearest(e); if (!f) return;
    cross.setAttribute('x1', X(f.p.date)); cross.setAttribute('x2', X(f.p.date)); cross.style.display = '';
    mark.setAttribute('cx', X(f.p.date)); mark.setAttribute('cy', Y(f.p.value)); mark.setAttribute('stroke', f.s.color || SERIES_COLORS[f.si % SERIES_COLORS.length]); mark.style.display = '';
    tip.show(opts.tipHtml ? opts.tipHtml(f.p, f.s) : `<b>${f.s.name}</b><br>${f.p.date}<br>${fmtY(f.p.value)}`, e.clientX, e.clientY);
  });
  overlay.addEventListener('mouseleave', () => { tip.hide(); cross.style.display = 'none'; mark.style.display = 'none'; });
  if (opts.onPick) overlay.addEventListener('click', (e) => { const f = nearest(e); if (f) opts.onPick(f.p, f.s); });
  root.append(overlay);
  container.replaceChildren(root);
}

/** Small inline sparkline path for tables. */
export function sparkline(points, w = 90, h = 22) {
  if (points.length < 2) return svg('svg', { width: w, height: h });
  const xs = points.map((p) => dateToYear(p.date));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ys = points.map((p) => p.value);
  const y0 = Math.min(...ys, 50), y1 = Math.max(...ys, 50);
  const X = (d) => 1 + ((dateToYear(d) - x0) / (x1 - x0 || 1)) * (w - 2);
  const Y = (v) => h - 1 - ((v - y0) / (y1 - y0 || 1)) * (h - 2);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${X(p.date).toFixed(1)},${Y(p.value).toFixed(1)}`).join('');
  return svg('svg', { width: w, height: h, class: 'spark', viewBox: `0 0 ${w} ${h}` }, [
    svg('line', { x1: 0, x2: w, y1: Y(50), y2: Y(50), class: 'ref' }),
    svg('path', { d, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6 }),
  ]);
}

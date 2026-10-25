// Pure helpers (no DOM). Unit-tested with `node --test tests/`.

export const CANTON_CODES = [
  'ZH','BE','LU','UR','SZ','OW','NW','GL','ZG','FR','SO','BS','BL','SH','AR','AI','SG','GR','AG','TG','TI','VD','VS','NE','GE','JU',
];

export const CANTON_NAMES = {
  de: {ZH:'Zürich',BE:'Bern',LU:'Luzern',UR:'Uri',SZ:'Schwyz',OW:'Obwalden',NW:'Nidwalden',GL:'Glarus',ZG:'Zug',FR:'Freiburg',
       SO:'Solothurn',BS:'Basel-Stadt',BL:'Basel-Landschaft',SH:'Schaffhausen',AR:'Appenzell A.Rh.',AI:'Appenzell I.Rh.',SG:'St. Gallen',
       GR:'Graubünden',AG:'Aargau',TG:'Thurgau',TI:'Tessin',VD:'Waadt',VS:'Wallis',NE:'Neuenburg',GE:'Genf',JU:'Jura'},
  en: {ZH:'Zurich',BE:'Bern',LU:'Lucerne',UR:'Uri',SZ:'Schwyz',OW:'Obwalden',NW:'Nidwalden',GL:'Glarus',ZG:'Zug',FR:'Fribourg',
       SO:'Solothurn',BS:'Basel-Stadt',BL:'Basel-Landschaft',SH:'Schaffhausen',AR:'Appenzell Outer Rhodes',AI:'Appenzell Inner Rhodes',
       SG:'St. Gallen',GR:'Grisons',AG:'Aargau',TG:'Thurgau',TI:'Ticino',VD:'Vaud',VS:'Valais',NE:'Neuchâtel',GE:'Geneva',JU:'Jura'},
};

// Swiss canton tile grid: [column, row]. Roughly geographic, one tile per canton.
export const TILE_GRID = {
  SH:[4,0],
  BS:[1,1],BL:[2,1],AG:[3,1],ZH:[4,1],TG:[5,1],
  JU:[0,2],SO:[1,2],LU:[2,2],ZG:[3,2],SZ:[4,2],SG:[5,2],AR:[6,2],
  NE:[0,3],BE:[1,3],OW:[2,3],NW:[3,3],UR:[4,3],GL:[5,3],AI:[6,3],
  VD:[0,4],FR:[1,4],VS:[2,4],TI:[4,4],GR:[5,4],
  GE:[0,5],
};

export const fmtPct = (x, d = 1) => (x == null || Number.isNaN(x) ? '–' : x.toFixed(d).replace('.', ',') + ' %');
export const fmtSigned = (x, d = 1) => (x == null ? '–' : (x > 0 ? '+' : x < 0 ? '−' : '±') + Math.abs(x).toFixed(d).replace('.', ',') + ' pp');

/** Diverging scale around 50 %: returns a CSS colour for a yes share. Colour-blind safe (orange ↔ blue). */
export function yesColor(yes, lo = 25, hi = 75) {
  if (yes == null) return 'var(--na)';
  const t = Math.max(-1, Math.min(1, (yes - 50) / ((hi - lo) / 2)));
  const a = Math.abs(t);
  // interpolate from near-neutral to saturated, in OKLab-ish simple RGB mix
  const neutral = [236, 236, 232];
  const target = t >= 0 ? [27, 108, 168] : [214, 110, 30];
  const c = neutral.map((n, i) => Math.round(n + (target[i] - n) * a));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export function textOn(yes) {
  return yes != null && Math.abs(yes - 50) > 16 ? '#fff' : '#1b1b1b';
}

export function voteTitle(v, lang = 'de') {
  const t = v.title || {};
  return t[lang] || t.de || t.fr || t.en || Object.values(t)[0] || v.id;
}

export function filterVotes(votes, { q = '', from = null, to = null, outcome = 'all', kind = 'all', lang = 'de' } = {}) {
  const needle = q.trim().toLowerCase();
  return votes.filter((v) => {
    const y = +v.date.slice(0, 4);
    if (from != null && y < from) return false;
    if (to != null && y > to) return false;
    if (outcome === 'yes' && !v.accepted) return false;
    if (outcome === 'no' && v.accepted) return false;
    if (kind !== 'all' && v.kind !== kind) return false;
    if (needle) {
      const hay = Object.values(v.title || {}).join(' ').toLowerCase() + ' ' + v.date;
      if (!hay.includes(needle)) return false;
    }
    return true;
  });
}

/** Series of {date, id, value} for one canton across the given votes. mode: 'yes' | 'delta' (vs national). */
export function cantonSeries(votes, cantons, code, mode = 'yes') {
  const out = [];
  for (const v of votes) {
    const r = cantons[v.id]?.[code];
    if (!r || r[0] == null) continue;
    const value = mode === 'delta' ? (v.yes == null ? null : r[0] - v.yes) : r[0];
    if (value == null) continue;
    out.push({ date: v.date, id: v.id, value, title: v.title });
  }
  return out;
}

export function movingAverage(points, window = 5) {
  return points.map((p, i) => {
    const slice = points.slice(Math.max(0, i - window + 1), i + 1);
    return { ...p, value: slice.reduce((s, q) => s + q.value, 0) / slice.length };
  });
}

/** Canton majority (Ständemehr) helper: number of cantons with yes > 50 %. */
export function cantonMajority(cantonResults) {
  const entries = Object.values(cantonResults || {});
  const yes = entries.filter((r) => r[0] > 50).length;
  return { yes, no: entries.length - yes, total: entries.length };
}

/** Rank cantons by deviation from the national result (largest absolute first). */
export function rankCantons(cantonResults, national, by = 'yes') {
  return Object.entries(cantonResults || {})
    .map(([code, r]) => ({ code, yes: r[0], turnout: r[1], delta: national == null ? null : r[0] - national }))
    .sort((a, b) => by === 'delta' ? Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0) : b.yes - a.yes);
}

/** Time of date ('YYYY-MM-DD') as fractional year for x scales. */
export function dateToYear(d) {
  const [y, m, day] = d.split('-').map(Number);
  return y + ((m - 1) * 30.4 + day) / 365.25;
}

export function niceTicks(min, max, count = 5) {
  if (min === max) return [min];
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) ticks.push(+t.toFixed(10));
  return ticks;
}

export function municipalityRows(muniFile, voteId, nationalYes = null) {
  if (!muniFile) return [];
  const res = muniFile.results?.[voteId] || {};
  return Object.entries(res).map(([bfs, r]) => ({
    bfs, name: muniFile.names?.[bfs] ?? bfs, yes: r[0], turnout: r[1],
    delta: nationalYes == null ? null : r[0] - nationalYes,
  }));
}

/** History of a single municipality over time. */
export function municipalitySeries(muniFile, votes, bfs) {
  const out = [];
  for (const v of votes) {
    const r = muniFile?.results?.[v.id]?.[bfs];
    if (r) out.push({ date: v.date, id: v.id, value: r[0], title: v.title });
  }
  return out;
}

/** Escape text for use inside innerHTML (tooltips). Data files are untrusted-ish: always escape. */
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

import {
  CANTON_CODES, CANTON_NAMES, fmtPct, fmtSigned, yesColor, textOn, voteTitle, filterVotes, cantonSeries,
  movingAverage, cantonMajority, rankCantons, municipalityRows, municipalitySeries, esc, armsUrl,
} from './lib.js';
import { tileMap, lineChart, sparkline, SERIES_COLORS } from './charts.js';
import { t, getLang, setLang } from './i18n.js';

const $ = (sel, root = document) => root.querySelector(sel);
const state = { meta: null, votes: [], cantons: {}, muni: {}, trend: { sel: ['ZH', 'GE', 'TI'], mode: 'yes', smooth: true, q: '' }, list: { q: '', from: null, to: null, outcome: 'all', kind: 'all' } };
const app = $('#app');

/** Tiny hyperscript helper; strings become text nodes (never HTML). */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
  return el;
}

const armsImg = (code, size = 'xs') => h('img', { class: 'arms ' + size, src: armsUrl(code), alt: '', loading: 'lazy', decoding: 'async' });
const names = () => CANTON_NAMES[getLang()] || CANTON_NAMES.de;
const kindLabel = (k) => ({ initiative: t('initiative'), referendum: t('referendum'), counter: t('counter') }[k] || k || '');

async function loadJson(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}
async function loadMuni(code) {
  if (state.muni[code] !== undefined) return state.muni[code];
  try { state.muni[code] = await loadJson(`data/municipalities/${code}.json`); } catch { state.muni[code] = null; }
  return state.muni[code];
}

// ---------------------------------------------------------------- views
function viewList() {
  const L = state.list;
  const years = [...new Set(state.votes.map((v) => +v.date.slice(0, 4)))].sort((a, b) => a - b);
  const rows = filterVotes(state.votes, { ...L, lang: getLang() }).slice().reverse();
  const yearSel = (key) => h('select', { 'aria-label': t(key), onChange: (e) => { L[key] = e.target.value ? +e.target.value : null; render(); } },
    h('option', { value: '' }, t(key)), years.map((y) => h('option', { value: y, selected: L[key] === y }, y)));

  const controls = h('div', { class: 'controls' },
    h('input', { type: 'search', placeholder: t('search'), value: L.q, 'aria-label': t('search'),
      onInput: (e) => { L.q = e.target.value; clearTimeout(viewList.tm); viewList.tm = setTimeout(() => render({ keepFocus: 'search' }), 180); }, id: 'search' }),
    yearSel('from'), yearSel('to'),
    h('select', { 'aria-label': t('outcome'), onChange: (e) => { L.outcome = e.target.value; render(); } },
      [['all', t('all')], ['yes', t('accepted')], ['no', t('rejected')]].map(([v, l]) => h('option', { value: v, selected: L.outcome === v }, l))),
    h('select', { 'aria-label': t('kind'), onChange: (e) => { L.kind = e.target.value; render(); } },
      [['all', t('all')], ['initiative', t('initiative')], ['referendum', t('referendum')]].map(([v, l]) => h('option', { value: v, selected: L.kind === v }, l))));

  const latest = state.votes[state.votes.length - 1];
  const stats = h('div', { class: 'stats' },
    stat(state.votes.length, t('votes_found')),
    stat(state.votes.filter((v) => v.accepted).length, t('accepted')),
    stat(latest ? latest.date : '–', t('built') + ' · ' + (state.meta.built || '').slice(0, 10)));

  const table = h('table', { class: 'list' },
    h('thead', {}, h('tr', {}, h('th', {}, 'Datum'), h('th', {}, 'Vorlage'), h('th', { class: 'num' }, t('yes')), h('th', { class: 'num' }, t('turnout')), h('th', {}, ''))),
    h('tbody', {}, rows.slice(0, 400).map((v) => h('tr', { tabindex: 0, class: 'row', onClick: () => go(`#/vote/${v.id}`),
      onKeydown: (e) => { if (e.key === 'Enter') go(`#/vote/${v.id}`); } },
      h('td', { class: 'date' }, v.date),
      h('td', {}, h('div', { class: 'vt' }, voteTitle(v, getLang())), v.kind ? h('span', { class: 'chip' }, kindLabel(v.kind)) : null),
      h('td', { class: 'num' }, h('span', { class: 'pill', style: `background:${yesColor(v.yes)};color:${textOn(v.yes)}` }, fmtPct(v.yes))),
      h('td', { class: 'num' }, fmtPct(v.turnout)),
      h('td', { class: 'out ' + (v.accepted ? 'ok' : 'ko') }, v.accepted ? '✓ ' + t('accepted') : '✕ ' + t('rejected'))))));
  return h('section', {}, stats, controls, h('p', { class: 'muted' }, `${rows.length} ${t('votes_found')}`), rows.length ? table : h('p', {}, t('none')));
}
const stat = (n, label) => h('div', { class: 'stat' }, h('div', { class: 'n' }, n), h('div', { class: 'l' }, label));

async function viewVote(id) {
  const v = state.votes.find((x) => x.id === id);
  if (!v) return h('p', {}, t('none'));
  const res = state.cantons[id] || {};
  const maj = cantonMajority(res);
  const sel = state.selCanton && res[state.selCanton] ? state.selCanton : null;
  const values = Object.fromEntries(Object.entries(res).map(([c, r]) => [c, { yes: r[0], turnout: r[1] }]));
  const mapBox = h('div', { class: 'mapbox' });
  const muniBox = h('div', { id: 'muni' }, h('p', { class: 'muted' }, t('pick_canton')));
  const ranking = rankCantons(res, v.yes, state.rankBy || 'yes');

  const page = h('section', {},
    h('a', { href: '#/', class: 'back' }, t('back')),
    h('h2', {}, voteTitle(v, getLang())),
    h('p', { class: 'muted' }, v.date, v.kind ? ' · ' + kindLabel(v.kind) : ''),
    h('div', { class: 'stats' },
      h('div', { class: 'stat big', style: `border-color:${yesColor(v.yes)}` }, h('div', { class: 'n' }, fmtPct(v.yes)), h('div', { class: 'l' }, `${t('yes')} · ${v.accepted ? t('accepted') : t('rejected')}`)),
      stat(fmtPct(v.turnout), t('turnout')),
      stat(`${maj.yes} / ${maj.total}`, t('cantons_yes'))),
    h('div', { class: 'grid2' },
      h('div', { class: 'card' }, h('h3', {}, t('canton_map')), mapBox, legend()),
      h('div', { class: 'card' }, h('h3', {}, t('rank')),
        h('div', { class: 'seg' }, ['yes', 'delta'].map((k) => h('button', { class: (state.rankBy || 'yes') === k ? 'on' : '', onClick: () => { state.rankBy = k; render(); } }, t('by_' + k)))),
        h('ol', { class: 'rank' }, ranking.map((r) => h('li', { onClick: () => { state.selCanton = r.code; render(); }, class: r.code === sel ? 'sel' : '' },
          h('span', { class: 'cn' }, armsImg(r.code), h('span', {}, names()[r.code])),
          h('span', { class: 'bar' }, h('i', { style: `width:${r.yes}%;background:${yesColor(r.yes)}` })),
          h('span', { class: 'rv' }, fmtPct(r.yes)), h('span', { class: 'rd muted' }, fmtSigned(r.delta))))))),
    h('div', { class: 'card', id: 'muni-card' }, h('h3', { class: 'hd-arms' }, sel ? armsImg(sel, 'sm') : null, t('municipalities') + (sel ? ' · ' + names()[sel] : '')), muniBox));

  queueMicrotask(() => {
    tileMap(mapBox, values, { names: names(), selected: sel, label: t('canton_map'),
      onSelect: (c) => { state.selCanton = c; render({ keepScroll: true }); },
      tipHtml: (c, r) => `<img class="arms tipimg" src="${armsUrl(c)}" alt=""><b>${esc(names()[c])}</b><br>${t('yes')}: ${r ? fmtPct(r.yes) : '–'}<br>${t('turnout')}: ${r ? fmtPct(r.turnout) : '–'}` });
    if (sel) fillMuni(muniBox, sel, v);
  });
  return page;
}

function legend() {
  const stops = [25, 35, 45, 50, 55, 65, 75];
  return h('div', { class: 'legend' }, h('span', {}, t('legend_no')),
    h('div', { class: 'ramp' }, stops.map((s) => h('i', { style: `background:${yesColor(s)}`, title: s + ' %' }))), h('span', {}, t('legend_yes')));
}

async function fillMuni(box, code, vote) {
  const file = await loadMuni(code);
  const rows = municipalityRows(file, vote.id, vote.yes);
  if (!rows.length) { box.replaceChildren(h('p', { class: 'muted' }, t('no_muni'))); return; }
  rows.sort((a, b) => b.yes - a.yes);
  const list = (title, arr) => h('div', {}, h('h4', {}, title), h('ol', { class: 'rank' }, arr.map((r) => {
    const series = municipalitySeries(file, state.votes, r.bfs).map((p) => ({ date: p.date, value: p.value }));
    return h('li', {}, h('span', { class: 'cn' }, h('span', {}, r.name)), h('span', { class: 'bar' }, h('i', { style: `width:${r.yes}%;background:${yesColor(r.yes)}` })),
      h('span', { class: 'rv' }, fmtPct(r.yes)), h('span', { class: 'rd muted' }, fmtSigned(r.delta)), h('span', { class: 'sp' }, sparkline(series)));
  })));
  box.replaceChildren(h('p', { class: 'muted' }, `${rows.length} ${t('municipalities')} · ${t('muni_hint')}`),
    h('div', { class: 'grid2' }, list(t('highest'), rows.slice(0, 10)), list(t('lowest'), rows.slice(-10).reverse())));
}

function viewTrends() {
  const T = state.trend;
  const votes = filterVotes(state.votes, { q: T.q, lang: getLang() });
  const chart = h('div', { class: 'chartbox' });
  const chips = h('div', { class: 'chips' }, CANTON_CODES.map((c) => {
    const on = T.sel.includes(c);
    const col = on ? SERIES_COLORS[T.sel.indexOf(c) % SERIES_COLORS.length] : null;
    return h('button', { class: 'chip-btn' + (on ? ' on' : ''), style: on ? `--c:${col}` : null, 'aria-pressed': on, title: names()[c],
      onClick: () => { T.sel = on ? T.sel.filter((x) => x !== c) : [...T.sel, c].slice(-6); render({ keepScroll: true }); } }, armsImg(c), c);
  }));
  const controls = h('div', { class: 'controls' },
    h('div', { class: 'seg' }, ['yes', 'delta'].map((m) => h('button', { class: T.mode === m ? 'on' : '', onClick: () => { T.mode = m; render({ keepScroll: true }); } }, t('mode_' + m)))),
    h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: T.smooth, onChange: (e) => { T.smooth = e.target.checked; render({ keepScroll: true }); } }), t('smooth')),
    h('input', { type: 'search', id: 'topic', placeholder: t('topic'), value: T.q, 'aria-label': t('topic'),
      onInput: (e) => { T.q = e.target.value; clearTimeout(viewTrends.tm); viewTrends.tm = setTimeout(() => render({ keepFocus: 'topic', keepScroll: true }), 220); } }));

  queueMicrotask(() => {
    const series = T.sel.map((c, i) => {
      let pts = cantonSeries(votes, state.cantons, c, T.mode);
      if (T.smooth) pts = movingAverage(pts, 5);
      return { name: names()[c], color: SERIES_COLORS[i % SERIES_COLORS.length], points: pts, noDots: T.smooth };
    });
    if (T.mode === 'yes') {
      let nat = votes.filter((v) => v.yes != null).map((v) => ({ date: v.date, id: v.id, value: v.yes, title: v.title }));
      if (T.smooth) nat = movingAverage(nat, 5);
      series.push({ name: t('national_line'), color: '#777', points: nat, thin: true, noDots: true });
    }
    lineChart(chart, series, {
      yDomain: T.mode === 'yes' ? [0, 100] : null, ref: T.mode === 'yes' ? 50 : 0, empty: t('none'),
      yFormat: T.mode === 'yes' ? (v) => v.toFixed(0) + ' %' : (v) => (v > 0 ? '+' : '') + v.toFixed(0) + ' pp',
      tipHtml: (p, s) => `<b>${esc(s.name)}</b> · ${esc(p.date)}<br>${esc(voteTitle({ title: p.title, id: p.id }, getLang()))}<br>${T.mode === 'yes' ? fmtPct(p.value) : fmtSigned(p.value)}`,
      onPick: (p) => go(`#/vote/${p.id}`),
    });
  });
  return h('section', {}, h('h2', {}, t('trend_title')), h('p', { class: 'muted' }, t('cantons') + ' (max. 6)'), chips, controls, h('div', { class: 'card' }, chart),
    h('p', { class: 'muted small' }, `${votes.length} ${t('votes_found')}`));
}

function viewAbout() {
  const src = state.meta.sources || [];
  return h('section', { class: 'prose' }, h('h2', {}, t('about_title')),
    h('ul', {}, src.map((s) => h('li', {}, s))),
    h('p', {}, t('source_line') + '. ', h('a', { href: 'https://opendata.swiss', rel: 'noopener' }, 'opendata.swiss'), ' · ',
      h('a', { href: 'https://www.bfs.admin.ch/bfs/de/home/statistiken/politik/abstimmungen.html', rel: 'noopener' }, 'BFS Abstimmungen'), ' · ',
      h('a', { href: 'https://github.com/lars4/abstimmungs-explorer', rel: 'noopener' }, 'GitHub')),
    h('h3', {}, t('method_title')),
    h('ul', {},
      h('li', {}, 'Ja-Anteil = Ja-Stimmen / gültige Stimmen. Der Kartogramm-Modus („Tile Grid“) zeigt jeden Kanton gleich gross.'),
      h('li', {}, 'Gemeindedaten folgen dem Gebietsstand der Quelle; durch Fusionen sind Zeitreihen einzelner Gemeinden nicht immer lückenlos.'),
      h('li', {}, 'Abweichung = Ja-Anteil des Kantons minus nationaler Ja-Anteil (Prozentpunkte, pp).'),
      h('li', {}, 'Kantonale und kommunale Vorlagen werden nicht dargestellt; Fokus sind eidgenössische Abstimmungen.'),
      h('li', {}, 'Kantonswappen: Wikimedia Commons, Serie «Wappen … matt» (siehe assets/arms/README.md).')),
    h('p', { class: 'muted' }, `${t('built')}: ${state.meta.built}`));
}

// ---------------------------------------------------------------- router
const go = (hash) => { location.hash = hash; };
async function render(opts = {}) {
  const y = window.scrollY;
  const hash = location.hash || '#/';
  let view;
  if (hash.startsWith('#/vote/')) view = await viewVote(decodeURIComponent(hash.slice(7)));
  else if (hash === '#/trends') view = viewTrends();
  else if (hash === '#/about') view = viewAbout();
  else view = viewList();
  app.replaceChildren(view);
  document.querySelectorAll('nav a').forEach((a) => a.classList.toggle('on', a.getAttribute('href') === (hash.startsWith('#/vote/') ? '#/' : hash)));
  if (opts.keepFocus) { const el = document.getElementById(opts.keepFocus); if (el) { el.focus(); const n = el.value.length; el.setSelectionRange?.(n, n); } }
  if (opts.keepScroll) window.scrollTo(0, y); else if (!opts.keepFocus) window.scrollTo(0, 0);
}

function chrome() {
  $('#title').textContent = t('title');
  $('#tagline').textContent = t('tagline');
  document.title = t('title');
  document.documentElement.lang = getLang();
  $('#nav-votes').textContent = t('nav_votes'); $('#nav-trends').textContent = t('nav_trends'); $('#nav-about').textContent = t('nav_about');
  const banner = $('#demo');
  banner.hidden = !state.meta?.demo; banner.textContent = t('demo_banner');
  $('#lang').value = getLang();
}

async function init() {
  $('#lang').addEventListener('change', (e) => { setLang(e.target.value); chrome(); render({ keepScroll: true }); });
  window.addEventListener('hashchange', () => render());
  try {
    const [vj, cj] = await Promise.all([loadJson('data/votes.json'), loadJson('data/cantons.json')]);
    state.meta = vj.meta; state.votes = vj.votes; state.cantons = cj;
  } catch (e) {
    app.replaceChildren(h('div', { class: 'error' }, h('h2', {}, 'Daten nicht gefunden / Data not found'),
      h('p', {}, String(e.message)), h('pre', {}, 'python -m pipeline.build demo   # synthetic\npython -m pipeline.build live   # real data')));
    return;
  }
  chrome();
  render();
}
init();

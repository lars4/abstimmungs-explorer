import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  CANTON_CODES, TILE_GRID, yesColor, filterVotes, cantonSeries, movingAverage, cantonMajority,
  rankCantons, armsUrl, niceTicks, municipalityRows, municipalitySeries, fmtPct, fmtSigned, dateToYear,
} from '../web/js/lib.js';

const votes = [
  { id: 'a', date: '2019-05-19', title: { de: 'Waffenrecht' }, kind: 'referendum', yes: 63.7, accepted: true },
  { id: 'b', date: '2020-09-27', title: { de: 'Begrenzungsinitiative' }, kind: 'initiative', yes: 38.3, accepted: false },
  { id: 'c', date: '2021-06-13', title: { de: 'CO2-Gesetz', fr: 'Loi CO2' }, kind: 'referendum', yes: 48.4, accepted: false },
];
const cantons = { a: { ZH: [60, 50], GE: [70, 52] }, b: { ZH: [35, 60] }, c: { ZH: [52, 58], GE: [55, 50] } };

test('tile grid covers every canton exactly once without collisions', () => {
  assert.equal(Object.keys(TILE_GRID).length, 26);
  assert.deepEqual(Object.keys(TILE_GRID).sort(), [...CANTON_CODES].sort());
  const cells = new Set(Object.values(TILE_GRID).map((p) => p.join(',')));
  assert.equal(cells.size, 26);
});

test('yesColor is neutral at 50 and saturated at the ends, handles null', () => {
  assert.equal(yesColor(50), 'rgb(236,236,232)');
  assert.notEqual(yesColor(80), yesColor(20));
  assert.equal(yesColor(null), 'var(--na)');
  assert.equal(yesColor(120), yesColor(75)); // clamped
});

test('filterVotes by text, years, outcome, kind', () => {
  assert.equal(filterVotes(votes, { q: 'co2' }).length, 1);
  assert.equal(filterVotes(votes, { from: 2020 }).length, 2);
  assert.equal(filterVotes(votes, { to: 2019 }).length, 1);
  assert.equal(filterVotes(votes, { outcome: 'yes' }).length, 1);
  assert.equal(filterVotes(votes, { kind: 'initiative' })[0].id, 'b');
  assert.equal(filterVotes(votes, { q: '2021-06' })[0].id, 'c');
});

test('cantonSeries yes and delta, skipping missing cantons', () => {
  const s = cantonSeries(votes, cantons, 'GE');
  assert.deepEqual(s.map((p) => p.id), ['a', 'c']);
  const d = cantonSeries(votes, cantons, 'ZH', 'delta');
  assert.equal(d.length, 3);
  assert.ok(Math.abs(d[0].value - (60 - 63.7)) < 1e-9);
});

test('movingAverage window', () => {
  const m = movingAverage([{ value: 10 }, { value: 20 }, { value: 30 }], 2);
  assert.deepEqual(m.map((p) => p.value), [10, 15, 25]);
});

test('cantonMajority and rankCantons', () => {
  assert.deepEqual(cantonMajority(cantons.c), { yes: 2, no: 0, total: 2 });
  const r = rankCantons(cantons.a, 63.7, 'delta');
  assert.equal(r[0].code, 'GE'); // |70-63.7| = 6.3 beats |60-63.7| = 3.7
  assert.equal(rankCantons(cantons.a, 63.7, 'yes')[0].code, 'GE');
});

test('niceTicks', () => {
  assert.deepEqual(niceTicks(0, 100, 5), [0, 20, 40, 60, 80, 100]);
  assert.deepEqual(niceTicks(30, 70, 4), [30, 40, 50, 60, 70]);
  assert.deepEqual(niceTicks(5, 5), [5]);
});

test('municipality helpers', () => {
  const f = { names: { 1: 'Alpha' }, results: { a: { 1: [55, 40] }, b: { 1: [45, 41] } } };
  const rows = municipalityRows(f, 'a', 50);
  assert.equal(rows[0].name, 'Alpha');
  assert.equal(rows[0].delta, 5);
  assert.equal(municipalitySeries(f, votes, '1').length, 2);
  assert.deepEqual(municipalityRows(null, 'a'), []);
});

test('formatters', () => {
  assert.equal(fmtPct(54.55), '54,5 %'.replace('54,5', (54.55).toFixed(1).replace('.', ',')));
  assert.equal(fmtPct(null), '–');
  assert.equal(fmtSigned(2.34), '+2,3 pp');
  assert.equal(fmtSigned(-2.34), '−2,3 pp');
  assert.ok(dateToYear('2020-07-01') > 2020.4 && dateToYear('2020-07-01') < 2020.6);
});

test('generated demo data matches what the app expects', { skip: !fs.existsSync('web/data/votes.json') }, () => {
  const { votes: vs, meta } = JSON.parse(fs.readFileSync('web/data/votes.json', 'utf8'));
  const cs = JSON.parse(fs.readFileSync('web/data/cantons.json', 'utf8'));
  assert.ok(vs.length > 10 && meta.built);
  for (const v of vs) {
    assert.ok(cs[v.id], 'canton results for ' + v.id);
    for (const [code, r] of Object.entries(cs[v.id])) {
      assert.ok(CANTON_CODES.includes(code));
      assert.ok(r[0] >= 0 && r[0] <= 100);
    }
  }
});

test('every canton has a well-formed coat of arms file', () => {
  assert.equal(armsUrl('ZH'), 'assets/arms/ZH.svg');
  for (const c of CANTON_CODES) {
    const f = `web/assets/arms/${c}.svg`;
    assert.ok(fs.existsSync(f), 'missing ' + f);
    const svg = fs.readFileSync(f, 'utf8');
    assert.ok(svg.startsWith('<svg') && svg.includes('viewBox'), 'bad svg ' + c);
    assert.ok(!/<script|onload=|onclick=|foreignObject|javascript:/i.test(svg), 'unsafe svg ' + c);
  }
});

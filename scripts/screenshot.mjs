// Smoke test + screenshots with Playwright (Chromium). Usage:
//   node scripts/screenshot.mjs [outDir]    (serves web/ on a free local port)
// Fails (exit 1) on console errors, page errors or failed requests.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); } catch { ({ chromium } = require('/opt/npm-tools/node_modules/playwright')); }

const root = path.resolve('web');
const out = path.resolve(process.argv[2] || 'docs');
fs.mkdirSync(out, { recursive: true });
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const p = path.join(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/$/, '/index.html'));
  if (!p.startsWith(root) || !fs.existsSync(p)) { res.writeHead(404); return res.end('nf'); }
  res.writeHead(200, { 'content-type': MIME[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
});
await new Promise((r) => server.listen(0, r));
const base = `http://localhost:${server.address().port}/`;

const problems = [];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 1 });
page.on('console', (m) => { if (m.type() === 'error') problems.push('console: ' + m.text()); });
page.on('pageerror', (e) => problems.push('pageerror: ' + e.message));
page.on('requestfailed', (r) => problems.push('requestfailed: ' + r.url()));
page.on('response', (r) => { if (r.status() >= 400) problems.push(`http ${r.status()}: ${r.url()}`); });

await page.goto(base, { waitUntil: 'networkidle' });
await page.waitForSelector('table.list tr.row');
await page.screenshot({ path: path.join(out, 'screenshot-list.png') });

await page.click('table.list tr.row');
await page.waitForSelector('.tilemap');
await page.click('.tile >> nth=0');
await page.waitForSelector('#muni ol.rank');
await page.waitForTimeout(500);
const brokenVote = await page.$$eval('img, svg image', (els) => els.filter((e) => e.tagName === 'IMG' && !(e.complete && e.naturalWidth > 0)).map((e) => e.src));
if (brokenVote.length) problems.push('broken images on vote page: ' + brokenVote.join(', '));
await page.screenshot({ path: path.join(out, 'screenshot-vote.png'), fullPage: true });

await page.goto(base + '#/trends');
await page.waitForSelector('.linechart path');
await page.mouse.move(600, 520);
await page.screenshot({ path: path.join(out, 'screenshot-trends.png') });

// every <img> must actually have loaded (catches wrong paths / MIME types / broken SVGs)
await page.waitForTimeout(500);
await page.goto(base + '#/trends');
await page.waitForSelector('.chip-btn img.arms');
await page.waitForTimeout(500);
const broken = await page.$$eval('img', (imgs) => imgs.filter((i) => !(i.complete && i.naturalWidth > 0)).map((i) => i.src));
if (broken.length) problems.push('broken images: ' + broken.join(', '));
const imgCount = await page.$$eval('img.arms', (n) => n.length);
if (imgCount < 26) problems.push('expected 26 coats of arms on trends page, found ' + imgCount);

await page.selectOption('#lang', 'en');
await page.goto(base + '#/about');
await page.waitForSelector('.prose');

await browser.close();
server.close();
if (problems.length) { console.error('PROBLEMS:\n' + problems.join('\n')); process.exit(1); }
console.log('smoke test ok; screenshots in', out);

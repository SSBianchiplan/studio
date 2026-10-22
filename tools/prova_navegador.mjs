/* Prova de ponta a ponta no Chrome de verdade: login, editor, formatos, filtros,
   exportação, configurações, PWA e telas de celular.
   Uso (da pasta onde puppeteer-core está instalado):
     BASE=http://127.0.0.1:8972 EMAIL=... SENHA=... AMOSTRAS=<pasta> SAIDA=<pasta> node prova_navegador.mjs */
import puppeteer from 'puppeteer-core';
import { readFileSync, readdirSync, mkdirSync } from 'fs';
import { join } from 'path';

const BASE = process.env.BASE || 'http://127.0.0.1:8972';
const AM = process.env.AMOSTRAS, OUT = process.env.SAIDA || '.';
mkdirSync(OUT, { recursive: true });
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
let falhas = 0;
const ok = (c, m) => { console.log((c ? '  ok   ' : '  FALHA ') + m); if (!c) falhas++; };

const nav = await puppeteer.launch({ executablePath: CHROME, headless: true, protocolTimeout: 120000, args: ['--force-color-profile=srgb'] });
const p = await nav.newPage();
const erros = [];
p.on('pageerror', e => erros.push('pageerror: ' + e.message));
p.on('console', m => { if (m.type() === 'error' && !/favicon|401|Failed to load resource/.test(m.text())) erros.push('console: ' + m.text()); });
await p.setViewport({ width: 1366, height: 860 });

/* ---- login ---- */
await p.goto(BASE + '/', { waitUntil: 'networkidle0' });
ok(new URL(p.url()).pathname === '/login', 'sem sessão, / leva ao login');
await p.screenshot({ path: join(OUT, 'login-desktop.png') });
await p.type('#email', process.env.EMAIL);
await p.type('#password', 'senha-errada');
await p.click('#b1');
await p.waitForFunction(() => document.getElementById('e1').textContent.length > 0);
ok(true, 'senha errada mostra erro: ' + await p.$eval('#e1', e => e.textContent));
await p.$eval('#password', e => e.value = '');
await p.type('#password', process.env.SENHA);
await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle0' }), p.click('#b1')]);
ok(new URL(p.url()).pathname === '/', 'login leva ao editor');
await p.waitForFunction(() => window.__studio && document.getElementById('bMe'), { timeout: 20000 });
ok(true, 'editor montou e a barra tem o avatar');
const db = await p.evaluate(() => window.__STUDIO_DB);
ok(/^gplansis-studio-u\d+$/.test(db), 'banco local separado por usuário: ' + db);
await p.screenshot({ path: join(OUT, 'editor-desktop.png') });

/* ---- leitura de formatos ---- */
for (const f of readdirSync(AM).sort()) {
  const b64 = readFileSync(join(AM, f)).toString('base64');
  const r = await p.evaluate(async (name, b64) => {
    const u8 = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const t0 = performance.now();
    try {
      const c = await Promise.race([studioDecodeFile(new File([u8], name)), new Promise((_, j) => setTimeout(() => j(new Error('tempo esgotado (30 s)')), 30000))]);
      const d = c.getContext('2d').getImageData(c.width >> 1, c.height >> 1, 1, 1).data;
      return { ok: true, w: c.width, h: c.height, px: [...d], ms: Math.round(performance.now() - t0), note: c._note || '' };
    } catch (e) { return { ok: false, err: String(e && e.message || e) }; }
  }, f, b64);
  const blank = r.ok && r.px[3] === 0;
  ok(r.ok && !blank, `${f.padEnd(10)} ${r.ok ? `${r.w}×${r.h} centro=rgba(${r.px}) ${r.ms} ms ${r.note}` : r.err}`);
}

/* ---- filtros novos: todos rodam e mudam a imagem ---- */
const fx = await p.evaluate(() => {
  const keys = ['exposure', 'vibrance', 'whitebal', 'shadhi', 'colorbal', 'chmix', 'photof', 'gradmap', 'autotone', 'clahe', 'dehaze', 'hdrtone', 'surface', 'denoise', 'median', 'highpass', 'clarity', 'motion', 'radial', 'tilt', 'lens', 'swirl', 'ripple', 'kuwahara', 'halftone', 'glow', 'sketch'];
  const src = genPhoto('industrial', 3, 400, 260); const base = imgData(src).data;
  const out = [];
  const tweak = { glow: { t: 30 }, exposure: { e: 1 }, chmix: { rr: 50, gb: 50 }, lens: { k: 40, ca: 50 }, gradmap: {}, colorbal: { sr: 40 }, whitebal: { t: 40 } };
  for (const k of keys) {
    const d = new Uint8ClampedArray(base); const t0 = performance.now();
    try {
      FX[k].run(d, src.width, src.height, Object.assign({}, FX[k].p, tweak[k] || {}));
      let diff = 0, nan = 0; for (let i = 0; i < d.length; i++) { diff += Math.abs(d[i] - base[i]); if (Number.isNaN(d[i])) nan++; }
      out.push([k, true, diff / d.length, Math.round(performance.now() - t0)]);
    } catch (e) { out.push([k, false, e.message]); }
  }
  return out;
});
for (const [k, good, diff, ms] of fx) ok(good && diff > 0.05, `filtro ${k.padEnd(9)} ${good ? `Δ médio ${diff.toFixed(2)} · ${ms} ms (400×260)` : diff}`);
const menus = await p.evaluate(() => ({ adj: ADJ_KEYS.length, fil: FIL_KEYS.length }));
ok(menus.adj >= 21 && menus.fil >= 23, `menus: ${menus.adj} ajustes, ${menus.fil} filtros`);

/* ---- filtro como camada de ajuste no documento ---- */
const camada = await p.evaluate(async () => { const L = pxAddLayer('Clareza', 'adj'); L.fx = [{ t: 'clahe', p: { ...FX.clahe.p }, on: true }]; pxCommit('teste'); pxDraw(); return P().layers.length; });
ok(camada >= 2, 'CLAHE como camada de ajuste no Pixel');

/* ---- preenchimento inteligente ---- */
const fill = await p.evaluate(async () => {
  const d = P(); d.act = 0; const L = d.layers[0];
  const before = imgData(L.c).data.slice(); pxSelPath(d, x => x.rect(200, 120, 160, 120), 'new');
  await pxSmartFill(); const after = imgData(L.c).data; let ch = 0, nan = 0;
  for (let i = 0; i < after.length; i += 4) { if (after[i] !== before[i]) ch++; }
  pxDeselect(); return { ch, total: after.length / 4 };
});
ok(fill.ch > 1000, `preenchimento inteligente alterou ${fill.ch} px dentro da seleção`);

/* ---- exportação: cada formato codifica e volta a abrir ---- */
const enc = await p.evaluate(async () => {
  const c = pxFlatten(P()); const small = fitCanvas(c, 300); const res = [];
  for (const [f, ext] of [['image/png', 'png'], ['image/jpeg', 'jpg'], ['image/webp', 'webp'], ['image/bmp', 'bmp'], ['image/tiff', 'tif'], ['image/x-icon', 'ico'], ['image/qoi', 'qoi']]) {
    try { const b = await encodeAs(small, f, .9); const back = await studioDecodeFile(new File([b], 'x.' + ext)); res.push([ext, true, b.size, back.width + '×' + back.height]); }
    catch (e) { res.push([ext, false, e.message]); }
  }
  try { const b = await encodePSDDoc(P()); const psd = await readPSD(new Uint8Array(await b.arrayBuffer()), true); res.push(['psd', true, b.size, psd.width + '×' + psd.height + ' · ' + (psd.children || []).length + ' camadas']); }
  catch (e) { res.push(['psd', false, e.message]); }
  res.push(['avif', 'info', await STUDIO_ENC.avifOK() ? 'codifica' : 'este navegador não codifica AVIF']);
  return res;
});
for (const [ext, good, a, b] of enc) good === 'info' ? console.log(`  info  avif: ${a}`) : ok(good, `exporta ${ext.padEnd(4)} ${good ? `${Math.round(a / 1024)} KB → reabre ${b}` : a}`);

/* ---- PSD com camadas reabre como documento de camadas ---- */
const psdL = await p.evaluate(async () => { const b = await encodePSDDoc(P()); const n0 = PX.docs.length; await pxOpenPSDLayers(new File([b], 'teste.psd')); return { docs: PX.docs.length - n0, layers: P().layers.map(l => l.name) }; });
ok(psdL.docs === 1 && psdL.layers.length >= 2, 'PSD reaberto com camadas: ' + psdL.layers.join(', '));

/* ---- animação como camadas ---- */
const anim = await p.evaluate(async b64 => { const u8 = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); await pxOpenAnimationLayers(new File([u8], 'anim.gif', { type: 'image/gif' })); return P().layers.length; }, readFileSync(join(AM, 'anim.gif')).toString('base64'));
ok(anim === 4, `GIF animado aberto como ${anim} camadas`);

/* ---- nuvem ---- */
const cloud = await p.evaluate(async () => { const r = await api('/api/projects?name=Prova%20E2E', { method: 'PUT', body: serializeProject(), raw: true }); const l = await api('/api/projects'); const t = await api('/api/projects/' + r.id); return { size: r.size, n: l.length, app: (typeof t === 'string' ? JSON.parse(t) : t).app }; });
ok(cloud.app === 'GPlanSiS|Studio', `projeto na nuvem: ${Math.round(cloud.size / 1024)} KB, ${cloud.n} no servidor`);

/* ---- configurações ---- */
await p.click('#bMe');
await p.waitForSelector('.menu');
const itens = await p.$$eval('.menu button', bs => bs.map(b => b.textContent));
ok(itens.includes('Configurações…') && itens.includes('Usuários e permissões…') && itens.includes('Sair'), 'menu da conta: ' + itens.join(' | '));
await p.evaluate(() => [...document.querySelectorAll('.menu button')].find(b => b.textContent === 'Configurações…').click());
await p.waitForSelector('.st-dlg .st-avbig');
await p.screenshot({ path: join(OUT, 'config-perfil.png') });
for (const t of ['seguranca', 'preferencias', 'formatos', 'usuarios', 'auditoria']) {
  await p.click(`.dtab[data-t="${t}"]`);
  await p.waitForFunction(() => !document.querySelector('.st-pane').textContent.startsWith('Carregando'), { timeout: 8000 });
  const err = await p.$eval('.st-pane', e => e.querySelector('.st-err')?.textContent || '');
  ok(!err, 'aba ' + t + (err ? ': ' + err : ''));
  await p.screenshot({ path: join(OUT, `config-${t}.png`) });
}
await p.keyboard.press('Escape');

/* ---- permissões aplicadas no editor ---- */
const perm = await p.evaluate(() => { const saved = JSON.parse(JSON.stringify(ME.u)); ME.u.perms.foto = false; ME.u.perms.exportar = false; applyPerms(); setMod('foto'); const r = { hidden: document.querySelector('.modbtn[data-mod=foto]').hidden, mod: S.mod }; return saveFile('x.png', new Blob(['x'])).then(v => { r.save = v; ME.u = saved; applyPerms(); setMod('pixel'); return r; }); });
ok(perm.hidden && perm.mod !== 'foto' && perm.save === false, `sem permissão: Foto oculto (${perm.mod} no lugar) e exportação bloqueada`);

/* ---- PWA ---- */
const pwa = await p.evaluate(async () => {
  const m = await (await fetch('/manifest.webmanifest')).json(); const ct = (await fetch('/manifest.webmanifest')).headers.get('content-type');
  const dec = async u => { const b = await (await fetch(u)).blob(); const im = await createImageBitmap(b); return im.width + '×' + im.height; };
  return { ct, icons: await Promise.all(m.icons.filter(i => i.type === 'image/png').map(i => dec(i.src))), apple: await dec('/icons/apple-touch-icon.png'), fav: (await fetch('/favicon.ico')).headers.get('content-type'), sw: !!(await navigator.serviceWorker.getRegistration()) || 'sem https local' };
});
ok(/manifest\+json/.test(pwa.ct) && pwa.icons.includes('192×192') && pwa.icons.includes('512×512') && pwa.apple === '180×180', `PWA: ${pwa.ct}; ícones ${pwa.icons.join(', ')}; apple ${pwa.apple}; favicon ${pwa.fav}; SW ${pwa.sw}`);

/* ---- celular ---- */
const m = await nav.newPage();
await m.emulate({ viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' });
await m.goto(BASE + '/', { waitUntil: 'networkidle0' });
await m.waitForFunction(() => window.__studio && document.getElementById('bMe'), { timeout: 20000 });
const ov = await m.evaluate(() => ({ sw: document.documentElement.scrollWidth, w: innerWidth, top: document.getElementById('top').scrollWidth > document.getElementById('top').clientWidth }));
ok(ov.sw <= ov.w, `celular 390 px: sem rolagem lateral da página (${ov.sw} ≤ ${ov.w})`);
await m.screenshot({ path: join(OUT, 'editor-celular.png') });
await m.click('#bMe'); await m.waitForSelector('.menu');
await m.evaluate(() => [...document.querySelectorAll('.menu button')].find(b => b.textContent === 'Configurações…').click());
await m.waitForSelector('.st-dlg .st-avbig');
await m.screenshot({ path: join(OUT, 'config-celular.png') });
await m.close();
const l = await nav.newPage();
await l.emulate({ viewport: { width: 390, height: 844, deviceScaleFactor: 2, isMobile: true, hasTouch: true }, userAgent: 'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36' });
await l.goto(BASE + '/login', { waitUntil: 'networkidle0' });
await l.screenshot({ path: join(OUT, 'login-celular.png') });

console.log('\nerros de página:', erros.length ? '\n  ' + erros.join('\n  ') : 'nenhum');
if (erros.length) falhas++;
console.log(falhas ? `${falhas} FALHA(S)` : 'TUDO CERTO');
await nav.close();
process.exit(falhas ? 1 : 0);

/* Prova das funções de IA no editor (Chrome real + servidor de teste com Claude simulado).
   BASE=http://127.0.0.1:8973 SENHA=... [EMAIL=contato@gplansis.com] SAIDA=<pasta> node prova_ia.mjs */
import puppeteer from 'puppeteer-core';
import { mkdirSync } from 'fs';
import { join } from 'path';

const BASE = process.env.BASE || 'http://127.0.0.1:8973', OUT = process.env.SAIDA || '.';
mkdirSync(OUT, { recursive: true });
let falhas = 0;
const ok = (c, m) => { console.log((c ? '  ok   ' : '  FALHA ') + m); if (!c) falhas++; };
const nav = await puppeteer.launch({ executablePath: process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, protocolTimeout: 180000 });
const p = await nav.newPage();
const erros = [];
p.on('pageerror', e => erros.push(e.message));
p.on('console', m => { if (m.type() === 'error' && !/401|402|422|Failed to load/.test(m.text())) erros.push(m.text()); });
await p.setViewport({ width: 1366, height: 860 });
await p.goto(BASE + '/login', { waitUntil: 'networkidle0' });
await p.type('#email', process.env.EMAIL || 'contato@gplansis.com'); await p.type('#password', process.env.SENHA);
await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle0' }), p.click('#b1')]);
await p.waitForFunction(() => window.__studio && document.getElementById('bMe'), { timeout: 20000 });
await p.evaluate(async () => { await api('/api/ai/config', { method: 'PUT', body: { key: 'sk-ant-api03-' + 'y'.repeat(40), quota_usd: 50, level: 'padrao' } }); await aiRefresh(); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const clickBtn = async txt => p.evaluate(t => { const b = [...document.querySelectorAll('.dlg .ft button, .dlg button')].find(x => x.textContent.trim() === t); if (!b) throw new Error('botão ' + t); b.click(); }, txt);

/* menus */
const menus = await p.evaluate(() => ['px-mbar', 'vx-mbar', 'fx-mbar'].map(id => [...document.querySelectorAll('#' + id + ' .mbtn')].map(b => b.textContent)));
ok(menus.every(m => m.includes('IA')), 'menu IA no Pixel, Vetor e Foto: ' + menus.map(m => m.join('/')).join(' · '));
const cat = await p.evaluate(() => { const c = aiCatalog(); return { n: c.length, bytes: JSON.stringify(c).length, ids: c.map(x => x.id) }; });
ok(cat.n >= 40 && !cat.ids.includes('develop'), `catálogo enviado ao Claude: ${cat.n} filtros, ${Math.round(cat.bytes / 1024)} KB`);

/* editar por instrução */
await p.evaluate(() => { setMod('pixel'); aiEditDialog(); });
await p.waitForSelector('.dlg textarea');
await p.type('.dlg textarea', 'mais quente e contrastado');
await clickBtn('Gerar / refazer');
await p.waitForSelector('.st-ops li', { timeout: 15000 });
const ed = await p.evaluate(() => { const L = P().layers[P().act]; return { kind: L.kind, fx: L.fx.map(f => [f.t, f.p]), name: L.name, items: document.querySelectorAll('.st-ops li').length }; });
ok(ed.kind === 'adj' && ed.fx.length === 2 && ed.fx[0][0] === 'whitebal' && ed.fx[0][1].t === 25, 'editar com IA cria camada de ajuste com as operações');
ok(ed.fx[1][1].b === 100 && ed.fx[1][1].c === 30, 'valor fora da faixa é recortado (brilho 999 → 100); filtro inexistente ignorado');
await p.screenshot({ path: join(OUT, 'ia-editar.png') });
await clickBtn('Concluir');
const nAdj = await p.evaluate(() => P().layers.length);
await p.evaluate(() => PXAPI.undo()); await sleep(200);
ok(await p.evaluate(() => P().layers.length) === nAdj - 1, 'Ctrl+Z desfaz a edição da IA');

/* melhorar, selecionar, recortar */
await p.evaluate(() => aiEnhancePixel()); await sleep(800);
ok(await p.evaluate(() => { const L = P().layers[P().act]; return L.kind === 'adj' && L.fx[0].t === 'develop' && L.fx[0].p.exp === 0.6; }), 'melhorar automaticamente: revelação como camada de ajuste');
p.evaluate(() => aiSelect());
await p.waitForSelector('.dlg input[type=text]'); await p.type('.dlg input[type=text]', 'o sol'); await clickBtn('OK'); await sleep(1200);
const sel = await p.evaluate(() => { const s = P().sel; return s ? s.bb : null; });
ok(sel && sel.w > 50 && sel.h > 50, 'selecionar com IA cria seleção: ' + JSON.stringify(sel));
const w0 = await p.evaluate(() => P().w);
p.evaluate(() => aiCropPixel());
await p.waitForSelector('.st-crop1', { timeout: 15000 }); await p.screenshot({ path: join(OUT, 'ia-enquadrar.png') });
await p.click('.st-crop1'); await sleep(500);
ok(await p.evaluate(() => P().w) < w0, 'sugestão de enquadramento aplica o recorte');

/* vetor */
p.evaluate(() => aiSvgDialog(null));
await p.waitForSelector('.dlg textarea'); await p.type('.dlg textarea', 'ícone de válvula'); await clickBtn('Gerar'); await sleep(1500);
const vx = await p.evaluate(() => ({ mod: S.mod, name: V().name, n: V().objs.length, svg: vExportSVG(V()) }));
ok(vx.mod === 'vetor' && vx.n >= 1 && !/script|javascript:|onclick/i.test(vx.svg), `SVG da IA virou documento no Vetor (“${vx.name}”) sem script`);
await p.screenshot({ path: join(OUT, 'ia-vetor.png') });

/* foto: catalogar */
await p.evaluate(() => { setMod('foto'); FXS.view = 'lib'; FXS.sel = new Set(FXS.photos.slice(0, 2).map(q => q.id)); fxUI(); aiCatalogPhotos(); });
await p.waitForSelector('.dlg'); await clickBtn('Catalogar'); await sleep(2500);
const cf = await p.evaluate(() => { const ps = FXS.photos.slice(0, 2); const ser = JSON.parse(serializeProject()); return { kw: ps.map(q => q.kw), cap: ps.map(q => q.caption), ser: ser.photos.slice(0, 2).map(q => q.caption) }; });
ok(cf.kw.every(k => /indústria/.test(k)) && cf.cap.every(Boolean), 'catalogar: palavras-chave e legenda nas fotos');
ok(cf.ser.every(Boolean), 'legenda e texto alternativo vão para o projeto salvo');

/* OCR, paleta, revisão */
await p.evaluate(() => { setMod('pixel'); aiOCR(pxFlatten(P())); }); await p.waitForSelector('.dlg textarea'); await sleep(300);
ok(/ALTA TENSÃO/.test(await p.$eval('.dlg textarea', t => t.value)), 'ler texto mostra a transcrição');
await p.keyboard.press('Escape');
await p.evaluate(() => aiPalette(pxFlatten(P()))); await p.waitForSelector('.st-sw'); await clickBtn('Adicionar às amostras');
ok(await p.evaluate(() => S.swatches.includes('#f2b46b')), 'paleta da IA vai para as amostras');
await p.keyboard.press('Escape');

/* configurações › IA */
await p.evaluate(() => openSettings('ia')); await p.waitForSelector('.st-bar', { timeout: 10000 }); await sleep(500);
ok(await p.evaluate(() => !!document.querySelector('.dtab[data-t="ia"][aria-selected="true"]') && document.querySelector('.st-pane').textContent.includes('Uso por pessoa')), 'aba Configurações › IA com uso, cotas e chave');
await p.screenshot({ path: join(OUT, 'ia-config.png') });
await p.keyboard.press('Escape');

/* recusa e sem permissão */
const rec = await p.evaluate(async () => { try { await aiCall('ask', { canvas: pxFlatten(P()), text: 'RECUSAR' }); return 'passou'; } catch (e) { return e.message; } });
ok(/recusou/.test(rec), 'recusa do modelo vira aviso: ' + rec);
const sem = await p.evaluate(() => { const s = ME.u.perms.ia; ME.u.perms.ia = false; const r = aiReady(); ME.u.perms.ia = s; return r; });
ok(sem === false, 'sem a permissão, as funções de IA avisam e não chamam o servidor');

console.log('\nerros de página:', erros.length ? '\n  ' + erros.join('\n  ') : 'nenhum');
if (erros.length) falhas++;
console.log(falhas ? `${falhas} FALHA(S)` : 'TUDO CERTO');
await nav.close(); process.exit(falhas ? 1 : 0);

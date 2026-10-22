/* Rasteriza os SVG do Studio nos tamanhos que navegador e sistemas pedem.
   Usa o Chrome: é o mesmo motor que desenha o ícone na tela inicial.
   Uso: NODE_PATH=<node_modules com puppeteer-core> node tools/gerar_icones.mjs */
import puppeteer from 'puppeteer-core';
import { readFileSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'web', 'icons');
const CHROME = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ALVOS = [
  ['logo.svg', 'icon-192.png', 192], ['logo.svg', 'icon-512.png', 512],
  ['maskable.svg', 'icon-maskable-512.png', 512], ['maskable.svg', 'icon-maskable-192.png', 192],
  /* o iOS não usa transparência nem cantos próprios: recebe o fundo sangrado */
  ['maskable.svg', 'apple-touch-icon.png', 180],
  ['logo.svg', 'fav-16.png', 16], ['logo.svg', 'fav-32.png', 32], ['logo.svg', 'fav-48.png', 48],
];
const nav = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--force-color-profile=srgb'] });
const p = await nav.newPage();
for (const [svg, saida, px] of ALVOS) {
  await p.setViewport({ width: px, height: px, deviceScaleFactor: 1 });
  await p.setContent(`<html><body style="margin:0;background:transparent">${readFileSync(join(DIR, svg), 'utf8').replace('<svg ', `<svg width="${px}" height="${px}" `)}</body></html>`);
  writeFileSync(join(DIR, saida), await p.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: px, height: px } }));
  console.log(saida);
}
await nav.close();

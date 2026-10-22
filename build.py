#!/usr/bin/env python3
"""Gera dist/web a partir do editor original (editor/GPlanSiS-Studio.html) + os módulos de web/plus.

O HTML original não é editado: o build aplica pontos de integração pequenos e
verificados (cada troca precisa casar exatamente o número de vezes esperado, senão
o build para) e injeta conta, formatos e filtros. Uso: python3 build.py
"""
from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "editor" / "GPlanSiS-Studio.html"
WEB = ROOT / "web"
OUT = ROOT / "dist" / "web"
VERSION = "2.0.0-" + time.strftime("%Y%m%d%H%M")

ACCEPT = ("image/*,.heic,.heif,.hif,.avif,.jxl,.tif,.tiff,.psd,.psb,.tga,.qoi,.ppm,.pgm,.pbm,.pnm,.pam,.pfm,"
          ".hdr,.pcx,.svg,.svgz,.ico,.cur,.bmp,.apng,.jfif,.dng,.cr2,.cr3,.crw,.nef,.nrw,.arw,.srf,.sr2,.orf,.raf,"
          ".rw2,.rwl,.pef,.srw,.3fr,.iiq,.erf,.kdc,.dcr,.mrw,.x3f,.raw,.gpr")

# (de, para, vezes esperadas)
PATCHES = [
    ("indexedDB.open('gplansis-studio',1)", "indexedDB.open(window.__STUDIO_DB||'gplansis-studio',1)", 1),
    ("(async()=>{status('Carregando…');pxMenus();", "(async()=>{await window.__studioReady;status('Carregando…');pxMenus();", 1),
    ("pickFiles('image/*',true)", "pickFiles(STUDIO_ACCEPT,true)", 3),
    ("const imgs=fs.filter(f=>f.type.startsWith('image/'))", "const imgs=fs.filter(isStudioImage)", 1),
    ("if(S.mod==='pixel'){for(const f of imgs){const c=await fileToCanvas(f);const d=P();",
     "if(S.mod==='pixel'){for(const f of imgs){if(!P()&&/\\.(psd|psb)$/i.test(f.name)){try{await pxOpenPSDLayers(f)}catch(er){toast('Não foi possível abrir '+f.name,'err')}continue}"
     "let c;try{c=await fileToCanvas(f)}catch(er){toast('Não foi possível abrir '+f.name,'err');continue}const d=P();", 1),
    ("<title>GPlanSiS|Studio</title>", "<title>GPlanSiS|Studio</title>\n<!--HEAD-->", 1),
]

PRE = r"""
window.STUDIO_VERSION=%(ver)r;
window.STUDIO_ACCEPT=%(accept)r;
window.STUDIO_PREF_DEF={theme:'system',startMod:'pixel',maxEdge:6000,exportFormat:'image/png',exportQuality:.92,autosave:true};
/* A sessão é conferida antes do editor montar: o banco local (IndexedDB) é
   separado por usuário, então quem divide o computador não vê o trabalho do outro. */
window.__studioReady=(async()=>{const hang=()=>new Promise(()=>{});const useMe=me=>{window.STUDIO_ME=me;window.STUDIO_PREFS=Object.assign({},STUDIO_PREF_DEF,me.prefs||{});window.__STUDIO_DB='gplansis-studio-u'+me.id;const t=STUDIO_PREFS.theme;try{if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t;localStorage.setItem('gps.studio.theme',t)}}catch(e){}};
 try{const r=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});if(r.status===401){try{localStorage.removeItem('gps.studio.me')}catch(e){}location.replace('/login');return hang()}if(!r.ok)throw new Error('HTTP '+r.status);const me=await r.json();try{localStorage.setItem('gps.studio.me',JSON.stringify(me))}catch(e){}useMe(me)}
 catch(e){let c=null;try{c=JSON.parse(localStorage.getItem('gps.studio.me')||'null')}catch(_){}if(!c){location.replace('/login');return hang()}window.STUDIO_OFFLINE=true;useMe(c)}})();
"""

HEAD = """<meta name="description" content="GPlanSiS|Studio — edição de imagem, ilustração vetorial e revelação de fotos.">
<meta name="theme-color" content="#1f2428">
<meta name="robots" content="noindex">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="icon" href="/icons/logo.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Studio">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>%(pre)s</script>"""


def main() -> int:
    html = SRC.read_text(encoding="utf-8")
    for old, new, n in PATCHES:
        got = html.count(old)
        if got != n:
            print(f"ERRO: ponto de integração casou {got}x (esperado {n}): {old[:70]}", file=sys.stderr)
            return 1
        html = html.replace(old, new)

    html = html.replace("<!--HEAD-->", HEAD % {"pre": PRE % {"ver": VERSION, "accept": ACCEPT}}, 1)

    css = (WEB / "plus" / "plus.css").read_text(encoding="utf-8")
    html = html.replace("</style>\n</head>", "</style>\n<style>\n" + css + "</style>\n</head>", 1)

    js = "\n".join((WEB / "plus" / f).read_text(encoding="utf-8") for f in ("formats.js", "filters.js", "account.js"))
    if "</script" in js:
        print("ERRO: módulo contém </script", file=sys.stderr)
        return 1
    i = html.rindex("</body>")
    html = html[:i] + "<script>\n" + js + "\n</script>\n" + html[i:]

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(WEB, OUT, ignore=shutil.ignore_patterns("formats.js", "filters.js", "account.js", "plus.css", ".DS_Store"))
    (OUT / "index.html").write_text(html, encoding="utf-8")

    # As fontes embutidas no editor também servem à página de login.
    fonts = re.findall(r"@font-face\{[^}]*\}", html[: html.index("</style>")])
    (OUT / "plus" / "fonts.css").write_text("\n".join(fonts), encoding="utf-8")

    sw = OUT / "sw.js"
    sw.write_text(sw.read_text(encoding="utf-8").replace("__VERSAO__", VERSION), encoding="utf-8")
    (OUT / "VERSION").write_text(VERSION + "\n")
    print(f"dist/web gerado · versão {VERSION} · index.html {len(html) / 1024:.0f} KB · {len(fonts)} fontes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

/* GPlanSiS|Studio — service worker.
   A página do editor é rede-primeiro: sessão encerrada ou versão nova sempre
   vencem; o cache só entra quando não há rede. Ícones e bibliotecas em /vendor
   são cache-primeiro (mudam só com a versão). A API nunca é guardada. */
const V = 'studio-__VERSAO__';
const SHELL = ['/', '/login', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png', '/favicon.ico'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => Promise.all(SHELL.map(u => c.add(new Request(u, { credentials: 'same-origin', redirect: 'follow' })).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  if (r.mode === 'navigate') {
    e.respondWith(fetch(r).then(res => {
      /* só guarda o editor quando ele veio de verdade (não o redirecionamento ao login) */
      if (res.ok && !res.redirected) caches.open(V).then(c => c.put(u.pathname === '/login' ? '/login' : '/', res.clone()));
      return res;
    }).catch(() => caches.match(u.pathname === '/login' ? '/login' : '/').then(m => m || caches.match('/login'))));
    return;
  }
  if (/^\/(vendor|icons)\//.test(u.pathname) || u.pathname === '/favicon.ico') {
    e.respondWith(caches.match(r).then(m => m || fetch(r).then(res => { if (res.ok) { const c = res.clone(); caches.open(V).then(x => x.put(r, c)); } return res; })));
  }
});

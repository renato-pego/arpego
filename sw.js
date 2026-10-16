// ARPego - Service Worker Offline-First (v8)
const CACHE_NAME = 'arpego-pwa-v8';
const PRECACHE_ASSETS = [
  '/',
  '/painel',
  '/painel.html',
  '/manifest.json',
  '/icon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS);
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Não intercepta requisições POST para o Service Worker lidar diretamente (elas são tratadas pela fila offline no cliente)
  if (req.method !== 'GET') {
    return;
  }

  // Requisições para APIs GET (ex: /api/tarefas, /api/projetos): Network-First com Fallback de Cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(req)
        .then((networkRes) => {
          if (networkRes.status === 200) {
            const resClone = networkRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
          }
          return networkRes;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // Navegação de páginas HTML: Network-First com recarga forçada da rede
  if (req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/painel' || url.pathname === '/painel.html') {
    event.respondWith(
      fetch(req, { cache: 'reload' })
        .then((networkRes) => {
          if (networkRes.status === 200) {
            const resClone = networkRes.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
          }
          return networkRes;
        })
        .catch(() => caches.match(req).then((cached) => cached || caches.match('/painel.html') || caches.match('/')))
    );
    return;
  }

  // Demais recursos estáticos (ícones, imagens): Cache-First com fallback de rede
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((networkRes) => {
        if (networkRes.status === 200) {
          const resClone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, resClone));
        }
        return networkRes;
      });
    })
  );
});

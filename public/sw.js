// Installable web shell, deliberately no cache: never retain family/API responses
// or present stale permission settings as an offline authenticated experience.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});

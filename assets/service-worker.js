const CACHE_NAME = "logistics-static-v2";
const STATIC_ASSETS = [
  "/driver",
  "/manifest.webmanifest",
  "/icon-192.svg",
  "/icon-512.svg",
  "/theme.css",
  "/scrollbar.css",
  "/driver-app.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.filter((key) => key.startsWith("logistics-static-") && key !== CACHE_NAME)
      .map((key) => caches.delete(key))
  )));
  self.clients.claim();
});

self.addEventListener("message", (event) => {
  if (event.data?.type !== "CLEAR_DRIVER_DATA") return;
  event.waitUntil(caches.keys().then((keys) => Promise.all(
    keys.map(async (key) => {
      const cache = await caches.open(key);
      const requests = await cache.keys();
      await Promise.all(requests
        .filter((request) => new URL(request.url).pathname.startsWith("/api/driver/"))
        .map((request) => cache.delete(request)));
    })
  )));
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
    if (response.ok && ["script", "style", "image", "font"].includes(request.destination)) {
      const copy = response.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
    }
    return response;
  })));
});

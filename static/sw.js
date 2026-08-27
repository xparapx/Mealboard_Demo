// 서비스워커: 정적 파일만 캐시한다. /api/ 는 절대 캐시하지 않는다 (30초 폴링이 무의미해짐)
const CACHE = "mealboard-v1";
const STATIC = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC))));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;          // 네트워크로 그냥 통과
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});

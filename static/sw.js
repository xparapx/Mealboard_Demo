// 서비스워커: 정적 파일만 캐시한다. /api/ 는 절대 캐시하지 않는다 (30초 폴링이 무의미해짐)
//
// 화면(HTML)은 반드시 네트워크 우선. 캐시 우선으로 두면 배포를 해도 예전 화면이 계속 뜬다 —
// v1 이 그랬고, v5 배포가 브라우저에 도달하지 않아 실제로 겪었다. 캐시는 오프라인 대비용일 뿐이다.
// CACHE 이름은 화면이 크게 바뀔 때 올린다. activate 에서 옛 캐시를 지우므로 이름이 곧 무효화 스위치다.
const CACHE = "mealboard-v5";
const SHELL = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));

self.addEventListener("activate", e =>
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())));      // 열려 있는 탭도 바로 새 워커가 맡는다

const isPage = (req, url) =>
  req.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith(".html");

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;           // 네트워크로 그냥 통과

  if (isPage(e.request, url)) {                           // 화면: 네트워크 우선, 실패하면 캐시(오프라인)
    e.respondWith(fetch(e.request)
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});

// 서비스워커: 정적 파일만 캐시한다. /api/ 는 절대 캐시하지 않는다 (30초 폴링이 무의미해짐)
//
// 화면(HTML)과 그 화면이 부르는 모듈(/js/)·스타일(/css/)은 반드시 네트워크 우선. 캐시 우선으로 두면 배포를 해도
// 예전 화면이 계속 뜬다 — v1 이 그랬고, v5 배포가 브라우저에 도달하지 않아 실제로 겪었다.
// 모듈을 캐시 우선으로 두면 새 셸 + 옛 모듈이 짝이 어긋난다. 캐시는 오프라인 대비용일 뿐이다.
// CACHE 이름은 화면이 크게 바뀔 때 올린다. activate 에서 옛 캐시를 지우므로 이름이 곧 무효화 스위치다.
const CACHE = "mealboard-v10";   // 09-03 오후: 한 화면 구조·밀집도 — 옛 셸 캐시를 지운다
const SHELL = ["/", "/index.html", "/manifest.json",
  "/css/base.css", "/css/screens.css", "/css/insight.css",
  "/js/core.js", "/js/floor.js", "/js/wait.js", "/js/room.js", "/js/week.js", "/js/today.js", "/js/news.js"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));

self.addEventListener("activate", e =>
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())));      // 열려 있는 탭도 바로 새 워커가 맡는다

const isPage = (req, url) =>
  req.mode === "navigate" || url.pathname === "/" || url.pathname.endsWith(".html");
const isShellPart = url => url.pathname.startsWith("/js/") || url.pathname.startsWith("/css/");

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return;           // 네트워크로 그냥 통과

  const page = isPage(e.request, url);
  if (page || isShellPart(url)) {                         // 화면·모듈·스타일: 네트워크 우선, 실패하면 캐시(오프라인)
    // cache:"no-cache" 는 브라우저 HTTP 캐시를 건너뛰지 않고 '반드시 검사'하게 한다.
    // 이게 없으면 네트워크 우선이어도 그 fetch 가 디스크 캐시의 옛 파일로 조용히 채워진다
    e.respondWith(fetch(e.request, { cache: "no-cache" })
      .then(res => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); }   // 502·404 로 좋은 사본을 덮지 않는다
        return res;
      })
      // 오프라인 폴백: 화면은 "/" 로 물러서도 되지만 모듈·스타일은 그 자신만 — HTML 을 스크립트로 돌려주지 않게
      .catch(() => caches.match(e.request).then(r => r || (page ? caches.match("/") : undefined))));
    return;
  }
  e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
});

/* 공통 도구 · 공유 상태 · 5화면 라우터 · 폴링 · 부팅. 빌드 도구 없이 브라우저가 ES 모듈을 직접 해석한다 (PLAN §0, §3.3).
   화면 모듈(wait·room·week·today·news)은 `screen` 훅 객체({mount, every, poll, slow, fail, activate, deactivate, render})만 내보내고,
   이 파일이 순서대로 등록해 부팅한다 — 순환 import 이지만 서로를 함수 안에서만 부르므로 안전하다(모듈 평가 시점엔 정의만.
   화면 모듈의 최상위에서 core 의 $ 등을 부르면 TDZ 오류 — 그런 준비는 mount() 에 둔다).

   화면 = 해시(#wait #room #week #today #news). 모바일(<900)은 문서 자체가 가로 스냅 페이저(이웃 화면을 스와이프),
   데스크톱(≥900)은 다섯 화면을 한 보드에 펼치고 좌측 레일이 그 카드로 스크롤한다.
   폴링은 보이는 화면만: 모바일은 활성 화면 하나, 데스크톱은 전부. 탭이 숨겨지면(document.hidden) 쉰다.
   두 박자: poll(라이브, every) 과 slow(집계에서 오는 인사이트, SLOW_EVERY) — 둘 다 core 가 시각으로 가른다 */
import * as wait from "./wait.js";
import * as room from "./room.js";
import * as week from "./week.js";
import * as today from "./today.js";
import * as news from "./news.js";

export const $ = s => document.querySelector(s);
export const $$ = s => [...document.querySelectorAll(s)];
export const j = async u => {
  const r = await fetch(u, { cache: "no-store" });
  if (!r.ok) throw new Error(`${u} → ${r.status}`);                 // 404·500 을 조용히 JSON 으로 읽지 않는다
  return r.json();
};
export const UNREACHABLE = "서버에 닿지 못했습니다";
/* 실패해도 카드가 그릴 수 있는 응답으로 — 인사이트 카드용 */
export const jSoft = u => j(u).catch(e => (console.error(u, e), { state: "no_data", reason: UNREACHABLE }));
export const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const minuteOfDay = d => d.getHours() * 60 + d.getMinutes();
export const hhmm = d => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
export const mm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;   // 자정부터 분 → "HH:MM"
export const hm = ts => ts ? ts.slice(11, 16) : "";                                                           // ISO 문자열 → "HH:MM"
export const WD = "일월화수목금토";
export const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;   // 전환·부드러운 스크롤·점멸을 생략
/* 인사이트 카드의 빈 상태 문구 — API 의 reason 은 개발자용(파일 이름)일 수 있다. 학생에게는 뜻만 남긴다. null 이면 카드의 기본 문구를 둔다 */
export const why = r => !r || /reports\.db/.test(r) ? null : /insights\.db/.test(r) ? "집계가 아직 시작되지 않았습니다" : r;
const DESK_MQ = matchMedia("(min-width: 900px)");
export const desktop = () => DESK_MQ.matches;
export const SLOW_EVERY = 30 * 60000;                  // 집계(14:10 하루 1회)에서 오는 카드는 30분마다면 충분하다

if (!CanvasRenderingContext2D.prototype.roundRect) {   // Safari 16 이전 대비. 모서리만 대신 그린다
  CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
    r = Math.min(+r || 0, w / 2, h / 2);
    this.moveTo(x + r, y); this.arcTo(x + w, y, x + w, y + h, r); this.arcTo(x + w, y + h, x, y + h, r);
    this.arcTo(x, y + h, x, y, r); this.arcTo(x, y, x + w, y, r); this.closePath();
  };
}

/* 캔버스는 배경 저장소를 DPR 에 맞춰 잡아야 선이 뭉개지지 않는다. 크기가 그대로면 저장소를 다시 잡지 않고(메모리 재할당 없이) 지우기만 한다 */
export function fit(c, h) {
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 318;
  const pw = Math.round(w * dpr), ph = Math.round(h * dpr);
  if (c.width !== pw || c.height !== ph) { c.width = pw; c.height = ph; }
  const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return { g, w, h };
}

/* 캔버스 상자 크기가 바뀌면 다시 그린다(다시 받지는 않는다). 숨은 화면(폭 0)은 건너뛴다 — 보이는 순간 상자가 생기며 다시 불린다 */
export function canvasAuto(c, draw) {
  let w = 0, h = 0;
  new ResizeObserver(() => {
    if (c.clientWidth > 0 && (c.clientWidth !== w || c.clientHeight !== h)) {
      w = c.clientWidth; h = c.clientHeight;
      try { draw(); } catch (e) { console.error("canvasAuto", e); }
    }
  }).observe(c.parentElement || c);
}

/* 인사이트 카드의 상태. 빈 상태 문구는 reason 이 있으면 학생용으로 옮겨 쓰고, 없으면 카드의 기본 문구로 되돌린다(옛 오류 문구가 남지 않게) */
export function setState(id, ok, reason) {
  const card = $("#" + id); card.dataset.state = ok ? "ok" : "no_data";
  const e = card.querySelector(".empty");
  if (e) { e.dataset.default ??= e.textContent; e.textContent = why(reason) ?? e.dataset.default; }
  return !!ok;
}

/* 화면 모듈이 공유하는 최근 응답 — 다시 그릴 때 다시 받지 않기 위해 */
export const S = { last: null, lastPos: null, meal: null, typ: null };

/* ---------------- 화면 등록 · 라우터 ---------------- */
const ORDER = ["wait", "room", "week", "today", "news"];
const NAMES = { wait: "대기시간", room: "실시간", week: "주간식단", today: "오늘급식", news: "이슈피드" };
const SCREENS = { wait: wait.screen, room: room.screen, week: week.screen, today: today.screen, news: news.screen };
const lastPoll = {}, lastSlow = {};                    // name → 마지막 폴링 시각 (라이브 / 느린 인사이트)
const scrollYs = {};                                   // 모바일: 화면별 세로 스크롤 위치
let active = null;
let spyLock = 0;                                       // 레일·키보드로 스크롤하는 동안 스파이가 끼어들지 않게

const view = name => document.getElementById(name);
const pageW = () => view("wait").offsetWidth || innerWidth;   // 페이저 한 칸 = 화면 폭(뷰 요소가 정한다 — innerWidth 는 환경마다 다르다)
const firstCard = name => view(name).querySelector(":scope > :not([hidden])") || view(name).firstElementChild;   // 숨은 카드(주간식단·이슈)는 건너뛴다

async function poll(name, force) {
  const s = SCREENS[name];
  if (!s) return;
  const now = Date.now();
  if (s.slow && (force || !lastSlow[name] || now - lastSlow[name] >= SLOW_EVERY)) {
    lastSlow[name] = now;
    Promise.resolve().then(s.slow).catch(e => console.error(name, "slow", e));
  }
  if (!s.poll) return;
  if (!force && lastPoll[name] && now - lastPoll[name] < (s.every || 30000)) return;
  lastPoll[name] = now;
  try { await s.poll(); }
  catch (e) { console.error(name, e); s.fail?.(e); }   // 서버에 닿지 못하면 옛 값을 '지금'처럼 두지 않는다 — 화면이 정한다
}

function tick() {                                      // 30초마다. 각 화면의 every 에 못 미치면 건너뛴다
  if (document.hidden) return;
  (desktop() ? ORDER : [active]).forEach(n => n && poll(n, false));
}

/* dock·레일의 현재 표시 + 문서 제목 + 해시 */
function mark(name, push) {
  $$("[data-go]").forEach(a => a.setAttribute("aria-current", a.dataset.go === name ? "page" : "false"));
  const cur = $(`.dock a[data-go="${name}"]`), m = $(".dock .mark");
  if (cur && m) { m.style.left = cur.offsetLeft + 6 + "px"; m.style.width = cur.offsetWidth - 12 + "px"; }
  document.title = `${NAMES[name]} · 급식실 대기 안내`;
  if (location.hash !== "#" + name) history[push ? "pushState" : "replaceState"](null, "", "#" + name);
}

/* 도착 화면의 카드에 짧은 등장 효과 — translateY 는 transform 이라 모션 축소 설정이면 자동으로 무효. 리플로우는 한 번만 */
function enter(sec) {
  if (REDUCE) return;
  const cards = [...sec.querySelectorAll(":scope > .card, :scope > .waitcard")];
  cards.forEach(c => c.classList.remove("enter"));
  void sec.offsetWidth;
  cards.forEach(c => { c.classList.add("enter"); c.addEventListener("animationend", () => c.classList.remove("enter"), { once: true }); });
}

/* 데스크톱: 그 화면의 첫 카드로 부드럽게 스크롤 + 잠깐 링. 스파이는 도착할 때까지 잠근다 */
function scrollToCard(name) {
  spyLock = Date.now() + 900;
  const card = firstCard(name);
  card.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" });
  card.classList.add("ring"); setTimeout(() => card.classList.remove("ring"), 900);
}

/* 화면으로 간다. push=false 는 뒤로가기·스와이프·스파이처럼 이미 일어난 이동을 따라가는 경우 */
export function go(name, { push = true, swipe = false } = {}) {
  if (!ORDER.includes(name)) name = "wait";
  const prev = active;
  if (desktop()) {                                     // 보드: 모든 화면이 보이므로 activate/poll 은 부팅 때 한 번. 여기선 표시와 스크롤만
    if (prev !== name) {
      active = name;
      const change = () => mark(name, push);
      if (!REDUCE && document.startViewTransition) document.startViewTransition(change); else change();
    }
    if (push) scrollToCard(name);
    return;
  }
  if (prev === name) return;
  if (prev) { scrollYs[prev] = scrollY; SCREENS[prev].deactivate?.(); view(prev).removeAttribute("data-active"); }
  active = name;
  view(name).setAttribute("data-active", "");
  mark(name, push);
  const top = scrollYs[name] || 0;
  if (swipe) scrollTo({ top, behavior: "auto" });                                   // 가로는 이미 왔다 — 세로만 그 화면의 자리로
  else scrollTo({ left: view(name).offsetLeft, top, behavior: REDUCE ? "auto" : "smooth" });
  enter(view(name));
  const first = !(name in lastPoll);
  SCREENS[name].activate?.({ first });
  poll(name, first);
}

/* 모바일: 스와이프가 끝나면 어느 화면에 멈췄는지 해시를 맞춘다 (scrollend, 없으면 120ms 디바운스) */
function landed() {
  if (desktop()) return;
  const n = ORDER[Math.round(scrollX / pageW())];
  if (n && n !== active) go(n, { push: false, swipe: true });
}
if ("onscrollend" in window) addEventListener("scrollend", landed);
else { let t; addEventListener("scroll", () => { clearTimeout(t); t = setTimeout(landed, 120); }, { passive: true }); }

/* 데스크톱: 스크롤 스파이 — 화면의 카드(숨은 것 제외) 중 가운데 띠와 가장 많이 겹치는 화면이 현재 */
function spy() {
  const ratio = {};                                    // 카드 → 겹침 비율. 세 행을 차지하는 실시간 카드가 늘 이기지 않게 비율로 견준다
  const io = new IntersectionObserver(es => {
    es.forEach(e => { ratio[e.target.id] = e.isIntersecting && !e.target.hidden ? e.intersectionRatio : 0; });
    if (Date.now() < spyLock) return;
    const byView = n => Math.max(0, ...[...view(n).children].map(c => ratio[c.id] || 0));
    const best = ORDER.filter(n => byView(n) > 0).sort((a, b) => byView(b) - byView(a) || ORDER.indexOf(a) - ORDER.indexOf(b))[0];
    if (best && best !== active) { active = best; mark(best, false); }
  }, { rootMargin: "-10% 0px -60% 0px", threshold: [0, .1, .25, .5, .75, 1] });
  ORDER.forEach(n => [...view(n).children].forEach(c => c.id && io.observe(c)));
}

/* ---------------- 부팅 ---------------- */
$$("[data-go]").forEach(a => a.addEventListener("click", e => { e.preventDefault(); go(a.dataset.go); }));
addEventListener("hashchange", () => go(location.hash.slice(1), { push: false }));
addEventListener("keydown", e => {                     // 데스크톱: 1~5 로 이동 (입력란 안에서는 무시)
  if (!desktop() || e.altKey || e.ctrlKey || e.metaKey || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const i = "12345".indexOf(e.key); if (i >= 0) go(ORDER[i]);
});
DESK_MQ.addEventListener("change", () => location.reload());   // 페이저 ↔ 보드는 구조가 다르다. 경계를 넘는 일은 드물다 — 새로 그린다
addEventListener("resize", () => { if (active && !desktop()) scrollTo({ left: view(active).offsetLeft, behavior: "auto" }); mark(active || "wait", false); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });

const start = ORDER.includes(location.hash.slice(1)) ? location.hash.slice(1) : "wait";
ORDER.forEach(n => SCREENS[n].mount?.());              // 캔버스 관찰 등 한 번만 하는 준비
if (desktop()) {
  active = start; view(start).setAttribute("data-active", ""); mark(start, false);
  ORDER.forEach(n => { SCREENS[n].activate?.({ first: true }); poll(n, true); });
  spy();
  if (start !== "wait") requestAnimationFrame(() => firstCard(start).scrollIntoView({ block: "start" }));
} else {
  go(start, { push: false });
  if (start !== "wait") requestAnimationFrame(() => scrollTo({ left: view(start).offsetLeft, behavior: "auto" }));
}
setInterval(tick, 30000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
/* 관리 origin 에서만 관리 뷰를 붙인다 — 호스트명이 아니라 서버가 답하는지로 판단. 공개 origin 에서는 세션당 404 한 번 (PLAN §3.1, Phase 3) */
try {
  if (sessionStorage.getItem("mb_admin_probe") !== "no")
    fetch("/api/admin/whoami", { cache: "no-store" }).then(r => {
      if (r.ok) import("/admin-ui/admin.js").then(m => m.default?.(window.MB)).catch(() => {});
      else sessionStorage.setItem("mb_admin_probe", "no");
    }).catch(() => {});
} catch {}
window.MB = { S, go, poll, ORDER, NAMES, screens: SCREENS, active: () => active };   // 콘솔·테스트에서 들여다보기 위한 손잡이

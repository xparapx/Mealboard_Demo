/* 공통 도구 · 공유 상태 · 5화면 라우터 · 폴링 · 부팅. 빌드 도구 없이 브라우저가 ES 모듈을 직접 해석한다 (PLAN §0, §3.3).
   화면 모듈(wait·room·week·today·news)은 `screen` 훅 객체({mount, every, poll, slow, fail, activate, deactivate, render})만 내보내고,
   이 파일이 순서대로 등록해 부팅한다 — 순환 import 이지만 서로를 함수 안에서만 부르므로 안전하다(모듈 평가 시점엔 정의만.
   화면 모듈의 최상위에서 core 의 $ 등을 부르면 TDZ 오류 — 그런 준비는 mount() 에 둔다).

   화면 = 해시(#wait #room #week #today #news). 한 번에 한 화면만 보인다(09-03 사용자 결정 — 스와이프 페이저·스크롤 스파이 폐기):
   모바일(<900)은 하단 dock, 데스크톱(≥900)은 좌측 레일이 곧 전환이고, 세로 스크롤은 그 화면 안만 오간다.
   데스크톱은 그 화면의 카드를 12컬럼 그리드(1920×1080 기준)에 펼친다. 폴링은 활성 화면 하나만. 탭이 숨겨지면(document.hidden) 쉰다.
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
/* 끼니 토글(09-16 중식/석식 분리) — 인사이트 카드 오른쪽 위 세그먼트. 데이터는 카드 쪽이 캐시하고 여기서는 선택만 다룬다 */
export const MEAL_KO = { lunch: "중식", dinner: "석식" };
export const defaultMeal = () => { const h = new Date().getHours(); return h >= 14 && h < 21 ? "dinner" : "lunch"; };   // 14시 이후엔 다음 끼니
export function mealSeg(el, initial, onPick) {
  el.innerHTML = ["lunch", "dinner"].map(m =>
    `<button type="button" data-meal="${m}" aria-pressed="${m === initial}">${MEAL_KO[m]}</button>`).join("");
  el.addEventListener("click", e => {
    const b = e.target.closest("button[data-meal]"); if (!b || b.getAttribute("aria-pressed") === "true") return;
    el.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
    onPick(b.dataset.meal);
  });
}
export const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;   // 전환·부드러운 스크롤·점멸을 생략
/* 인사이트 카드의 빈 상태 문구 — API 의 reason 은 개발자용(파일 이름)일 수 있다. 학생에게는 뜻만 남긴다. null 이면 카드의 기본 문구를 둔다 */
export const why = r => !r || /reports\.db/.test(r) ? null : /insights\.db/.test(r) ? "일정 기간 데이터 수집 후 반영됩니다" : r;
const DESK_MQ = matchMedia("(min-width: 900px)");
export const desktop = () => DESK_MQ.matches;
export const SLOW_EVERY = 30 * 60000;                  // 집계(14:10 하루 1회)에서 오는 카드는 30분마다면 충분하다
export const UI_VERSION = "v31";                       // 관리 UI 모듈 캐시 무효화 꼬리표 — sw.js CACHE 번호와 같이 올린다(09-11)

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

/* 안내 띠(09-04, 09-11 개정) — /api/status 의 feed 로 그린다. live(카메라 노드 + 수집 창 안 + 표본 이어짐)면 숨긴다.
   카메라(vision): 창 밖은 "지금은 급식 시간이 아닙니다" + 다음 창(창 밖에는 아무 표본도 없다), 창 안인데 표본이 끊기면 "카메라 표본이 끊겼습니다".
   스테이징 mock: 값이 더미라는 것을 창 안팎 모두 적는다. 어느 화면에 있든 같은 띠 — 대기시간 화면은 30초 status 로, 나머지는 60초 feedTick 으로 */
export function renderFeed(f) {
  const bar = $("#feedbar");
  if (!bar || !f) return;
  if (f.live) { bar.hidden = true; return; }
  // 다음 급식(09-11): 서버가 급식 있는 날(주말·공휴일 제외, NEIS 캐시 기준)을 준다. 날짜를 못 정하면 '급식 시간이 아닙니다' 만 남긴다
  const n = f.next, when = !n ? "" : n.days === 0 ? "" : n.days === 1 ? " (내일)" : n.weekday ? ` (${esc(n.weekday)}요일)` : ` (${n.days}일 뒤)`;
  const next = n && n.date ? ` · 다음 급식 <b>${esc(n.label)} ${mm(n.lo)}</b>${when}` : "";
  const win = f.now ? `<b>${esc(f.now.label)}</b> ${mm(f.now.lo)}~${mm(f.now.hi)}` : "";
  bar.innerHTML = f.source === "vision"
    ? (f.now ? `${win} · 카메라 표본이 끊겼습니다 · 잠시 후 다시 확인해 주세요`
             : `지금은 <b>급식 시간이 아닙니다</b>${next}`)
    : (f.now ? `${win} · 급식실 설치 전 시험 운영 중이라 지금 보이는 값은 <b>더미데이터</b>입니다`
             : `지금은 급식시간이 아닙니다 · 실시간 데이터가 아닌 <b>더미데이터</b>입니다${next}`);
  bar.hidden = false;
}
/* 급식 시간 자동 전환(09-11 사용자 요청): 해시 없이 열면 창 밖에는 이슈피드에서 시작하고, 창이 열리는 순간 대기시간으로 한 번 넘어간다.
   사용자가 탭을 직접 누른 뒤(userNav)에는 개입하지 않는다. 아이콘 순서는 그대로 */
let userNav = false, wasInWindow = null;
const mealLive = f => !!(f && f.now && f.meal_day !== false);   // 창 안 ∧ 오늘이 급식 있는 날(meal_day 없는 옛 응답은 참으로)
function autoSwitch(f) {
  const inWin = mealLive(f);
  if (wasInWindow === null) { wasInWindow = inWin; return; }
  if (inWin && !wasInWindow && !userNav && active === "news") go("wait", { push: false, anim: true });
  wasInWindow = inWin;
}
async function feedTick() { if (document.hidden) return; try { const f = (await j("/api/status")).feed; renderFeed(f); autoSwitch(f); } catch (e) { console.error("feed", e); } }

/* ---------------- 화면 등록 · 라우터 ---------------- */
const ORDER = ["wait", "room", "week", "today", "news"];
const NAMES = { wait: "대기시간", room: "실시간뷰", week: "주간식단", today: "오늘급식", news: "이슈피드" };
const SCREENS = { wait: wait.screen, room: room.screen, week: week.screen, today: today.screen, news: news.screen };
const lastPoll = {}, lastSlow = {};                    // name → 마지막 폴링 시각 (라이브 / 느린 인사이트)
const scrollYs = {};                                   // 화면별 세로 스크롤 위치 — 돌아오면 그 자리
let active = null;

const view = name => document.getElementById(name);

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

function tick() {                                      // 30초마다 활성 화면만. 화면의 every 에 못 미치면 건너뛴다
  if (document.hidden || !active) return;
  poll(active, false);
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

/* 화면으로 간다 — 즉시. 이전 화면은 숨기고(deactivate) 새 화면만 보인다. push=false 는 뒤로가기·해시처럼 이미 일어난 이동 */
export function go(name, { push = true, anim = false } = {}) {
  if (!ORDER.includes(name)) name = "wait";
  const prev = active;
  if (prev === name) { scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" }); mark(name, push); return; }   // 같은 탭 다시 누르면 맨 위로
  if (prev) { scrollYs[prev] = scrollY; SCREENS[prev].deactivate?.(); view(prev).removeAttribute("data-active"); }
  active = name;
  view(name).setAttribute("data-active", "");
  // 자동 전환(급식 창이 열릴 때)만의 화면 전체 페이드 — 카드 enter 보다 큰 호흡. 모션 축소면 생략
  if (anim && !REDUCE) { const v = view(name); v.classList.remove("xfade"); void v.offsetWidth;
    v.classList.add("xfade"); v.addEventListener("animationend", () => v.classList.remove("xfade"), { once: true }); }
  mark(name, push);
  scrollTo({ top: scrollYs[name] || 0, behavior: "auto" });
  enter(view(name));
  const first = !(name in lastPoll);
  SCREENS[name].activate?.({ first });
  poll(name, first);
}
export function observe() {}                           // 호환용 — 스크롤 스파이가 없어졌다(관리 모듈이 등록 뒤 부른다)

/* ---------------- 부팅 ---------------- */
$$("[data-go]").forEach(a => a.addEventListener("click", e => { e.preventDefault(); userNav = true; go(a.dataset.go); }));
addEventListener("hashchange", () => go(location.hash.slice(1), { push: false }));
addEventListener("keydown", e => {                     // 데스크톱: 1~9 로 이동 — ORDER 길이만큼(관리 화면이 붙으면 6) (입력란 안에서는 무시)
  if (!desktop() || e.altKey || e.ctrlKey || e.metaKey || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
  const i = /^[1-9]$/.test(e.key) ? Number(e.key) - 1 : -1; if (i >= 0 && i < ORDER.length) go(ORDER[i]);
});
addEventListener("resize", () => mark(active || "wait", false));   // dock 인디케이터 자리
document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(); });

const wanted = location.hash.slice(1);                 // 부팅 때 없는 화면(관리)을 가리켰다면 그 화면이 등록될 때 되돌아간다(MB.wanted)
ORDER.forEach(n => SCREENS[n].mount?.());              // 캔버스 관찰 등 한 번만 하는 준비
// 시작 화면(09-11): 해시가 있으면 그대로, 없으면 status 를 먼저 보고 급식 창 밖이면 이슈피드·안이면 대기시간. status 가 늦어도 대기시간으로 시작한다
async function boot() {
  let start = ORDER.includes(wanted) ? wanted : null;
  let f = null;
  if (!start) {
    try { f = (await Promise.race([j("/api/status"), new Promise((_, rej) => setTimeout(rej, 1500))])).feed; } catch {}
    start = f && !mealLive(f) ? "news" : "wait";       // 창 밖 또는 급식 없는 날(주말·방학) → 이슈피드에서 시작
  }
  go(start, { push: false });
  if (f) { renderFeed(f); wasInWindow = mealLive(f); }
  setInterval(tick, 30000);
  feedTick(); setInterval(feedTick, 60000);            // 안내 띠·자동 전환은 화면과 무관하게 60초(status 응답은 200B 남짓)
}
boot();
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  // 새 워커가 이 탭을 넘겨받으면(배포) 한 번 다시 읽는다 — 옛 워커가 캐시해 둔 셸·모듈이 새 API 응답을 옛 방식으로 그리던 문제(09-11).
  // 처음 설치될 때는 controller 가 없으므로 그때는 재로드하지 않는다. 폼 입력 같은 상태가 없는 화면이라 안전하다
  const hadController = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener("controllerchange", () => { if (hadController && !window.__mbReloaded) { window.__mbReloaded = true; location.reload(); } });
}
/* 관리 origin 에서만 관리 뷰를 붙인다 — 호스트명이 아니라 서버가 답하는지로 판단. 공개 origin 에서는 세션당 404 한 번 (PLAN §3.1, Phase 3) */
window.MB = { S, go, poll, observe, ORDER, NAMES, screens: SCREENS, active: () => active, wanted };   // 콘솔·테스트·관리 모듈의 손잡이
try {
  // SSH 터널은 `/?key=…` 로 들어온다(서버가 그 응답에 쿠키를 준다) — 그때는 세션의 '없음' 기억을 무시하고 다시 묻는다
  if (sessionStorage.getItem("mb_admin_probe") !== "no" || location.search.includes("key="))
    fetch("/api/admin/whoami", { cache: "no-store" }).then(r => {
      // ?v= 꼬리표(09-11): 배포마다 새 모듈 그래프 — 브라우저 모듈 맵은 탭 수명 동안 재검증하지 않아 편집기가 옛 코드로 남았다. 값은 sw.js CACHE 와 함께 올린다
      if (r.ok) { sessionStorage.removeItem("mb_admin_probe"); import(`/admin-ui/admin.js?v=${UI_VERSION}`).then(m => m.default?.(window.MB)).catch(() => {}); }
      else sessionStorage.setItem("mb_admin_probe", "no");
    }).catch(() => {});
} catch {}

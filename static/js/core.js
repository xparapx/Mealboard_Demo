/* 공통 도구 · 공유 상태 · 부팅. 빌드 도구 없이 브라우저가 ES 모듈을 직접 해석한다 (PLAN §0).
   화면 모듈(wait·room·week·today·news)이 여기서 도구를 가져오고, 이 파일이 그 모듈들을 불러 부팅한다 —
   순환 import 이지만 서로를 함수 안에서만 부르므로 안전하다(모듈 평가 시점에는 정의만 한다). */
import { refresh, drawChart } from "./wait.js";
import { renderPlan } from "./room.js";
import { loadMeal } from "./today.js";
import { loadNews } from "./news.js";

export const $ = s => document.querySelector(s);
export const j = async u => (await fetch(u, { cache: "no-store" })).json();
export const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const minuteOfDay = d => d.getHours() * 60 + d.getMinutes();
export const hhmm = d => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");

if (!CanvasRenderingContext2D.prototype.roundRect) {   // Safari 16 이전 대비. 모서리만 대신 그린다
  CanvasRenderingContext2D.prototype.roundRect = function (x, y, w, h, r) {
    r = Math.min(+r || 0, w / 2, h / 2);
    this.moveTo(x + r, y); this.arcTo(x + w, y, x + w, y + h, r); this.arcTo(x + w, y + h, x, y + h, r);
    this.arcTo(x, y + h, x, y, r); this.arcTo(x, y, x + w, y, r); this.closePath();
  };
}

/* 캔버스는 배경 저장소를 DPR 에 맞춰 잡아야 선이 뭉개지지 않는다 */
export function fit(c, h) {
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth || 318;
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  return { g, w, h };
}

/* 화면 모듈이 공유하는 최근 응답 — 다시 그릴 때 다시 받지 않기 위해 */
export const S = { last: null, lastPos: null, meal: null };

/* 데스크톱에서 두 패널의 아래 끝을 맞춘다. 어느 쪽이 긴지는 그날 데이터에 달렸으므로
   양쪽 모두 마지막으로 '보이는' 카드에 .grow 를 걸어 둔다 — 긴 쪽은 흡수할 여백이 없어 그대로다 */
export function balance() {
  document.querySelectorAll("main > .col").forEach(col => {
    const kids = [...col.children];
    kids.forEach(el => el.classList.remove("grow"));
    const vis = kids.filter(el => !el.hidden && el.classList.contains("card"));
    if (vis.length) vis[vis.length - 1].classList.add("grow");
  });
  if (S.lastPos) renderPlan(S.lastPos);    // 카드의 상자가 바뀌었으니 그 크기로 다시 그린다
}

async function tick() {                              // 서버에 닿지 못하면 옛 위치를 '지금'처럼 두지 않는다
  try { await refresh(); }
  catch (e) { console.error("refresh", e); S.lastPos = { state: "no_data" }; renderPlan(S.lastPos); }
}
tick(); loadMeal(); loadNews();
setInterval(tick, 30000);
let rt;                                              // 캔버스는 폭이 바뀌면 다시 그려야 한다 — 다시 받지는 않는다
addEventListener("resize", () => {
  clearTimeout(rt);
  rt = setTimeout(() => {
    balance();
    if (S.last) drawChart(S.last.rows, S.last.typ, S.last.st);
    if (S.lastPos) renderPlan(S.lastPos);
  }, 150);
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
window.MB = { S, balance };                          // 콘솔·테스트에서 들여다보기 위한 손잡이

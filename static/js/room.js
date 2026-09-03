/* 실시간 화면 — 탑뷰 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2)
   두 겹 캔버스: #plan 에 정적 평면도(floor.js), 그 위 #marks 에 마커만 — 점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1)이며
   이 화면이 활성일 때만 돈다(.plan.live). 평면도는 데이터·상자 크기가 바뀔 때만 그린다(canvasAuto).
   /api/positions 는 이 화면이 보일 때만 30초마다 — 다른 화면에서는 요청이 나가지 않는다 */
import { $, j, S, fit, canvasAuto } from "./core.js";
import { drawFloor, drawMarkers, geom } from "./floor.js";

export function renderPlan(p) {
  try { drawPlan(p); } catch (e) { console.error("drawPlan", e); }
}

export function drawPlan(p) {
  const ok = p.state === "ok";
  $("#plancard").dataset.state = ok ? "ok" : "no_data";
  $("#posn").textContent = ok ? `${p.n}명` : "—";
  const c = $("#plan"), W = c.clientWidth || 318;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  const G = geom(W, H);
  drawFloor(g, G);
  const { g: m } = fit($("#marks"), H);
  if (ok) drawMarkers(m, G, p.points);
}

export const screen = {
  mount() { canvasAuto($("#plan"), () => renderPlan(S.lastPos || { state: "no_data" })); },   // 부팅 때 core 가 부른다(순환 import 의 TDZ 회피)
  every: 30000,
  async poll() { S.lastPos = await j("/api/positions"); renderPlan(S.lastPos); },
  fail() { S.lastPos = { state: "no_data" }; renderPlan(S.lastPos); },    // 서버에 닿지 못하면 옛 위치를 '지금'처럼 두지 않는다
  activate() { $("#plancard").classList.add("live"); },                   // 점멸은 보일 때만
  deactivate() { $("#plancard").classList.remove("live"); },
};

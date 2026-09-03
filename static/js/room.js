/* 급식실 화면 — 탑뷰 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2)
   두 겹 캔버스: #plan 에 정적 평면도(floor.js), 그 위 #marks 에 마커만 — 점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1).
   평면도는 데이터·크기가 바뀔 때만 그리고, 모션 축소 설정은 @media 규칙이 자동으로 애니메이션을 끈다 */
import { $, fit } from "./core.js";
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

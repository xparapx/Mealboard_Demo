/* 실시간뷰 화면 — 탑뷰 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2)
   두 겹 캔버스: #plan 에 정적 평면도(floor.js)는 상자 크기가 바뀔 때만(canvasAuto), 그 위 #marks 에 마커만 30초마다.
   점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1)이며 이 화면이 활성일 때만 돈다(.plan.live).
   /api/positions 는 이 화면이 보일 때만 30초마다 — 다른 화면에서는 요청이 나가지 않는다.
   아래 카드: 최근 30분 밀집도(육각 타일별 인원수 합계 — 같은 평면도 위에 flare 히트맵, 30초마다) · 오늘 리포트(로컬 LLM 글, 30분마다) */
import { $, j, jSoft, S, esc, fit, hm, canvasAuto, setState } from "./core.js";
import { JET, gradient } from "./colors.js";
import { drawFloor, drawHeat, drawMarkers, drawZoneLabels, geom } from "./floor.js";

let G = null;
let ZONES = null;                                      // zones.json 의 구역(정규화 다각형·이름) — 라벨만 그린다. /api/insight/zones 에서 한 번                                          // #plan 의 투영 — 평면도를 그린 크기. 상자가 바뀌면 canvasAuto 가 다시 만든다

function drawFloorLayer() {
  const c = $("#plan"), W = c.clientWidth || 318;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  G = geom(W, H);
  drawFloor(g, G);
  drawZoneLabels(g, G, ZONES);
}

async function loadZones() {                           // 구역 정의는 설정이라 하루에 몇 번 바뀌지 않는다 — 부팅 때 + 30분 slow 에서
  const z = await jSoft("/api/insight/zones?weeks=1");
  if (z && z.zones && z.zones.length) { ZONES = z.zones; drawFloorLayer(); renderPlan(S.lastPos || { state: "no_data" }); drawZoneCard(); }
}

export function renderPlan(p) {
  try { drawPlan(p); } catch (e) { console.error("drawPlan", e); }
}

export function drawPlan(p) {
  const ok = p.state === "ok";
  $("#plancard").dataset.state = ok ? "ok" : "no_data";
  $("#posn").textContent = ok ? `${p.n}명` : "—";
  if (!G) drawFloorLayer();
  const { g: m } = fit($("#marks"), G.H);              // 마커 층만 지우고 다시 그린다 — 평면도는 그대로
  if (ok) drawMarkers(m, G, p.points);
}

/* ---------------- 인사이트 카드 ---------------- */
let DENS = null;                                       // 마지막 밀집도 응답 — 상자 크기가 바뀌면 다시 그린다

function drawZoneCard() {
  const d = DENS; if (!d) return;
  const c = $("#zoneplan"), W = c.clientWidth || 318;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  const Gz = geom(W, H);
  drawFloor(g, Gz);
  drawZoneLabels(g, Gz, ZONES);
  drawHeat(g, Gz, d.cells, d.grid.cols, d.grid.rows);   // 타일이 진할수록(jet) 최근 30분에 사람이 많았던 자리 — 마커 없음
}

/* 최근 30분 밀집도(09-03 사용자 결정: 최근 4주 구역 평균 대신 당일 최근 30분, 히트맵). 30초마다 poll 로 */
function renderZones(d) {
  const ok = d.state === "ok" && d.cells && d.cells.length;
  if (!setState("zonecard", ok, d.reason)) { DENS = null; $("#zonebar").hidden = true; return; }
  DENS = d;
  drawZoneCard();
  const top = d.zones[0];
  $("#zonelead").innerHTML = top ? `최근 ${d.minutes}분, <b>${esc(top.label)}</b>에 사람이 가장 많았습니다 (${top.share_pct}%)` : `최근 ${d.minutes}분 밀집도`;
  $("#zonechips").innerHTML = d.zones.map((z, i) =>
    `<span class="${i ? "ghost" : ""}">${esc(z.label)}<small>${z.share_pct}% · 평균 ${z.avg_n}명</small></span>`).join("");
  $("#zonefoot").textContent = `${hm(d.since)} 이후 표본 ${d.ticks}개 · 육각 타일 ${d.grid.cols}×${d.grid.rows} 타일별 인원수 합계 · 개별 위치는 저장하지 않습니다`;
  $("#zonebar").hidden = false;
}

function renderReport(d) {
  const item = (d.items || []).find(x => x.kind === "recap") || (d.items || [])[0];
  if (!setState("reportcard", d.state === "ok" && !!item, d.reason)) return;
  $("#reporthead").textContent = item.headline || "";
  $("#reportbody").textContent = item.body || "";
  $("#reportchips").innerHTML = `<em class="teal">${item.engine === "hailo" ? "AI 작성" : "규칙 문장"}${item.model ? " · " + esc(item.model) : ""}</em>`
    + `<small>${item.kind === "preview" ? "아침 예보" : "점심 결산"} · ${(item.created_at || "").slice(5, 16).replace("T", " ")}</small>`;
}

const RENDER = { zonecard: renderZones, reportcard: renderReport };

export const screen = {
  mount() {                                            // 부팅 때 core 가 부른다(순환 import 의 TDZ 회피)
    canvasAuto($("#plan"), () => { drawFloorLayer(); renderPlan(S.lastPos || { state: "no_data" }); });
    canvasAuto($("#zoneplan"), drawZoneCard);
    $("#zonebar").querySelector("i").style.background = gradient(JET);
    loadZones();
  },
  every: 30000,
  async poll() {                                       // 위치 마커 + 최근 30분 밀집도(둘 다 라이브)
    const [p, z] = await Promise.all([j("/api/positions"), jSoft("/api/insight/density?minutes=30")]);
    S.lastPos = p; renderPlan(p); renderZones(z);
  },
  async slow() { renderReport(await jSoft("/api/insight/text")); loadZones(); },   // 리포트·구역 정의 — core 가 30분마다
  fail() { S.lastPos = { state: "no_data" }; renderPlan(S.lastPos); },    // 서버에 닿지 못하면 옛 위치를 '지금'처럼 두지 않는다
  activate() { $("#plancard").classList.add("live"); },                   // 점멸은 보일 때만
  deactivate() { $("#plancard").classList.remove("live"); },
  render(cardId, data) { RENDER[cardId]?.(data); },
};

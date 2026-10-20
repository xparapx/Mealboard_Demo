/* 실시간뷰 화면 — 탑뷰 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2)
   두 겹 캔버스: #plan 에 정적 평면도(floor.js)는 상자 크기가 바뀔 때만(canvasAuto), 그 위 #marks 에 마커만 5초마다(09-16).
   점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1)이며 이 화면이 활성일 때만 돈다(.plan.live).
   /api/positions 는 이 화면이 보일 때만 5초마다 — 다른 화면에서는 요청이 나가지 않는다.
   아래 카드: 최근 10분 밀집도(육각 타일별 인원수 합계 — 같은 평면도 위에 flare 히트맵, 5초마다) · 오늘 리포트(로컬 LLM 글, 30분마다) */
import { $, j, jSoft, S, esc, fit, hm, canvasAuto, setState, MEAL_KO, defaultMeal, mealSeg } from "./core.js";
import { SUNSETDARK, gradient } from "./colors.js";
import { drawClusters, drawFloor, drawHeat, drawMarkers, drawZoneLabels, geom } from "./floor.js";

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
  if (z && z.zones && z.zones.length) { ZONES = z.zones; drawFloorLayer(); renderPlan(S.lastPos || { state: "no_data" }); drawZoneCard(); drawTypCard(); }
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
  drawHeat(g, Gz, d.cells, d.grid.cols, d.grid.rows);   // 타일이 어두울수록(Sunsetdark) 최근 10분에 사람이 많았던 자리 — 마커 없음
}

/* 최근 10분 밀집도(09-03 사용자 결정: 당일 즉석 히트맵. 09-16 사용자 결정: 30분→10분). 5초마다 poll 로 */
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

/* 평소 밀집도(10-13 사용자 요청) — 최근 7일 그 끼니 창의 타일별 평균 누적 + 클러스터 ①②③. 두 끼니를 함께 받아 캐시, 토글은 즉시 */
const TYP = { lunch: null, dinner: null };
let typMeal = "lunch";
const CIRC = ["①", "②", "③"];

function drawTypCard() {
  const d = TYP[typMeal]; if (!d || d.state !== "ok") return;
  const c = $("#typplan"), W = c.clientWidth || 318;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  const Gt = geom(W, H);
  drawFloor(g, Gt);
  drawZoneLabels(g, Gt, ZONES);
  drawHeat(g, Gt, d.cells, d.grid.cols, d.grid.rows);
  drawClusters(g, Gt, d.clusters, d.grid.cols, d.grid.rows);
}

function renderTyp(d) {
  if (d) TYP[d.meal || typMeal] = d;
  const cur = TYP[typMeal];
  const ok = cur && cur.state === "ok" && cur.cells && cur.cells.length;
  if (!setState("typcard", !!ok, cur && cur.reason)) { $("#typbar").hidden = true; return; }
  drawTypCard();
  const cl = cur.clusters || [];
  $("#typlead").innerHTML = cl.length
    ? `최근 ${cur.n_days}일 ${MEAL_KO[typMeal]} 시간, 사람이 늘 모이는 자리는 <b>${esc(cl[0].label)}</b> 쪽입니다`
    : `최근 ${cur.n_days}일 ${MEAL_KO[typMeal]} 시간의 평균 밀집도`;
  $("#typchips").innerHTML = cl.map((c, i) =>
    `<span class="${i ? "ghost" : ""}"><b>${CIRC[i] || i + 1}</b>${esc(c.label)}<small>타일 ${c.n_cells}개 · 평균 ${c.avg}명</small></span>`).join("")
    + (cur.zones || []).slice(0, 3).map(z => `<span class="ghost dim">${esc(z.label)}<small>${z.share_pct}% · 평균 ${z.avg_n}명</small></span>`).join("");
  $("#typfoot").textContent = `${cur.since} 이후 ${cur.n_days}일 · 표본 ${cur.ticks}개 · 타일별 평균 인원, 번호는 진한 타일(최대의 절반↑)이 이어진 묶음 · 개별 위치는 저장하지 않습니다`;
  $("#typbar").hidden = false;
}

async function loadTyp() {
  const [l, d] = await Promise.all([jSoft("/api/insight/density_typical?days=7&meal=lunch"), jSoft("/api/insight/density_typical?days=7&meal=dinner")]);
  TYP.lunch = l; TYP.dinner = d;
  renderTyp(null);
}

function renderReport(d) {
  const item = (d.items || []).find(x => x.kind === "recap") || (d.items || [])[0];
  if (!setState("reportcard", d.state === "ok" && !!item, d.reason)) return;
  $("#reporthead").textContent = item.headline || "";
  $("#reportbody").textContent = item.body || "";
  $("#reportchips").innerHTML = `<em class="teal">${item.engine && item.engine !== "template" ? "AI 작성" : "규칙 문장"}${item.model ? " · " + esc(item.model) : ""}</em>`
    + `<small>${item.kind === "preview" ? "아침 예보" : "점심 결산"} · ${(item.created_at || "").slice(5, 16).replace("T", " ")}</small>`;
}

const RENDER = { zonecard: renderZones, reportcard: renderReport, typcard: renderTyp };

export const screen = {
  mount() {                                            // 부팅 때 core 가 부른다(순환 import 의 TDZ 회피)
    canvasAuto($("#plan"), () => { drawFloorLayer(); renderPlan(S.lastPos || { state: "no_data" }); });
    canvasAuto($("#zoneplan"), drawZoneCard);
    canvasAuto($("#typplan"), drawTypCard);
    $("#zonebar").querySelector("i").style.background = gradient(SUNSETDARK);
    $("#typbar").querySelector("i").style.background = gradient(SUNSETDARK);
    typMeal = defaultMeal();
    mealSeg($("#typseg"), typMeal, m => { typMeal = m; renderTyp(null); });
    loadZones();
  },
  every: 5000,                                         // 09-16: 마커·밀집도 5초(vision 의 positions 갱신 주기와 맞춤 — core tick 도 5초)
  async poll() {                                       // 위치 마커 + 최근 10분 밀집도(둘 다 라이브)
    const [p, z] = await Promise.all([j("/api/positions"), jSoft("/api/insight/density?minutes=10")]);
    S.lastPos = p; renderPlan(p); renderZones(z);
  },
  async slow() { renderReport(await jSoft("/api/insight/text")); loadZones(); loadTyp(); },   // 리포트·구역 정의·평소 밀집도 — core 가 30분마다
  fail() { S.lastPos = { state: "no_data" }; renderPlan(S.lastPos); },    // 서버에 닿지 못하면 옛 위치를 '지금'처럼 두지 않는다
  activate() { $("#plancard").classList.add("live"); },                   // 점멸은 보일 때만
  deactivate() { $("#plancard").classList.remove("live"); },
  render(cardId, data) { RENDER[cardId]?.(data); },
};

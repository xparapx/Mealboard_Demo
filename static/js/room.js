/* 실시간 화면 — 탑뷰 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2)
   두 겹 캔버스: #plan 에 정적 평면도(floor.js), 그 위 #marks 에 마커만 — 점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1)이며
   이 화면이 활성일 때만 돈다(.plan.live). 평면도는 데이터·상자 크기가 바뀔 때만 그린다(canvasAuto).
   /api/positions 는 이 화면이 보일 때만 30초마다 — 다른 화면에서는 요청이 나가지 않는다.
   아래 인사이트 카드: 구역별 점유율(집계 숫자만 — 같은 평면도 위에 틴트) · 오늘 리포트(로컬 LLM 글, Phase 4 가 채운다). 5분마다 */
import { $, j, S, esc, fit, canvasAuto, why } from "./core.js";
import { drawFloor, drawMarkers, drawZones, geom } from "./floor.js";

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

/* ---------------- 인사이트 카드 ---------------- */
const mm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const setState = (id, ok, reason) => {
  const card = $("#" + id); card.dataset.state = ok ? "ok" : "no_data";
  const e = card.querySelector(".empty"), w = why(reason); if (e && w) e.textContent = w;
};
let ZONES = null;                                     // 마지막 구역 응답 — 상자 크기가 바뀌면 다시 그린다

function drawZoneCard() {
  const d = ZONES; if (!d) return;
  const c = $("#zoneplan"), W = c.clientWidth || 318;
  if (!W) return;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  const G = geom(W, H);
  drawFloor(g, G);
  drawZones(g, G, d.zones, d.occ);
}

function renderZones(d) {
  const ok = d.state === "ok" && d.bins && d.bins.length && d.zones && d.zones.length;
  setState("zonecard", ok, d.reason);
  if (!ok) { ZONES = null; return; }
  // 창 전체의 평균 점유율(%) — 5분 구간 share_pct 의 평균. 틴트는 가장 붐빈 구역을 1 로 정규화
  const share = {}, avg = {};
  d.zones.forEach(z => { share[z.id] = 0; avg[z.id] = 0; });
  d.bins.forEach(b => d.zones.forEach(z => { share[z.id] += b.share_pct?.[z.id] || 0; avg[z.id] += b.avg_n?.[z.id] || 0; }));
  d.zones.forEach(z => { share[z.id] /= d.bins.length; avg[z.id] /= d.bins.length; });
  const top = Math.max(1, ...Object.values(share));
  const occ = {}; d.zones.forEach(z => occ[z.id] = share[z.id] / top);
  ZONES = { zones: d.zones, occ };
  drawZoneCard();
  const busiest = d.zones.slice().sort((a, b) => share[b.id] - share[a.id])[0];
  $("#zonelead").innerHTML = `<b>${esc(busiest.label)}</b>에 사람이 가장 많았습니다 (${Math.round(share[busiest.id])}%)`;
  $("#zonechips").innerHTML = d.zones.map(z =>
    `<span class="${z.id === busiest.id ? "" : "ghost"}">${esc(z.label)}<small>${Math.round(share[z.id])}% · 평균 ${avg[z.id].toFixed(1)}명</small></span>`).join("");
  const peak = d.peak ? ` · 가장 붐빈 시각 ${mm(d.peak.minute_of_day)} (${d.peak.total}명)` : "";
  $("#zonefoot").textContent = (d.basis === "day" ? `${d.date} 하루` : `최근 ${d.weeks}주 평균`) + peak + " · 구역별 인원수만 집계, 개별 위치는 저장하지 않습니다";
}

function renderReport(d) {
  const item = (d.items || []).find(x => x.kind === "recap") || (d.items || [])[0];
  setState("reportcard", d.state === "ok" && !!item, d.reason);
  if (!item) return;
  $("#reporthead").textContent = item.headline || "";
  $("#reportbody").textContent = item.body || "";
  $("#reportchips").innerHTML = `<em class="teal">${item.engine === "hailo" ? "AI 작성" : "규칙 문장"}${item.model ? " · " + esc(item.model) : ""}</em>`
    + `<small>${item.kind === "preview" ? "아침 예보" : "점심 결산"} · ${(item.created_at || "").slice(5, 16).replace("T", " ")}</small>`;
}

const RENDER = { zonecard: renderZones, reportcard: renderReport };
let lastInsight = 0;
async function loadInsights() {
  lastInsight = Date.now();
  const get = u => j(u).catch(e => (console.error(u, e), { state: "no_data", reason: "서버에 닿지 못했습니다" }));
  const [z, t] = await Promise.all([get("/api/insight/zones?weeks=4"), get("/api/insight/text")]);
  renderZones(z); renderReport(t);
}

export const screen = {
  mount() {                                            // 부팅 때 core 가 부른다(순환 import 의 TDZ 회피)
    canvasAuto($("#plan"), () => renderPlan(S.lastPos || { state: "no_data" }));
    canvasAuto($("#zoneplan"), drawZoneCard);
  },
  every: 30000,
  async poll() {
    if (Date.now() - lastInsight >= 300000) loadInsights();
    S.lastPos = await j("/api/positions"); renderPlan(S.lastPos);
  },
  fail() { S.lastPos = { state: "no_data" }; renderPlan(S.lastPos); },    // 서버에 닿지 못하면 옛 위치를 '지금'처럼 두지 않는다
  activate() { $("#plancard").classList.add("live"); },                   // 점멸은 보일 때만
  deactivate() { $("#plancard").classList.remove("live"); },
  render(cardId, data) { RENDER[cardId]?.(data); },
};

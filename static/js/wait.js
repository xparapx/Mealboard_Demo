/* 대기시간 화면 — 히어로(지금 줄을 서면) + 추이(최근 30분, 평소 곡선 겹침). 30초 폴링.
   그 아래 인사이트 카드 다섯 장(히트맵 · 황금 구간 · 예보 · 병목 로그 · 측정 품질)은 화면이 열릴 때 1회 + 5분마다 (PLAN §3.5) */
import { $, j, S, esc, fit, hhmm, minuteOfDay, canvasAuto, why } from "./core.js";

const BUSY_MIN = 12, EASY_MIN = 5;   // 판정 임계값 (학교마다 다를 수 있음)
const CHART_MIN = 30;                 // 추이 카드의 시간창(분) — 카드 제목·축 라벨과 함께 바꾼다

function level(st) {
  if (st.state === "no_data") return "off";
  if (st.state === "insufficient_rate") return "wait";
  return st.wait_min > BUSY_MIN ? "busy" : "ok";
}
function verdict(st) {
  return { off: "정보 없음", wait: "배식 시작 대기", busy: "혼잡 · 잠시 후 추천",
           ok: st.wait_min <= EASY_MIN ? "여유 · 바로 가세요" : "보통" }[level(st)];
}

/* ---------------- 대기 상태 ---------------- */
let lastWait = null;
function renderStatus(st) {
  const shown = st.wait_min == null ? "—" : String(st.wait_min);
  if (shown !== lastWait) {                          // 값이 실제로 바뀔 때만 0.25s 스케일 펄스
    $("#wait-min").textContent = shown;
    if (lastWait !== null) {
      const b = $("#bigbox"); b.classList.remove("pulse"); void b.offsetWidth; b.classList.add("pulse");
      b.addEventListener("animationend", () => b.classList.remove("pulse"), { once: true });
    }
    lastWait = shown;
  }
  $("#queue").textContent = st.queue_len ?? "—";
  $("#rate").textContent = st.rate_per_min ?? "—";
  $("#state").textContent = verdict(st);
  $("#hero").dataset.level = level(st);
  $("#updated").textContent = st.updated_at ? new Date(st.updated_at).toLocaleTimeString("ko-KR") : "—";
  // ③ 도착 시각 — 지금 줄을 서면 몇 시에 배식대에 닿는가. 데이터가 끊긴(no_data) 옛 값으로는 계산하지 않는다
  const ok = st.state !== "no_data" && st.wait_min != null;
  $("#arrive").hidden = !ok;
  if (ok) $("#arriveat").textContent = hhmm(new Date(Date.now() + st.wait_min * 60000));
}

export async function refresh() {
  const st = await j("/api/status");
  renderStatus(st);
  const [h, t] = await Promise.all([
    j(`/api/history?minutes=${CHART_MIN}`),
    j(`/api/typical?minutes=${CHART_MIN}`).catch(() => ({ state: "no_data", rows: [] }))]);
  S.last = { rows: h.rows, typ: t, st };
  drawChart(h.rows, t, st);
}

/* ---------------- ④ 추이 + 평소 곡선 ----------------
   x 는 '자정부터 몇 분'. 오늘 이력과 평소 곡선을 같은 축에 얹으려면 인덱스가 아니라 시각이어야 한다 */
export function drawChart(rows, typ, st) {
  const pts = rows.filter(r => r.wait_min != null)
                  .map(r => ({ m: minuteOfDay(new Date(r.ts)), v: r.wait_min }));
  $("#trend").hidden = pts.length < 2;
  if (pts.length < 2) return;

  const hi = minuteOfDay(new Date()), lo = Math.max(0, hi - CHART_MIN);
  const ref = (typ.state === "ok" ? typ.rows : []).filter(r => r.minute_of_day >= lo && r.minute_of_day <= hi);
  $("#reflab").hidden = !ref.length;
  $("#reflab").textContent = ref.length
    ? (typ.basis === "weekday" ? `평소 · 같은 요일 ${typ.days}일` : `평소 · 최근 ${typ.days}일`) : "";

  const c = $("#chart"), H = c.clientHeight || 92, { g, w } = fit(c, H);
  const padR = ref.length ? 34 : 8, padT = 6, padB = 4;              // 오른쪽은 선 끝 라벨 자리
  const plotW = Math.max(1, w - padR - 4), plotH = H - padT - padB;
  // 스프레드(...)로 넘기면 행이 수만 개일 때(고배속 mock) 호출 스택이 터진다 — reduce 로
  const max = Math.max(5, pts.reduce((a, p) => Math.max(a, p.v), 0),
                       ref.reduce((a, r) => Math.max(a, r.wait_min), 0));
  const X = m => 4 + (m - lo) / Math.max(1, hi - lo) * plotW;
  const Y = v => padT + (1 - v / max) * plotH;
  const path = (arr, fx, fy) => { g.beginPath(); arr.forEach((d, i) => (i ? g.lineTo : g.moveTo).call(g, fx(d), fy(d))); };

  g.lineJoin = g.lineCap = "round";
  // 오늘: 위로 갈수록 진한 틸 채움 — 봉우리가 스스로 강조된다
  const grad = g.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, "rgba(18,151,147,.24)"); grad.addColorStop(1, "rgba(18,151,147,0)");
  path(pts, p => X(p.m), p => Y(p.v));
  g.lineTo(X(pts[pts.length - 1].m), H); g.lineTo(X(pts[0].m), H); g.closePath();
  g.fillStyle = grad; g.fill();

  if (ref.length) {                                                   // 평소: 중립 회색 파선 (색이 아니라 선으로 구분)
    g.setLineDash([4, 4]); g.strokeStyle = "#B9B1A0"; g.lineWidth = 1.5;
    path(ref, r => X(r.minute_of_day), r => Y(r.wait_min)); g.stroke();
    g.setLineDash([]);
  }
  g.strokeStyle = "#129793"; g.lineWidth = 2;
  path(pts, p => X(p.m), p => Y(p.v)); g.stroke();

  const last = pts[pts.length - 1];
  g.setLineDash([3, 3]); g.strokeStyle = "rgba(209,74,56,.5)"; g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(X(last.m), 2); g.lineTo(X(last.m), H); g.stroke(); g.setLineDash([]);
  g.beginPath(); g.arc(X(last.m), Y(last.v), 4, 0, Math.PI * 2);
  g.fillStyle = "#129793"; g.fill(); g.strokeStyle = "#FFFCF6"; g.lineWidth = 2; g.stroke();

  if (ref.length) {
    g.font = "700 9px system-ui, sans-serif"; g.textBaseline = "middle"; g.textAlign = "left";
    const r = ref[ref.length - 1];
    g.fillStyle = "#0C6D6A"; g.fillText("오늘", X(last.m) + 8, Y(last.v));
    g.fillStyle = "#A9A296"; g.fillText("평소", X(r.minute_of_day) + 8, Y(r.wait_min));
  }
  // 결론 한 줄 — 곡선을 읽지 않아도 답이 나오게
  const near = ref.length ? ref.reduce((a, b) =>
    Math.abs(b.minute_of_day - last.m) < Math.abs(a.minute_of_day - last.m) ? b : a) : null;
  const lead = $("#chartlead");
  lead.hidden = !near || st.wait_min == null;
  if (!lead.hidden) {
    const d = Math.round(near.wait_min - st.wait_min);
    lead.innerHTML = Math.abs(d) < 1 ? "평소 이 시각과 <b>비슷합니다</b>"
      : `평소 이 시각보다 <b>${Math.abs(d)}분 ${d > 0 ? "짧습니다" : "깁니다"}</b>`;
  }
}

/* ---------------- 인사이트 카드 ----------------
   render(cardId, data) 는 DOM 만 만진다 — 픽스처 JSON 으로 그대로 검사할 수 있다 (MB.screens.wait.render("heatcard", json)) */
const WD = "일월화수목금토";
const GOLDEN_WAIT = 3;                       // app/insight_calc.GOLDEN_WAIT 과 같은 문턱(셀 링 표시용)
const MAX_COLS = 36;                         // 히트맵 열 상한 — 창이 넓으면(스테이징 all) 구간을 묶는다
const mm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const hm = ts => ts ? ts.slice(11, 16) : "";
const setState = (id, ok, reason) => {
  const card = $("#" + id); card.dataset.state = ok ? "ok" : "no_data";
  const e = card.querySelector(".empty"), w = why(reason); if (e && w) e.textContent = w;
};

function renderHeat(d) {
  const ok = d.state === "ok" && d.cells && d.cells.length;
  setState("heatcard", ok, d.reason);
  if (!ok) return;
  const lo = d.window?.lo ?? Math.min(...d.cells.map(c => c.minute_of_day));
  const hi = d.window?.hi ?? Math.max(...d.cells.map(c => c.minute_of_day)) + 5;
  const step = Math.max(5, Math.ceil((hi - lo) / 5 / MAX_COLS) * 5);   // 5분 구간을 step 분으로 묶는다
  const cols = Math.ceil((hi - lo) / step);
  const todayWd = new Date().getDay();
  const grid = {};                            // "wd:col" → {sum, n, days}
  d.cells.forEach(c => {
    if (c.wait_min == null) return;
    const k = `${c.weekday}:${Math.floor((c.minute_of_day - lo) / step)}`;
    const g = grid[k] || (grid[k] = { sum: 0, n: 0, days: 0 });
    g.sum += c.wait_min; g.n += 1; g.days = Math.max(g.days, c.n_days || 0);
  });
  const vals = Object.values(grid).map(g => g.sum / g.n);
  const max = Math.max(1, ...vals);
  let html = "";
  for (const wd of [1, 2, 3, 4, 5]) {
    html += `<div class="wd" data-wd="${wd}"${wd === todayWd ? " data-today" : ""}>${WD[wd]}</div><div class="row">`;
    for (let col = 0; col < cols; col++) {
      const g = grid[`${wd}:${col}`];
      if (!g) { html += `<button class="c" type="button" data-none disabled aria-label="자료 없음"></button>`; continue; }
      const w = g.sum / g.n, t = Math.min(1, w / max);
      html += `<button class="c" type="button" style="--t:${t.toFixed(3)}" data-wd="${wd}" data-min="${lo + col * step}" data-w="${w.toFixed(1)}" data-days="${g.days}"`
        + (w <= GOLDEN_WAIT ? " data-golden" : "") + ` aria-label="${WD[wd]} ${mm(lo + col * step)} 평소 ${w.toFixed(1)}분"></button>`;
    }
    html += "</div>";
  }
  html += `<div class="axis"><span>${mm(lo)}</span><b>${mm(Math.round((lo + hi) / 2 / 5) * 5)}</b><span>${mm(hi)}</span></div>`;
  $("#heat").innerHTML = html;
  $("#heat").querySelectorAll(".c[data-min]").forEach(b => b.addEventListener("click", () => {
    $("#heat").querySelectorAll('[aria-pressed="true"]').forEach(x => x.removeAttribute("aria-pressed"));
    b.setAttribute("aria-pressed", "true");
    const wd = +b.dataset.wd, m = +b.dataset.min;
    $("#heatlead").innerHTML = `${WD[wd]}요일 <b>${mm(m)}~${mm(m + step)}</b> 평소 대기 <b>${b.dataset.w}분</b> <small style="color:var(--ink3)">· ${b.dataset.days}일 평균</small>`;
  }));
  $("#heatlead").textContent = "셀을 누르면 그 시각의 평소 대기를 읽습니다";
  $("#heatfoot").textContent = (d.basis === "weekday" ? `같은 요일 최근 ${d.weeks}주` : `최근 ${d.days}일`) + ` · ${step}분 단위 · 틸이 진할수록 오래 기다렸습니다`;
}

function renderGolden(d) {
  const list = (d.golden || []).slice(0, 3);
  setState("goldencard", d.state !== "no_data" && list.length, d.state === "no_data" ? d.reason : undefined);
  if (!list.length) return;
  const total = (d.golden || []).reduce((a, e) => a + (e.minutes || 0), 0);
  $("#goldenlead").innerHTML = `오늘 <b>${Math.round(total)}분</b> 동안 바로 먹을 수 있었습니다` + (d.basis === "live" ? ` <small style="color:var(--ink3)">· 지금까지</small>` : "");
  $("#goldenchips").innerHTML = list.map(e => `<span>${hm(e.start_ts)}–${hm(e.end_ts)}<small>평균 ${e.value}분</small></span>`).join("");
}

function renderForecast(d) {
  const day = d.date ? new Date(d.date + "T12:00:00") : null;
  const when = day ? `${day.getMonth() + 1}/${day.getDate()} ${WD[day.getDay()]}요일` : "";
  const todayIso = new Date().toLocaleDateString("sv-SE");   // 로컬 날짜 YYYY-MM-DD
  $("#forecasteyebrow").textContent = d.date && d.date === todayIso ? "오늘 예보" : "내일 예보";
  if (d.state === "no_meal") { setState("forecastcard", false, `${when} 급식이 없습니다`); return; }
  const ok = d.state === "ok" && d.curve && d.curve.length;
  setState("forecastcard", ok, d.reason);
  if (!ok) return;
  $("#forecastlead").innerHTML = `${when} 피크 <b>${mm(d.peak.minute_of_day)}</b> 무렵 약 <b>${d.peak.wait_min}분</b>`;
  $("#forecastchips").innerHTML = (d.golden || []).slice(0, 3).map(g => `<span class="ghost">${mm(g.start_min)}–${mm(g.end_min)}<small>3분 이하</small></span>`).join("");
  const menu = (d.menu || [])[0] ? `주요리 ${esc(d.menu[0])} · ` : "";
  $("#forecastfoot").textContent = `${menu}메뉴 보정 ×${d.menu_factor} · 평소 곡선 ${d.basis === "weekday" ? "같은 요일 " + d.weeks + "주" : "최근 7일"}`;
}

function renderBottle(d) {
  const list = d.bottlenecks || [];
  setState("bottlecard", d.state !== "no_data" && list.length, d.state === "no_data" ? d.reason : undefined);
  if (!list.length) return;
  $("#bottlelist").innerHTML = list.map(e =>
    `<li><b>${hm(e.start_ts)}–${hm(e.end_ts)} 배식 정체 ${e.minutes}분</b><div><em>최대 ${e.value}명 대기</em><small>${esc(e.detail || "")}</small></div></li>`).join("");
}

function renderQuality(d) {
  const ok = d.state === "ok";
  setState("qualitycard", ok, d.reason);
  if (!ok) return;
  const tile = (v, unit, label, warn) => `<div${warn ? " data-warn" : ""}><b>${v ?? "—"}<i>${unit}</i></b><span>${label}</span></div>`;
  $("#qualitywell").innerHTML = tile(d.coverage_pct, "%", "측정 커버리지", d.coverage_pct != null && d.coverage_pct < 90)
    + tile(d.n_samples, "개", "표본") + tile(d.stale_min, "분", "빈 시간", d.stale_min > 0) + tile(d.insufficient_min, "분", "산출 불가", d.insufficient_min > 0);
  const w = d.window ? `${mm(d.window.lo)}~${mm(d.window.hi)}` : "";
  $("#qualityfoot").textContent = (d.basis === "live" ? `지금까지 즉석 계산 ${w}` : `집계 ${w}`) + (d.rollup?.last_run ? ` · 마지막 집계 ${d.rollup.last_run.slice(5, 16).replace("T", " ")}` : "");
}

const RENDER = { heatcard: renderHeat, goldencard: renderGolden, forecastcard: renderForecast, bottlecard: renderBottle, qualitycard: renderQuality };
let lastInsight = 0;
async function loadInsights() {
  lastInsight = Date.now();
  const get = (u, fb) => j(u).catch(e => (console.error(u, e), { state: "no_data", reason: "서버에 닿지 못했습니다", ...fb }));
  const [heat, day, fc, q] = await Promise.all([get("/api/insight/heatmap?weeks=4"), get("/api/insight/day"),
                                               get("/api/insight/forecast"), get("/api/insight/quality")]);
  renderHeat(heat); renderGolden(day); renderBottle(day); renderForecast(fc); renderQuality(q);
}

export const screen = {
  mount() { canvasAuto($("#chart"), () => S.last && drawChart(S.last.rows, S.last.typ, S.last.st)); },   // 모듈 최상위에서 core 의 도구를 쓰면 순환 import 의 TDZ 에 걸린다 — 부팅 때 core 가 부른다
  every: 30000,
  async poll() {                              // 라이브는 30초, 인사이트는 5분 (같은 tick 에서 시각으로 가른다)
    const live = refresh();
    if (Date.now() - lastInsight >= 300000) loadInsights();
    await live;
  },
  fail() { renderStatus({ state: "no_data" }); $("#trend").hidden = true; },   // 서버에 닿지 못하면 '정보 없음' — 옛 숫자를 지금처럼 두지 않는다
  render(cardId, data) { RENDER[cardId]?.(data); },
};

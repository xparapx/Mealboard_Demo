/* 대기시간 화면 — 히어로(지금 줄을 서면) + 추이(최근 30분, 평소 곡선 겹침). 30초 폴링 */
import { $, j, S, fit, hhmm, minuteOfDay, canvasAuto } from "./core.js";

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

export const screen = {
  mount() { canvasAuto($("#chart"), () => S.last && drawChart(S.last.rows, S.last.typ, S.last.st)); },   // 모듈 최상위에서 core 의 도구를 쓰면 순환 import 의 TDZ 에 걸린다 — 부팅 때 core 가 부른다
  every: 30000,
  poll: refresh,
  fail() { renderStatus({ state: "no_data" }); $("#trend").hidden = true; },   // 서버에 닿지 못하면 '정보 없음' — 옛 숫자를 지금처럼 두지 않는다
};

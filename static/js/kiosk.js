/* 송출 화면(/kiosk, 11-02 — 제안서 P9): 통행로 42인치 모니터용. 고정 1920×1080 무대 + 왼쪽 고정 패널(시계·지금 대기·다음 급식·QR) +
   오른쪽 10초 회전 슬라이드. 학생 앱의 API 를 그대로 읽고(상태 10초, 추이·위치·밀집도 15초, 집계 5분, 식단·리포트 10분), 화면은 스냅숏에서 그린다.
   core.js 는 부팅 로직(라우터·서비스워커)이라 들여오지 않고 floor.js·colors.js 만 쓴다. 숫자·평면도·익명 마커뿐 — 실사 없음.
   쿼리: ?interval=10 &slides=wait,room,... &hold &fit=0 &noanim */
import { drawFloor, drawHeat, drawClusters, drawMarkers, drawZoneLabels, geom } from "/js/floor.js";
import { SUNSETDARK, ramp, gradient } from "/js/colors.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const mm = m => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const WD = "일월화수목금토";
const MEAL_KO = { lunch: "중식", dinner: "석식" };
const q = new URLSearchParams(location.search);
const OPT = { dwell: Math.min(300, Math.max(5, +q.get("interval") || 10)) * 1000,
              slides: (q.get("slides") || "").split(",").map(s => s.trim()).filter(Boolean),
              hold: q.has("hold"), fit: q.get("fit") !== "0", anim: !q.has("noanim") };
if (!OPT.anim) document.documentElement.classList.add("noanim");

/* ---------------- 무대 축소 ---------------- */
function fitStage() {
  const root = $("#k-root");
  if (!OPT.fit) { root.style.transform = ""; return; }
  const s = Math.min(innerWidth / 1920, innerHeight / 1080);
  root.style.transform = `scale(${s})`;
  root.style.left = `${Math.max(0, (innerWidth - 1920 * s) / 2)}px`;
  root.style.top = `${Math.max(0, (innerHeight - 1080 * s) / 2)}px`;
}
addEventListener("resize", fitStage);
fitStage();

/* ---------------- 데이터 ---------------- */
const D = { status: null, history: null, positions: null, density: null, typical: { lunch: null, dinner: null }, zones: null,
            forecast: { lunch: null, dinner: null }, heat: { lunch: null, dinner: null }, text: null, meal: null, net: "ok", skew: 0 };
let lastOk = Date.now();
async function get(url) {
  const ac = new AbortController(), to = setTimeout(() => ac.abort(), 10000);
  try {
    const r = await fetch(url, { cache: "no-store", signal: ac.signal });
    if (!r.ok) throw new Error(r.status);
    lastOk = Date.now();
    return await r.json();
  } catch (e) { return null; } finally { clearTimeout(to); }
}
const now = () => new Date(Date.now() + D.skew);                 // 데모(가상 시계)는 서버 now 와의 차를 보정
const meal = () => { const h = now().getHours(); return h >= 14 && h < 21 ? "dinner" : "lunch"; };
function sched(name, fn, every) {                                  // 먼저 다음을 예약한다 — 그리기 오류가 폴링을 멈추지 않게
  const tick = async () => { setTimeout(tick, every); try { await fn(); } catch (e) { console.error(name, e); } };
  tick();
}
sched("status", async () => {
  const s = await get("/api/status");
  if (!s) { D.net = Date.now() - lastOk > 90000 ? "lost" : "late"; renderSide(); return; }
  D.net = "ok"; D.status = s;
  if (s.now) { const sk = new Date(s.now).getTime() - Date.now(); if (Math.abs(sk - D.skew) > 30000) { D.skew = sk; paintClock(); } }   // 가상 시계(데모)면 즉시 맞춘다
  renderSide();
}, 10000);
sched("live", async () => {
  const [h, p, d] = await Promise.all([get("/api/history?minutes=30&step=10"), get("/api/positions"), get("/api/insight/density?minutes=10")]);
  if (h) D.history = h; if (p) D.positions = p; if (d) D.density = d;
}, 15000);
sched("insight", async () => {
  for (const m of ["lunch", "dinner"]) {
    const [f, hm, t] = await Promise.all([get(`/api/insight/forecast?meal=${m}`), get(`/api/insight/heatmap?meal=${m}`), get(`/api/insight/density_typical?days=7&meal=${m}`)]);
    if (f) D.forecast[m] = f; if (hm) D.heat[m] = hm; if (t) D.typical[m] = t;
  }
  const z = await get("/api/insight/zones?weeks=1"); if (z && z.zones) D.zones = z.zones;
}, 5 * 60000);
sched("daily", async () => {
  const [m, t] = await Promise.all([get("/api/meal"), get("/api/insight/text")]);
  if (m) D.meal = m; if (t) D.text = t;
}, 10 * 60000);
fetch("/icons/qr.png", { method: "HEAD", cache: "no-store" }).then(r => { if (r.ok) { $("#k-qrimg").src = "/icons/qr.png"; $("#k-qr").hidden = false; } }).catch(() => {});

/* ---------------- 판정(학생 앱 wait.js 와 같은 규칙) ---------------- */
const BUSY_MIN = 12, EASY_MIN = 0.5;
function level(st) {
  if (!st || st.state === "no_data") return "off";
  if (st.state === "insufficient_rate") return "wait";
  const r = st.wait_range;
  if (r && st.wait_min != null && r.hi - r.lo >= 2) return (st.wait_min - r.lo) / (r.hi - r.lo) >= 2 / 3 ? "busy" : "ok";
  return st.wait_min > BUSY_MIN ? "busy" : "ok";
}
function verdict(st) {
  const lv = level(st), closed = st?.feed?.source === "vision" && !st?.feed?.now;
  const easy = st?.wait_min != null && st.wait_min <= EASY_MIN;
  return { off: closed ? "급식 시간이 아닙니다" : "정보 없음", wait: "측정 준비 중", busy: "혼잡 · 잠시 후 추천", ok: easy ? "여유 · 바로 가세요" : "보통" }[lv];
}
const fmtWait = v => v == null ? "—" : v < 1 ? Math.round(v * 60) : Math.round(v * 10) / 10;
const unitWait = v => v == null ? "" : v < 1 ? "초" : "분";

/* ---------------- 왼쪽 패널 ---------------- */
function paintClock() {
  const t = now();
  $("#k-clock").textContent = `${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}`;
  $("#k-date").textContent = `${t.getMonth() + 1}월 ${t.getDate()}일 ${WD[t.getDay()]}요일`;
}
function renderClock() { paintClock(); setTimeout(renderClock, 60050 - ((Date.now() + D.skew) % 60000)); }
renderClock();
function renderSide() {
  const st = D.status, lv = level(st), easy = st?.wait_min != null && st.wait_min <= EASY_MIN;
  const root = $("#k-root");
  root.className = `lv-${lv === "ok" && easy ? "easy" : lv}`;
  $("#k-lvlabel").textContent = st ? verdict(st) : "—";
  const live = st && lv !== "off" && lv !== "wait" && st.wait_min != null;
  $("#k-lvmin").textContent = live ? fmtWait(st.wait_min) : lv === "wait" ? "…" : "—";
  $("#k-lvunit").textContent = live ? unitWait(st.wait_min) : "";
  $("#k-lvsub").textContent = live ? `지금 줄을 서면 · 대기 ${st.queue_len ?? "—"}명 · 배식 ${st.rate_per_min ?? "—"}명/분` : lv === "wait" ? "배식 속도를 재는 중입니다" : "카메라는 급식 시간에만 셉니다";
  const nx = st?.feed?.next;
  $("#k-next").innerHTML = st?.feed?.now ? `지금 <b>${esc(st.feed.now.label)}</b> 시간 · ${mm(st.feed.now.lo)}~${mm(st.feed.now.hi)}`
    : nx ? `다음 급식 <b>${esc(nx.label)}</b><br>${nx.days ? `${esc(nx.weekday)}요일 ` : ""}<b>${mm(nx.lo)}</b> 시작` : "";
  const fr = $("#k-fresh");
  fr.classList.toggle("lost", D.net !== "ok");
  fr.querySelector("span").textContent = D.net === "ok" ? (st?.updated_at ? `갱신 ${st.updated_at.slice(11, 16)} · 30초마다` : "연결됨")
    : D.net === "late" ? "서버 응답 지연" : "서버에 닿지 않습니다 — 마지막 값";
}

/* ---------------- 캔버스 도구 ---------------- */
function fit(c, w, h) {
  const dpr = devicePixelRatio || 1;
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  return g;
}
function bars(c, w, h, pts, { max, band, label } = {}) {
  /* 큰 막대 그래프 — pts [{x(0~1), v, hot}] */
  const g = fit(c, w, h), padL = 90, padB = 54, padT = 34;
  const pw = w - padL - 20, ph = h - padT - padB;
  const top = Math.max(3, max || 0, ...pts.map(p => p.v)) * 1.1;
  const Y = v => padT + (1 - v / top) * ph;
  g.font = "600 24px system-ui, sans-serif"; g.fillStyle = "#9A958A"; g.textAlign = "right"; g.textBaseline = "middle";
  [0, Math.round(top / 2), Math.round(top)].forEach(v => { g.strokeStyle = "rgba(51,49,45,.1)"; g.lineWidth = 2; g.beginPath(); g.moveTo(padL, Y(v)); g.lineTo(w - 20, Y(v)); g.stroke(); g.fillText(`${v}분`, padL - 14, Y(v)); });
  if (band) { g.fillStyle = "rgba(155,215,213,.35)"; band.forEach(([a, b]) => g.fillRect(padL + a * pw, padT, Math.max(2, (b - a) * pw), ph)); }
  const bw = Math.max(6, pw / Math.max(1, pts.length) - 4);
  pts.forEach(p => {
    const x = padL + p.x * pw - bw / 2, y = Y(p.v);
    g.fillStyle = p.hot ? "#7c1d6f" : ramp(SUNSETDARK, p.v / top); g.beginPath(); g.roundRect(x, y, bw, Math.max(3, h - padB - y), [6, 6, 0, 0]); g.fill();
  });
  if (label) { g.textAlign = "left"; g.textBaseline = "alphabetic"; g.fillStyle = "#6E6A61"; g.font = "600 24px system-ui, sans-serif";
    label.forEach(([x, t, al]) => { g.textAlign = al || "center"; g.fillText(t, padL + x * pw, h - 14); }); }
}

/* ---------------- 슬라이드 ---------------- */
const tile = (v, u, lab, warn) => `<div class="tile${warn ? " warn" : ""}"><b>${v}${u ? `<i>${u}</i>` : ""}</b><span>${lab}</span></div>`;
const SLIDES = [
  { id: "wait", title: () => "지금 줄을 서면", ready: () => !!D.status,
    key: st => st?.feed?.now ? `<span>${esc(st.feed.now.label)}</span>` : "",
    html() {
      const st = D.status, lv = level(st), live = st.wait_min != null && lv !== "off" && lv !== "wait";
      const t = now(), arrive = live ? new Date(t.getTime() + st.wait_min * 60000) : null;
      const nx = st?.feed?.next, fc = D.forecast[meal()];
      const hero = live
        ? `<div class="eyebrow">예상 대기</div><div class="num"><b data-count="${st.wait_min}">${fmtWait(st.wait_min)}</b><i>${unitWait(st.wait_min)}</i></div>
           <div class="pill">${esc(verdict(st))}</div>
           <div class="arrive">배식대 도착 <b>${String(arrive.getHours()).padStart(2, "0")}:${String(arrive.getMinutes()).padStart(2, "0")}</b></div>
           <div class="tiles">${tile(st.queue_len ?? "—", "명", "대기 인원")}${tile(st.rate_per_min == null ? "—" : Math.round(st.rate_per_min * 10) / 10, "명/분", "배식 속도")}${st.wait_range ? tile(`${st.wait_range.lo}~${st.wait_range.hi}`, "분", "오늘 범위") : ""}</div>`
        : `<div class="eyebrow">${lv === "wait" ? "측정 준비 중" : "급식 시간이 아닙니다"}</div>
           <div class="num off"><b>${lv === "wait" ? "배식 속도를 재는 중" : nx ? `다음 ${esc(nx.label)} ${mm(nx.lo)}` : "—"}</b></div>
           ${nx && nx.days ? `<div class="arrive">${esc(nx.weekday)}요일 ${mm(nx.lo)}~${mm(nx.hi)}</div>` : nx ? `<div class="arrive">오늘 ${mm(nx.lo)}~${mm(nx.hi)}</div>` : ""}
           ${fc && fc.state === "ok" && fc.peak ? `<div class="tiles">${tile(mm(fc.peak.minute_of_day), "", "가장 붐빌 예상 시각")}${tile(fmtWait(fc.peak.wait_min), unitWait(fc.peak.wait_min), "그때 예상 대기")}</div>` : ""}`;
      return `<div class="card hero" style="--i:0">${hero}</div>
        <div class="card trend" style="--i:1"><div class="eyebrow">최근 30분</div><div class="lead" id="k-trendlead">${live ? "막대가 높을수록 오래 기다립니다" : "급식 시간에 채워집니다"}</div>
          <canvas id="k-trend"></canvas><div class="legend"><span><i style="background:#e34f6f"></i>1분 단위 예상 대기</span></div></div>`;
    },
    after() {
      const c = $("#k-trend"); if (!c) return;
      const rows = (D.history?.rows || []).filter(r => r.wait_min != null);
      const hi = now().getHours() * 60 + now().getMinutes(), lo = hi - 30;
      const byMin = new Map();
      rows.forEach(r => { const d = new Date(r.ts), m = d.getHours() * 60 + d.getMinutes(); if (m < lo || m > hi) return; const b = byMin.get(m) || { s: 0, n: 0 }; b.s += r.wait_min; b.n++; byMin.set(m, b); });
      const pts = [...byMin.entries()].map(([m, b]) => ({ x: (m - lo) / 30, v: b.s / b.n })).sort((a, b) => a.x - b.x);
      const w = c.clientWidth || 560, h = c.clientHeight || 400;
      if (!pts.length) { const g = fit(c, w, h); g.font = "600 30px system-ui, sans-serif"; g.fillStyle = "#9A958A"; g.textAlign = "center"; g.fillText("아직 표본이 없습니다", w / 2, h / 2); return; }
      bars(c, w, h, pts, { label: [[0, mm(Math.max(0, lo)), "left"], [1, "지금", "right"]] });
      const b = $("[data-count]"); if (b && OPT.anim) countUp(b, +b.dataset.count);
    } },
  { id: "room", title: () => "급식실 어디가 붐비나", ready: () => !!(D.density?.cells?.length || D.typical[meal()]?.cells?.length),
    key: () => D.density?.state === "ok" && D.density.cells?.length ? "<span>최근 10분 · 실시간</span>" : "<span>최근 7일 평소</span>",
    html() {
      const liveD = D.density?.state === "ok" && D.density.cells?.length, d = liveD ? D.density : D.typical[meal()];
      const zones = (d?.zones || []).slice(0, 4);
      return `<div class="card stage" style="--i:0"><canvas id="k-floor" width="560" height="810"></canvas></div>
        <div class="card" style="--i:1"><div class="eyebrow">${liveD ? "최근 10분 밀집도" : `최근 7일 ${MEAL_KO[meal()]} 평소 밀집도`}</div>
          <div class="lead">${zones[0] ? `<b>${esc(zones[0].label)}</b>에 사람이 가장 많습니다` : "타일이 어두울수록 사람이 많은 자리"}${liveD && D.positions?.state === "ok" ? ` · 지금 <b>${D.positions.n}명</b>이 보입니다` : ""}</div>
          <div class="chips">${zones.map((z, j) => `<div style="--j:${j}"><span>${esc(z.label)}</span><small>${z.share_pct}% · 평균 ${z.avg_n}명</small></div>`).join("")}</div>
          <div class="heatbar"><span>적음</span><i style="background:${gradient(SUNSETDARK)}"></i><span>많음</span><span style="margin-left:auto">영상이 아닙니다 · 익명 위치만</span></div></div>`;
    },
    after() {
      const c = $("#k-floor"); if (!c) return;
      const W = 560, H = 810, g = fit(c, W, H), G = geom(W, H);
      drawFloor(g, G); drawZoneLabels(g, G, D.zones);
      const liveD = D.density?.state === "ok" && D.density.cells?.length, d = liveD ? D.density : D.typical[meal()];
      if (d?.cells) drawHeat(g, G, d.cells, d.grid.cols, d.grid.rows);
      if (!liveD && d?.clusters) drawClusters(g, G, d.clusters, d.grid.cols, d.grid.rows);
      if (liveD && D.positions?.state === "ok") drawMarkers(g, G, D.positions.points);
    } },
  { id: "forecast", title: () => `오늘 ${MEAL_KO[meal()]} 예보`, ready: () => D.forecast[meal()]?.state === "ok",
    key: () => { const f = D.forecast[meal()]; return f?.peak ? `가장 붐빌 시각 <b>${mm(f.peak.minute_of_day)}</b>` : ""; },
    html() {
      const f = D.forecast[meal()], gold = f.golden || [];
      return `<div class="card" style="--i:0"><div class="eyebrow">시각별 예상 대기 · 같은 요일 평소 × 오늘 메뉴 인기</div><canvas id="k-fc"></canvas></div>
        <div class="card" style="--i:1"><div class="eyebrow">황금 시간대 · 3분 안에 받는 때</div>
          <div class="golden">${gold.length ? gold.map(gd => `<span>${mm(gd.start_min)}~${mm(gd.end_min)}</span>`).join("") : `<span style="background:var(--well);color:var(--ink2)">오늘은 황금 시간대 예보 없음</span>`}</div>
          <div class="lead" style="margin-top:26px">피크 <b>${mm(f.peak.minute_of_day)}</b> 약 <b>${fmtWait(f.peak.wait_min)}${unitWait(f.peak.wait_min)}</b>${f.menu_factor && f.menu_factor !== 1 ? `<br>오늘 메뉴 인기 보정 ×${f.menu_factor}` : ""}</div>
          ${f.menu?.length ? `<div class="lead" style="margin-top:auto;font-size:26px">${esc(f.menu.slice(0, 4).join(" · "))}</div>` : ""}</div>`;
    },
    after() {
      const c = $("#k-fc"); if (!c) return;
      const f = D.forecast[meal()], cur = f.curve || [];
      if (!cur.length) return;
      const lo = cur[0].minute_of_day, hi = cur[cur.length - 1].minute_of_day + 5, span = Math.max(5, hi - lo);
      const pts = cur.map(p => ({ x: (p.minute_of_day + 2.5 - lo) / span, v: p.forecast_wait, hot: p.minute_of_day === f.peak.minute_of_day }));
      const band = (f.golden || []).map(gd => [(gd.start_min - lo) / span, (gd.end_min - lo) / span]);
      const w = c.clientWidth || 900, h = c.clientHeight || 500, mid = Math.round((lo + hi) / 2 / 5) * 5;
      bars(c, w, h, pts, { band, label: [[0, mm(lo), "left"], [0.5, mm(mid)], [1, mm(hi), "right"]] });
    } },
  { id: "today", title: () => "오늘 급식", ready: () => !!D.meal?.today,
    key: () => { const a = D.meal?.today?.assess; return a?.energy_pct != null ? `에너지 충족 <b>${a.energy_pct}%</b>` : ""; },
    html() {
      const t = D.meal.today, dn = t.dinner, a = t.assess || {};
      const list = (items, n = 7) => `<ul class="menu">${(items || []).slice(0, n).map((x, j) => { const [name, al] = splitAllergy(x); return `<li style="--j:${j}"><span>${esc(name)}</span>${al ? `<small>${esc(al)}</small>` : ""}</li>`; }).join("")}${items && items.length > n ? `<li class="more">외 ${items.length - n}가지</li>` : ""}</ul>`;
      const kcal = v => v ? `<span class="kcal">${Math.round(v)} kcal</span>` : "";
      return `<div class="card" style="--i:0"><div class="eyebrow">중식${kcal(t.kcal)}</div>${t.menu?.length ? list(t.menu) : '<div class="empty">오늘 중식 식단이 없습니다</div>'}</div>
        <div class="card" style="--i:1"><div class="eyebrow">석식${dn ? kcal(dn.kcal) : ""}</div>${dn?.menu?.length ? list(dn.menu) : '<div class="empty">석식 없음</div>'}</div>
        <div class="card kpi" style="--i:2">${tile(a.energy_pct == null ? "—" : a.energy_pct, a.energy_pct == null ? "" : "%", "에너지 충족률(중식)", a.energy_pct != null && (a.energy_pct < 90 || a.energy_pct > 110))}
          ${tile(a.macro_ratio_ok == null ? "—" : a.macro_ratio_ok ? "적정" : "범위 밖", "", "탄·단·지 비율", a.macro_ratio_ok === false)}${tile(a.mar == null ? "—" : a.mar, a.mar == null ? "" : "%", "미량영양소")}
          <div class="tile" style="flex:1.4"><b style="font-size:28px;line-height:1.3;margin-top:4px">괄호 숫자는 알레르기 표시번호</b><span>내 알레르기 설정은 휴대폰 앱(오늘급식)에서</span></div></div>`;
    } },
  { id: "heat", title: () => `요일 · 시각별 평소 대기 <small>${MEAL_KO[meal()]}</small>`, ready: () => D.heat[meal()]?.state === "ok" && D.heat[meal()].cells?.length,
    key: () => "<span>어두울수록 오래 기다린 시간대 · 점선 칸이 지금</span>",
    html() {
      const d = D.heat[meal()], win = d.window || {}, lo = win.lo ?? Math.min(...d.cells.map(c => c.minute_of_day)), hi = win.hi ?? Math.max(...d.cells.map(c => c.minute_of_day)) + 5;
      const step = Math.max(5, Math.ceil((hi - lo) / 5 / 14) * 5), cols = Math.ceil((hi - lo) / step);
      const grid = new Map();
      d.cells.forEach(c => { if (c.wait_min == null || c.minute_of_day < lo || c.minute_of_day >= hi) return; const k = `${c.weekday}:${Math.floor((c.minute_of_day - lo) / step)}`; const g = grid.get(k) || { s: 0, n: 0 }; g.s += c.wait_min; g.n++; grid.set(k, g); });
      const max = Math.max(1, ...[...grid.values()].map(g => g.s / g.n));
      const t = now(), wdNow = t.getDay(), mNow = t.getHours() * 60 + t.getMinutes();
      let html = '<div class="heat">';
      for (const wd of [1, 2, 3, 4, 5]) {
        html += `<div class="wd wd${wd}">${WD[wd]}</div><div class="row">`;
        for (let col = 0; col < cols; col++) {
          const g = grid.get(`${wd}:${col}`), m0 = lo + col * step, isNow = wd === wdNow && mNow >= m0 && mNow < m0 + step;
          html += g ? `<div class="c" style="--j:${col};background:${ramp(SUNSETDARK, g.s / g.n / max)}"${isNow ? " data-now" : ""}></div>` : `<div class="c" style="--j:${col}"${isNow ? " data-now" : ""}></div>`;
        }
        html += "</div>";
      }
      html += `<div class="axis"><span>${mm(lo)}</span><b>${mm(Math.round((lo + hi) / 2 / 5) * 5)}</b><span>${mm(hi)}</span></div></div>`;
      return `<div class="card" style="--i:0"><div class="eyebrow">지난 4주 · 오늘 행은 실시간</div>${html}</div>`;
    } },
  { id: "report", title: () => "오늘 리포트", ready: () => !!(D.text?.items || []).length,
    key: () => "",
    html() {
      const items = D.text.items, it = items.find(x => x.kind === "recap") || items[0];
      return `<div class="card" style="--i:0"><div class="eyebrow">${it.kind === "preview" ? "아침 예보" : "점심 결산"} · ${(it.created_at || "").slice(5, 16).replace("T", " ")}</div>
        <div class="quote">“${esc(it.headline)}”</div><div class="body">${esc(it.body)}</div>
        <div class="meta"><em>${it.engine && it.engine !== "template" ? "AI 작성" : "규칙 문장"}</em>${it.model ? `<span>${esc(it.model)}</span>` : ""}<span>· 집계된 숫자만 받아 씁니다 · 입력에 없는 숫자는 검증기가 막습니다</span></div></div>`;
    } },
  { id: "week", title: () => "이번 주 식단", ready: () => (D.meal?.week || []).filter(d => d.menu?.length).length >= 2,
    key: () => "",
    html() {
      const week = D.meal.week.filter(d => d.menu?.length).slice(0, 5), t = now();
      const today = `${t.getFullYear()}${String(t.getMonth() + 1).padStart(2, "0")}${String(t.getDate()).padStart(2, "0")}`;
      const row = (label, mmx) => {                       // 첫 메뉴는 굵게, 다음 둘은 작게 — 세로 여백을 쓰고 칸을 넘지 않게(11-02)
        if (!mmx?.menu?.length) return `<div class="row"><i>${label}</i><div class="k">없음</div></div>`;
        const names = mmx.menu.map(x => splitAllergy(x)[0]);
        return `<div class="row"><i>${label}</i><div class="m">${esc(names[0])}</div>${names.length > 1 ? `<div class="sub">${esc(names.slice(1, 3).join(" · "))}</div>` : ""}<div class="k">${names.length > 3 ? `외 ${names.length - 3}가지` : ""}${mmx.kcal ? `${names.length > 3 ? " · " : ""}${Math.round(mmx.kcal)} kcal` : ""}</div></div>`;
      };
      return `<div class="card" style="--i:0"><div class="wk">${week.map((d, j) => { const dd = new Date(+d.date.slice(0, 4), +d.date.slice(4, 6) - 1, +d.date.slice(6, 8)); return `<div class="wd${dd.getDay()}" style="--j:${j}"${d.date === today ? " data-today" : ""}><div class="d">${WD[dd.getDay()]}<span>${dd.getMonth() + 1}/${dd.getDate()}</span></div>${row("중식", d)}${row("석식", d.dinner)}</div>`; }).join("")}</div></div>`;
    } },
];
function splitAllergy(s) {                                  // "삼선자장면 (1.5.6)" → ["삼선자장면", "1.5.6"]
  const m = String(s).match(/^(.*?)\s*[(（]\s*([\d.,\s]+)\s*[)）]\s*$/);
  return m ? [m[1].trim(), m[2].replace(/\s/g, "")] : [String(s).replace(/\s+\d{1,2}(?:\.\d{1,2})+\.?\s*$/, "").trim(), ""];
}
function countUp(el, target) {                              // 히어로 숫자 0 → 값(0.9초)
  const t0 = performance.now(), dur = 900, small = target < 1;
  const step = ts => { const k = Math.min(1, (ts - t0) / dur), e = 1 - Math.pow(1 - k, 3), v = target * e; el.textContent = small ? Math.round(v * 60) : (Math.round(v * 10) / 10).toFixed(target % 1 ? 1 : 0); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

/* ---------------- 회전 ---------------- */
const picked = OPT.slides.length ? SLIDES.filter(s => OPT.slides.includes(s.id)) : SLIDES;
let pos = -1, timer = null;
$("#k-dots").innerHTML = picked.map(s => `<i data-sid="${s.id}"></i>`).join("");
function paint(s) {
  const stage = $("#k-stage");
  $("#k-h1").innerHTML = s.title();
  $("#k-key").innerHTML = s.key(D.status) || "";
  stage.innerHTML = `<div class="slide s-${s.id === "forecast" ? "fc" : s.id}">${s.html()}</div>`;
  stage.dataset.sid = s.id;
  document.querySelectorAll("#k-dots i").forEach(i => i.classList.toggle("on", i.dataset.sid === s.id));
  $("#k-footnote").textContent = { wait: "카메라가 센 대기 인원 ÷ 배식 속도 · 추정치", room: "육각 타일별 인원수 합계 · 개별 위치는 저장하지 않습니다", forecast: "예보는 평소 곡선 × 메뉴 인기 · 실제와 다를 수 있습니다",
    today: "교육청 NEIS 급식 정보 · 한 끼 권장량 대비", heat: "지난 4주 집계 · 5분 구간", report: "numbers only — 영상은 어디에도 저장되지 않습니다", week: "NEIS 주간 식단" }[s.id] || "";
  s.after?.();
}
function next() {
  clearTimeout(timer);
  const ready = picked.filter(s => { try { return s.ready(); } catch { return false; } });
  if (!ready.length) { $("#k-stage").innerHTML = '<div class="slide"><div class="card"><div class="empty">데이터를 불러오는 중입니다…</div></div></div>'; timer = setTimeout(next, 2000); return; }
  pos = (pos + 1) % ready.length;
  const s = ready[pos], stage = $("#k-stage"), prog = $("#k-prog");
  const go = () => {
    stage.classList.remove("out", "in");
    try { paint(s); } catch (e) { console.error(s.id, e); timer = setTimeout(next, 1500); return; }
    void stage.offsetWidth; stage.classList.add("in");
    prog.classList.remove("run"); void prog.offsetWidth; prog.style.setProperty("--dwell", `${OPT.dwell}ms`); prog.classList.add("run");
    if (!OPT.hold) timer = setTimeout(next, OPT.dwell);
  };
  if (stage.dataset.sid && OPT.anim) { stage.classList.add("out"); setTimeout(go, 380); } else go();
}
/* 같은 슬라이드를 머무는 동안에도 값은 바뀐다(대기시간·마커) — 10초마다 현재 슬라이드를 제자리에서 다시 그린다(진입 효과 없이) */
setInterval(() => { if (!OPT.hold) return; const s = picked.find(x => x.id === $("#k-stage").dataset.sid); if (s) { document.documentElement.classList.add("noanim"); try { paint(s); } catch {} if (OPT.anim) setTimeout(() => document.documentElement.classList.remove("noanim"), 50); } }, 10000);
setTimeout(next, 600);
/* 배포 뒤 옛 화면이 남지 않게 — 6시간마다 다시 읽고, 자정 직후에도 */
setTimeout(() => location.reload(), 6 * 3600 * 1000);

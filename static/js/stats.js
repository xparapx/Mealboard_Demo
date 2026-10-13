/* 통계 화면(10-13 사용자 요청) — 실시간 위주였던 앱에 '이력' 을 더한다. 전부 집계 숫자(insights.db) 이고 라이브러리 없이 인라인 SVG 로 그린다.
   카드 6: ① 시간대별 대기 분포(평균 ± 1σ 띠 = '볼린저 밴드' + 오늘 실황 선) ② 요일별 비교 ③ 일별 추이(평균·최고 대기 + 식수)
   ④ 영양 인사이트(에너지 충족률 적정 띠 · 탄단지 적정 범위 게이지 · 미량영양소) ⑤ 줄이 길어지는 메뉴 ⑥ 시각별 황금·병목(시차 배식 P21 재료).
   끼니 토글(mealSeg)은 카드마다, 기간(4·8·12주)은 화면 위 한 곳. 두 끼니를 한꺼번에 받아 캐시 — 토글은 재요청 없이 즉시.
   render(cardId, data) 는 DOM 만 만진다(픽스처 검사용: MB.screens.stats.render("bandcard", json)). */
import { $, jSoft, esc, mm, WD, setState, MEAL_KO, defaultMeal, mealSeg } from "./core.js";
import { SUNSETDARK, ramp } from "./colors.js";

const CARDS = ["band", "wd", "daily", "nut", "menu", "ev"];
const SEL = { band: "lunch", wd: "lunch", daily: "lunch", nut: "lunch", menu: "lunch", ev: "lunch" };
const INS = { lunch: {}, dinner: {} };          // {stats, nutrition} 끼니별 캐시
let WEEKS = 4;
const f1 = v => v == null ? "—" : (Math.round(v * 10) / 10).toFixed(1);
const md = d => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;
const INK = "#33312D", INK3 = "#9A958A", TEAL = "#129793", MELON = "#D14A38", PURPLE = "#7c1d6f", PAPER = "#FFFCF6", HAIR = "#E7E1D3";
const txt = (x, y, s, o = {}) => `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-size="${o.size || 9}" font-weight="${o.w || 500}" fill="${o.fill || INK3}" text-anchor="${o.a || "middle"}" dominant-baseline="${o.b || "middle"}" font-family="system-ui, sans-serif">${esc(s)}</text>`;

/* ---------------- ① 시간대별 대기 분포 ---------------- */
let bandGeo = null;
function renderBand(d) {
  const ok = d && d.state === "ok" && d.bands && d.bands.length >= 2;
  if (!setState("bandcard", ok, d && d.reason)) { bandGeo = null; return; }
  const W = 320, H = 150, padL = 26, padR = 8, padT = 10, padB = 18;
  const lo = d.window?.lo ?? d.bands[0].bin, hi = d.window?.hi ?? d.bands[d.bands.length - 1].bin + 5;
  const bands = d.bands.filter(b => b.bin >= lo && b.bin < hi), today = (d.today || []).filter(t => t.bin >= lo && t.bin < hi);
  const max = Math.max(3, ...bands.map(b => b.hi), ...today.map(t => t.wait)) * 1.08;
  const X = m => padL + (m + 2.5 - lo) / (hi - lo) * (W - padL - padR);
  const Y = v => padT + (1 - v / max) * (H - padT - padB);
  const P = (arr, fx, fy) => arr.map((r, i) => `${i ? "L" : "M"}${fx(r).toFixed(1)},${fy(r).toFixed(1)}`).join(" ");
  const area = P(bands, b => X(b.bin), b => Y(b.hi)) + " " + [...bands].reverse().map(b => `L${X(b.bin).toFixed(1)},${Y(b.lo).toFixed(1)}`).join(" ") + " Z";
  const iqr = P(bands, b => X(b.bin), b => Y(b.p75)) + " " + [...bands].reverse().map(b => `L${X(b.bin).toFixed(1)},${Y(b.p25).toFixed(1)}`).join(" ") + " Z";
  const ticks = [0, Math.round(max / 2), Math.round(max)];
  let s = ticks.map(v => `<line x1="${padL}" y1="${Y(v).toFixed(1)}" x2="${W - padR}" y2="${Y(v).toFixed(1)}" stroke="${HAIR}" stroke-width="1"/>` + txt(padL - 6, Y(v), `${v}분`, { a: "end", size: 8.5 })).join("");
  s += `<path d="${area}" fill="${TEAL}" fill-opacity=".14"/><path d="${iqr}" fill="${TEAL}" fill-opacity=".18"/>`;
  s += `<path d="${P(bands, b => X(b.bin), b => Y(b.mean))}" fill="none" stroke="${TEAL}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  if (today.length >= 2) {
    s += `<path d="${P(today, t => X(t.bin), t => Y(t.wait))}" fill="none" stroke="${PURPLE}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>`;
    const l = today[today.length - 1];
    s += `<circle cx="${X(l.bin).toFixed(1)}" cy="${Y(l.wait).toFixed(1)}" r="4" fill="${PURPLE}" stroke="${PAPER}" stroke-width="1.5"/>`;
  }
  const mid = Math.round((lo + hi) / 2 / 5) * 5;
  s += txt(X(lo) - 2, H - 5, mm(lo), { a: "start" }) + txt(X(mid), H - 5, mm(mid), { w: 700, fill: "#5E5A52" }) + txt(X(hi - 5) + 2, H - 5, mm(hi), { a: "end" });
  s += `<line id="bandcur" x1="0" y1="${padT}" x2="0" y2="${H - padB}" stroke="${MELON}" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/>`;
  $("#bandsvg").innerHTML = s;
  bandGeo = { lo, hi, bands, today, X, padL, padR, W };
  const top = bands.reduce((a, b) => b.mean > a.mean ? b : a), low = bands.reduce((a, b) => b.mean < a.mean ? b : a);
  $("#bandlead").innerHTML = `평소 가장 긴 시각 <b>${mm(top.bin)}</b> (${f1(top.mean)}분) · 가장 짧은 시각 <b>${mm(low.bin)}</b> (${f1(low.mean)}분)`;
  $("#bandfoot").textContent = `${MEAL_KO[d.meal]} · 최근 ${d.weeks}주 ${d.n_days}일 집계 · 진한 띠 = 가운데 50%(P25~P75), 옅은 띠 = 평균 ± 1σ(표준편차) · 5분 구간`;
}
function bandHover(e) {
  if (!bandGeo) return;
  const svg = $("#bandsvg"), r = svg.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width * bandGeo.W;
  const m = bandGeo.lo + (x - bandGeo.padL) / (bandGeo.W - bandGeo.padL - bandGeo.padR) * (bandGeo.hi - bandGeo.lo) - 2.5;
  const b = bandGeo.bands.reduce((a, c) => Math.abs(c.bin - m) < Math.abs(a.bin - m) ? c : a);
  const t = bandGeo.today.find(x => x.bin === b.bin);
  const cur = $("#bandcur"); cur.setAttribute("x1", bandGeo.X(b.bin).toFixed(1)); cur.setAttribute("x2", bandGeo.X(b.bin).toFixed(1)); cur.setAttribute("visibility", "visible");
  $("#bandlead").innerHTML = `<b>${mm(b.bin)}</b> 평소 ${f1(b.mean)}분 (±${f1(b.sd)}, 가운데 ${f1(b.p25)}~${f1(b.p75)}분, ${b.n}일)` + (t ? ` · 오늘 <b style="color:${PURPLE}">${f1(t.wait)}분</b>` : "");
}

/* ---------------- ② 요일별 비교 ---------------- */
const WDC = { 1: "#9BD7D5", 2: "#FBE9B7", 3: "#F3B2A4", 4: "#CBC2FB", 5: "#BFE3F7" };   // 요일 5색(히트맵·식단 칩과 같은 램프)
function renderWd(d) {
  const rows = (d && d.weekdays || []).filter(w => w.avg_wait != null);
  if (!setState("wdcard", d && d.state === "ok" && rows.length > 0, d && d.reason)) return;
  const W = 320, H = 150, padT = 30, padB = 36, padL = 26, padR = 8, n = 5;
  // 축은 평균 대기 기준 — 최고 대기(피크)는 평균의 10배가 흔해 같은 축에 두면 막대가 납작해진다(10-13 실데이터 확인). 피크는 막대 위 숫자로
  const max = Math.max(1, ...rows.map(w => w.avg_wait)) * 1.25;
  const Y = v => padT + (1 - v / max) * (H - padT - padB), colW = (W - padL - padR) / n, bw = colW * .5;
  const by = Object.fromEntries(rows.map(w => [w.weekday, w]));
  const tick = max >= 2 ? Math.round(max / 2) : Math.round(max * 5) / 10;
  let s = [0, tick].map(v => `<line x1="${padL}" y1="${Y(v).toFixed(1)}" x2="${W - padR}" y2="${Y(v).toFixed(1)}" stroke="${HAIR}"/>` + txt(padL - 6, Y(v), `${v}분`, { a: "end", size: 8.5 })).join("");
  for (let wd = 1; wd <= 5; wd++) {
    const cx = padL + (wd - .5) * colW, w = by[wd];
    s += `<rect x="${(cx - 14).toFixed(1)}" y="${H - padB + 8}" width="28" height="16" rx="6" fill="${WDC[wd]}"/>` + txt(cx, H - padB + 16, WD[wd], { w: 700, fill: INK, size: 9.5 });
    if (!w) { s += txt(cx, H - padB - 6, "자료 없음", { size: 8 }); continue; }
    const y = Y(w.avg_wait), h = H - padB - y;
    s += `<rect x="${(cx - bw / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(2, h).toFixed(1)}" rx="4" fill="${ramp(SUNSETDARK, w.avg_wait / max)}"/>`;
    s += txt(cx, y - 7, `${f1(w.avg_wait)}분`, { w: 700, fill: INK, size: 9 });
    if (w.peak_wait != null) s += txt(cx, y - 18, `최고 ${f1(w.peak_wait)}`, { size: 8, fill: "#A23A2B" });
    s += txt(cx, H - 6, `${w.days}일${w.served != null ? ` · ${Math.round(w.served)}명` : ""}`, { size: 8 });
  }
  $("#wdsvg").innerHTML = s;
  const top = rows.reduce((a, b) => b.avg_wait > a.avg_wait ? b : a), low = rows.reduce((a, b) => b.avg_wait < a.avg_wait ? b : a);
  $("#wdlead").innerHTML = rows.length > 1 ? `가장 붐비는 요일 <b>${WD[top.weekday]}요일</b> (평균 ${f1(top.avg_wait)}분) · 가장 한산한 요일 <b>${WD[low.weekday]}요일</b> (${f1(low.avg_wait)}분)` : `요일 비교는 2개 요일 이상 쌓이면 뜻이 생깁니다`;
  $("#wdfoot").textContent = `${MEAL_KO[d.meal]} · 최근 ${d.weeks}주 · 막대 = 평균 대기, 위 붉은 숫자 = 최고 대기(하루 피크의 평균), 아래 = 집계 일수 · 식수 추정`;
}

/* ---------------- ③ 일별 추이 ---------------- */
let dailyGeo = null;
function renderDaily(d) {
  const rows = (d && d.daily || []).filter(r => r.avg_wait != null);
  if (!setState("dailycard", d && d.state === "ok" && rows.length > 0, d && d.reason)) { dailyGeo = null; return; }
  const W = 320, H = 150, padT = 10, padB = 18, padL = 26, padR = 30, n = rows.length;
  const max = Math.max(1, ...rows.map(r => r.avg_wait)) * 1.25;        // 축은 평균 기준(피크는 호버 읽기·리드에서) — 요일 카드와 같은 이유
  const served = rows.map(r => r.served).filter(v => v != null), smax = Math.max(1, ...served) * 1.1;
  const X = i => padL + (i + .5) / n * (W - padL - padR), Y = v => padT + (1 - v / max) * (H - padT - padB), YS = v => padT + (1 - v / smax) * (H - padT - padB);
  const bw = Math.max(2, Math.min(14, (W - padL - padR) / n * .6));
  const tick = max >= 2 ? Math.round(max / 2) : Math.round(max * 5) / 10;
  let s = [0, tick].map(v => `<line x1="${padL}" y1="${Y(v).toFixed(1)}" x2="${W - padR}" y2="${Y(v).toFixed(1)}" stroke="${HAIR}"/>` + txt(padL - 6, Y(v), `${v}분`, { a: "end", size: 8.5 })).join("");
  rows.forEach((r, i) => {
    s += `<rect x="${(X(i) - bw / 2).toFixed(1)}" y="${Y(r.avg_wait).toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(2, H - padB - Y(r.avg_wait)).toFixed(1)}" rx="3" fill="${ramp(SUNSETDARK, r.avg_wait / max)}"/>`;
  });
  if (served.length >= 2) {
    const pts = rows.map((r, i) => r.served == null ? null : `${X(i).toFixed(1)},${YS(r.served).toFixed(1)}`).filter(Boolean);
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="#8F877A" stroke-width="1.5" stroke-dasharray="4 3" stroke-linejoin="round"/>`;
    [0, Math.round(smax / 2), Math.round(smax)].forEach(v => { s += txt(W - padR + 6, YS(v), `${v}명`, { a: "start", size: 8.5 }); });
  }
  const step = Math.max(1, Math.ceil(n / 6));
  rows.forEach((r, i) => { if (i % step === 0 || i === n - 1) s += txt(X(i), H - 5, md(r.date), { size: 8.5, fill: WDC[r.weekday] ? "#5E5A52" : INK3 }); });
  s += `<line id="dailycur" x1="0" y1="${padT}" x2="0" y2="${H - padB}" stroke="${MELON}" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/>`;
  $("#dailysvg").innerHTML = s;
  dailyGeo = { rows, X, W, padL, padR, n };
  const last = rows[rows.length - 1], prev = rows.length > 1 ? rows[rows.length - 2] : null;
  const diff = prev ? last.avg_wait - prev.avg_wait : 0;
  $("#dailylead").innerHTML = `마지막 집계 <b>${md(last.date)}(${WD[last.weekday]})</b> 평균 ${f1(last.avg_wait)}분 · 최고 ${f1(last.peak_wait)}분`
    + (last.served != null ? ` · 식수 약 ${last.served}명` : "") + (prev ? ` · 전날 대비 <b>${Math.abs(diff) < 0.05 ? "비슷" : (diff > 0 ? "+" : "−") + f1(Math.abs(diff)) + "분"}</b>` : "");
  const ks = rows.map(r => r.k).filter(v => v != null);
  $("#dailyfoot").textContent = `${MEAL_KO[d.meal]} · 최근 ${d.weeks}주 ${rows.length}일 · 막대 = 평균 대기, 회색 파선 = 식수 추정(오른쪽 눈금) · 막대에 대면 최고 대기·커버리지·K`
    + (ks.length ? ` · 실측 보정 K 중앙값 ${f1(ks.reduce((a, b) => a + b, 0) / ks.length)}` : "");
}
function dailyHover(e) {
  if (!dailyGeo) return;
  const svg = $("#dailysvg"), r = svg.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width * dailyGeo.W;
  const i = Math.min(dailyGeo.n - 1, Math.max(0, Math.floor((x - dailyGeo.padL) / (dailyGeo.W - dailyGeo.padL - dailyGeo.padR) * dailyGeo.n)));
  const row = dailyGeo.rows[i], cur = $("#dailycur");
  cur.setAttribute("x1", dailyGeo.X(i).toFixed(1)); cur.setAttribute("x2", dailyGeo.X(i).toFixed(1)); cur.setAttribute("visibility", "visible");
  $("#dailylead").innerHTML = `<b>${md(row.date)}(${WD[row.weekday]})</b> 평균 ${f1(row.avg_wait)}분 · 최고 ${f1(row.peak_wait)}분${row.peak_at ? ` (${row.peak_at.slice(11, 16)})` : ""}`
    + (row.served != null ? ` · 식수 약 ${row.served}명` : "") + (row.coverage_pct != null ? ` · 커버리지 ${Math.round(row.coverage_pct)}%` : "") + (row.k != null ? ` · K ${f1(row.k)}` : "");
}

/* ---------------- ④ 영양 인사이트 ---------------- */
const MACRO = { carb: [55, 65, "탄수화물"], protein: [7, 20, "단백질"], fat: [15, 30, "지방"] };   // 에너지 적정비율(현행 별표3, 2021) — CLAUDE.md §2
function renderNut(d) {
  const days = (d && d.days || []).filter(r => r.energy_pct != null);
  if (!setState("nutstatcard", d && d.state === "ok" && days.length > 0, d && d.reason)) return;
  // (a) 에너지 충족률 — 90~110% 적정 띠, 밖은 멜론 점
  const W = 320, H = 96, padT = 8, padB = 16, padL = 30, padR = 8, n = days.length;
  const vals = days.map(r => r.energy_pct), lo = Math.min(80, ...vals) - 5, hi = Math.max(120, ...vals) + 5;
  const X = i => n > 1 ? padL + i / (n - 1) * (W - padL - padR) : W / 2, Y = v => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  let s = `<rect x="${padL}" y="${Y(110).toFixed(1)}" width="${W - padL - padR}" height="${(Y(90) - Y(110)).toFixed(1)}" fill="${TEAL}" fill-opacity=".12" rx="3"/>`
    + `<line x1="${padL}" y1="${Y(100).toFixed(1)}" x2="${W - padR}" y2="${Y(100).toFixed(1)}" stroke="#B9B1A0" stroke-dasharray="4 4"/>`
    + txt(padL - 5, Y(110), "110%", { a: "end", size: 8 }) + txt(padL - 5, Y(90), "90%", { a: "end", size: 8 })
    + `<polyline points="${vals.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ")}" fill="none" stroke="${TEAL}" stroke-width="1.6" stroke-linejoin="round"/>`
    + vals.map((v, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${i === n - 1 ? 3.6 : 2.6}" fill="${v < 90 || v > 110 ? MELON : TEAL}" stroke="${PAPER}" stroke-width="1.2"/>`).join("")
    + txt(X(0), H - 4, md(days[0].date), { a: "start", size: 8.5 }) + txt(X(n - 1), H - 4, md(days[n - 1].date), { a: "end", size: 8.5 });
  $("#nutsvg").innerHTML = s;
  // (b) 탄·단·지 — 최근 평균이 적정 범위 안인가(게이지)
  const avg = k => { const v = days.map(r => r[k]).filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const m = { carb: avg("carb_ratio"), protein: avg("protein_ratio"), fat: avg("fat_ratio") };
  $("#macrog").innerHTML = Object.entries(MACRO).map(([k, [a, b, name]]) => {
    const v = m[k], okr = v != null && v >= a && v <= b, pct = x => Math.min(100, Math.max(0, x / 80 * 100));
    return `<div class="gauge${okr ? "" : " off"}"><span>${name}</span><div class="track"><i class="band" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%"></i>`
      + (v == null ? "" : `<i class="pin" style="left:${pct(v)}%"></i>`) + `</div><b>${v == null ? "—" : Math.round(v) + "%"}</b><small>${a}~${b}%</small></div>`;
  }).join("");
  // (c) 미량영양소 MAR + 요약
  const mars = days.map(r => r.mar).filter(v => v != null), okDays = days.filter(r => r.macro_ok).length;
  const eavg = vals.reduce((a, b) => a + b, 0) / n, inBand = vals.filter(v => v >= 90 && v <= 110).length;
  $("#nutlead").innerHTML = `최근 ${n}일 에너지 충족률 평균 <b>${Math.round(eavg)}%</b> (적정 90~110% 안 ${inBand}일) · 탄·단·지 적정비율 충족 <b>${okDays}일</b>`
    + (mars.length ? ` · 미량영양소 평균 <b>${Math.round(mars.reduce((a, b) => a + b, 0) / mars.length)}%</b>` : "");
  $("#nutfoot").textContent = `${MEAL_KO[d.meal]} · ${d.basis === "nutrition_days" ? "영양 이력(집계)" : "이번 주 식단 캐시"} · 한 끼 권장량 대비 '제공 영양' 기준(섭취량 아님) · 미량영양소는 NEIS 6종만 · 적정비율은 현행(2021) 기준`;
}

/* ---------------- ⑤ 줄이 길어지는 메뉴 ---------------- */
function renderMenu(d) {
  const items = (d && d.menus || []);
  if (!setState("menuwaitcard", d && d.state === "ok" && items.length > 0, d && (d.reason || "2일 이상 나온 메뉴가 아직 없다"))) return;
  const max = Math.max(1, ...items.map(m => m.peak_wait)), base = d.menu_base;
  $("#menuwaitlist").innerHTML = items.map((m, i) =>
    `<li style="--p:${Math.round(m.peak_wait / max * 100)}%"><i>${i + 1}</i><span>${esc(m.menu)}<small> · ${m.n_days}일</small></span>`
    + `<b>${f1(m.peak_wait)}분${base ? `<small> ×${(m.peak_wait / base).toFixed(1)}</small>` : ""}</b></li>`).join("");
  $("#menuwaitlead").innerHTML = `<b>${esc(items[0].menu)}</b>가 나온 날 최고 대기가 가장 길었습니다 (평균 ${f1(items[0].peak_wait)}분${base ? `, 기준 ${f1(base)}분` : ""})`;
  $("#menuwaitfoot").textContent = `${MEAL_KO[d.meal]} · 메뉴가 나온 날들의 '하루 최고 대기' 평균 · 2일 이상 나온 메뉴만 · ×배수는 목록 중앙값 대비 · 인기 메뉴일수록 줄이 길어지는 경향의 근거`;
}

/* ---------------- ⑥ 시각별 황금·병목 ---------------- */
function renderEv(d) {
  const rows = (d && d.events || []);
  if (!setState("evcard", d && d.state === "ok" && rows.length > 0, d && (d.reason || "황금·병목 구간이 아직 없다"))) return;
  const W = 320, H = 150, padL = 26, padR = 8, padT = 8, padB = 18, lo = d.window?.lo ?? rows[0].bin, hi = d.window?.hi ?? rows[rows.length - 1].bin + 5;
  const gmax = Math.max(1, ...rows.map(r => r.golden_min)), bmax = Math.max(1, ...rows.map(r => r.bottleneck_min)), top = Math.max(gmax, bmax);
  const mid = padT + (H - padT - padB) * .5, half = (H - padT - padB) / 2 - 4;
  const X = m => padL + (m - lo) / (hi - lo) * (W - padL - padR), bw = Math.max(2, (W - padL - padR) / ((hi - lo) / 5) - 1);
  let s = `<line x1="${padL}" y1="${mid.toFixed(1)}" x2="${W - padR}" y2="${mid.toFixed(1)}" stroke="${HAIR}"/>` + txt(padL - 5, mid - half / 2, "황금", { a: "end", size: 8, fill: "#0C6D6A" }) + txt(padL - 5, mid + half / 2, "병목", { a: "end", size: 8, fill: "#A23A2B" });
  rows.forEach(r => {
    const x = X(r.bin);
    if (r.golden_min) s += `<rect x="${x.toFixed(1)}" y="${(mid - r.golden_min / top * half).toFixed(1)}" width="${bw.toFixed(1)}" height="${(r.golden_min / top * half).toFixed(1)}" fill="#9BD7D5" rx="2"/>`;
    if (r.bottleneck_min) s += `<rect x="${x.toFixed(1)}" y="${mid.toFixed(1)}" width="${bw.toFixed(1)}" height="${(r.bottleneck_min / top * half).toFixed(1)}" fill="#F3B2A4" rx="2"/>`;
  });
  const m2 = Math.round((lo + hi) / 2 / 5) * 5;
  s += txt(X(lo), H - 5, mm(lo), { a: "start" }) + txt(X(m2), H - 5, mm(m2), { w: 700, fill: "#5E5A52" }) + txt(X(hi), H - 5, mm(hi), { a: "end" });
  $("#evsvg").innerHTML = s;
  const g = rows.reduce((a, b) => b.golden_min > a.golden_min ? b : a), b = rows.reduce((a, c) => c.bottleneck_min > a.bottleneck_min ? c : a);
  $("#evlead").innerHTML = (g.golden_min ? `황금 구간이 가장 자주 열린 시각 <b>${mm(g.bin)}</b> (${Math.round(g.golden_min)}분 누적)` : "황금 구간 없음")
    + (b.bottleneck_min ? ` · 병목이 가장 잦은 시각 <b>${mm(b.bin)}</b> (${Math.round(b.bottleneck_min)}분)` : "");
  $("#evfoot").textContent = `${MEAL_KO[d.meal]} · 최근 ${d.weeks}주 · 위 = 황금(대기 3분 이하가 5분 넘게) · 아래 = 병목(줄 5명↑인데 배식 정체) 시작 시각별 누적 분 · 시차 배식 설계의 재료`;
}

/* ---------------- 공통: 토글·수신·폴링 ---------------- */
const RENDER = { bandcard: renderBand, wdcard: renderWd, dailycard: renderDaily, nutstatcard: renderNut, menuwaitcard: renderMenu, evcard: renderEv };
const CARD_ID = { band: "bandcard", wd: "wdcard", daily: "dailycard", nut: "nutstatcard", menu: "menuwaitcard", ev: "evcard" };
const CARD_KEY = { band: "stats", wd: "stats", daily: "stats", nut: "nutrition", menu: "stats", ev: "stats" };
const TOUCHED = {};

function showCard(card) {
  const d = INS[SEL[card]][CARD_KEY[card]];
  RENDER[CARD_ID[card]](d || { state: "no_data", reason: "불러오는 중" });
}
function setSeg(card, m) {
  SEL[card] = m;
  $(`#${card}seg`)?.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b.dataset.meal === m));
}
export function followMeal(m) {                 // 끼니 경계(14시)에서 손대지 않은 카드만 따라간다 — wait.js 와 같은 규칙
  CARDS.forEach(c => { if (!TOUCHED[c] && SEL[c] !== m) { setSeg(c, m); showCard(c); } });
}

async function load(force) {
  const q = m => Promise.all([jSoft(`/api/insight/stats?weeks=${WEEKS}&meal=${m}`), jSoft(`/api/insight/nutrition?weeks=${Math.max(8, WEEKS)}&meal=${m}`)]);
  const [[ls, ln], [ds, dn]] = await Promise.all([q("lunch"), q("dinner")]);
  INS.lunch = { stats: ls, nutrition: ln }; INS.dinner = { stats: ds, nutrition: dn };
  CARDS.forEach(showCard);
}

export const screen = {
  mount() {
    const m = defaultMeal();
    CARDS.forEach(c => { SEL[c] = m; const el = $(`#${c}seg`); if (el) mealSeg(el, m, v => { TOUCHED[c] = true; SEL[c] = v; showCard(c); }); });
    const rb = $("#statsrange");
    rb.addEventListener("click", e => {
      const b = e.target.closest("button[data-weeks]"); if (!b || +b.dataset.weeks === WEEKS) return;
      WEEKS = +b.dataset.weeks; rb.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b));
      load(true);
    });
    const hover = (id, fn, back) => { const el = $(id); el.addEventListener("pointermove", fn); el.addEventListener("pointerleave", back); };
    hover("#bandsvg", bandHover, () => { $("#bandcur")?.setAttribute("visibility", "hidden"); showCard("band"); });
    hover("#dailysvg", dailyHover, () => { $("#dailycur")?.setAttribute("visibility", "hidden"); showCard("daily"); });
  },
  every: 5 * 60000,                             // 집계는 하루 1~2회 — 5분이면 충분(오늘 실황 선만 움직인다)
  async poll() { followMeal(defaultMeal()); await load(false); },   // 14시 경계에서 손대지 않은 토글은 석식으로(wait.js 와 같은 규칙)
  render(cardId, data) { RENDER[cardId]?.(data); },
};

/* 주간식단 화면 — 이번 주 식단(요일 컬럼). meal.json 이 이미 월~금을 통째로 담고 있다. 오늘급식과 같은 응답을 쓴다(loadMeal 이 한 번 받아 둘 다 그린다).
   아래 인사이트 카드: 주간 영양 추이(kpi 3타일 + 스파크라인) · 메뉴 인기 TOP5(순위 목록). 집계에서 오므로 30분마다 */
import { $, jSoft, esc, WD, setState } from "./core.js";
import { splitAllergy, loadMeal } from "./today.js";

export function renderWeek(m) {
  const card = $("#weekcard"), week = (m.week || []).filter(d => d.menu && d.menu.length);
  card.hidden = week.length < 2;
  if (card.hidden) return;
  const n = new Date();                              // 오늘은 브라우저 시계로 정한다 — meal.json 은 05:40 캐시라 today 가 비는 날이 있다
  const today = `${n.getFullYear()}${String(n.getMonth() + 1).padStart(2, "0")}${String(n.getDate()).padStart(2, "0")}`;
  $("#weekgrid").innerHTML = week.map(d => {
    const dd = new Date(+d.date.slice(0, 4), +d.date.slice(4, 6) - 1, +d.date.slice(6, 8));
    const when = d.date === today ? "today" : d.date < today ? "past" : "future";
    const main = splitAllergy(d.menu[0]).name;
    // 램프는 인덱스가 아니라 실제 요일에 건다 — 주가 화요일부터 시작해도 색이 밀리지 않게
    return `<div data-wd="${dd.getDay()}" data-when="${when}">`
      + `<span class="d">${WD[dd.getDay()]}</span><span class="n">${dd.getDate()}</span>`
      + `<span class="m">${esc(main)}</span>`
      + `<span class="k">외 ${d.menu.length - 1}가지` + (d.kcal ? `<br>${Math.round(d.kcal)} kcal` : "") + "</span></div>";
  }).join("");
  const w = m.week_avg || {};
  $("#weekavg").innerHTML = w.energy_pct == null ? ""
    : `이번 주 평균 에너지 충족 <b style="color:var(--ink2)">${w.energy_pct}%</b>`
      + (w.mar == null ? "" : ` · 미량영양소 <b style="color:var(--ink2)">${w.mar}%</b>`);
}

/* ---------------- 인사이트 카드 ---------------- */
const md = w => `${+w.slice(5, 7)}/${+w.slice(8, 10)}`;   // "2026-08-24" → "8/24"

function renderNutrition(d) {
  const weeks = (d.weeks || []).filter(w => w.energy_pct != null);
  if (!setState("nutricard", d.state === "ok" && weeks.length > 0, d.reason)) return;
  const last = weeks[weeks.length - 1];
  const flag = last.energy_pct > 110 ? "많음" : last.energy_pct < 90 ? "적음" : "";
  $("#nutrikpi").innerHTML =
    `<div><em>01</em><b>${last.energy_pct}%</b><span>에너지 충족</span><span class="flag">${flag}</span></div>`
    + `<div><em>02</em><b>${last.macro_ok_days}/${last.days}</b><span>적정비율 충족 일</span></div>`
    + `<div><em>03</em><b>${last.mar ?? "—"}${last.mar == null ? "" : "%"}</b><span>미량영양소</span></div>`;
  // 스파크라인 — 주별 에너지 충족률. 100% 기준선은 회색 파선
  const W = 320, H = 64, pad = 6;
  const vals = weeks.map(w => w.energy_pct), lo = Math.min(90, ...vals) - 5, hi = Math.max(110, ...vals) + 5;
  const X = i => weeks.length > 1 ? pad + i / (weeks.length - 1) * (W - 2 * pad) : W / 2;
  const Y = v => pad + (1 - (v - lo) / (hi - lo)) * (H - 2 * pad);
  const path = vals.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  $("#nutrispark").innerHTML =
    `<line x1="${pad}" y1="${Y(100).toFixed(1)}" x2="${W - pad}" y2="${Y(100).toFixed(1)}" stroke="#B9B1A0" stroke-width="1" stroke-dasharray="4 4"/>`
    + `<path d="${path}" fill="none" stroke="#129793" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`
    + vals.map((v, i) => `<circle cx="${X(i).toFixed(1)}" cy="${Y(v).toFixed(1)}" r="${i === vals.length - 1 ? 4 : 2.5}" fill="#129793" stroke="#FFFCF6" stroke-width="1.5"/>`).join("");
  $("#nutriaxis").innerHTML = `<span>${md(weeks[0].week)} 주</span><span>100% 기준</span><span>${md(last.week)} 주</span>`;
  $("#nutrifoot").textContent = (d.basis === "nutrition_days" ? `최근 ${weeks.length}주 이력` : "이번 주 식단 캐시(집계 전)") + " · 값은 주별 평균";
}

function renderTop(d) {
  const items = d.items || [];
  if (!setState("topcard", d.state === "ok" && items.length > 0, d.reason)) return;
  const top = Math.max(1, ...items.map(x => x.popularity || 0));
  $("#toplead").innerHTML = `<b>${esc(items[0].menu)}</b> 날에 줄이 가장 빨리 늘었습니다`;
  $("#toplist").innerHTML = items.map((x, i) =>
    `<li style="--p:${Math.round(100 * (x.popularity || 0) / top)}%"><i>${i + 1}</i><span>${esc(x.menu)}</span><small>${x.n_days}일</small><b>${x.popularity}</b></li>`).join("");
  $("#topfoot").textContent = `인기 지수 = 줄이 느는 속도와 최대 대기의 평균 대비(100 = 보통) · ${d.min_days}일 이상 나온 메뉴만`;
}

const RENDER = { nutricard: renderNutrition, topcard: renderTop };

export const screen = {
  every: 300000,
  poll: loadMeal,                                      // 식단은 5분마다 다시 받는다(05:40 캐시가 바뀐 뒤 화면에 머물러도 따라온다)
  async slow() {
    const [n, t] = await Promise.all([jSoft("/api/insight/nutrition?weeks=8"), jSoft("/api/insight/menus?n=5")]);
    renderNutrition(n); renderTop(t);
  },
  render(cardId, data) { RENDER[cardId]?.(data); },
};

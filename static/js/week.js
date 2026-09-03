/* 주간식단 화면 — 이번 주 식단(요일 컬럼). meal.json 이 이미 월~금을 통째로 담고 있다. 오늘급식과 같은 응답을 쓴다 */
import { $, S, esc } from "./core.js";
import { splitAllergy, loadMeal } from "./today.js";

const WD = "일월화수목금토";
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

export const screen = { every: 300000, poll: () => S.meal ? renderWeek(S.meal) : loadMeal() };

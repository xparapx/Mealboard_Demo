/* 오늘급식 화면 — 오늘 중식(메뉴·알레르기·영양 3칸·영양소 칩) + 잔반 탄소. 진입 시 1회 + 5분마다 */
import { $, j, S, esc } from "./core.js";
import { RDBU, luma, ramp } from "./colors.js";
import { renderWeek } from "./week.js";

/* ---------------- ① 알레르기 ----------------
   식약처 고시 19종. NEIS 는 DDISH_NM 끝에 "(5.6.10.13)" 형태로 붙여 보낸다 */
export const ALLERGENS = { 1: "난류", 2: "우유", 3: "메밀", 4: "땅콩", 5: "대두", 6: "밀", 7: "고등어",
  8: "게", 9: "새우", 10: "돼지고기", 11: "복숭아", 12: "토마토", 13: "아황산류", 14: "호두",
  15: "닭고기", 16: "쇠고기", 17: "오징어", 18: "조개류", 19: "잣" };
const MY_KEY = "mb_allergy";
const loadMy = () => { try { return new Set(JSON.parse(localStorage.getItem(MY_KEY)) || []); } catch { return new Set(); } };
let MY = loadMy();

export function splitAllergy(raw) {
  // 괄호로 묶였거나, 끝에 점으로 이어진 숫자가 둘 이상일 때만 뗀다 ("우유200" 같은 이름을 자르지 않도록)
  const m = raw.match(/\s*[(（]\s*([\d.,\s]+)\s*[)）]\s*$/) || raw.match(/\s+(\d{1,2}(?:\.\d{1,2})+)\.?\s*$/);
  if (!m) return { name: raw.trim(), codes: [] };
  const codes = [...new Set(m[1].split(/\D+/).filter(Boolean).map(Number))].filter(n => n >= 1 && n <= 19);
  return { name: raw.slice(0, m.index).trim() || raw.trim(), codes: codes.sort((a, b) => a - b) };
}

function renderPicker() {
  $("#pick").innerHTML = Object.entries(ALLERGENS).map(([n, label]) =>
    `<button type="button" data-n="${n}" aria-pressed="${MY.has(+n)}">${label}</button>`).join("");
  $("#pick").querySelectorAll("button").forEach(b => b.onclick = () => {
    const n = +b.dataset.n;
    MY.has(n) ? MY.delete(n) : MY.add(n);
    try { localStorage.setItem(MY_KEY, JSON.stringify([...MY])); } catch {}
    if (S.meal) renderMeal(S.meal);
  });
  const names = [...MY].sort((a, b) => a - b).map(n => ALLERGENS[n]);
  $("#mysummary").textContent = names.length ? names.join(" · ") : "없음";
}

/* ---------------- 급식 ---------------- */
function bandOf(x) {
  if (x.band === "부족") return "short";
  const d = x.pct - 100;
  return d >= 10 ? "hi" : d >= 0 ? "mid" : "lo";
}
const shortLabel = s => s.replace(/\s*\(.*\)\s*$/, "");   // "비타민A (㎍RAE)" → "비타민A"
/* 영양소 칩 색 — plotly "RdBu"(09-04 사용자 결정): 권장섭취량 100% 가 가운데 흰색, 50% 이하는 진한 빨강, 150% 이상은 진한 파랑. 글자는 밝기로 검/흰 */
function chipStyle(pct) {
  const t = Math.min(1, Math.max(0, ((pct ?? 100) - 50) / 100));
  const bg = ramp(RDBU, t);
  return `background:${bg};color:${luma(bg) > .6 ? "#33312D" : "#FFFCF6"}`;
}

let inflight = null;
export function loadMeal() {                          // 진행 중이면 그 약속을 나눠 준다 — 두 화면이 동시에 불러도 요청은 하나
  return inflight ??= j("/api/meal").then(m => { S.meal = m; renderMeal(m); return m; }).finally(() => { inflight = null; });
}

export function renderMeal(m) {
  const menu = $("#menu");
  renderWeek(m);                                     // 주말·공휴일에도 "그럼 언제 뭐가 나오나"는 답할 수 있다
  if (m.state !== "ok" || !m.today) {
    // state 는 ok 인데 today 만 없는 날 = 주말·공휴일. 받아오지 못한 것과 구별해서 말한다
    menu.innerHTML = `<li class="main">${m.state === "no_meal" ? "이번 주 급식 정보가 없습니다"
      : m.state === "ok" ? "오늘은 급식이 없습니다" : "급식 정보를 아직 받지 못했습니다"}</li>`;
    ["#allergybox", "#carbonsec", "#microlab", "#awarn"].forEach(s => $(s).hidden = true);
    $("#allergens").innerHTML = ""; $("#micro").innerHTML = ""; $("#dinnermenu").innerHTML = ""; $("#lunchkcal").textContent = ""; $("#dinnerkcal").textContent = "";
    ["#energy", "#ratio", "#mar"].forEach(s => $(s).textContent = "—");
    ["#energyflag", "#marflag"].forEach(s => $(s).textContent = "");
    return;
  }
  // 메뉴 한 열 — 대표 메뉴는 굵게, 내 알레르기가 든 메뉴는 멜론 바탕 + 번호 굵게. 번호 나열은 그대로 두되(참고용) 이름 옆 태그가 먼저 눈에 들어온다
  const listOf = (items) => items.map((d, i) => {
    const hit = d.codes.some(c => MY.has(c));
    const codes = d.codes.map(c => MY.has(c) ? `<b>${c}</b>` : c).join("·");
    return `<li class="${i === 0 ? "main" : ""}${hit ? " hit" : ""}"><span>${esc(d.name)}</span>`
      + (hit ? `<span class="tag">내 알레르기</span>` : "")
      + (codes ? `<span class="codes">${codes}</span>` : "") + "</li>";
  }).join("");
  const dishes = m.today.menu.map(splitAllergy);
  menu.innerHTML = listOf(dishes);
  $("#lunchkcal").textContent = m.today.kcal ? `${Math.round(m.today.kcal)} kcal` : "";
  // 석식(09-11) — 없는 날은 열을 비우지 않고 '석식 없음' 으로 둔다(2열 리듬 유지)
  const dn = m.today.dinner, dinner = dn && dn.menu?.length ? dn.menu.map(splitAllergy) : [];
  $("#dinnermenu").innerHTML = dinner.length ? listOf(dinner) : `<li class="none">석식 없음</li>`;
  $("#dinnerkcal").textContent = dinner.length && dn.kcal ? `${Math.round(dn.kcal)} kcal` : "";
  $("#dinnercol").classList.toggle("off", !dinner.length);

  // 알레르기 요약 — 중식·석식을 합쳐 오늘 나오는 번호 전체. 내 것을 앞에 두고, 걸리면 위에 한 줄로 먼저 알린다
  const all = [...dishes, ...dinner];
  const today = [...new Set(all.flatMap(d => d.codes))].sort((a, b) => (MY.has(b) - MY.has(a)) || a - b);
  const mine = today.filter(c => MY.has(c));
  $("#allergens").innerHTML = today.map(c =>
    `<span class="${MY.has(c) ? "on" : ""}">${c} ${ALLERGENS[c]}</span>`).join("");
  const hitNames = all.filter(d => d.codes.some(c => MY.has(c))).map(d => d.name);
  $("#awarn").hidden = !mine.length;
  if (mine.length) $("#awarn").innerHTML = `오늘 <b>${mine.map(c => ALLERGENS[c]).join(" · ")}</b> 이(가) 든 메뉴 ${hitNames.length}개: ${esc(hitNames.join(", "))}`;
  $("#allergybox").hidden = false;
  renderPicker();

  const a = m.today.assess;
  $("#energy").textContent = a.energy_pct == null ? "—" : a.energy_pct + "%";
  $("#energyflag").textContent = a.energy_pct == null ? "" : a.energy_pct > 110 ? "많음" : a.energy_pct < 90 ? "적음" : "";
  $("#ratio").textContent = a.macro_ratio_ok ? "적정" : "범위 밖";
  $("#ratio").title = `탄 ${a.macro_ratio.carb} · 단 ${a.macro_ratio.protein} · 지 ${a.macro_ratio.fat} %`;
  $("#mar").textContent = a.mar == null ? "—" : a.mar + "%";
  const short = a.micro.filter(x => x.band === "부족").length;
  $("#marflag").textContent = short ? `부족 ${short}` : "";

  $("#microlab").hidden = !a.micro.length;
  $("#micro").innerHTML = a.micro.map(x => {
    const d = x.pct - 100, band = bandOf(x);
    const tag = band === "short" ? "<em>부족</em>" : x.band === "과다" ? "<em>과다</em>" : "";
    return `<div data-band="${band}"><div class="v" style="${chipStyle(x.pct)}">${d >= 0 ? "+" : "−"}${Math.abs(d)}%${tag}</div>`
         + `<div class="n" title="${esc(x.label)}">${esc(shortLabel(x.label))}</div></div>`;
  }).join("");

  renderCarbon(m);
}

/* ⑧ 잔반 탄소 — 계수는 /api/meal 의 carbon_std(= data/carbon_std.json) */
function renderCarbon(m) {
  const c = m.today && m.today.carbon, cs = m.carbon_std || {};
  $("#carbonsec").hidden = !c;
  if (!c) return;
  $("#co2").textContent = c.kgco2e.toFixed(1);
  $("#co2unit").textContent = `kg CO₂e · 1인분 약 ${c.portion_g} g 기준`;
  $("#vsworld").textContent = c.pct_world + "%";
  $("#vskorea").textContent = c.pct_korea + "%";
  $("#carbonnote").textContent = `1인분 무게 = kcal ÷ 에너지밀도 환산(NEIS 는 g 미제공) · 배출계수: ${cs.ef_source}`
    + ` · 1인 평균: ${cs.capita_source} · 승용차 환산 ${c.car_km} km`;
}

export const screen = { every: 300000, poll: loadMeal };

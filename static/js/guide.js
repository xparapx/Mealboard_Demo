/* 앱 안내 화면(10-18, 심사위원 구동 경로 N3) — 서버가 /api/status.guide 를 줄 때만 core.addGuide 가 이 모듈을 읽어 일곱 번째 탭으로 붙인다.
   ① 이 앱은: 핵심 기능 셋(점검서 N8 — 대기시간 · 밀집도 · 영양·탄소·리포트) + '자동 시연 시작'
   ② 자동 시연: 여섯 화면을 차례로 돌며 카드 하나를 밝게 남기고 말풍선으로 설명한다(약 2분, 자동 진행·일시정지·이전·다음·ESC).
      시연 대본(STEPS)이 곧 제출 영상(N7)의 대본 — 이 화면을 녹화하면 영상이 된다. 급식실 실사는 어디에도 없다(공개 화면·평면도·숫자만).
   ③ 시연 영상: /media/demo.mp4 가 있으면 인앱 재생(없으면 단추를 숨긴다)
   ④ 숫자는 이렇게 나옵니다(투명성 1장, 제안서 P12) · 심사위원 안내(모의 데이터·가상 시계·구동 명령) */
import { $, $$, esc, now, REDUCE, WD, hhmm } from "./core.js";

const FEATURES = [
  { n: "01", t: "예상 대기시간", d: "카메라가 센 대기 인원 L 을 배식 속도 λ 로 나눈 W = L ÷ λ. 줄에 선 사람의 진입→통과 시간을 스스로 재어 보정합니다." },
  { n: "02", t: "급식실 밀집도", d: "평면도 위 익명 마커와 육각 타일 히트맵. 영상이 아니라 그 순간의 인원수만 — 개별 위치 이력은 저장하지 않습니다." },
  { n: "03", t: "영양 · 탄소 · 리포트", d: "NEIS 식단에서 에너지 충족률·적정비율·미량영양소(MAR)·알레르기·잔반 탄소를 내고, 아침 예보·점심 결산을 씁니다." },
];
const HOW = [
  ["세기만 한다", "카메라 프레임은 메모리에서 사람 수만 센 뒤 즉시 버립니다. 저장·전송 0 — 개인정보 보호법 §25①6(통계 목적 일시 처리) 설계입니다."],
  ["W = L ÷ λ", "L 은 화면 안 대기 인원, λ 는 최근 3분 동안 배식대 측정선을 지난 인원(명/분). Little's law 로 지금 줄 서면 기다릴 시간을 냅니다."],
  ["스스로 보정", "진입·통과 누적곡선(FIFO)으로 실제 대기를 복원해 보정계수 K 를 만들고, 수동 실측과 대조한 하한을 둡니다 — 과소 표시를 막습니다."],
  ["판정은 보수적으로", "25초·90초 중앙값으로 널뜀을 지우고, '여유'는 30초 이하일 때만, '혼잡'은 오늘 범위의 상위 ⅓ 입니다."],
  ["하루 한 번 집계", "급식이 끝나면 하루치를 집계해 요일×시각 히트맵·황금 구간·병목·예보·메뉴별 대기를 만들고, 규칙 문장(또는 로컬 LLM)으로 리포트를 씁니다."],
];
/* 자동 시연 대본 — screen(화면) · sel(밝게 남길 카드) · title · text · ms(머무는 시간) */
const STEPS = [
  { screen: "wait", sel: "#hero", title: "지금 줄을 서면", text: "큰 숫자가 예상 대기입니다. 카메라가 센 대기 인원 L 과 배식 속도 λ(명/분)로 W = L ÷ λ 를 내고, 여유·보통·혼잡을 판정합니다. 도착 예상 시각도 함께.", ms: 9000 },
  { screen: "wait", sel: "#trend", title: "최근 30분 추이와 평소", text: "오늘 막대 위에 같은 요일 평소 곡선(파선)을 겹칩니다. 한 줄 결론 — 지금이 평소보다 긴지 짧은지.", ms: 7000 },
  { screen: "wait", sel: "#heatcard", title: "요일 · 시각별 평소 대기", text: "지난 4주 집계. 어두울수록 오래 기다린 시각이고, 오늘 행은 실시간으로 채워집니다. 점멸하는 칸이 지금.", ms: 8000 },
  { screen: "wait", sel: "#forecastcard", title: "예보와 황금 구간", text: "같은 요일 평소 곡선에 오늘 메뉴의 인기 보정을 곱해 피크 시각과 '3분 이하' 황금 구간을 미리 알립니다.", ms: 7000 },
  { screen: "wait", sel: "#bottlecard", title: "병목 로그", text: "줄이 5명 넘게 서 있는데 배식이 멈췄거나 평소의 절반 아래로 느려진 구간 — 급식 운영진이 원인을 되짚는 기록입니다.", ms: 7000 },
  { screen: "wait", sel: "#qualitycard", title: "측정 품질을 숨기지 않습니다", text: "커버리지·표본 수·빈 시간·산출 불가 시간을 그대로 보입니다. 정확도는 주장이 아니라 수치로.", ms: 6500 },
  { screen: "room", sel: "#plancard", title: "실시간뷰 — 영상이 아닙니다", text: "평면도 위 노란 점은 익명 위치 마커. 5초마다 그 순간만 바뀌고 이력은 어디에도 남지 않습니다.", ms: 8000 },
  { screen: "room", sel: "#zonecard", title: "최근 10분 밀집도", text: "육각 타일별 인원수 합계로 어디에 사람이 모였는지. 구역별 점유율 칩과 함께.", ms: 6500 },
  { screen: "room", sel: "#typcard", title: "평소 밀집도 · 최근 7일", text: "누적 타일에서 진한 묶음 ①②③ 을 찾아 '늘 모이는 자리'를 가리킵니다 — 좌석·동선 조정의 근거.", ms: 7000 },
  { screen: "room", sel: "#reportcard", title: "오늘 리포트", text: "집계 숫자만 받아 규칙 문장(또는 로컬 LLM)이 아침 예보·점심 결산을 씁니다. 숫자는 입력에 있는 것만 — 검증기가 지킵니다.", ms: 7500 },
  { screen: "stats", sel: "#bandcard", title: "통계 — 시간대별 분포", text: "4·8·12주 집계로 시각별 평균과 변동 폭(P25~P75·±1σ), 그 위에 오늘 선. 급식 시정표를 바꿀 때 보는 그림입니다.", ms: 7500 },
  { screen: "stats", sel: "#menuwaitcard", title: "줄이 길어지는 메뉴", text: "메뉴별 최고 대기를 모아 인기 메뉴 날의 운영 대비(배식 인력·시차 배식)에 쓸 수 있습니다.", ms: 6500 },
  { screen: "week", sel: "#weekcard", title: "주간식단", text: "NEIS 급식 API 캐시. 요일 컬럼에 중식·석식, 오늘은 색과 숨쉬기로 표시. 주간 영양 추이와 메뉴 빈도도 아래에.", ms: 6500 },
  { screen: "today", sel: "#mealcard", title: "오늘급식 — 영양 · 알레르기 · 탄소", text: "에너지 충족률·탄단지 적정비율·미량영양소 세 지표, 내 알레르기 경고(기기에만 저장), 다 남기면 나오는 탄소 추정.", ms: 8000 },
  { screen: "news", sel: "#newscard", title: "이슈피드(부가)", text: "기후·환경과 기술·과학 소식을 요약해 급식실 대기 중에 읽을거리로. 핵심 기능은 앞의 셋입니다.", ms: 5000 },
  { screen: "guide", sel: "#guidehow", title: "숫자는 이렇게 나옵니다", text: "세기만 한다 → W = L ÷ λ → 스스로 보정 → 보수적 판정 → 하루 집계. 시연을 마칩니다 — 화면은 자유롭게 눌러 보세요.", ms: 9000 },
];

/* ---------------- 화면 글 ---------------- */
let DEMO = null;
function fillIntro() {
  $("#guidelead").textContent = "학교 급식실 입구의 라즈베리파이 한 대가 줄 선 사람 수를 세어 예상 대기시간을 알리고, 급식 영양·탄소·운영 리포트까지 한 화면에 모았습니다. "
    + "학생은 QR 로, 영양교사·운영진은 같은 주소의 통계·리포트로 봅니다.";
  $("#guidefeat").innerHTML = FEATURES.map(f => `<div><em>${f.n}</em><b>${esc(f.t)}</b><span>${esc(f.d)}</span></div>`).join("");
  $("#guidesteps").innerHTML = HOW.map(([t, d]) => `<li><b>${esc(t)}</b><span>${esc(d)}</span></li>`).join("");
  $("#guiderunbody").innerHTML =
    `<p><b>구동</b> 저장소 루트에서 <code>uv sync</code> 뒤 <code>uv run python -m jobs.demo</code> 한 줄 — 모의 데이터 8주치를 만들고 이 화면을 띄웁니다(포트 8800, 운영 데이터와 분리된 <code>data/demo/</code>).</p>`
    + `<p><b>핵심 흐름 셋</b> ① 대기시간(히어로·추이·히트맵·예보·병목·품질) → ② 실시간뷰·통계(밀집도·분포·메뉴별 대기) → ③ 오늘급식·리포트(영양·알레르기·탄소·결산).</p>`
    + `<p><b>실제 운영</b> <a href="https://kjhs-meal.com" target="_blank" rel="noopener">kjhs-meal.com</a> — 급식 시간(11:20~13:40 · 석식)에만 카메라 실측이 흐르고, 창 밖에는 '급식 시간이 아닙니다' 를 띄웁니다.</p>`;
}
function fillDemoNote() {
  const el = $("#guidedemo");
  if (!DEMO) { el.textContent = "지금 보시는 값은 실제 운영 데이터입니다."; return; }
  const t = now();
  el.innerHTML = `지금 보시는 값은 <b>모의 데이터</b>입니다 — 8주치 가상 급식 기록을 같은 규칙으로 만들어 실제 집계·리포트 코드가 그대로 처리했습니다. `
    + `가상 시계 <b>${t.getMonth() + 1}/${t.getDate()} (${WD[t.getDay()]}) ${hhmm(t)}</b>${DEMO.clock ? ` · 기준 ${esc(DEMO.clock.replace("T", " ").slice(0, 16))} 부터 실제 시간이 흐릅니다` : ""}.`;
}
async function probeVideo() {                          // /media/demo.mp4 가 있으면 단추·플레이어를 연다(없는 것이 기본 — 영상은 N7 뒤에)
  try {
    const r = await fetch("/media/demo.mp4", { method: "HEAD", cache: "no-store" });
    if (!r.ok) return;
    $("#videobtn").hidden = false;
    $("#videobtn").addEventListener("click", () => {
      const card = $("#guidevideo"); card.hidden = false;
      const v = $("#guideplayer"); if (!v.src) v.src = "/media/demo.mp4";
      card.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" }); v.play().catch(() => {});
    });
  } catch {}
}

/* ---------------- 자동 시연 ---------------- */
let i = -1, timer = null, tick = null, paused = false, t0 = 0, left = 0;
const tour = () => $("#tour");

function place() {                                    // 밝은 칸(spot)과 말풍선을 대상 카드에 맞춘다 — 스크롤·크기 변화마다 다시
  const st = STEPS[i]; if (!st) return;
  const el = document.querySelector(st.sel) || document.getElementById(st.screen);
  const r = el.getBoundingClientRect(), pad = 8;
  const spot = $("#tourspot");
  const w = Math.max(40, r.width + pad * 2), h = Math.max(40, r.height + pad * 2);
  spot.style.cssText = `left:${r.left - pad}px;top:${r.top - pad}px;width:${w}px;height:${h}px`;
  const b = $("#tourbubble"), bw = b.offsetWidth, bh = b.offsetHeight, vw = innerWidth, vh = innerHeight;
  if (vw < 900) { b.style.left = ""; b.style.top = ""; return; }           // 모바일: CSS 가 아래에 고정
  let top = r.bottom + pad + 14;                                           // 기본은 카드 아래, 모자라면 위, 그래도 모자라면 오른쪽/왼쪽
  let leftPx = Math.min(vw - bw - 16, Math.max(16, r.left));
  if (top + bh > vh - 16) top = r.top - pad - bh - 14;
  if (top < 16) { top = Math.max(16, Math.min(vh - bh - 16, r.top)); leftPx = r.right + pad + 14 + bw <= vw - 16 ? r.right + pad + 14 : Math.max(16, r.left - pad - bw - 14); }
  b.style.left = leftPx + "px"; b.style.top = top + "px";
}

function bar(ms) {                                    // 진행 띠 — 남은 시간만큼 CSS transition
  const el = $("#tourbar b");
  el.style.transition = "none"; el.style.width = paused ? el.style.width : "0%";
  if (paused) return;
  void el.offsetWidth; el.style.transition = `width ${ms}ms linear`; el.style.width = "100%";
}

function arm(ms) {
  clearTimeout(timer); t0 = Date.now(); left = ms;
  timer = setTimeout(() => show(i + 1), ms);
  bar(ms);
}

async function show(k) {
  if (k < 0) k = 0;
  if (k >= STEPS.length) { stop(); return; }
  i = k;
  const st = STEPS[i];
  if (window.MB.active() !== st.screen) window.MB.go(st.screen, { push: false });
  $("#tourno").textContent = `${i + 1} / ${STEPS.length}`;
  $("#tourtitle").textContent = st.title; $("#tourtext").textContent = st.text;
  $("#tourprev").disabled = i === 0;
  $("#tournext").textContent = i === STEPS.length - 1 ? "마치기" : "다음";
  await new Promise(r => setTimeout(r, 350));                          // 카드 등장·첫 폴링이 자리를 잡은 뒤에
  const el = document.querySelector(st.sel) || document.getElementById(st.screen);
  el.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: innerWidth < 900 ? "start" : "center" });
  await new Promise(r => setTimeout(r, REDUCE ? 50 : 450));
  place();
  if (!paused) arm(st.ms);
}

export function start() {
  if (i >= 0) return;
  paused = false;
  tour().hidden = false; document.body.classList.add("touring");
  clearInterval(tick); tick = setInterval(place, 400);                 // 카드 내용이 뒤늦게 차오르면 칸도 따라간다
  show(0);
}
export function stop() {
  clearTimeout(timer); clearInterval(tick); timer = tick = null; i = -1; paused = false;
  tour().hidden = true; document.body.classList.remove("touring");
  $("#tourpause").textContent = "일시정지";
}
function pause() {
  if (i < 0) return;
  paused = !paused;
  $("#tourpause").textContent = paused ? "계속" : "일시정지";
  if (paused) { clearTimeout(timer); left = Math.max(1500, left - (Date.now() - t0)); const el = $("#tourbar b"); const w = getComputedStyle(el).width; el.style.transition = "none"; el.style.width = w; }
  else arm(left);
}
function keys(e) {
  if (i < 0) return;
  if (e.key === "Escape") stop();
  else if (e.key === "ArrowRight") show(i + 1);
  else if (e.key === "ArrowLeft") show(i - 1);
  else if (e.key === " ") { e.preventDefault(); pause(); }
}

export const screen = {
  mount() {
    fillIntro(); fillDemoNote(); probeVideo();
    $("#tourstart").addEventListener("click", start);
    $("#tourstop").addEventListener("click", stop);
    $("#tournext").addEventListener("click", () => show(i + 1));
    $("#tourprev").addEventListener("click", () => show(i - 1));
    $("#tourpause").addEventListener("click", pause);
    addEventListener("keydown", keys);
    addEventListener("resize", () => i >= 0 && place());
    addEventListener("scroll", () => i >= 0 && place(), { passive: true });
  },
  every: 60000,
  async poll() {                                       // 가상 시계 안내 문구의 시각을 따라가게 — status 는 core 가 60초마다 받으므로 여기선 글만 고친다
    try { const st = await (await fetch("/api/status", { cache: "no-store" })).json(); DEMO = st.demo || null; } catch {}
    fillDemoNote();
  },
  render() {},
};

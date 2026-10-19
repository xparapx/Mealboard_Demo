/* 앱 안내 화면(10-18, 심사위원 구동 경로 N3) — 서버가 /api/status.guide 를 줄 때만 core.addGuide 가 이 모듈을 읽어 일곱 번째 탭으로 붙인다.
   ① 이 앱은: 핵심 기능 셋(점검서 N8 — 대기시간 · 밀집도 · 영양·탄소·리포트) + '자동 시연 시작'
   ② 자동 시연(10-19 개정, 사용자 요청 + 모션·광고 전문가 자문): 인트로 → 15단계 → 엔드카드, 약 2분.
      - 화면이 바뀔 때 Y축 피벗 전환(−12°/+10° + 가로 6% 슬라이드 + 페이드, View Transition API — 미지원·축소 모션이면 컷)
      - 카드 하나를 설명할 때는 그 카드를 실제 DOM transform 으로 줌인(데스크톱 ≤1.25, 모바일은 화면에 맞춤 0.88~1.06), 나머지는 어둡게
      - 줌인한 카드 둘레의 틸 링 할로가 2.2초 주기로 숨 쉬듯 점멸(완전히 꺼지지 않는다 — 네온 간판 회피), 말풍선은 차콜 '안내자'
      - 같은 화면 안 이동은 전환 없이 '카메라 팬'(이전 카드 260ms 복귀 ∥ 새 카드 450ms 줌)
      - 체류 시간 = 글자 수 기반 공식, 첫 단계 제목엔 실시간 대기 숫자. 시연 대본(STEPS)이 곧 제출 영상(N7)의 대본.
   ③ 시연 영상: /media/demo.mp4 가 있으면 인앱 재생(없으면 단추를 숨긴다)
   ④ 숫자는 이렇게 나옵니다(투명성 1장, 제안서 P12) · 심사위원 안내(모의 데이터·가상 시계·구동 명령) */
import { $, $$, esc, now, REDUCE, WD, hhmm, desktop } from "./core.js";

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
/* 자동 시연 대본 — screen(화면) · sel(줌인할 카드 안의 대상) · title · text(≤60자 권장: 380px 말풍선 2~3줄) · ms(생략하면 글자 수 공식)
   순서는 '효용 먼저, 증명 뒤'(전문가 자문): 지금 몇 분 → 추이 → 예보 → 히트맵 → 병목 → 품질 → 실시간뷰 → 통계 → 식단 → 영양 → 원리 */
const STEPS = [
  { screen: "wait", sel: "#hero", title: "지금 줄 서면 {wait}", text: "카메라가 센 대기 인원 L ÷ 배식 속도 λ. 여유·보통·혼잡 판정과 도착 예상 시각까지." },
  { screen: "wait", sel: "#trend", title: "최근 30분, 평소와 비교", text: "오늘 막대 위에 같은 요일 평소 곡선(파선). 한 줄 결론 — 지금이 평소보다 긴지 짧은지." },
  { screen: "wait", sel: "#forecastcard", title: "황금 구간 미리 알림", text: "같은 요일 평소 곡선에 오늘 메뉴 인기를 곱해 피크 시각과 '3분 이하' 시각을 예보합니다." },
  { screen: "wait", sel: "#heatcard", title: "요일 · 시각별 평소 대기", text: "4주 집계, 어두울수록 긴 대기. 오늘 행은 실시간으로 채워지고 점멸하는 칸이 지금." },
  { screen: "wait", sel: "#bottlecard", title: "병목 로그", text: "줄이 5명 넘게 있는데 배식이 멈췄거나 평소의 절반 아래로 느려진 구간 — 운영진이 원인을 되짚는 기록." },
  { screen: "wait", sel: "#qualitycard", title: "정확도는 수치로", text: "커버리지·표본 수·빈 시간·산출 불가 시간을 숨기지 않습니다." },
  { screen: "room", sel: "#plancard", title: "영상이 아닙니다", text: "평면도 위 노란 점은 익명 위치 마커. 5초마다 그 순간만, 이력 저장 0." },
  { screen: "room", sel: "#zonecard", title: "최근 10분 밀집도", text: "육각 타일별 인원수 합계로 어디에 사람이 모였는지. 구역별 점유율 칩과 함께." },
  { screen: "room", sel: "#typcard", title: "늘 모이는 자리 ①②③", text: "최근 7일 누적 타일에서 진한 묶음을 찾습니다 — 좌석·동선 조정의 근거." },
  { screen: "room", sel: "#reportcard", title: "숫자만 받아 쓰는 리포트", text: "집계값만으로 아침 예보·점심 결산. 입력에 없는 숫자는 검증기가 막습니다." },
  { screen: "stats", sel: "#bandcard", title: "시간대별 분포 · 4~12주", text: "시각별 평균과 변동 폭(P25~P75·±1σ) 위에 오늘 선. 급식 시정표를 바꿀 때 보는 그림." },
  { screen: "stats", sel: "#menuwaitcard", title: "줄이 길어지는 메뉴", text: "메뉴별 최고 대기 — 인기 메뉴 날의 배식 인력·시차 배식 대비에." },
  { screen: "week", sel: "#weekcard", title: "주간식단", text: "NEIS 급식 API 캐시. 요일 컬럼에 중식·석식, 오늘은 색과 숨쉬기로. 주간 영양 추이도 아래에." },
  { screen: "today", sel: "#mealcard", title: "영양 · 알레르기 · 탄소", text: "에너지 충족률·적정비율·미량영양소 세 지표, 내 알레르기 경고(기기에만 저장), 다 남기면 나오는 탄소." },
  { screen: "guide", sel: "#guidehow", title: "다섯 단계로 나옵니다", text: "세기만 한다 → W = L ÷ λ → 스스로 보정 → 보수적 판정 → 하루 집계." },
];
const INTRO = { title: "급식실 줄, 몇 분 기다릴까요?", text: "카메라는 숫자만 남깁니다.", ms: 2800 };
const OUTRO = { title: "지금 운영 중 · kjhs-meal.com", text: "저장 프레임 0 · Pi 한 대 + NEIS(전국 공통) · 평면도 보정만 바꾸면 다른 학교에도." };
const dwell = st => st.ms || Math.min(11000, Math.max(4500, 1500 + 100 * (st.text || "").length + 600));
const ZOOM_MAX = 1.25, ZOOM_MIN_MOBILE = 0.88, ZOOM_MAX_MOBILE = 1.06, PAD = 8;
const T_ZOOM = 450, T_UNZOOM = 260, T_OUT = 220, T_IN = 320;

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

/* ---------------- 자동 시연 엔진 ---------------- */
let i = -1, timer = null, tick = null, paused = false, t0 = 0, left = 0, zoomed = null, seq = 0, curSide = "below";
const tour = () => $("#tour");
const sleep = ms => new Promise(r => setTimeout(r, ms));
const motion = () => !REDUCE;                          // 축소 모션: 줌·피벗 없이 컷 + 정적 링

function cardOf(el) {                                  // 줌인은 카드 단위(히어로는 .waitcard 안 overflow:hidden 이라 상자째 키운다)
  return el.closest(".card, .waitcard") || el;
}
function liveWait() {                                  // 첫 단계 제목의 실시간 숫자 — 히어로가 그리는 값을 그대로 읽는다
  const n = $("#wait-min")?.textContent, u = $("#wait-unit")?.textContent;
  return n && n !== "—" ? `${n}${u}` : "몇 분?";
}

/* 줌 — 자유 영역(뷰포트에서 말풍선 자리를 뺀 곳)의 중앙으로 translate + scale. 스크롤은 즉시 1회만(측정 전), 그 뒤엔 transform 만 */
function freeArea(card) {
  const vw = innerWidth, vh = innerHeight;
  if (!desktop()) {
    const sheet = $("#tourbubble").offsetHeight || 230, dock = 56;
    return { x: 16, y: 12, w: vw - 32, h: vh - sheet - dock - 40, side: "sheet" };
  }
  const r = card.getBoundingClientRect(), bw = 380 + 22, bh = ($("#tourbubble").offsetHeight || 220) + 22;
  const tall = r.height > r.width * 1.1;
  if (tall) return { x: 24, y: 24, w: vw - bw - 48, h: vh - 48, side: "right" };
  return { x: 24, y: 24, w: vw - 48, h: vh - bh - 48, side: "below" };
}
function zoomTo(card) {
  const rect = card.getBoundingClientRect();           // transform 없는 자연 크기(unzoom 뒤에 부른다)
  const A = freeArea(card);
  let s;
  if (desktop()) s = Math.min(ZOOM_MAX, (A.w - 48) / rect.width, (A.h - 48) / rect.height);
  else s = Math.max(ZOOM_MIN_MOBILE, Math.min(ZOOM_MAX_MOBILE, (A.w - 24) / rect.width, (A.h - 24) / rect.height));
  if (!motion()) s = 1;
  const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
  let tx = A.x + A.w / 2 - cx, ty = A.y + A.h / 2 - cy;
  if (rect.height * s > A.h) ty = A.y + rect.height * s / 2 - cy;            // 자유 영역보다 긴 카드는 위를 맞춘다(모바일 평면도)
  card.classList.add("tz");
  card.style.transition = motion() ? `transform ${T_ZOOM}ms var(--ease)` : "none";
  card.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(${s.toFixed(3)})`;
  zoomed = card;
  return A.side;
}
function unzoom(card, ms = T_UNZOOM) {
  if (!card) return;
  card.style.transition = motion() ? `transform ${ms}ms ease-in` : "none";
  card.style.transform = "";
  const done = () => { card.classList.remove("tz"); card.style.transition = ""; };
  motion() ? setTimeout(done, ms + 20) : done();
  if (zoomed === card) zoomed = null;
}

/* 스포트라이트 링 + 말풍선 배치 — 대상 요소의 (변환 뒤) 사각형 기준. 전환 중엔 링을 뷰포트 전체로 펴서 베일을 유지한다 */
function veil() {
  const spot = $("#tourspot");
  spot.classList.add("veil");
  spot.style.cssText = `left:-20px;top:-20px;width:${innerWidth + 40}px;height:${innerHeight + 40}px`;
}
function place(side = curSide) {
  const st = STEPS[i]; if (!st) return;
  const el = document.querySelector(st.sel) || document.getElementById(st.screen);
  const r0 = el.getBoundingClientRect();
  if (!r0.width && !r0.height) return;                 // 아직 숨은 화면의 요소(전환 전) — 링을 0×0 으로 접지 않는다
  const spot = $("#tourspot");
  spot.classList.remove("veil");
  spot.style.cssText = `left:${r0.left - PAD}px;top:${r0.top - PAD}px;width:${Math.max(40, r0.width + PAD * 2)}px;height:${Math.max(40, r0.height + PAD * 2)}px`;
  const r = cardOf(el).getBoundingClientRect();        // 말풍선은 줌인한 카드 상자 밖에(히어로처럼 카드 일부가 대상이어도 카드를 가리지 않게), 링은 대상에
  const b = $("#tourbubble"), bw = b.offsetWidth, bh = b.offsetHeight, vw = innerWidth, vh = innerHeight, gap = 22;
  if (!desktop()) { b.style.left = ""; b.style.top = ""; b.removeAttribute("data-pos"); return; }
  let pos = side || "below", top, leftPx;
  if (pos === "right") { top = Math.max(16, Math.min(vh - bh - 16, r.top)); leftPx = Math.min(vw - bw - 16, r.right + PAD + gap); }
  else { pos = "below"; top = r.bottom + PAD + gap; leftPx = Math.min(vw - bw - 16, Math.max(16, r.left)); }
  if (pos === "below" && top + bh > vh - 16) { pos = "above"; top = r.top - PAD - bh - gap; }
  if (top < 16) { pos = "right"; top = Math.max(16, Math.min(vh - bh - 16, r.top)); leftPx = Math.min(vw - bw - 16, r.right + PAD + gap); }
  b.dataset.pos = pos;
  b.style.left = leftPx + "px"; b.style.top = top + "px";
}

/* 화면 피벗 전환 — View Transition API. 오버레이(#tour)는 view-transition-name 으로 분리돼 같이 돌지 않는다 */
async function switchScreen(name, dir) {
  if (window.MB.active() === name) return;
  if (!motion() || !document.startViewTransition) { window.MB.go(name, { push: false }); return; }
  document.documentElement.dataset.tourdir = dir < 0 ? "back" : "fwd";
  veil();
  try {
    const vt = document.startViewTransition(() => { window.MB.go(name, { push: false }); });
    await Promise.race([vt.finished.catch(() => {}), sleep(T_OUT + T_IN + 400)]);   // 숨은 탭 등에서 finished 가 안 올 때를 대비한 상한
  } catch {}
  if (window.MB.active() !== name) window.MB.go(name, { push: false });              // 전환이 건너뛰어졌어도 화면은 반드시 바뀐다
  delete document.documentElement.dataset.tourdir;
}

function setBubble(title, text) {
  const b = $("#tourbubble");
  b.classList.remove("in"); void b.offsetWidth; b.classList.add("in");
  $("#tourtitle").textContent = title; $("#tourtext").textContent = text;
}
function bar(ms) {
  const el = $("#tourbar b");
  el.style.transition = "none"; el.style.width = paused ? el.style.width : "0%";
  if (paused) return;
  void el.offsetWidth; el.style.transition = `width ${ms}ms linear`; el.style.width = "100%";
}
function arm(ms, next) {
  clearTimeout(timer); t0 = Date.now(); left = ms;
  timer = setTimeout(next, ms);
  bar(ms);
}

/* 인트로·엔드카드 — 전면 차콜 카드(#tourcard). 인트로는 2.8초 뒤(또는 클릭) 1단계로, 엔드는 머문다 */
function showCard(kind) {
  const c = $("#tourcard");
  c.dataset.kind = kind; c.hidden = false;
  const d = kind === "intro" ? INTRO : OUTRO;
  $("#tourcardtitle").textContent = d.title; $("#tourcardtext").textContent = d.text;
  $("#tourcardctl").hidden = kind !== "outro";
  $("#tourbubble").hidden = true;
  veil();
}
function hideCard() { $("#tourcard").hidden = true; $("#tourbubble").hidden = false; }

async function show(k) {
  const my = ++seq;                                    // 빠른 연타·종료 뒤 늦게 도착하는 await 가 화면을 건드리지 않게
  clearTimeout(timer);
  if (k < 0) k = 0;
  if (k >= STEPS.length) { outro(); return; }
  const prev = i, st = STEPS[k];
  i = k;
  hideCard();
  $("#tourno").textContent = `${i + 1} / ${STEPS.length}`;
  $("#tourprev").disabled = i === 0;
  $("#tournext").textContent = i === STEPS.length - 1 ? "마치기" : "다음";
  const sameScreen = window.MB.active() === st.screen;
  if (zoomed) unzoom(zoomed, sameScreen ? T_UNZOOM : 120);
  if (!sameScreen) {
    await switchScreen(st.screen, k - prev);
    if (my !== seq) return;
    await sleep(360);                                  // 카드 등장(.enter 240ms)·첫 폴링이 자리를 잡은 뒤에
  } else await sleep(motion() ? 120 : 0);
  if (my !== seq) return;
  const el = document.querySelector(st.sel) || document.getElementById(st.screen);
  const card = cardOf(el);
  el.scrollIntoView({ behavior: "auto", block: desktop() ? "center" : "start" });   // 측정 전 1회, 즉시
  await sleep(30);
  const side = curSide = zoomTo(card);
  setBubble(st.title.replace("{wait}", liveWait()), st.text);
  // 줌 전환 중엔 rAF 로 링을 따라가고, 끝나면 400ms 틱(카드 내용이 뒤늦게 차오를 때)
  const t1 = performance.now() + (motion() ? T_ZOOM + 40 : 0);
  const follow = () => { if (my !== seq) return; place(side); if (performance.now() < t1) requestAnimationFrame(follow); };
  requestAnimationFrame(follow);
  if (!paused) arm(dwell(st), () => show(i + 1));
}

function outro() {
  if (zoomed) unzoom(zoomed);
  i = STEPS.length;
  showCard("outro");
  $("#tourno").textContent = `${STEPS.length} / ${STEPS.length}`;
  clearTimeout(timer);
  $("#tourbar b").style.width = "100%";
}

export function start(at = null, hold = false) {
  if (at !== null && typeof at !== "number" && at !== "outro") at = null;   // 클릭 핸들러가 이벤트 객체를 넘겨도 처음부터(10-19 사고: 버튼이 안 먹었다)
  if (i >= 0) return;
  paused = !!hold; seq++;                              // hold: 자동 진행 없이 그 단계에 머문다(정지 화면 검증·캡처용)
  document.body.classList.toggle("tourhold", paused);  // 정지 캡처(헤드리스)에서는 등장 애니메이션·전환을 0 으로 — 끝 상태만 찍힌다
  $("#tourpause").textContent = paused ? "계속" : "일시정지";
  tour().hidden = false; document.body.classList.add("touring");
  clearInterval(tick); tick = setInterval(() => { if (i >= 0 && i < STEPS.length && $("#tourcard").hidden) place(); }, 400);
  if (at === "outro") { i = STEPS.length - 1; outro(); return; }   // ?tour=outro — 엔드카드만(검증용)
  if (at !== null) { i = -0.5; show(at); return; }     // ?tour=N — 특정 단계에서 바로(녹화·검증용). 인트로 생략
  i = -0.5;                                            // 인트로 중(단계 아님)
  showCard("intro");
  arm(INTRO.ms, () => show(0));
}
export function stop() {
  clearTimeout(timer); clearInterval(tick); timer = tick = null; seq++;
  if (zoomed) unzoom(zoomed);
  i = -1; paused = false;
  hideCard();
  tour().hidden = true; document.body.classList.remove("touring");
  delete document.documentElement.dataset.tourdir;
  $("#tourpause").textContent = "일시정지";
  scrollTo({ top: 0, behavior: "auto" });
}
function pause() {
  if (i < 0 || i >= STEPS.length) return;
  paused = !paused;
  $("#tourpause").textContent = paused ? "계속" : "일시정지";
  if (paused) { clearTimeout(timer); left = Math.max(1500, left - (Date.now() - t0)); const el = $("#tourbar b"); const w = getComputedStyle(el).width; el.style.transition = "none"; el.style.width = w; }
  else arm(left, () => show(i + 1));
}
function keys(e) {
  if (i < 0) return;
  if (e.key === "Escape") stop();
  else if (e.key === "ArrowRight") show(Math.floor(i) + 1);
  else if (e.key === "ArrowLeft") show(Math.floor(i) - 1);
  else if (e.key === " ") { e.preventDefault(); pause(); }
}

export const screen = {
  mount() {
    fillIntro(); fillDemoNote(); probeVideo();
    window.MB.tour = { start, stop, show, step: () => i };          // 콘솔·미리보기 검증용 손잡이
    // ?tour=N 또는 ?tour=auto — 페이지를 열자마자 시연(녹화·헤드리스 검증용). N 은 0부터의 단계 번호, auto 는 인트로부터
    const qs = new URLSearchParams(location.search), q = qs.get("tour");
    if (q !== null) setTimeout(() => start(q === "auto" || q === "" ? null : q === "outro" ? "outro" : Math.max(0, Math.min(STEPS.length - 1, +q || 0)), qs.has("hold")), 1200);
    $("#tourstart").addEventListener("click", () => start());
    $("#tourstop").addEventListener("click", stop);
    $("#tournext").addEventListener("click", () => show(Math.floor(i) + 1));
    $("#tourprev").addEventListener("click", () => show(Math.floor(i) - 1));
    $("#tourpause").addEventListener("click", pause);
    $("#tourcard").addEventListener("click", e => { if ($("#tourcard").dataset.kind === "intro" && !e.target.closest("button")) show(0); });
    $("#tourreplay").addEventListener("click", () => { stop(); start(); });
    $("#tourbrowse").addEventListener("click", () => { stop(); window.MB.go("wait"); });
    addEventListener("keydown", keys);
    addEventListener("resize", () => { if (i >= 0 && i < STEPS.length && zoomed) { const c = zoomed; unzoom(c, 0); zoomTo(c); place(); } });
    addEventListener("scroll", () => { if (i >= 0 && i < STEPS.length) requestAnimationFrame(() => place()); }, { passive: true });
  },
  every: 60000,
  async poll() {                                       // 가상 시계 안내 문구의 시각을 따라가게 — status 는 core 가 60초마다 받으므로 여기선 글만 고친다
    try { const st = await (await fetch("/api/status", { cache: "no-store" })).json(); DEMO = st.demo || null; } catch {}
    fillDemoNote();
  },
  render() {},
};

/* 관리 화면 — 관리 origin(8101 / Serve 8443)에서만 실린다. core.js 가 /api/admin/whoami 200 을 보고 import('/admin-ui/admin.js') 한 뒤
   default(MB) 를 부른다. 여기서 여섯 번째 화면(#admin)을 등록한다: dock·레일 버튼, 섹션, 카드(스트림 · 서비스 상태 · 원샷 작업 · 통과 이벤트 ·
   로그 테일 · 감사 로그), 확인 대화상자. 디자인 컨셉은 v5 그대로 — 틸=정상/라이브, 멜론=경고·파괴적, 차콜=구조, 옐로 금지 (PLAN §4.5).
   스트림 패널(3c): 메타 = SSE(/api/admin/stream/meta) 를 평면도(익명 마커) 또는 프레임(bbox) 뷰로 그린다 — 브라우저 메모리에만, 저장 없음.
   실사 = stream/on 으로 플래그를 켠 뒤 <img> 에 mjpeg 프록시를 물린다(켤 때만 src, 끌 때 비움). 화면을 떠나면 클라이언트 쪽은 모두 끊는다.
   3d(구역 편집기)가 카드를 더한다 */
import { fit, mm } from "/js/core.js";
import { drawFloor, drawMarkers, drawZones, geom } from "/js/floor.js";
import * as zonesEditor from "/admin-ui/zones-editor.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const UNITS = ["api", "mock", "vision", "admin", "neis", "news", "rollup", "report"];
const RESTARTABLE = ["api", "mock", "vision"];
const JOBS = [["neis", "NEIS 재수신"], ["news", "뉴스 재수신"], ["rollup", "집계 재실행"], ["report", "리포트 재생성"]];
const age = s => s == null ? "—" : s < 90 ? `${s}초` : s < 5400 ? `${Math.round(s / 60)}분` : `${(s / 3600).toFixed(1)}시간`;
const mmss = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
const CROSS_MAX = 50;

async function api(path, body, method = "POST") {
  const r = await fetch("/api/admin" + path, body === undefined ? { cache: "no-store" }
    : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch {}
  return { ok: r.ok, status: r.status, j };
}

/* 확인 대화상자 — Promise<boolean>. 파괴적이면 확인 버튼이 멜론 채움.
   답은 form 의 submit(e.submitter 가 누른 버튼, 동기) 에서 읽는다 — dialog 의 close 이벤트·returnValue 에 기대지 않는다
   (임베디드 브라우저에서 showModal 뒤에 단 close 리스너가 불리지 않는 경우가 있었다). Esc·바깥 닫힘은 취소 */
function confirm({ title, body, ok = "확인", danger = false }) {
  const d = $("#adminconfirm"), form = d.querySelector("form");
  d.querySelector("h3").textContent = title; d.querySelector("p").textContent = body;
  const okb = d.querySelector("button.ok"); okb.textContent = ok; okb.classList.toggle("danger", danger);
  return new Promise(res => {
    const done = v => { res(v); if (d.open) d.close(); };
    form.onsubmit = e => { e.preventDefault(); done(e.submitter?.value === "ok"); };
    d.oncancel = () => done(false);
    d.onclose = () => done(false);
    d.showModal();
  });
}

function build(MB) {
  document.head.insertAdjacentHTML("beforeend", '<link rel="stylesheet" href="/admin-ui/admin.css">');
  $("svg symbol#i-news").insertAdjacentHTML("afterend",
    '<symbol id="i-admin" viewBox="0 0 24 24"><path d="M14.5 6.5a4 4 0 0 0 5 5L9 22l-3-3L16.5 8.5"/><path d="M3.5 6.5 6 4l3 3-2.5 2.5z"/></symbol>');
  const btn = `<svg><use href="#i-admin"/></svg>관리`;
  $(".dock").insertAdjacentHTML("beforeend", `<a href="#admin" data-go="admin" role="tab">${btn}</a>`);
  $(".rail").insertAdjacentHTML("beforeend", `<a href="#admin" data-go="admin">${btn}</a>`);
  $(".dock").dataset.n = "6";
  $(".views").insertAdjacentHTML("beforeend", `
<section class="view" id="admin" role="tabpanel" aria-label="관리">
  <section class="card adminhead" id="adminhead"><div class="eyebrow">관리</div><div class="who" id="adminwho">—</div>
    <div class="lock" id="adminlock" hidden>관리 포트가 공개 Funnel 에 노출되어 잠겼습니다 — <code>tailscale funnel status</code> 를 확인하세요</div></section>
  <section class="card" id="streamcard">
    <div class="eyebrow">스트림</div>
    <div class="streamhead"><div class="big"><b id="streamfps">—</b><i>fps</i></div><span class="chip" id="streamchip">꺼짐</span></div>
    <div class="well six" id="streamwell"></div>
    <div class="seg" id="streamseg" role="group" aria-label="스트림 모드">
      <button type="button" data-mode="meta">메타</button><button type="button" data-mode="mjpeg">실사</button>
      <button type="button" data-mode="off" aria-pressed="true">끄기</button>
      <select id="streammin" aria-label="실사 시간"><option value="2">2분</option><option value="5" selected>5분</option><option value="10">10분</option></select>
    </div>
    <div class="sstage plan" id="stage"><img id="streamimg" alt="" hidden><canvas id="streamcanvas"></canvas><span class="badge" id="streambadge" hidden></span></div>
    <div class="seg small" id="streamview" role="group" aria-label="보기">
      <button type="button" data-view="plan" aria-pressed="true">평면도</button><button type="button" data-view="frame">프레임</button>
    </div>
    <div class="note foot">실사는 이 화면에만 · 저장·전송 없음 · 켜짐 이력 기록 · 메타 구독 ≤3 · 실사 뷰어 1명 · 최대 10분 뒤 자동 종료</div>
  </section>
  <section class="card" id="svccard">
    <div class="eyebrow">서비스 상태</div>
    <div class="well" id="adminwell"></div>
    <ul class="units" id="adminunits"></ul>
    <div class="note foot" id="adminfoot"></div>
  </section>
  <section class="card" id="jobcard">
    <div class="eyebrow">원샷 작업</div>
    <div class="jobs" id="adminjobs">${JOBS.map(([k, l]) => `<button type="button" class="pill" data-job="${k}">${l}</button>`).join("")}</div>
    <div class="note foot">타이머를 기다리지 않고 지금 한 번 실행합니다 · 결과는 로그 테일에서</div>
  </section>
  <section class="card" id="crosscard">
    <div class="eyebrow">통과 이벤트</div>
    <ul class="cross" id="admincross"><li><small>메타 스트림을 켜면 배식대 통과(λ 선)가 여기 쌓입니다 · 최근 ${CROSS_MAX}건 · 화면에만</small></li></ul>
  </section>
  <section class="card" id="logcard">
    <details class="fold" id="logfold"><summary><span class="eyebrow">로그 테일</span><i></i></summary>
    <div class="logbar"><select id="adminunit">${UNITS.map(u => `<option value="mealboard-${u}">${u}</option>`).join("")}</select>
      <button type="button" class="pill ghost" id="adminfollow" aria-pressed="false">따라가기</button></div>
    <pre class="log" id="adminlog">—</pre></details>
  </section>
  <section class="card" id="auditcard">
    <details class="fold" id="auditfold"><summary><span class="eyebrow">감사 로그</span><i></i></summary>
    <ul class="log" id="adminaudit"></ul></details>
  </section>
</section>
<dialog class="confirm" id="adminconfirm"><form method="dialog"><h3></h3><p></p>
  <div class="row"><button value="" class="pill ghost">취소</button><button value="ok" class="pill ok">확인</button></div></form></dialog>`);
  document.querySelectorAll('[data-go="admin"]').forEach(a => a.addEventListener("click", e => { e.preventDefault(); MB.go("admin"); }));
  $("#adminjobs").addEventListener("click", async e => {
    const b = e.target.closest("[data-job]"); if (!b) return;
    const label = b.textContent;
    if (!await confirm({ title: label, body: "지금 한 번 실행합니다. 결과는 로그 테일에서 확인하세요.", ok: "실행" })) return;
    b.disabled = true;
    const r = await api(`/jobs/${b.dataset.job}/run`, {});
    b.disabled = false;
    toast(r.ok ? `${label} 시작` : `실패 (${r.status}) ${r.j?.detail?.stderr || r.j?.detail?.reason || r.j?.reason || ""}`, !r.ok);
    loadAudit();
  });
  $("#adminunits").addEventListener("click", async e => {
    const b = e.target.closest("[data-restart]"); if (!b) return;
    const svc = b.dataset.restart;
    if (!await confirm({ title: `${svc} 재시작`, body: RESTARTABLE.slice(1).includes(svc) ? "카운팅 프로세스입니다. 급식 시간이면 대기 표시가 잠깐 끊깁니다." : "몇 초 동안 화면이 갱신되지 않습니다.", ok: "재시작", danger: svc !== "api" })) return;
    let r = await api(`/services/${svc}/restart`, { force: false });
    if (r.status === 409) {
      if (!await confirm({ title: "지금은 급식 시간입니다", body: "재시작하면 카운팅에 공백이 생깁니다. 그래도 진행할까요?", ok: "그래도 재시작", danger: true })) return;
      r = await api(`/services/${svc}/restart`, { force: true });
    }
    toast(r.ok ? `${svc} 재시작 요청` : `실패 (${r.status}) ${r.j?.detail?.stderr || r.j?.detail?.reason || r.j?.reason || ""}`, !r.ok);
    setTimeout(loadServices, 3000); loadAudit();
  });
  $("#adminunit").addEventListener("change", loadLog);
  // 접기/펼치기(09-04): 펼칠 때만 읽고, 상태는 이 브라우저에 기억
  for (const [id, load] of [["logfold", loadLog], ["auditfold", loadAudit]]) {
    const d = $("#" + id);
    try { d.open = localStorage.getItem("mb_" + id) === "1"; } catch {}
    d.addEventListener("toggle", () => { try { localStorage.setItem("mb_" + id, d.open ? "1" : "0"); } catch {} if (d.open) load(); });
  }
  $("#adminfollow").addEventListener("click", e => { const on = e.target.getAttribute("aria-pressed") !== "true"; e.target.setAttribute("aria-pressed", on); if (on) loadLog(); });
  $("#streamseg").addEventListener("click", e => { const b = e.target.closest("[data-mode]"); if (b) setMode(b.dataset.mode); });
  $("#streamview").addEventListener("click", e => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view); });
  $("#streamimg").addEventListener("error", () => {
    if (ST.mode !== "mjpeg") return;
    toast("실사 스트림을 열지 못했습니다 — vision 이 없거나(502) 다른 뷰어가 보는 중(409)", true);
    $("#streamimg").hidden = true; $("#streamimg").removeAttribute("src");
  });
  new ResizeObserver(() => draw()).observe($("#stage"));
  zonesEditor.mount({ api, confirm, toast, lastFrame: () => ST.last, streamImg: () => $("#streamimg"), onSaved: loadAudit });
}

function toast(text, bad) {
  let t = $("#admintoast"); if (!t) { document.body.insertAdjacentHTML("beforeend", '<div id="admintoast" role="status"></div>'); t = $("#admintoast"); }
  t.textContent = text; t.classList.toggle("bad", !!bad); t.classList.add("on"); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("on"), 3500);
}

async function loadServices() {
  const [w, s] = await Promise.all([api("/whoami"), api("/services")]);
  const locked = w.ok ? w.j.lockdown : w.j?.reason === "lockdown";     // lockdown 이면 whoami 자체가 403 — 그 본문의 reason 으로 안다
  $("#adminlock").hidden = !locked;
  if (w.ok) $("#adminwho").textContent = `${w.j.user} · ${w.j.via === "tailscale" ? "tailnet" : "SSH 터널"}`;
  else $("#adminwho").textContent = locked ? "잠김" : "—";
  if (locked && ST.mode !== "off") setMode("off", { keepFlag: true });
  if (!s.ok) { $("#adminfoot").textContent = `상태를 읽지 못했습니다 (${s.status})`; return; }
  const h = s.j.health || {};
  $("#adminwell").innerHTML = tile(age(h.db_age_s), "", "DB 최신 행", h.db_age_s == null || h.db_age_s > 120)
    + tile(h.disk?.free_gb, "GB", "디스크 여유", h.disk && h.disk.used_pct > 90) + tile(h.temp_c, "°C", "온도", h.temp_c > 75)
    + tile(h.ntp == null ? "—" : h.ntp ? "동기" : "어긋남", "", "시간 동기(NTP)", h.ntp === false);
  $("#adminunits").innerHTML = s.j.units.map(u => {
    const name = u.unit.replace("mealboard-", ""), ok = u.active === "active", off = u.active === "unknown";
    return `<li><b>${name}</b><em class="${ok ? "teal" : off ? "mute" : "melon"}">${esc(u.active)}${u.sub ? " · " + esc(u.sub) : ""}</em>`
      + (u.restarts ? `<small>재시작 ${u.restarts}회</small>` : "")
      + (u.enabled === "disabled" ? "<small>꺼 둠</small>" : "")
      + (RESTARTABLE.includes(name) && u.enabled !== "disabled" ? `<button type="button" class="pill ghost small" data-restart="${name}">재시작</button>` : "") + "</li>";
  }).join("");                                        // disabled 카운팅 유닛(학교 Pi 의 mock)은 버튼도 없다 — 켜면 상대를 끈다(서버도 409)
  $("#adminfoot").textContent = `코드 ${h.git || "?"} · 가동 ${age(h.uptime_s)} · 위치 파일 ${age(h.positions_age_s)} 전 · 급식 창 ${mm(s.j.lunch.lo)}~${mm(s.j.lunch.hi)}`;
}

const tile = (v, unit, label, warn) => `<div${warn ? " data-warn" : ""}><b>${esc(v ?? "—")}<i>${esc(unit)}</i></b><span>${label}</span></div>`;   // v 는 프레임 JSON 에서 온다

async function loadLog() {
  const unit = $("#adminunit").value;
  const r = await api(`/logs/${unit}?lines=80`);
  const pre = $("#adminlog");
  pre.textContent = r.ok && r.j.state === "ok" ? (r.j.lines.join("\n") || "(비어 있음)") : (r.j?.reason || `읽지 못했습니다 (${r.status})`);
  pre.scrollTop = pre.scrollHeight;
}

async function loadAudit() {
  const r = await api("/audit?n=50");
  if (!r.ok) return;
  $("#adminaudit").innerHTML = r.j.items.map(x =>
    `<li><b>${esc(x.action)}${x.target ? " · " + esc(x.target) : ""}</b><div><em class="${x.ok ? "teal" : ""}">${x.ok ? "ok" : "실패"}</em><small>${esc(x.user || "system")} · ${esc((x.ts || "").slice(5, 16).replace("T", " "))}${x.detail ? " · " + esc(x.detail) : ""}</small></div></li>`).join("")
    || '<li><small>아직 기록이 없습니다</small></li>';
}

/* ---------------- 스트림 패널 ---------------- */
const ST = { mode: "off", view: "plan", es: null, last: null, state: null, zones: null, cross: [], stamps: [], tick: null };

async function loadStreamState() {
  const r = await api("/stream/state");
  if (r.ok) { ST.state = r.j; badge(); }
  return r.j;
}

async function loadZones() {
  const r = await fetch("/api/insight/zones", { cache: "no-store" }).then(x => x.ok ? x.json() : null).catch(() => null);
  if (r?.zones) { ST.zones = r.zones; draw(); }
}

function setView(v) {
  ST.view = v;
  document.querySelectorAll("#streamview [data-view]").forEach(b => b.setAttribute("aria-pressed", b.dataset.view === v));
  $("#stage").classList.toggle("plan", v === "plan" && ST.mode !== "mjpeg");
  draw();
}

async function setMode(mode, { keepFlag = false } = {}) {
  const img = $("#streamimg");
  if (mode === "mjpeg") {
    const st = await loadStreamState();
    if (!st || st.state !== "on") {
      const min = Number($("#streammin").value);
      if (!await confirm({ title: `실사 스트림을 ${min}분 켭니다`, body: "카메라 실사가 이 화면에만 흐릅니다. 저장·전송되지 않고 켜짐 이력이 감사 로그에 남습니다. 시간이 지나면 자동으로 꺼집니다.", ok: "켜기", danger: true })) return;
      const r = await api("/stream/on", { minutes: min });
      if (!r.ok) { toast(`켜지 못했습니다 (${r.status}) ${r.j?.detail?.reason || ""}`, true); return; }
      ST.state = r.j; loadAudit();
    }
    ST.mode = "mjpeg";
    img.hidden = false; img.src = `/api/admin/stream/mjpeg?t=${Date.now()}`;
    startMeta();                                                 // 오버레이용 — 실사 위에 bbox
  } else {
    if (ST.mode === "mjpeg" || mode === "off") { img.hidden = true; img.removeAttribute("src"); }
    if (mode === "off") {
      stopMeta();
      if (!keepFlag && ST.state?.state === "on") { const r = await api("/stream/off", {}); if (r.ok) { ST.state = r.j; loadAudit(); } }
    } else startMeta();
    ST.mode = mode;
  }
  document.querySelectorAll("#streamseg [data-mode]").forEach(b => b.setAttribute("aria-pressed", b.dataset.mode === ST.mode));
  $("#stage").classList.toggle("plan", ST.view === "plan" && ST.mode !== "mjpeg");
  badge(); hud(); draw();
}

function startMeta() {
  if (ST.es) return;
  const es = new EventSource("/api/admin/stream/meta");
  ST.es = es; ST.stamps = [];
  es.onmessage = e => { let ev; try { ev = JSON.parse(e.data); } catch { return; } onFrame(ev); };
  es.addEventListener("bye", () => { setMode("off", { keepFlag: true }); toast("서버가 스트림을 닫았습니다", true); });
  es.onerror = () => {
    if (es.readyState === EventSource.CLOSED) { setMode("off", { keepFlag: true }); toast("메타 스트림에 연결하지 못했습니다 — 구독 상한(3) 또는 권한", true); }
    else $("#streamchip").textContent = "재연결 중…";
  };
  if (!ST.tick) ST.tick = setInterval(() => { badge(); if (ST.mode !== "off" && ST.stamps.length && performance.now() - ST.stamps.at(-1) > 5000) hud(true); }, 1000);
}

function stopMeta() {
  if (ST.es) { ST.es.close(); ST.es = null; }
  if (ST.tick) { clearInterval(ST.tick); ST.tick = null; }
  ST.last = null; ST.stamps = [];
}

function onFrame(ev) {
  ST.last = ev;
  const now = performance.now();
  ST.stamps.push(now); while (ST.stamps.length && ST.stamps[0] < now - 3000) ST.stamps.shift();
  if (ev.crossings?.length) {
    ev.crossings.forEach(c => ST.cross.unshift({ ...c, at: (ev.ts || "").slice(11, 19) }));
    ST.cross.length = Math.min(ST.cross.length, CROSS_MAX);
    $("#admincross").innerHTML = ST.cross.map(c => `<li><b>${esc(c.at)}</b><span>#${esc(c.id)} ${c.dir === "out" ? "배식대 통과 →" : "← 되돌아감"}</span></li>`).join("");
  }
  hud(); draw();
}

function hud(stale = false) {
  const ev = ST.last, fps = ST.stamps.length ? Math.round(ST.stamps.length / 3) : null;
  $("#streamfps").textContent = ev && !stale ? (fps ?? ev.fps ?? "—") : "—";
  const chip = $("#streamchip");
  chip.textContent = ST.mode === "off" ? "꺼짐" : stale ? "프레임 없음 — vision/mock 이 --meta 로 도는지" : ev ? `${ev.state === "ok" ? "정상" : esc(ev.state)} · 추론 ${ev.infer_ms ?? "—"}ms` : "연결 중…";
  chip.className = "chip " + (ST.mode === "off" ? "" : stale || !ev ? "melon" : ev.state === "ok" ? "teal" : "melon");
  $("#streamwell").innerHTML = ev && !stale
    ? tile(ev.infer_ms, "ms", "추론") + tile(ev.tracks?.length ?? 0, "명", "트랙") + tile(ev.roi_count, "명", "ROI 안")
      + tile(ev.rate_per_min, "/분", "처리율 λ") + tile(ev.wait_min ?? "—", "분", "예상 대기") + tile(`${esc(ev.source ?? "?")}·${esc(ev.model ?? "?")}`, "", "소스 · 모델")
    : "";
}

function badge() {
  const b = $("#streambadge"), st = ST.state;
  if (ST.mode === "off") { b.hidden = true; return; }
  b.hidden = false;
  if (ST.mode === "mjpeg") {
    const rem = st?.until ? Math.max(0, Math.round((new Date(st.until) - Date.now()) / 1000)) : 0;
    b.className = "badge melon"; b.textContent = `실사 · ${mmss(rem)} 남음`;
    // 서버가 껐으면(자동 종료·다른 관리자·lockdown) 실사 모드를 떠난다 — 곱게 끝난 multipart 는 <img> error 를 내지 않아 마지막 프레임이 남는다
    if (rem === 0 || (st && st.state !== "on")) { setMode("meta"); toast("실사 스트림이 종료됐습니다"); }
  } else { b.className = "badge"; b.textContent = `메타 · ${ST.state?.meta?.subscribers ?? "?"}명 구독`; }
}

function draw() {
  const c = $("#streamcanvas"); if (!c || !c.clientWidth) return;
  const { g, w, h } = fit(c, c.clientHeight || Math.round(c.clientWidth * 9 / 16));
  const ev = ST.last, tracks = ev?.tracks || [];
  if (ST.mode === "off") return;
  if (ST.mode === "meta" && ST.view === "plan") {
    const G = geom(w, h);
    drawFloor(g, G);
    if (ST.zones) drawZones(g, G, ST.zones, {});
    drawMarkers(g, G, tracks.map(t => ({ x: t.floor_xy_norm[0], y: t.floor_xy_norm[1] })));
    g.font = `700 ${Math.max(8, 8.5 * G.u)}px system-ui, sans-serif`; g.fillStyle = "#33312D"; g.textAlign = "center";
    tracks.forEach(t => { const [x, y] = G.P(t.floor_xy_norm[0], t.floor_xy_norm[1]); g.fillText(t.id, x, y - 7 * G.u); });
    return;
  }
  // 프레임 뷰(합성 배경) 또는 실사 위 오버레이(투명)
  if (ST.mode === "meta") {
    g.fillStyle = "#2B2A27"; g.fillRect(0, 0, w, h);
    g.strokeStyle = "rgba(255,252,246,.12)"; g.lineWidth = 1;
    for (let i = 1; i < 4; i++) { g.beginPath(); g.moveTo(0, h * i / 4); g.lineTo(w, h * i / 4); g.stroke(); }
  }
  g.font = "700 11px system-ui, sans-serif"; g.textAlign = "left";
  tracks.forEach(t => {
    const [x0, y0, x1, y1] = t.bbox_norm;
    const X = x0 * w, Y = y0 * h, W = (x1 - x0) * w, H = (y1 - y0) * h;
    g.lineWidth = 2; g.strokeStyle = t.in_roi ? "#0C6D6A" : "rgba(255,252,246,.75)"; g.strokeRect(X, Y, W, H);
    g.fillStyle = t.in_roi ? "#0C6D6A" : "rgba(51,49,45,.8)"; g.fillRect(X, Y - 14, 30, 14);
    g.fillStyle = "#FFFCF6"; g.fillText(t.id, X + 3, Y - 3);
    const [fx, fy] = t.foot_xy_norm;
    g.beginPath(); g.arc(fx * w, fy * h, 3.5, 0, Math.PI * 2); g.fillStyle = "#F6C445"; g.fill();
  });
}

export default function (MB) {
  build(MB);
  MB.ORDER.push("admin"); MB.NAMES.admin = "관리";
  MB.screens.admin = {
    every: 30000,
    async poll() { await Promise.all([loadServices(), loadStreamState()]); if ($("#adminfollow").getAttribute("aria-pressed") === "true") loadLog(); },
    async slow() { if ($("#auditfold").open) loadAudit(); if ($("#logfold").open) loadLog(); loadZones(); zonesEditor.load(); },     // 편집 중(더티)이면 편집기는 다시 읽지 않는다
    deactivate() { if (ST.mode !== "off") setMode("off", { keepFlag: true }); },   // 화면을 떠나면 클라이언트 쪽 스트림은 모두 끊는다(플래그는 타이머가)
    render(cardId, data) { if (cardId === "svccard") loadServices(); },
  };
  MB.observe?.("admin");           // 데스크톱 스크롤 스파이에 이 화면의 카드도 넣는다
  MB.poll("admin", true);          // core 의 부팅 폴링은 이미 지나갔다 — 등록 직후 한 번 강제로(poll + slow)
  if (MB.wanted === "admin") MB.go("admin", { push: false });   // #admin 으로 열었는데 부팅 때는 이 화면이 없어 #wait 로 갔다면 되돌린다
}

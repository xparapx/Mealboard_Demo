/* 관리 화면 — 관리 origin(8101 / Serve 8443)에서만 실린다. core.js 가 /api/admin/whoami 200 을 보고 import('/admin-ui/admin.js') 한 뒤
   default(MB) 를 부른다. 여기서 여섯 번째 화면(#admin)을 등록한다: dock·레일 버튼, 섹션, 카드 4장(서비스 상태 · 원샷 작업 · 로그 테일 · 감사 로그),
   확인 대화상자. 디자인 컨셉은 v5 그대로 — 틸=정상, 멜론=경고·파괴적, 차콜=구조, 옐로 금지 (PLAN §4.5). 3c(스트림)·3d(구역 편집기)가 카드를 더한다 */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const UNITS = ["api", "mock", "vision", "admin", "neis", "news", "rollup", "report"];
const RESTARTABLE = ["api", "mock", "vision"];
const JOBS = [["neis", "NEIS 재수신"], ["news", "뉴스 재수신"], ["rollup", "집계 재실행"], ["report", "리포트 재생성"]];
const age = s => s == null ? "—" : s < 90 ? `${s}초` : s < 5400 ? `${Math.round(s / 60)}분` : `${(s / 3600).toFixed(1)}시간`;

async function api(path, body) {
  const r = await fetch("/api/admin" + path, body === undefined ? { cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch {}
  return { ok: r.ok, status: r.status, j };
}

/* 확인 대화상자 — Promise<boolean>. 파괴적이면 확인 버튼이 멜론 채움 */
function confirm({ title, body, ok = "확인", danger = false }) {
  const d = $("#adminconfirm");
  d.querySelector("h3").textContent = title; d.querySelector("p").textContent = body;
  const okb = d.querySelector("button.ok"); okb.textContent = ok; okb.classList.toggle("danger", danger);
  return new Promise(res => {
    d.returnValue = ""; d.showModal();
    d.addEventListener("close", () => res(d.returnValue === "ok"), { once: true });
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
  <section class="card" id="logcard">
    <div class="eyebrow">로그 테일</div>
    <div class="logbar"><select id="adminunit">${UNITS.map(u => `<option value="mealboard-${u}">${u}</option>`).join("")}</select>
      <button type="button" class="pill ghost" id="adminfollow" aria-pressed="false">따라가기</button></div>
    <pre class="log" id="adminlog">—</pre>
  </section>
  <section class="card" id="auditcard">
    <div class="eyebrow">감사 로그</div>
    <ul class="log" id="adminaudit"></ul>
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
    toast(r.ok ? `${label} 시작` : `실패 (${r.status}) ${esc(r.j?.detail?.stderr || r.j?.reason || "")}`, !r.ok);
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
    toast(r.ok ? `${svc} 재시작 요청` : `실패 (${r.status}) ${esc(r.j?.detail?.stderr || r.j?.reason || "")}`, !r.ok);
    setTimeout(loadServices, 3000); loadAudit();
  });
  $("#adminunit").addEventListener("change", loadLog);
  $("#adminfollow").addEventListener("click", e => { const on = e.target.getAttribute("aria-pressed") !== "true"; e.target.setAttribute("aria-pressed", on); if (on) loadLog(); });
}

function toast(text, bad) {
  let t = $("#admintoast"); if (!t) { document.body.insertAdjacentHTML("beforeend", '<div id="admintoast" role="status"></div>'); t = $("#admintoast"); }
  t.textContent = text; t.classList.toggle("bad", !!bad); t.classList.add("on"); clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("on"), 3500);
}

async function loadServices() {
  const [w, s] = await Promise.all([api("/whoami"), api("/services")]);
  if (w.ok) { $("#adminwho").textContent = `${w.j.user} · ${w.j.via === "tailscale" ? "tailnet" : "SSH 터널"}`; $("#adminlock").hidden = !w.j.lockdown; }
  if (!s.ok) { $("#adminfoot").textContent = `상태를 읽지 못했습니다 (${s.status})`; return; }
  const h = s.j.health || {};
  const tile = (v, unit, label, warn) => `<div${warn ? " data-warn" : ""}><b>${v ?? "—"}<i>${unit}</i></b><span>${label}</span></div>`;
  $("#adminwell").innerHTML = tile(age(h.db_age_s), "", "DB 최신 행", h.db_age_s == null || h.db_age_s > 120)
    + tile(h.disk?.free_gb, "GB", "디스크 여유", h.disk && h.disk.used_pct > 90) + tile(h.temp_c, "°C", "온도", h.temp_c > 75)
    + tile(h.ntp == null ? "—" : h.ntp ? "동기" : "어긋남", "", "시간 동기(NTP)", h.ntp === false);
  $("#adminunits").innerHTML = s.j.units.map(u => {
    const name = u.unit.replace("mealboard-", ""), ok = u.active === "active", off = u.active === "unknown";
    return `<li><b>${name}</b><em class="${ok ? "teal" : off ? "mute" : "melon"}">${esc(u.active)}${u.sub ? " · " + esc(u.sub) : ""}</em>`
      + (u.restarts ? `<small>재시작 ${u.restarts}회</small>` : "")
      + (RESTARTABLE.includes(name) ? `<button type="button" class="pill ghost small" data-restart="${name}">재시작</button>` : "") + "</li>";
  }).join("");
  $("#adminfoot").textContent = `코드 ${h.git || "?"} · 가동 ${age(h.uptime_s)} · 위치 파일 ${age(h.positions_age_s)} 전 · 급식 창 ${Math.floor(s.j.lunch.lo / 60)}:${String(s.j.lunch.lo % 60).padStart(2, "0")}~${Math.floor(s.j.lunch.hi / 60)}:${String(s.j.lunch.hi % 60).padStart(2, "0")}`;
}

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

export default function (MB) {
  build(MB);
  MB.ORDER.push("admin"); MB.NAMES.admin = "관리";
  MB.screens.admin = {
    every: 30000,
    async poll() { await loadServices(); if ($("#adminfollow").getAttribute("aria-pressed") === "true") loadLog(); },
    async slow() { loadAudit(); loadLog(); },
    render(cardId, data) { if (cardId === "svccard") loadServices(); },
  };
}

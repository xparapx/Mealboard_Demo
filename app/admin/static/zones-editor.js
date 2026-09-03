/* 구역 편집기(3d) — 관리 화면 카드 한 장. 평면도 모드에서 구역 폴리곤을, 프레임 모드에서 ROI(λ 변·출구 방향)와 보정 4점(호모그래피)을 편집한다.
   저장은 PUT /api/admin/zones → 서버가 검증해 data/zones.local.json 에만 쓴다(템플릿은 그대로, 직전 판 .bak 5개).
   실사 프레임 스냅은 <img>(mjpeg) 를 캔버스에 복사한 브라우저 메모리뿐 — 어디에도 저장·전송되지 않는다.
   캔버스는 touch-action:none, 꼭짓점 핸들 r6 / 히트 반경 22px(지름 44). 틸=선택·정상, 멜론=ROI·λ·파괴적, 옐로 금지 (PLAN §4.5) */
import { fit } from "/js/core.js";
import { drawFloor, drawZones, geom } from "/js/floor.js";

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const HIT = 22, HANDLE = 6, IMG_W = 1280;
const clamp01 = v => Math.min(1, Math.max(0, v));
const r3 = v => Math.round(v * 1000) / 1000;
const copy = o => JSON.parse(JSON.stringify(o));
const TEAL = "#0C6D6A", MELON = "#C2452D", MELON_TINT = "rgba(194,69,45,.22)", PAPER = "#FFFCF6", INK = "#33312D";

let D = null;                      // deps: {api, confirm, toast, lastFrame, streamImg, onSaved}
const Z = { doc: null, orig: null, info: null, dirty: false, mode: "floor", sel: null, vsel: null, drag: null, place: null, snap: null, calib: [], hres: null };

/* ---------------- 기하 ---------------- */
function pip(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
  const t = Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / l2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function inv3(h) {
  const [[a, b, c], [d, e, f], [g, k, i]] = h;
  const det = a * (e * i - f * k) - b * (d * i - f * g) + c * (d * k - e * g);
  if (Math.abs(det) < 1e-12) return null;
  return [[(e * i - f * k) / det, (c * k - b * i) / det, (b * f - c * e) / det],
          [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
          [(d * k - e * g) / det, (b * g - a * k) / det, (a * e - b * d) / det]];
}
function proj(h, u, v) {
  const w = h[2][0] * u + h[2][1] * v + h[2][2];
  return Math.abs(w) < 1e-12 ? null : [(h[0][0] * u + h[0][1] * v + h[0][2]) / w, (h[1][0] * u + h[1][1] * v + h[1][2]) / w];
}

/* ---------------- 선택 대상 ---------------- */
function target() {
  if (!Z.doc || !Z.sel) return null;
  if (Z.sel.kind === "zone") return Z.doc.zones[Z.sel.i] || null;
  if (Z.sel.kind === "roi") return Z.doc.roi;
  return null;
}
function polyOf() { const t = target(); return t ? t.polygon : null; }

/* ---------------- 좌표 변환 ---------------- */
function mapping(w, h) {
  if (Z.mode === "floor") {
    const G = geom(w, h), p00 = G.P(0, 0), p11 = G.P(1, 1);
    return { G, toS: (x, y) => G.P(x, y), toN: (sx, sy) => [clamp01((p00[0] - sx) / (p00[0] - p11[0])), clamp01((sy - p00[1]) / (p11[1] - p00[1]))] };
  }
  return { G: null, toS: (u, v) => [u * w, v * h], toN: (sx, sy) => [clamp01(sx / w), clamp01(sy / h)] };
}

/* ---------------- 그리기 ---------------- */
function draw() {
  const c = $("#zcanvas"); if (!c || !c.clientWidth) return;
  const { g, w, h } = fit(c, c.clientHeight || Math.round(c.clientWidth * 9 / 16));
  if (!Z.doc) { g.fillStyle = "#2B2A27"; g.fillRect(0, 0, w, h); return; }
  const M = mapping(w, h);
  const poly = polyOf();
  if (Z.mode === "floor") {
    drawFloor(g, M.G);
    drawZones(g, M.G, Z.doc.zones.map(z => ({ id: z.id, label: z.name, polygon: z.polygon })), {});
    const fr = D.lastFrame?.();                                     // 메타 스트림의 바닥 점 — 정렬 확인용(그리기만, 보관 없음)
    (fr?.tracks || []).forEach(t => { const [sx, sy] = M.toS(...t.floor_xy_norm); g.beginPath(); g.arc(sx, sy, 3, 0, Math.PI * 2); g.fillStyle = "#F6C445"; g.fill(); });
  } else {
    if (Z.snap) g.drawImage(Z.snap, 0, 0, w, h);
    else { g.fillStyle = "#2B2A27"; g.fillRect(0, 0, w, h); }
    const fr = D.lastFrame?.();
    (fr?.tracks || []).forEach(t => { const [x0, y0, x1, y1] = t.bbox_norm; g.lineWidth = 1; g.strokeStyle = "rgba(255,252,246,.45)"; g.strokeRect(x0 * w, y0 * h, (x1 - x0) * w, (y1 - y0) * h); });
    const H = Z.doc.image_to_floor, Hi = H && inv3(H);
    if (Hi) Z.doc.zones.forEach(z => {                              // 바닥 구역을 프레임 위에 — 보정이 맞는지 눈으로
      g.beginPath();
      z.polygon.forEach(([x, y], i) => { const p = proj(Hi, x, y); if (!p) return; const [sx, sy] = M.toS(...p); (i ? g.lineTo : g.moveTo).call(g, sx, sy); });
      g.closePath(); g.strokeStyle = "rgba(12,109,106,.7)"; g.lineWidth = 1.5; g.setLineDash([5, 4]); g.stroke(); g.setLineDash([]);
    });
    const roi = Z.doc.roi;
    if (roi) {
      g.beginPath(); roi.polygon.forEach(([u, v], i) => { const [sx, sy] = M.toS(u, v); (i ? g.lineTo : g.moveTo).call(g, sx, sy); }); g.closePath();
      g.fillStyle = MELON_TINT; g.fill(); g.strokeStyle = MELON; g.lineWidth = 2; g.stroke();
      const [i, j] = roi.lambda_edge, a = M.toS(...roi.polygon[i]), b = M.toS(...roi.polygon[j]);
      const band = (Z.doc.buffer_px ?? 20) * w / (D.lastFrame?.()?.img_w || IMG_W);
      g.save(); g.globalAlpha = .35; g.strokeStyle = MELON; g.lineWidth = band * 2; g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke(); g.restore();
      g.strokeStyle = PAPER; g.lineWidth = 3; g.beginPath(); g.moveTo(...a); g.lineTo(...b); g.stroke();
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1;
      const nx = -dy / L * roi.out_dir, ny = dx / L * roi.out_dir;                 // out_dir=1: i→j 의 왼쪽이 출구
      g.strokeStyle = PAPER; g.lineWidth = 2; g.beginPath(); g.moveTo(mx, my); g.lineTo(mx + nx * 22, my + ny * 22); g.stroke();
      g.font = "700 11px system-ui, sans-serif"; g.fillStyle = PAPER; g.fillText("λ → 출구", mx + nx * 26, my + ny * 26);
    }
    Z.calib.forEach((p, k) => {
      if (!p.img) return;
      const [sx, sy] = M.toS(...p.img);
      g.beginPath(); g.arc(sx, sy, 9, 0, Math.PI * 2); g.fillStyle = TEAL; g.fill(); g.strokeStyle = PAPER; g.lineWidth = 2; g.stroke();
      g.font = "700 11px system-ui, sans-serif"; g.fillStyle = PAPER; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(k + 1), sx, sy); g.textBaseline = "alphabetic";
    });
  }
  if (poly) {                                                       // 선택된 폴리곤 — 굵은 외곽선 + 핸들
    g.beginPath(); poly.forEach((p, i) => { const [sx, sy] = M.toS(...p); (i ? g.lineTo : g.moveTo).call(g, sx, sy); }); g.closePath();
    g.strokeStyle = Z.sel.kind === "roi" ? MELON : TEAL; g.lineWidth = 2.5; g.stroke();
    poly.forEach((p, i) => {
      const [sx, sy] = M.toS(...p);
      g.beginPath(); g.arc(sx, sy, HANDLE, 0, Math.PI * 2); g.fillStyle = i === Z.vsel ? MELON : PAPER; g.fill();
      g.strokeStyle = Z.sel.kind === "roi" ? MELON : TEAL; g.lineWidth = 2; g.stroke();
    });
  }
  const hint = $("#zhint");
  hint.hidden = !Z.place;
  hint.textContent = Z.place === "lambda" ? "λ 변이 될 변을 누르세요" : Z.place?.calib != null ? `보정점 ${Z.place.calib + 1} 위치를 누르세요` : "";
}

/* ---------------- 포인터 ---------------- */
function onDown(e) {
  if (!Z.doc) return;
  const c = e.currentTarget, r = c.getBoundingClientRect(), sx = e.clientX - r.left, sy = e.clientY - r.top;
  const M = mapping(r.width, r.height);
  c.setPointerCapture(e.pointerId);
  if (Z.place === "lambda" && Z.doc.roi && Z.mode === "image") {
    const P = Z.doc.roi.polygon; let best = null;
    P.forEach((p, i) => { const q = P[(i + 1) % P.length], a = M.toS(...p), b = M.toS(...q), d = segDist(sx, sy, ...a, ...b); if (d < 20 && (!best || d < best.d)) best = { i, d }; });
    if (best) { Z.doc.roi.lambda_edge = [best.i, (best.i + 1) % P.length]; Z.place = null; dirty(); fields(); }
    draw(); return;
  }
  if (Z.place?.calib != null && Z.mode === "image") {
    const k = Z.place.calib; Z.calib[k] = { ...(Z.calib[k] || { m: [0, 0] }), img: M.toN(sx, sy).map(r3) };
    Z.place = null; fields(); draw(); return;
  }
  const poly = polyOf();
  if (poly) {
    let hit = -1, hd = HIT;
    poly.forEach((p, i) => { const [x, y] = M.toS(...p), d = Math.hypot(x - sx, y - sy); if (d < hd) { hd = d; hit = i; } });
    if (hit >= 0) { Z.vsel = hit; Z.drag = { vi: hit }; draw(); return; }
  }
  const [nx, ny] = M.toN(sx, sy);
  if (Z.mode === "floor") {
    const i = Z.doc.zones.findIndex(z => pip(nx, ny, z.polygon));
    Z.sel = i >= 0 ? { kind: "zone", i } : null;
  } else Z.sel = Z.doc.roi && pip(nx, ny, Z.doc.roi.polygon) ? { kind: "roi" } : null;
  Z.vsel = null; chips(); fields(); draw();
}
function onMove(e) {
  if (!Z.drag) return;
  const c = e.currentTarget, r = c.getBoundingClientRect(), M = mapping(r.width, r.height);
  const poly = polyOf(); if (!poly) return;
  poly[Z.drag.vi] = M.toN(e.clientX - r.left, e.clientY - r.top).map(r3);
  dirty(); draw();
}
function onUp() { Z.drag = null; }

/* ---------------- 편집 동작 ---------------- */
function dirty() {
  Z.dirty = true;
  $("#zdirty").hidden = false; $("#zsave").disabled = false; $("#zreset").disabled = false;
}
function clean() {
  Z.dirty = false;
  $("#zdirty").hidden = true; $("#zsave").disabled = true; $("#zreset").disabled = true;
}
function addVertex() {
  const poly = polyOf(); if (!poly) return;
  const i = Z.vsel ?? poly.length - 1, j = (i + 1) % poly.length;
  poly.splice(i + 1, 0, [r3((poly[i][0] + poly[j][0]) / 2), r3((poly[i][1] + poly[j][1]) / 2)]);
  if (Z.sel.kind === "roi") Z.doc.roi.lambda_edge = [0, 1];
  Z.vsel = i + 1; dirty(); fields(); draw();
}
function delVertex() {
  const poly = polyOf(); if (!poly || poly.length <= 3 || Z.vsel == null) { D.toast("꼭짓점은 3개 이상 · 먼저 핸들을 고르세요", true); return; }
  poly.splice(Z.vsel, 1);
  if (Z.sel.kind === "roi") Z.doc.roi.lambda_edge = [0, 1];
  Z.vsel = null; dirty(); fields(); draw();
}
function addZone() {
  const n = Z.doc.zones.length + 1;
  Z.doc.zones.push({ id: `zone_${n}`, name: `구역 ${n}`, polygon: [[0.3, 0.4], [0.7, 0.4], [0.7, 0.6], [0.3, 0.6]] });
  Z.sel = { kind: "zone", i: Z.doc.zones.length - 1 }; Z.vsel = null; dirty(); chips(); fields(); draw();
}
async function delZone() {
  const z = target(); if (!z) return;
  if (!await D.confirm({ title: `${z.name} 삭제`, body: "구역 정의에서 지웁니다. 저장 전까지는 되돌리기로 복구할 수 있습니다.", ok: "삭제", danger: true })) return;
  Z.doc.zones.splice(Z.sel.i, 1); Z.sel = null; dirty(); chips(); fields(); draw();
}
function addRoi() {
  Z.doc.roi = { polygon: [[0.25, 0.55], [0.75, 0.55], [0.75, 0.95], [0.25, 0.95]], lambda_edge: [0, 1], out_dir: 1 };
  Z.sel = { kind: "roi" }; Z.vsel = null; dirty(); chips(); fields(); draw();
}
async function delRoi() {
  if (!await D.confirm({ title: "ROI 삭제", body: "ROI 와 λ 변을 지웁니다. vision 은 ROI 없이는 대기 인원을 세지 못합니다.", ok: "삭제", danger: true })) return;
  Z.doc.roi = null; Z.sel = null; dirty(); chips(); fields(); draw();
}
function presets() {
  const { width_m: W, length_m: L } = Z.doc.floor, A = 2.2;
  return [["원점 — 배식구 벽 ∧ 창가 통로", 0, 0], ["배식구 벽 ∧ 반대쪽 벽", W, 0], ["출입문 벽 ∧ 창가 통로", 0, L], ["출입문 벽 ∧ 반대쪽 벽", W, L],
          ["통로 경계 · 배식구 쪽", A, 0], ["통로 경계 · 출입문 쪽", A, L]];
}
function snapFrame() {
  const img = D.streamImg?.();
  if (!img || !img.naturalWidth || img.hidden) { D.toast("스트림 패널에서 실사를 먼저 켜세요 — 그 프레임을 캔버스에 복사합니다", true); return; }
  const s = document.createElement("canvas"); s.width = img.naturalWidth; s.height = img.naturalHeight;
  s.getContext("2d").drawImage(img, 0, 0);
  Z.snap = s; draw(); D.toast("프레임을 잡았습니다 — 브라우저 메모리에만");
}
async function computeH() {
  if (Z.calib.filter(p => p?.img).length < 4) { D.toast("보정점 4개를 모두 찍으세요", true); return; }
  const { width_m: W, length_m: L } = Z.doc.floor;
  const pairs = Z.calib.map(p => ({ img: p.img, floor: [r3(clamp01(p.m[0] / W)), r3(clamp01(p.m[1] / L))] }));
  const r = await D.api("/zones/homography", { pairs });
  if (!r.ok) { D.toast(`계산 실패: ${(r.j?.detail?.errors || []).join(" · ") || r.status}`, true); return; }
  Z.hres = r.j;
  if (!r.j.ok) { fields(); D.toast(`오차 ${r.j.reproj_err} ≥ ${r.j.tol} — 점을 다시 찍으세요 (문서에 넣지 않음)`, true); return; }   // 저장하면 422 가 될 H 는 넣지 않는다
  Z.doc.image_to_floor = r.j.image_to_floor; Z.doc.calib_points = pairs;
  dirty(); fields(); draw();
  D.toast(`호모그래피 계산 — 재투영 오차 ${r.j.reproj_err}`);
}
function clearH() { Z.doc.image_to_floor = null; Z.doc.calib_points = null; Z.hres = null; dirty(); fields(); draw(); }

/* ---------------- 카드 조립 ---------------- */
function chips() {
  const el = $("#zchips"); if (!Z.doc) { el.innerHTML = ""; return; }
  if (Z.mode === "floor")
    el.innerHTML = Z.doc.zones.map((z, i) => `<button type="button" class="pill small ghost" data-zsel="${i}" aria-pressed="${Z.sel?.kind === "zone" && Z.sel.i === i}">${esc(z.name)}</button>`).join("")
      + '<button type="button" class="pill small ghost" data-zadd="zone">＋ 구역</button>';
  else
    el.innerHTML = (Z.doc.roi ? `<button type="button" class="pill small ghost" data-zsel="roi" aria-pressed="${Z.sel?.kind === "roi"}">ROI · λ</button>` : '<button type="button" class="pill small ghost" data-zadd="roi">＋ ROI</button>')
      + `<button type="button" class="pill small ghost" data-zsel="calib" aria-pressed="${Z.sel?.kind === "calib"}">보정 4점${Z.doc.image_to_floor ? " ✓" : ""}</button>`
      + '<button type="button" class="pill small ghost" data-zsnap="1">프레임 잡기</button>';
}
function fields() {
  const el = $("#zfields"), t = target();
  if (!Z.doc) { el.innerHTML = ""; return; }
  if (Z.sel?.kind === "zone" && t)
    el.innerHTML = `<div class="zrow"><label>id <input id="zid" value="${esc(t.id)}" maxlength="16" pattern="[a-z][a-z0-9_]{0,15}"></label>
      <label>이름 <input id="zname" value="${esc(t.name)}" maxlength="20"></label></div>
      <div class="zrow"><button type="button" class="pill small ghost" data-zv="add">꼭짓점 추가</button><button type="button" class="pill small ghost" data-zv="del">꼭짓점 삭제</button>
      <button type="button" class="pill small danger" data-zdel="zone">구역 삭제</button><span class="note">꼭짓점 ${t.polygon.length}</span></div>`;
  else if (Z.sel?.kind === "roi" && t)
    el.innerHTML = `<div class="zrow"><button type="button" class="pill small ghost" data-zv="add">꼭짓점 추가</button><button type="button" class="pill small ghost" data-zv="del">꼭짓점 삭제</button>
      <button type="button" class="pill small ghost" data-zlambda="1" aria-pressed="${Z.place === "lambda"}">λ 변 선택</button><button type="button" class="pill small ghost" data-zflip="1">출구 방향 뒤집기</button>
      <button type="button" class="pill small danger" data-zdel="roi">ROI 삭제</button></div>
      <div class="note">λ 변 [${t.lambda_edge.join(", ")}] · out_dir ${t.out_dir} (${t.out_dir === 1 ? "i→j 의 왼쪽이 출구" : "오른쪽이 출구"}) · 완충 ${Z.doc.buffer_px ?? 20}px · 꼭짓점 ${t.polygon.length}</div>`;
  else if (Z.sel?.kind === "calib") {
    const P = presets();
    el.innerHTML = Z.calib.map((p, k) => `<div class="zrow calib"><b>${k + 1}</b><span class="note">${p?.img ? `이미지 (${p.img[0]}, ${p.img[1]})` : "이미지 —"}</span>
        <button type="button" class="pill small ghost" data-zpick="${k}" aria-pressed="${Z.place?.calib === k}">찍기</button>
        <label>x <input type="number" step="0.01" data-zm="${k}:0" value="${p?.m?.[0] ?? 0}">m</label><label>y <input type="number" step="0.01" data-zm="${k}:1" value="${p?.m?.[1] ?? 0}">m</label>
        <select data-zpre="${k}"><option value="">프리셋</option>${P.map(([n, x, y], i) => `<option value="${i}">${esc(n)} (${x}, ${y})</option>`).join("")}</select></div>`).join("")
      + `<div class="zrow"><button type="button" class="pill small" data-zh="calc">호모그래피 계산</button><button type="button" class="pill small ghost" data-zh="clear">보정 지우기</button>
        <span class="note">${Z.doc.image_to_floor ? `image_to_floor 있음${Z.hres ? ` · 재투영 오차 ${Z.hres.reproj_err}` : ""}` : "아직 보정 없음"}</span></div>`;
  } else el.innerHTML = `<div class="note">${Z.mode === "floor" ? "구역을 누르면 핸들이 나타납니다 · 핸들을 끌어 옮기고, 칩으로 구역을 고릅니다" : "ROI 를 만들거나 보정 4점을 찍으세요 · 실사를 켜고 '프레임 잡기' 로 배경을 가져올 수 있습니다"}</div>`;
}
function setMode(m) {
  Z.mode = m; Z.sel = null; Z.vsel = null; Z.place = null;
  document.querySelectorAll("#zmode [data-zmode]").forEach(b => b.setAttribute("aria-pressed", b.dataset.zmode === m));
  $("#zstage").classList.toggle("plan", m === "floor");
  chips(); fields(); draw();
}
function apply(info) {
  Z.info = info; Z.doc = copy(info.doc); Z.orig = copy(info.doc); Z.sel = null; Z.vsel = null; Z.place = null; Z.hres = null;
  const { width_m: W, length_m: L } = Z.doc.floor;
  Z.calib = (Z.doc.calib_points || [null, null, null, null]).map(p => p ? { img: p.img, m: [r3(p.floor[0] * W), r3(p.floor[1] * L)] } : { img: null, m: [0, 0] });
  while (Z.calib.length < 4) Z.calib.push({ img: null, m: [0, 0] });
  clean(); chips(); fields(); draw();
  $("#zinfo").textContent = `${info.local ? "zones.local.json " + (info.local_mtime || "").slice(5, 16).replace("T", " ") : "템플릿만(로컬 없음)"} · 백업 ${info.backups.length}개`
    + (Z.doc.updated_by ? ` · ${Z.doc.updated_by}` : "");
}

export async function load({ force = false } = {}) {
  if (Z.dirty && !force) return;
  const r = await D.api("/zones");
  if (!r.ok || r.j.state !== "ok") { $("#zinfo").textContent = r.j?.reason ? `읽지 못했습니다 — ${r.j.reason}` : `읽지 못했습니다 (${r.status})`; Z.doc = null; draw(); return; }
  apply(r.j);
}

async function save() {
  const r = await D.api("/zones", Z.doc, "PUT");
  if (!r.ok) { const errs = r.j?.detail?.errors; D.toast(errs ? `저장 거부 — ${errs[0]}${errs.length > 1 ? ` 외 ${errs.length - 1}` : ""}` : `저장 실패 (${r.status})`, true); if (errs) $("#zinfo").textContent = errs.join(" · "); return; }
  D.toast(`저장했습니다${r.j.backup ? " · 직전 판 " + r.j.backup.slice(-15) : ""}`);
  apply({ doc: r.j.doc, local: true, local_mtime: r.j.doc.updated_at, backups: r.j.backups });
  D.onSaved?.();
}

export function mount(deps) {
  D = deps;
  $("#streamcard").insertAdjacentHTML("afterend", `
  <section class="card" id="zoneeditcard">
    <div class="eyebrow">구역 편집기 <span class="dirty" id="zdirty" hidden>저장 안 됨</span></div>
    <div class="seg small" id="zmode" role="group" aria-label="편집 모드"><button type="button" data-zmode="floor" aria-pressed="true">평면도 · 구역</button><button type="button" data-zmode="image">프레임 · ROI · 보정</button></div>
    <div class="stage plan zstage" id="zstage"><canvas id="zcanvas"></canvas><span class="badge melon" id="zhint" hidden></span></div>
    <div class="zchips" id="zchips"></div>
    <div class="zfields" id="zfields"></div>
    <div class="zbar"><button type="button" class="pill" id="zsave" disabled>저장</button><button type="button" class="pill ghost" id="zreset" disabled>되돌리기</button><span class="note" id="zinfo">—</span></div>
    <div class="note foot">저장은 data/zones.local.json 에만(템플릿은 그대로) · 직전 판 .bak 5개 보존 · vision 은 파일 시각으로 2초 안에 다시 읽고 mock 은 재시작 때 읽는다 · 프레임 스냅은 브라우저 메모리뿐</div>
  </section>`);
  const c = $("#zcanvas");
  c.addEventListener("pointerdown", onDown); c.addEventListener("pointermove", onMove); c.addEventListener("pointerup", onUp); c.addEventListener("pointercancel", onUp);
  $("#zmode").addEventListener("click", e => { const b = e.target.closest("[data-zmode]"); if (b) setMode(b.dataset.zmode); });
  $("#zchips").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.zadd === "zone") addZone(); else if (b.dataset.zadd === "roi") addRoi(); else if (b.dataset.zsnap) snapFrame();
    else if (b.dataset.zsel === "roi") { Z.sel = { kind: "roi" }; Z.vsel = null; chips(); fields(); draw(); }
    else if (b.dataset.zsel === "calib") { Z.sel = { kind: "calib" }; Z.vsel = null; Z.place = null; chips(); fields(); draw(); }
    else if (b.dataset.zsel != null) { Z.sel = { kind: "zone", i: Number(b.dataset.zsel) }; Z.vsel = null; chips(); fields(); draw(); }
  });
  $("#zfields").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.zv === "add") addVertex(); else if (b.dataset.zv === "del") delVertex();
    else if (b.dataset.zdel === "zone") delZone(); else if (b.dataset.zdel === "roi") delRoi();
    else if (b.dataset.zlambda) { Z.place = Z.place === "lambda" ? null : "lambda"; fields(); draw(); }
    else if (b.dataset.zflip) { Z.doc.roi.out_dir = -Z.doc.roi.out_dir; dirty(); fields(); draw(); }
    else if (b.dataset.zpick != null) { const k = Number(b.dataset.zpick); Z.place = Z.place?.calib === k ? null : { calib: k }; fields(); draw(); }
    else if (b.dataset.zh === "calc") computeH(); else if (b.dataset.zh === "clear") clearH();
  });
  $("#zfields").addEventListener("input", e => {
    const t = e.target, z = target();
    if (t.id === "zid" && z) { z.id = t.value.trim(); dirty(); chips(); }
    else if (t.id === "zname" && z) { z.name = t.value; dirty(); chips(); }
    else if (t.dataset.zm) { const [k, i] = t.dataset.zm.split(":").map(Number); Z.calib[k].m[i] = Number(t.value) || 0; }
  });
  $("#zfields").addEventListener("change", e => {
    const t = e.target; if (!t.dataset.zpre || t.value === "") return;
    const [, x, y] = presets()[Number(t.value)], k = Number(t.dataset.zpre);
    Z.calib[k].m = [x, y]; fields();
  });
  $("#zsave").addEventListener("click", save);
  $("#zreset").addEventListener("click", () => { Z.doc = copy(Z.orig); Z.sel = null; Z.vsel = null; Z.place = null; Z.hres = null; clean(); apply({ ...Z.info, doc: Z.orig }); });
  new ResizeObserver(() => draw()).observe($("#zstage"));
  return { load, draw, state: () => Z };
}

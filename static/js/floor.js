/* 급식실 평면도 그리기 — 공용. 급식실 현황 카드(마커)와 구역 점유율 카드(구역 틴트)가 같은 평면도를 쓴다.
   실측 기반 탑뷰(세로형) — 방 15.55m(폭 x) × 24.65m(길이 y), 원점 = 배식구 벽 ∧ 창가 통로 구석.
   /api/positions 와 zones.json 의 x,y 는 이 바닥의 0~1 정규화 값 — 같은 좌표계.
   화면 방향은 확정 도면(docs/layout.html): 배식대 위(카메라는 그 오른쪽 끝) · 퇴식구→출구 왼쪽(위부터) ·
   대기통로(창가) 오른쪽 · 입구 아래(통로 쪽). 투영: sx=(W−x)·k, sy=y·k — 왜곡 없음.
   테이블 6열 × [6인×3 | 6인×2 | 6인×4+4인], 의자는 도면 기호처럼 테이블 가장자리에 살짝만.
   여기 함수들은 캔버스 컨텍스트 g 와 geom 만 받는다 — DOM 을 모른다 */

import { SUNSETDARK, ramp } from "./colors.js";

export const ROOM = { W: 15.55, D: 24.65, H: 2.68 };
const GAP = { door: [0.2, 3.2], dish: [1.6, 4.4], exit: [5.6, 8.4] };   // 입구(아래 벽, 통로 쪽) · 퇴식구·출구(좌측 벽, 위부터)

/* 캔버스 크기(W,H, CSS px) → 투영 도구. u = 318px 기준 배율, k = m → px, X/Y = 세계좌표 → 화면 */
export function geom(W, H) {
  const u = W / 318;
  const ML = 50 * u, MR = 10 * u, MT = 22 * u, MB = 8 * u;          // 좌측은 퇴식구·출구 라벨 자리
  const k = Math.min((W - ML - MR) / ROOM.W, (H - MT - MB) / ROOM.D);
  const ox = ML + (W - ML - MR - ROOM.W * k) / 2;
  const oy = MT + (H - MT - MB - ROOM.D * k) / 2;
  return { W, H, u, k, T: Math.max(3, .45 * k), fu: Math.min(u, 1.35),   // fu = 글자 배율 상한 — 관리 편집기의 큰 캔버스에서도 사용자 앱과 같은 글자 크기(09-04)
           X: x => ox + (ROOM.W - x) * k, Y: y => oy + y * k,
           P: (nx, ny) => [ox + (ROOM.W - nx * ROOM.W) * k, oy + ny * ROOM.D * k] };   // 정규화 0~1 → 화면
}

/* 정적 평면도 — 바닥·타일·벽·개구부·배식대·싱크대·테이블·라벨 */
export function drawFloor(g, G) {
  const { u, k, T, X, Y } = G;
  const rect = (y0, x0, dy, dx, r, fill) => {                       // 세계 y0..y0+dy × x0..x0+dx
    g.beginPath(); g.roundRect(X(x0 + dx), Y(y0), dx * k, dy * k, r);
    g.fillStyle = fill; g.fill();
  };
  // 바닥 + 통로 띠(우측) + 타일 줄눈
  rect(0, 0, ROOM.D, ROOM.W, 10 * u, "#FBF8F0");
  rect(0, 0, ROOM.D, 2.2, 0, "rgba(51,49,45,.05)");
  g.strokeStyle = "rgba(51,49,45,.045)"; g.lineWidth = 1;
  for (let ty = 2.5; ty < ROOM.D; ty += 2.5) {
    g.beginPath(); g.moveTo(X(ROOM.W), Y(ty)); g.lineTo(X(0), Y(ty)); g.stroke();
  }
  for (let tx = 2.65; tx < ROOM.W; tx += 2.65) {
    g.beginPath(); g.moveTo(X(tx), Y(0)); g.lineTo(X(tx), Y(ROOM.D)); g.stroke();
  }
  // 벽 네 변 — 두께 띠. 개구부: 배식구 벽(위) · 퇴식구→출구(좌) · 창(우, 하늘빛) · 입구(아래, 통로 쪽)
  g.fillStyle = "#E3DCC9";
  g.fillRect(X(ROOM.W) - T, Y(0) - T, ROOM.W * k + 2 * T, T);        // 위 (y=0 배식구 벽) — 좌우 벽 두께까지 늘려 모서리를 채운다
  g.fillRect(X(ROOM.W) - T, Y(ROOM.D), ROOM.W * k + 2 * T, T);       // 아래 (y=D 출입문 벽) — 위와 같이
  g.fillRect(X(ROOM.W) - T, Y(0), T, ROOM.D * k);                    // 좌 (x=W 벽)
  g.fillRect(X(0), Y(0), T, ROOM.D * k);                             // 우 (x=0 창가 벽)
  g.fillStyle = "#B9DBD9";                                          // 입구 (아래 벽, 통로 쪽)
  g.fillRect(X(GAP.door[1]), Y(ROOM.D), (GAP.door[1] - GAP.door[0]) * k, T);
  g.fillStyle = "#CFC9B8";                                          // 퇴식구 (좌측, 위부터)
  g.fillRect(X(ROOM.W) - T, Y(GAP.dish[0]), T, (GAP.dish[1] - GAP.dish[0]) * k);
  g.fillStyle = "#B9DBD9";                                          // 출구 (퇴식구 아래)
  g.fillRect(X(ROOM.W) - T, Y(GAP.exit[0]), T, (GAP.exit[1] - GAP.exit[0]) * k);
  g.fillStyle = "#D9E7EE";                                          // 창 (우측 벽 세 칸)
  [[2.6, 7.4], [9.2, 14], [15.8, 20.6]].forEach(([a, b]) =>
    g.fillRect(X(0), Y(a), T, (b - a) * k));
  // 배식대 — 위 벽 안쪽의 긴 카운터 (카메라는 그 오른쪽 끝, 통로 쪽 구석)
  rect(0.15, 1.5, 0.85, 12.0, 3 * u, "#FFD9D0");
  g.strokeStyle = "#F0A897"; g.lineWidth = 1;
  g.strokeRect(X(13.5), Y(0.15), 12.0 * k, 0.85 * k);
  // 퇴식구 싱크대 — 좌측 벽 안쪽의 회색 카운터 (배식대와 같은 표기법)
  rect(1.4, ROOM.W - 0.97, 3.2, 0.85, 3 * u, "#E4DFD3");
  g.strokeStyle = "#C7C0AE"; g.lineWidth = 1;
  g.strokeRect(X(ROOM.W - 0.12), Y(1.4), 0.85 * k, 3.2 * k);
  // 테이블 6열(세로) — 흰 상판 + 도면 기호식 의자(양옆에 살짝)
  const pitch = 1.8, x0 = 3.2, tw = 0.82;
  const blocks = [[1.8, 1.8, 1.8], [1.8, 1.8], [1.8, 1.8, 1.8, 1.8, 1.25]];
  for (let r = 0; r < 6; r++) {
    const xr = x0 + r * pitch;
    let y = 2.2;
    blocks.forEach(bl => {
      bl.forEach(len => {
        const nc = len > 1.5 ? 3 : 2, step = len / nc;              // 6인 = 양측 의자 3개, 4인 = 2개
        for (let i = 0; i < nc; i++) {                              // 의자 먼저 — 테이블이 안쪽을 덮는다
          const cy = y + step * (i + 0.5), cw = .44, cd = .28;
          rect(cy - cw / 2, xr + tw - .08, cw, cd, 2.5 * u, "#BCD98C");
          rect(cy - cw / 2, xr - cd + .08, cw, cd, 2.5 * u, "#BCD98C");
        }
        g.save(); g.shadowColor = "rgba(51,49,45,.18)"; g.shadowBlur = 3 * u;
        g.shadowOffsetY = 1.2 * u;
        rect(y, xr, len, tw, 2.5 * u, "#FFFEF8");
        g.restore();
        y += len + 0.12;
      });
      y += 1.2;                                                      // 가로 통로
    });
  }
  // 라벨 — 흰 halo. 평면도 층에 그리므로 통로 라벨 위로 마커가 지나갈 수 있다(마커가 우선)
  g.textAlign = "center";
  label(g, G, "배식대", X(7.5), Y(0) - T - 4 * u, "#D14A38");
  label(g, G, "입구", X((GAP.door[0] + GAP.door[1]) / 2 - 0.7), Y(ROOM.D) - 5 * u, "#6E6A61");   // 문 틈보다 조금 오른쪽(통로 쪽)에 — 09-03 사용자 확인
  g.textAlign = "right";                                            // 레이아웃 바깥(좌측 여백)에
  label(g, G, "퇴식구", X(ROOM.W) - T - 4 * u, Y((GAP.dish[0] + GAP.dish[1]) / 2) + 4 * u, "#6E6A61");
  label(g, G, "출구", X(ROOM.W) - T - 4 * u, Y((GAP.exit[0] + GAP.exit[1]) / 2) + 4 * u, "#6E6A61");
}

/* 구역 이름 라벨 — 사용자 화면(급식실 현황·밀집도)에 zones.json 의 이름을 옅은 회색으로(09-04 사용자 요청, 이전의 고정 "통로" 글자를 대신한다).
   세로로 긴 구역(길이가 폭의 2.5배 이상 — 출구쪽·입구쪽 통로)은 시계 방향 90° 로 돌려 통로를 따라 읽히게. 배식대 띠(y<0.12)는 위의 "배식대" 글자와 겹쳐 뺀다 */
export function drawZoneLabels(g, G, zones) {
  (zones || []).forEach(z => {
    const P = z.polygon; if (!P || P.length < 3) return;
    const xs = P.map(p => p[0]), ys = P.map(p => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    if (cy < 0.12) return;
    const w = (Math.max(...xs) - Math.min(...xs)) * ROOM.W, h = (Math.max(...ys) - Math.min(...ys)) * ROOM.D;
    const [sx, sy] = G.P(cx, cy);
    g.save(); g.translate(sx, sy);
    if (h > 2.5 * w) g.rotate(Math.PI / 2);                            // 시계 방향 90° — 위에서 아래로 읽힌다
    g.textAlign = "center";
    label(g, G, z.label || z.name || z.id, 0, 4 * (G.fu ?? G.u), "#A9A296");
    g.restore();
  });
}

/* 흰 halo 라벨 — 마커 위에서도 읽힌다 */
export function label(g, G, t, x, y, col) {
  const fu = G.fu ?? G.u;
  g.textBaseline = "alphabetic"; g.font = `700 ${Math.max(9, 10.5 * fu)}px system-ui, sans-serif`;
  g.lineJoin = "round"; g.lineWidth = 3 * fu; g.strokeStyle = "#FFFCF6";
  g.strokeText(t, x, y); g.fillStyle = col; g.fillText(t, x, y);
}

/* 익명 마커 — 노란 스마일(테두리 없음), r=5.2u. 좌표 두 개뿐, 식별 정보 없음. points = [{x, y}] 정규화 */
export function drawMarkers(g, G, points, alpha = 1) {
  const r = 5.2 * G.u;
  g.save(); g.globalAlpha = alpha;
  (points || []).forEach(({ x, y }) => {
    const [sx, sy] = G.P(x, y);
    g.beginPath(); g.arc(sx, sy, r, 0, Math.PI * 2);
    g.fillStyle = "#F6C445"; g.fill();
    g.fillStyle = "#33312D";
    g.beginPath(); g.arc(sx - r * .33, sy - r * .22, r * .155, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.arc(sx + r * .33, sy - r * .22, r * .155, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.lineWidth = Math.max(1, r * .17); g.strokeStyle = "#33312D"; g.lineCap = "round";
    g.arc(sx, sy + r * .06, r * .44, .16 * Math.PI, .84 * Math.PI); g.stroke();
  });
  g.restore();
}

/* 구역 틴트 — zones = [{id, label, polygon:[[x,y],…]}] (정규화), occ = {id: 0~1 점유 비율}.
   구역 점유율 카드가 쓴다(마커 없음). 틸 한 램프: 비율이 클수록 진하게, 가운데에 이름 */
export function drawZones(g, G, zones, occ = {}, labels = true) {
  (zones || []).forEach(z => {
    if (!z.polygon || z.polygon.length < 3) return;
    const t = Math.min(1, Math.max(0, occ[z.id] ?? 0));
    g.beginPath();
    z.polygon.forEach(([x, y], i) => { const [sx, sy] = G.P(x, y); (i ? g.lineTo : g.moveTo).call(g, sx, sy); });
    g.closePath();
    g.fillStyle = `rgba(12,109,106,${(.06 + .5 * t).toFixed(3)})`; g.fill();
    g.strokeStyle = "rgba(12,109,106,.35)"; g.lineWidth = 1; g.stroke();
    if (!labels) return;                                              // 점유율 카드는 아래 칩이 이름·비율을 담는다 — 좌석 위 글자는 읽히지 않아 뺀다
    const cx = z.polygon.reduce((a, p) => a + p[0], 0) / z.polygon.length;
    const cy = z.polygon.reduce((a, p) => a + p[1], 0) / z.polygon.length;
    const [lx, ly] = G.P(cx, cy);
    g.textAlign = "center";
    label(g, G, z.label || z.id, lx, ly + 4 * (G.fu ?? G.u), "#0C6D6A");        // 언제나 틸 잉크 + 종이색 테두리(label) — 흰 글자는 테두리와 같아 보이지 않았다
  });
}

/* 밀집도 육각 타일 — cells = [{i, w}] (i = row*cols+col, w 0~1). 기하는 vision/zones.py(hex_center)와 같다:
   뾰족한 꼭짓점이 위, 홀수 행은 반 칸 오른쪽, 반지름은 x 로 1/(cols·√3) · y 로 1/(rows·1.5). 값이 있는 타일만 plotly "Sunsetdark"(colors.js, 09-04 — 잠깐 jet 을 썼다가 같은 날 되돌림) 로 채우고
   나머지는 벌집 윤곽만 아주 옅게. 구역 이름·마커 없음. 최근 30분의 타일별 합계이지 개별 위치가 아니다 */
export function drawHeat(g, G, cells, cols, rows) {
  const { X, Y } = G, S3 = Math.sqrt(3);
  const rx = 1 / (cols * S3), ry = 1 / (rows * 1.5);                // 정규화 반지름(x·y)
  const hex = (col, row, s) => {                                     // s = 타일 축소 비율(사이 틈)
    const cx = (col + .5 + .5 * (row & 1)) / cols, cy = (1 + 1.5 * row) / (rows * 1.5);
    g.beginPath();
    for (let k = 0; k < 6; k++) {
      const th = Math.PI / 6 + k * Math.PI / 3;
      const [sx, sy] = G.P(cx + rx * s * Math.cos(th), cy + ry * s * Math.sin(th));
      (k ? g.lineTo : g.moveTo).call(g, sx, sy);
    }
    g.closePath();
  };
  g.save();
  g.beginPath(); g.rect(X(ROOM.W), Y(0), ROOM.W * G.k, ROOM.D * G.k); g.clip();   // 홀수 행 오른쪽 반 칸·마지막 행 아랫단은 벽에서 자른다
  g.strokeStyle = "rgba(51,49,45,.07)"; g.lineWidth = 1;
  for (let row = 0; row < rows; row++) for (let col = 0; col < cols; col++) { hex(col, row, .96); g.stroke(); }
  (cells || []).forEach(c => {
    const w = Math.min(1, Math.max(0, c.w));
    hex(c.i % cols, Math.floor(c.i / cols), .9);
    g.fillStyle = ramp(SUNSETDARK, w); g.globalAlpha = .55 + .25 * w; g.fill();   // 최대 .8 — 바닥 도면이 비쳐 보이게(09-04 사용자 요청, 이전 .7~.95)
  });
  g.restore();
}

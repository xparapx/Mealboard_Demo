/* 급식실 평면도 그리기 — 공용. 급식실 현황 카드(마커)와 구역 점유율 카드(구역 틴트)가 같은 평면도를 쓴다.
   실측 기반 탑뷰(세로형) — 방 15.55m(폭 x) × 24.65m(길이 y), 원점 = 배식구 벽 ∧ 창가 통로 구석.
   /api/positions 와 zones.json 의 x,y 는 이 바닥의 0~1 정규화 값 — 같은 좌표계.
   화면 방향은 확정 도면(docs/layout.html): 배식대 위(카메라는 그 오른쪽 끝) · 퇴식구→출구 왼쪽(위부터) ·
   대기통로(창가) 오른쪽 · 입구 아래(통로 쪽). 투영: sx=(W−x)·k, sy=y·k — 왜곡 없음.
   테이블 6열 × [6인×3 | 6인×2 | 6인×4+4인], 의자는 도면 기호처럼 테이블 가장자리에 살짝만.
   여기 함수들은 캔버스 컨텍스트 g 와 geom 만 받는다 — DOM 을 모른다 */

export const ROOM = { W: 15.55, D: 24.65, H: 2.68 };
const GAP = { door: [0.2, 3.2], dish: [1.6, 4.4], exit: [5.6, 8.4] };   // 입구(아래 벽, 통로 쪽) · 퇴식구·출구(좌측 벽, 위부터)

/* 캔버스 크기(W,H, CSS px) → 투영 도구. u = 318px 기준 배율, k = m → px, X/Y = 세계좌표 → 화면 */
export function geom(W, H) {
  const u = W / 318;
  const ML = 50 * u, MR = 10 * u, MT = 22 * u, MB = 8 * u;          // 좌측은 퇴식구·출구 라벨 자리
  const k = Math.min((W - ML - MR) / ROOM.W, (H - MT - MB) / ROOM.D);
  const ox = ML + (W - ML - MR - ROOM.W * k) / 2;
  const oy = MT + (H - MT - MB - ROOM.D * k) / 2;
  return { W, H, u, k, T: Math.max(3, .45 * k),
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
  g.textAlign = "center";
  label(g, G, "통로", X(1.1), Y(ROOM.D * .5), "#A9A296");
}

/* 흰 halo 라벨 — 마커 위에서도 읽힌다 */
export function label(g, G, t, x, y, col) {
  g.textBaseline = "alphabetic"; g.font = `700 ${Math.max(9, 10.5 * G.u)}px system-ui, sans-serif`;
  g.lineJoin = "round"; g.lineWidth = 3 * G.u; g.strokeStyle = "#FFFCF6";
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
    label(g, G, z.label || z.id, lx, ly + 4 * G.u, "#0C6D6A");        // 언제나 틸 잉크 + 종이색 테두리(label) — 흰 글자는 테두리와 같아 보이지 않았다
  });
}

/* 밀집도 격자 — cells = [{i, w}] (i = row*cols+col, w 0~1). 평면도 위에 셀을 틸로 채운다: 값이 클수록 진하게.
   구역 이름·마커 없음. 최근 30분의 셀별 합계이지 개별 위치가 아니다 */
export function drawHeat(g, G, cells, cols, rows) {
  (cells || []).forEach(c => {
    const col = c.i % cols, row = Math.floor(c.i / cols);
    const [x0, y0] = G.P(col / cols, row / rows), [x1, y1] = G.P((col + 1) / cols, (row + 1) / rows);
    const x = Math.min(x0, x1), y = Math.min(y0, y1), w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
    g.fillStyle = `rgba(12,109,106,${(.06 + .74 * Math.min(1, Math.max(0, c.w))).toFixed(3)})`;
    g.fillRect(x + 1, y + 1, Math.max(1, w - 2), Math.max(1, h - 2));
  });
}

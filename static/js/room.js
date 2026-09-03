/* 급식실 화면 — 실측 탑뷰 2D 평면도 + 익명 위치 마커. 영상 아님 · 순간 상태만 · 이력 없음 (CLAUDE.md §2) */
import { $, fit } from "./core.js";

export const ROOM = { W: 15.55, D: 24.65, H: 2.68 };
export function renderPlan(p) {
  try { drawPlan(p); } catch (e) { console.error("drawPlan", e); }
}
/* ---------------- ⑩ 급식실 현황 (탑뷰 2D) ----------------
   실측 기반 평면 탑뷰(세로형) — 방 15.55m(폭 x) × 24.65m(길이 y), 원점 = 배식구 벽 ∧ 창가 통로 구석.
   /api/positions 의 x,y 는 이 바닥의 0~1 정규화 값 — zones.json 과 공유하는 좌표계.
   화면 방향은 확정 도면: 배식대 위(카메라는 그 오른쪽 끝) · 퇴식구→출구 왼쪽(위부터) ·
   대기통로(창가) 오른쪽 · 입구 아래(통로 쪽). 투영: sx=(W−x)·k, sy=y·k — 왜곡 없음.
   테이블 6열 × [6인×3 | 6인×2 | 6인×4+4인], 의자는 도면 기호처럼 테이블 가장자리에 살짝만.
   두 겹 캔버스: #plan 에 정적 평면도, 그 위 #marks 에 마커만 — 점멸은 #marks 의 CSS opacity 애니메이션(1.4초, 0.55~1).
   평면도는 데이터·크기가 바뀔 때만 그리고, 모션 축소 설정은 기존 @media 규칙이 자동으로 애니메이션을 끈다 */
export function drawPlan(p) {
  const ok = p.state === "ok";
  $("#plancard").dataset.state = ok ? "ok" : "no_data";
  $("#posn").textContent = ok ? `${p.n}명` : "—";
  const c = $("#plan"), W = c.clientWidth || 318;
  const H = c.clientHeight || Math.round(W * 460 / 318);
  const { g } = fit(c, H);
  const u = W / 318;
  const ML = 50 * u, MR = 10 * u, MT = 22 * u, MB = 8 * u;          // 좌측은 퇴식구·출구 라벨 자리
  const k = Math.min((W - ML - MR) / ROOM.W, (H - MT - MB) / ROOM.D);
  const ox = ML + (W - ML - MR - ROOM.W * k) / 2;
  const oy = MT + (H - MT - MB - ROOM.D * k) / 2;
  const X = x => ox + (ROOM.W - x) * k, Yy = y => oy + y * k;       // 세계좌표 → 화면
  const rect = (y0, x0, dy, dx, r, fill) => {                       // 세계 y0..y0+dy × x0..x0+dx
    g.beginPath(); g.roundRect(X(x0 + dx), Yy(y0), dx * k, dy * k, r);
    g.fillStyle = fill; g.fill();
  };
  // 바닥 + 통로 띠(우측) + 타일 줄눈
  rect(0, 0, ROOM.D, ROOM.W, 10 * u, "#FBF8F0");
  rect(0, 0, ROOM.D, 2.2, 0, "rgba(51,49,45,.05)");
  g.strokeStyle = "rgba(51,49,45,.045)"; g.lineWidth = 1;
  for (let ty = 2.5; ty < ROOM.D; ty += 2.5) {
    g.beginPath(); g.moveTo(X(ROOM.W), Yy(ty)); g.lineTo(X(0), Yy(ty)); g.stroke();
  }
  for (let tx = 2.65; tx < ROOM.W; tx += 2.65) {
    g.beginPath(); g.moveTo(X(tx), Yy(0)); g.lineTo(X(tx), Yy(ROOM.D)); g.stroke();
  }
  // 벽 네 변 — 두께 띠. 개구부: 배식구 벽(위) · 퇴식구→출구(좌) · 창(우, 하늘빛) · 입구(아래, 통로 쪽)
  const T = Math.max(3, .45 * k);
  const gapDoor = [0.2, 3.2], gapDish = [1.6, 4.4], gapExit = [5.6, 8.4];  // 입구 = 통로 끝단(아래 벽, 창가 쪽)
  g.fillStyle = "#E3DCC9";
  g.fillRect(X(ROOM.W) - T, Yy(0) - T, ROOM.W * k + 2 * T, T);      // 위 (y=0 배식구 벽) — 좌우 벽 두께까지 늘려 모서리를 채운다
  g.fillRect(X(ROOM.W) - T, Yy(ROOM.D), ROOM.W * k + 2 * T, T);     // 아래 (y=D 출입문 벽) — 위와 같이
  g.fillRect(X(ROOM.W) - T, Yy(0), T, ROOM.D * k);                  // 좌 (x=W 벽)
  g.fillRect(X(0), Yy(0), T, ROOM.D * k);                           // 우 (x=0 창가 벽)
  g.fillStyle = "#B9DBD9";                                          // 입구 (아래 벽, 통로 쪽)
  g.fillRect(X(gapDoor[1]), Yy(ROOM.D), (gapDoor[1] - gapDoor[0]) * k, T);
  g.fillStyle = "#CFC9B8";                                          // 퇴식구 (좌측, 위부터)
  g.fillRect(X(ROOM.W) - T, Yy(gapDish[0]), T, (gapDish[1] - gapDish[0]) * k);
  g.fillStyle = "#B9DBD9";                                          // 출구 (퇴식구 아래)
  g.fillRect(X(ROOM.W) - T, Yy(gapExit[0]), T, (gapExit[1] - gapExit[0]) * k);
  g.fillStyle = "#D9E7EE";                                          // 창 (우측 벽 세 칸)
  [[2.6, 7.4], [9.2, 14], [15.8, 20.6]].forEach(([a, b]) =>
    g.fillRect(X(0), Yy(a), T, (b - a) * k));
  // 배식대 — 위 벽 안쪽의 긴 카운터 (카메라는 그 오른쪽 끝, 통로 쪽 구석)
  rect(0.15, 1.5, 0.85, 12.0, 3 * u, "#FFD9D0");
  g.strokeStyle = "#F0A897"; g.lineWidth = 1;
  g.strokeRect(X(13.5), Yy(0.15), 12.0 * k, 0.85 * k);
  // 퇴식구 싱크대 — 좌측 벽 안쪽의 회색 카운터 (배식대와 같은 표기법)
  rect(1.4, ROOM.W - 0.97, 3.2, 0.85, 3 * u, "#E4DFD3");
  g.strokeStyle = "#C7C0AE"; g.lineWidth = 1;
  g.strokeRect(X(ROOM.W - 0.12), Yy(1.4), 0.85 * k, 3.2 * k);
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
  g.textBaseline = "alphabetic"; g.font = `700 ${Math.max(9, 10.5 * u)}px system-ui, sans-serif`;
  g.lineJoin = "round"; g.lineWidth = 3 * u; g.strokeStyle = "#FFFCF6";
  const label = (t, x, y, col) => { g.strokeText(t, x, y); g.fillStyle = col; g.fillText(t, x, y); };
  g.textAlign = "center";
  label("배식대", X(7.5), Yy(0) - T - 4 * u, "#D14A38");
  label("입구", X((gapDoor[0] + gapDoor[1]) / 2), Yy(ROOM.D) - 5 * u, "#6E6A61");
  g.textAlign = "right";                                            // 레이아웃 바깥(좌측 여백)에
  label("퇴식구", X(ROOM.W) - T - 4 * u, Yy((gapDish[0] + gapDish[1]) / 2) + 4 * u, "#6E6A61");
  label("출구", X(ROOM.W) - T - 4 * u, Yy((gapExit[0] + gapExit[1]) / 2) + 4 * u, "#6E6A61");
  g.textAlign = "center";
  label("통로", X(1.1), Yy(ROOM.D * .5), "#A9A296");
  // 익명 마커 — 노란 스마일(테두리 없음), r=5.2u. 좌표 두 개뿐, 식별 정보 없음. 위 겹 #marks 에만 그린다
  const { g: m } = fit($("#marks"), H);
  if (ok) (p.points || []).forEach(({ x, y }) => {
    const sx = X(x * ROOM.W), sy = Yy(y * ROOM.D), r = 5.2 * u;
    m.beginPath(); m.arc(sx, sy, r, 0, Math.PI * 2);
    m.fillStyle = "#F6C445"; m.fill();
    m.fillStyle = "#33312D";
    m.beginPath(); m.arc(sx - r * .33, sy - r * .22, r * .155, 0, Math.PI * 2); m.fill();
    m.beginPath(); m.arc(sx + r * .33, sy - r * .22, r * .155, 0, Math.PI * 2); m.fill();
    m.beginPath(); m.lineWidth = Math.max(1, r * .17); m.strokeStyle = "#33312D"; m.lineCap = "round";
    m.arc(sx, sy + r * .06, r * .44, .16 * Math.PI, .84 * Math.PI); m.stroke();
  });
}

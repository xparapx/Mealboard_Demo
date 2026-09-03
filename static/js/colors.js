/* 컬러맵 — plotly 의 이름 있는 스케일을 그대로 옮겼다(09-04 사용자 결정). 다른 파일은 색을 만들지 않고 여기서 받는다.
   ramp(SCALE, t) : t 0~1 → "rgb(r,g,b)". 각 스케일은 [위치, 색] 쌍의 목록, 사이는 선형 보간.
   - SUNSETDARK : 대기시간 화면 — 최근 30분 막대 · 요일×시각 히트맵 (값이 클수록 어둡게)
   - JET        : 실시간뷰 최근 30분 밀집도 육각 타일
   - RDBU       : 오늘급식 영양소 칩 — 권장섭취량 100% 를 가운데(흰색)로 두는 발산 스케일(적음=빨강, 많음=파랑) */
const hex = h => h.match(/\w\w/g).map(v => parseInt(v, 16));
const rgb = s => s.match(/\d+/g).map(Number);
const parse = c => c.startsWith("#") ? hex(c) : rgb(c);

export const SUNSETDARK = ["#fcde9c", "#faa476", "#f0746e", "#e34f6f", "#dc3977", "#b9257a", "#7c1d6f"].map((c, i, a) => [i / (a.length - 1), c]);
export const JET = [[0, "rgb(0,0,131)"], [0.125, "rgb(0,60,170)"], [0.375, "rgb(5,255,255)"], [0.625, "rgb(255,255,0)"], [0.875, "rgb(250,0,0)"], [1, "rgb(128,0,0)"]];
export const RDBU = ["rgb(103,0,31)", "rgb(178,24,43)", "rgb(214,96,77)", "rgb(244,165,130)", "rgb(253,219,199)", "rgb(247,247,247)",
                     "rgb(209,229,240)", "rgb(146,197,222)", "rgb(67,147,195)", "rgb(33,102,172)", "rgb(5,48,97)"].map((c, i, a) => [i / (a.length - 1), c]);

export function ramp(scale, t) {
  t = Math.min(1, Math.max(0, +t || 0));
  let i = 0;
  while (i < scale.length - 2 && t > scale[i + 1][0]) i++;
  const [p0, c0] = scale[i], [p1, c1] = scale[i + 1];
  const f = p1 > p0 ? (t - p0) / (p1 - p0) : 0;
  const a = parse(c0), b = parse(c1);
  return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",")})`;
}

/* CSS linear-gradient 문자열 — 범례 막대용 */
export const gradient = scale => `linear-gradient(90deg, ${scale.map(([p, c]) => `${c} ${Math.round(p * 100)}%`).join(", ")})`;

/* 밝기(0~1) — 칩 글자색을 흰/검 중 고를 때 */
export function luma(color) {
  const [r, g, b] = parse(color);
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

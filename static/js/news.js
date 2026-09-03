/* 이슈피드 화면 — 오늘의 이슈 링크. 외부 문자열이므로 이스케이프. no_data 면 카드 숨김(인사이트 카드 중 유일한 예외). 진입 시 1회 + 5분마다.
   §5.4 요약 레이아웃: 제목(원문 링크) · 칩 행(출처 · 날짜 · "AI 요약 · 모델" 또는 "DeepL 번역") · 요약 3줄(digest.bullets, 틸 점) ·
   "왜 중요한가" 한 줄(이탤릭) · 원문 보기. digest 가 없으면(Phase 4c 전) 예전처럼 요약 2줄 클램프 */
import { $, j, esc } from "./core.js";

export function renderNews(n) {
  const card = $("#newscard");
  card.hidden = n.state !== "ok" || !(n.items && n.items.length);
  if (card.hidden) return;
  // 제목·요약은 CSS 로 줄 수를 자른다 — 글자 수로 자르면 낱말 중간에서 끊긴다.
  // 한국어가 있으면 그것을, 없으면 원문을. 링크의 title 에는 언제나 원문 제목을 남긴다
  $("#newslist").innerHTML = n.items.map(x => {
    const t = x.title_ko || x.title, s = x.summary_ko || x.summary, d = x.digest;
    const chips = `<em>${esc(x.source)}</em><small>${esc(x.date)}</small>`
      + (d ? `<em class="ko">AI 요약${d.model ? " · " + esc(d.model) : ""}</em>` : x.title_ko ? `<em class="ko">DeepL 번역</em>` : "");
    const body = d && d.bullets && d.bullets.length
      ? `<ul class="bullets">${d.bullets.slice(0, 3).map(b => `<li>${esc(b)}</li>`).join("")}</ul>`
        + (d.why ? `<p class="why">${esc(d.why)}</p>` : "")
      : (s ? `<p>${esc(s)}</p>` : "");
    return `<li><a href="${esc(x.link)}" target="_blank" rel="noopener" title="${esc(x.title)}">${esc(t)}</a>`
      + `<div>${chips}</div>${body}`
      + `<a class="more" href="${esc(x.link)}" target="_blank" rel="noopener">원문 보기 ↗</a></li>`;
  }).join("");
}

export async function loadNews() {
  let n;
  try { n = await j("/api/news"); } catch { n = { state: "no_data", items: [] }; }
  renderNews(n);
}

export const screen = { every: 300000, poll: loadNews, render(cardId, data) { if (cardId === "newscard") renderNews(data); } };

/* 이슈피드 화면 — 오늘의 이슈 링크. 외부 문자열이므로 이스케이프. no_data 면 카드 숨김. 진입 시 1회 + 5분마다 */
import { $, j, esc } from "./core.js";

export async function loadNews() {
  let n;
  try { n = await j("/api/news"); } catch { n = { state: "no_data", items: [] }; }
  const card = $("#newscard");
  card.hidden = n.state !== "ok" || !(n.items && n.items.length);
  if (card.hidden) return;
  // 제목·요약은 CSS 로 줄 수를 자른다 — 글자 수로 자르면 낱말 중간에서 끊긴다.
  // 한국어가 있으면 그것을, 없으면 원문을. 링크의 title 에는 언제나 원문 제목을 남긴다
  $("#newslist").innerHTML = n.items.map(x => {
    const t = x.title_ko || x.title, s = x.summary_ko || x.summary;
    return `<li><a href="${esc(x.link)}" target="_blank" rel="noopener" title="${esc(x.title)}">${esc(t)}</a>`
      + (s ? `<p>${esc(s)}</p>` : "")
      + `<div><em>${esc(x.source)}</em>`
      + (x.title_ko ? `<em class="ko">번역</em>` : "")
      + `<small>${esc(x.date)}</small></div></li>`;
  }).join("");
}

export const screen = { every: 300000, poll: loadNews };

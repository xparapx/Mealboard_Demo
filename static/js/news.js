/* 이슈피드 화면(09-11 확장) — 기후·환경(차콜 카드) · 기술·과학·IT(틸 카드) 두 섹션 + 오늘의 키워드(워드클라우드). 외부 문자열이므로 이스케이프.
   no_data 면 카드 숨김. 진입 시 1회 + 5분마다.
   §5.4 요약 레이아웃: 제목(원문 링크) · 칩 행(출처 · 날짜 · "AI 요약 · 모델" 또는 "DeepL 번역") · 요약 3줄(digest.bullets) · "왜 중요한가" 한 줄 · 원문 보기.
   워드클라우드는 라이브러리 없이: 빈도 상위 40 낱말을 크기 5단·색(기후/기술/둘 다)으로 흐름 배치 — 서버는 [word, n] 만 준다 */
import { $, j, esc } from "./core.js";

function itemHtml(x) {
  const t = x.title_ko || x.title, s = x.summary_ko || x.summary, d = x.digest;
  const chips = `<em>${esc(x.source)}</em><small>${esc(x.date)}</small>`
    + (d ? `<em class="ko">AI 요약${d.model ? " · " + esc(d.model) : ""}</em>` : x.title_ko ? `<em class="ko">DeepL 번역</em>` : "");
  const body = d && d.bullets && d.bullets.length
    ? `<ul class="bullets">${d.bullets.slice(0, 3).map(b => `<li>${esc(b)}</li>`).join("")}</ul>` + (d.why ? `<p class="why">${esc(d.why)}</p>` : "")
    : (s ? `<p>${esc(s)}</p>` : "");
  return `<li><a href="${esc(x.link)}" target="_blank" rel="noopener" title="${esc(x.title)}">${esc(t)}</a><div>${chips}</div>${body}`
    + `<a class="more" href="${esc(x.link)}" target="_blank" rel="noopener">원문 보기 ↗</a></li>`;
}

function fill(cardId, listId, items) {
  const card = $("#" + cardId);
  card.hidden = !(items && items.length);
  if (!card.hidden) $("#" + listId).innerHTML = items.map(itemHtml).join("");
}

/* 낱말이 어느 섹션에서 왔는지 — 각 섹션의 제목·요약에 등장하는지로 색을 정한다(서버 키워드는 합산 빈도) */
function sideOf(word, sec) {
  const re = new RegExp(`\\b${word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
  const inC = sec.climate.some(x => re.test(x.title + " " + x.summary)), inT = sec.tech.some(x => re.test(x.title + " " + x.summary));
  return inC && inT ? "b" : inT ? "t" : "c";
}

export function renderCloud(n, sec) {
  const card = $("#cloudcard"), kw = (n.keywords || []).slice(0, 40);
  card.hidden = kw.length < 6;
  if (card.hidden) return;
  const max = kw[0][1], min = kw[kw.length - 1][1];
  // 빈도 → 5단 크기. 순서를 섞어(큰 낱말이 앞에 몰리지 않게) 흐름 배치 — 낱말마다 가벼운 기울기·간격은 CSS 가 준다
  const sized = kw.map(([w, n], i) => ({ w, n, lv: 1 + Math.round(4 * (n - min) / Math.max(1, max - min)), side: sideOf(w, sec), i }));
  const order = [...sized].sort((a, b) => ((a.i * 7919) % 97) - ((b.i * 7919) % 97));
  $("#cloud").innerHTML = order.map(k => `<span class="w${k.lv} ${k.side}" title="${k.n}회">${esc(k.w)}</span>`).join(" ");
}

export function renderNews(n) {
  const secs = n.sections || (n.items ? [{ id: "climate", items: n.items }] : []);
  const by = Object.fromEntries(secs.map(s => [s.id, s.items || []]));
  const sec = { climate: by.climate || [], tech: by.tech || [] };
  fill("newscard", "newslist", n.state === "ok" ? sec.climate : []);
  fill("techcard", "techlist", n.state === "ok" ? sec.tech : []);
  renderCloud(n.state === "ok" ? n : {}, sec);
}

export async function loadNews() {
  let n;
  try { n = await j("/api/news"); } catch { n = { state: "no_data", items: [] }; }
  renderNews(n);
}

export const screen = { every: 300000, poll: loadNews, render(cardId, data) { if (cardId === "newscard") renderNews(data); } };

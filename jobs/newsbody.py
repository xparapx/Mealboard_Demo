"""기사 본문 확보 (PLAN §5.4) — 요약(LLM)의 입력으로만 쓰고 **어디에도 저장하지 않는다**(메모리에서 요약 → 버림).
전략 순서는 피드 설정(news_feeds.json `body`)이 정하고, 없으면 rss_content → guardian_api → html → description:
  rss_content  피드 항목의 <content:encoded> 전문 (Carbon Brief 처럼 전문을 싣는 워드프레스 피드)
  guardian_api Guardian Content API `show-fields=bodyText` (GUARDIAN_API_KEY 있을 때, theguardian.com 링크만; 비상업 무료 키·출처 표기)
  html         기사 URL 의 <article>/<main> 안 <p> 단락 — 스크립트·스타일·광고성 짧은 단락 제거, MAX_CHARS 상한, 30초, UA 명시.
               매체가 거부(403·robots)하면 그 매체는 description 으로.
  description  피드 요약(이미 있는 것) — 언제나 마지막 폴백
결과: (본문 텍스트, 출처 이름). 개인 비상업 요약 용도로 제한한다(저작권 메모: PLAN §5.4)."""
import html as htmlmod
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_CHARS = 6000
TIMEOUT = 30
UA = "Mealboard/0.1 (+school cafeteria dashboard; non-commercial summary)"
DEFAULT_ORDER = ("rss_content", "guardian_api", "html", "description")
MIN_PARA = 40                       # 이보다 짧은 <p> 는 캡션·버튼·광고 문구로 본다

_SCRIPT = re.compile(r"<(script|style|noscript|svg|figure|aside|nav|footer|header|form)\b.*?</\1\s*>", re.S | re.I)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_ARTICLE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1\s*>", re.S | re.I)
_P = re.compile(r"<p\b[^>]*>(.*?)</p\s*>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_tags(s):
    return _WS.sub(" ", _TAG.sub(" ", htmlmod.unescape(s or ""))).strip()


def paragraphs_from_html(page):
    """HTML → 본문 단락 리스트. <article>/<main> 이 있으면 그 안만, 없으면 문서 전체의 <p>. 스크립트·잡동사니 제거"""
    page = _COMMENT.sub("", _SCRIPT.sub("", page or ""))
    m = _ARTICLE.search(page)
    scope = m.group(2) if m else page
    paras = [strip_tags(p) for p in _P.findall(scope)]
    return [p for p in paras if len(p) >= MIN_PARA]


def join_capped(paras, cap=MAX_CHARS):
    """단락을 이어 붙이되 cap 을 넘으면 앞 단락들 + 마지막 단락(결론이 보통 끝에 있다)"""
    text = "\n".join(paras)
    if len(text) <= cap:
        return text
    last = paras[-1] if paras else ""
    budget = cap - len(last) - 1
    head = []
    for p in paras[:-1]:
        if sum(len(x) + 1 for x in head) + len(p) > budget:
            break
        head.append(p)
    return "\n".join(head + [last])[:cap]


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")


# ---- 전략 ----
def from_rss_content(item):
    raw = item.get("_content") or ""
    paras = paragraphs_from_html(raw) if "<p" in raw.lower() else [strip_tags(raw)]
    return join_capped([p for p in paras if p]) or None


def from_guardian_api(item, key=None):
    key = (key if key is not None else os.getenv("GUARDIAN_API_KEY") or "").strip()
    link = item.get("link") or ""
    if not key or "theguardian.com/" not in link:
        return None
    path = urllib.parse.urlparse(link).path.strip("/")
    url = f"https://content.guardianapis.com/{path}?{urllib.parse.urlencode({'api-key': key, 'show-fields': 'bodyText'})}"
    data = json.loads(_get(url))
    body = ((data.get("response") or {}).get("content") or {}).get("fields", {}).get("bodyText")
    return join_capped([body]) if body else None


def from_html(item):
    paras = paragraphs_from_html(_get(item.get("link") or ""))
    return join_capped(paras) if len(paras) >= 2 else None


def fetch_body(item, order=None, log=print):
    """→ (text, source). 어떤 전략도 실패하면 (description, 'description'). 예외는 여기서 삼킨다 — 뉴스는 나가야 한다"""
    for name in order or DEFAULT_ORDER:
        try:
            if name == "rss_content":
                text = from_rss_content(item)
            elif name == "guardian_api":
                text = from_guardian_api(item)
            elif name == "html":
                text = from_html(item)
            else:
                text = None
            if text and len(text) >= 400:
                return text, name
        except urllib.error.HTTPError as e:
            log(f"    본문 {name} 거부 HTTP {e.code} — 다음 전략")
        except Exception as e:
            log(f"    본문 {name} 실패 {type(e).__name__}: {str(e)[:80]} — 다음 전략")
    return item.get("summary") or "", "description"

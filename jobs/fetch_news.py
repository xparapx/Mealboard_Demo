"""기후 이슈 RSS → data/news.json  (하루 1회, systemd timer)

제목·요약·출처·날짜·링크를 저장한다. 요약은 우리가 본문을 읽어 만드는 것이 아니라
피드가 스스로 실어 보내는 <description> — 매체가 배포하라고 내놓은 문장이다.
그래서 출처와 원문 링크를 반드시 함께 두고, 본문을 더 긁어오지 않는다.
(LLM 요약은 여전히 로드맵 ⑦. 여기서는 남의 요약을 옮길 뿐이다.)

실행:  uv run python -m jobs.fetch_news
"""
import datetime as dt
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from app.config import DATA

FEEDS_FILE = DATA / "news_feeds.json"
OUT = DATA / "news.json"

TAG = re.compile(r"<[^>]+>")
# 워드프레스 피드가 요약 끝에 붙이는 상투구 — 문장이 아니라 발행 도구의 흔적이라 지운다
BOILER = re.compile(r"\s*The post .*? appeared first on .*?\.?\s*$", re.S)
# 요약 자리에 문장 대신 링크 문구만 들어오는 항목이 있다(가디언 만평 등) — 걸러낸다
JUNK = re.compile(r"\s*(continue reading|read more)\.*\s*$", re.I)
MIN_SUMMARY = 60          # 이보다 짧으면 카드에서 요약이 제 몫을 못 한다


def clean(s):
    """HTML 태그·엔티티·연속 공백을 걷어낸 한 줄로"""
    return re.sub(r"\s+", " ", TAG.sub(" ", html.unescape(s or ""))).strip()


def summarize(s, limit):
    """낱말 경계에서 자른다. 단어 중간에서 끊기면 읽다 만 것처럼 보인다"""
    s = JUNK.sub("", BOILER.sub("", clean(s)))
    if len(s) <= limit:
        return s
    cut = s[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).rstrip(" ,.;:—-") + "…"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mealboard/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return ET.fromstring(r.read())


def main():
    cfg = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    limit = cfg.get("summary_chars", 150)
    items = []                                        # 피드마다 한 바구니
    for f in cfg["feeds"]:
        try:
            root = fetch(f["url"])
        except Exception as e:                       # 피드 하나가 죽어도 나머지는 진행
            print(f"건너뜀 {f['name']}: {e}")
            continue
        bucket = []
        for it in root.iter("item"):
            title = clean(it.findtext("title"))
            link = (it.findtext("link") or "").strip()
            src = clean(it.findtext("source")) or f["name"]
            summary = summarize(it.findtext("description"), limit)
            try:
                d = parsedate_to_datetime(it.findtext("pubDate"))
            except Exception:
                d = None
            if title and link and len(summary) >= MIN_SUMMARY:   # 요약 없는 항목은 싣지 않는다
                bucket.append({"title": title, "summary": summary, "link": link, "source": src,
                               "date": d.strftime("%m-%d") if d else "",
                               "_ts": d.timestamp() if d else 0})
        bucket.sort(key=lambda x: -x["_ts"])
        items.append(bucket)

    # 매체별로 한 건씩 돌아가며 뽑는다. 최신순으로만 자르면 그날 많이 쓴 한 매체가 전부를 차지한다
    seen, top = set(), []
    for rnd in range(max(len(b) for b in items) if items else 0):
        for bucket in items:
            if rnd >= len(bucket):
                continue
            x = bucket[rnd]
            key = x["title"][:40].lower()
            if key in seen:
                continue
            seen.add(key)
            x.pop("_ts")
            top.append(x)
            if len(top) >= cfg.get("max_items", 3):
                break
        if len(top) >= cfg.get("max_items", 3):
            break
    OUT.write_text(json.dumps({"fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                               "state": "ok" if top else "no_data",
                               "items": top}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장 {OUT}  {len(top)}건")
    for x in top:
        print(f"  [{x['source']}] {x['title'][:60]}")
        print(f"      {x['summary'][:80]}")


if __name__ == "__main__":
    main()

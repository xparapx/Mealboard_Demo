"""기후·탄소 이슈 RSS → data/news.json  (하루 1회, systemd timer)
제목·출처·날짜·링크만 저장한다. 본문 요약은 넣지 않는다(저작권, LLM 요약은 로드맵 ⑦).

실행:  uv run python -m jobs.fetch_news
"""
import datetime as dt
import json
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from app.config import DATA

FEEDS_FILE = DATA / "news_feeds.json"
OUT = DATA / "news.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mealboard/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return ET.fromstring(r.read())


def main():
    cfg = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))
    items = []
    for f in cfg["feeds"]:
        try:
            root = fetch(f["url"])
        except Exception as e:                       # 피드 하나가 죽어도 나머지는 진행
            print(f"건너뜀 {f['name']}: {e}")
            continue
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            src = (it.findtext("source") or f["name"]).strip()
            try:
                d = parsedate_to_datetime(it.findtext("pubDate"))
            except Exception:
                d = None
            if title and link:
                items.append({"title": title, "link": link, "source": src,
                              "date": d.strftime("%m-%d") if d else "",
                              "_ts": d.timestamp() if d else 0})
    items.sort(key=lambda x: -x["_ts"])
    seen, top = set(), []
    for x in items:                                   # 제목 앞부분으로 중복 제거
        key = x["title"][:40]
        if key in seen:
            continue
        seen.add(key)
        x.pop("_ts")
        top.append(x)
        if len(top) >= cfg.get("max_items", 3):
            break
    OUT.write_text(json.dumps({"fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                               "state": "ok" if top else "no_data",
                               "items": top}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장 {OUT}  {len(top)}건")


if __name__ == "__main__":
    main()

"""헤드라인·요약 번역기 (PLAN §5.4). `.env TRANSLATOR=deepl|local|none` (기본 deepl).
  deepl  DeepL API Free — 월 50만 자. 하루 세 건(약 800자)이면 한도의 5% 도 쓰지 않는다. 무료 키는 끝이 ":fx" 이고 엔드포인트가 다르다.
  local  로컬 LLM(jobs/llm.py)로 제목만 옮긴다 — 4a 스파이크를 통과한 뒤에 켜는 옵션. 검증에 떨어지면 원문.
  none   번역하지 않는다.
어디서 실패하든 원문 영어는 그대로 남는다 — 번역이 안 됐다고 카드를 비우지 않는다."""
import json
import os
import urllib.error
import urllib.request

from jobs.llm import LLMUnavailable, LocalLLM, valid_korean

DEEPL = {True: "https://api-free.deepl.com/v2/translate", False: "https://api.deepl.com/v2/translate"}
MODES = ("deepl", "local", "none")


def mode():
    m = (os.getenv("TRANSLATOR") or "deepl").strip().lower()
    return m if m in MODES else "deepl"


def deepl_texts(texts, key=None, timeout=20, log=print):
    """영어 문자열 리스트 → 한국어 리스트(같은 길이). 실패하면 None (호출자가 원문 유지)"""
    key = (key if key is not None else os.getenv("DEEPL_API_KEY") or "").strip()
    if not key:
        log("  번역 건너뜀: DEEPL_API_KEY 없음 — 원문 영어로 싣는다")
        return None
    if not texts:
        return []
    body = json.dumps({"text": texts, "target_lang": "KO"}).encode("utf-8")
    req = urllib.request.Request(DEEPL[key.endswith(":fx")], data=body, method="POST",
                                 headers={"Authorization": f"DeepL-Auth-Key {key}", "Content-Type": "application/json", "User-Agent": "Mealboard/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.load(r)["translations"]
        if len(out) != len(texts):                        # 개수가 어긋나면 짝이 밀린다 — 통째로 포기
            raise ValueError(f"{len(out)}개 회신, {len(texts)}개 요청")
        return [o["text"] for o in out]
    except urllib.error.HTTPError as e:                   # 456 한도 초과 · 403 키 오류를 구분해 남긴다
        hint = {403: "키가 잘못됐거나 권한 없음", 456: "이번 달 무료 한도 소진", 429: "요청이 너무 잦음"}.get(e.code, "")
        log(f"  번역 실패: HTTP {e.code} {hint} — 원문 영어로 싣는다")
    except Exception as e:                                # 번역이 실패해도 뉴스는 나가야 한다
        log(f"  번역 실패({type(e).__name__}: {e}) — 원문 영어로 싣는다")
    return None


def local_titles(titles, llm_factory=None, log=print):
    """로컬 LLM 으로 제목만. 항목별로 검증(valid_korean, 길이비 0.4~2.5) — 떨어진 것은 None"""
    factory = llm_factory or LocalLLM
    try:
        with factory() as m:
            out = []
            for t in titles:
                raw = m.complete("영어 뉴스 제목을 자연스러운 한국어 한 줄로 옮긴다. 번역문만 출력한다.", t, max_tokens=60)
                raw = (raw or "").strip().strip('"')
                out.append(raw if valid_korean(t, raw, len_ratio=(0.4, 2.5))[0] else None)
            return out
    except LLMUnavailable as e:
        log(f"  로컬 번역 없음: {e}")
        return None


def translate(items, clean, log=print, llm_factory=None):
    """items 에 title_ko(모두)·summary_ko(digest 없는 것만)를 붙인다. → 쓴 엔진 이름 또는 None"""
    if not items:
        return None
    m = mode()
    if m == "none":
        return None
    if m == "local":
        kos = local_titles([x["title"] for x in items], llm_factory, log)
        if kos is None:
            return None
        for x, ko in zip(items, kos):
            if ko:
                x["title_ko"] = clean(ko)
        return "local"
    need = [x for x in items if not x.get("digest")]
    texts = [x["title"] for x in items] + [x["summary"] for x in need]
    out = deepl_texts(texts, log=log)
    if out is None:
        return None
    for x, ko in zip(items, out[:len(items)]):
        x["title_ko"] = clean(ko) or x["title"]
    for x, ko in zip(need, out[len(items):]):
        x["summary_ko"] = clean(ko) or x["summary"]
    return "deepl"

"""뉴스 파이프라인(PLAN §5.4) — 본문 추출·절단·요약 검증·폴백 체인. 네트워크 없이 돈다."""
import pytest

from jobs import fetch_news, newsbody, translators
from jobs.llm import LLMUnavailable, LocalLLM

PAGE = """<html><head><script>var x=1;</script><style>p{}</style></head><body><nav><p>Menu item that is long enough to look like text here</p></nav>
<article><p>First paragraph of the article body, with enough characters to pass the minimum length filter.</p>
<p>Short.</p><p>Second paragraph of the article body, again long enough to survive the filter and be kept as text.</p>
<aside><p>Advertisement paragraph that should be dropped because aside is removed from the page first.</p></aside>
<p>Third paragraph closes the article with a conclusion sentence that is long enough as well.</p></article>
<footer><p>Footer text that is long enough but lives outside the article element and is ignored.</p></footer></body></html>"""


def test_본문_단락은_article_안의_긴_p_만():
    paras = newsbody.paragraphs_from_html(PAGE)
    assert len(paras) == 3 and paras[0].startswith("First paragraph") and paras[-1].startswith("Third paragraph")
    assert newsbody.paragraphs_from_html("<p>x</p>") == []


def test_상한을_넘으면_앞_단락과_마지막_단락():
    paras = [f"para {i} " + "x" * 100 for i in range(10)]
    out = newsbody.join_capped(paras, cap=450)
    assert len(out) <= 450 and out.startswith("para 0") and out.rstrip().endswith("x") and "para 9" in out and "para 8" not in out


def test_fetch_body_는_rss_전문을_먼저_쓰고_없으면_description():
    item = {"summary": "s" * 100, "link": "https://example.org/a", "_content": "<p>" + ("Long paragraph text. " * 30) + "</p>"}
    text, src = newsbody.fetch_body(item, ["rss_content", "description"], log=lambda *a: None)
    assert src == "rss_content" and text.startswith("Long paragraph")
    text, src = newsbody.fetch_body({"summary": "only summary", "link": "", "_content": ""}, ["rss_content", "description"], log=lambda *a: None)
    assert (text, src) == ("only summary", "description")
    assert newsbody.from_guardian_api({"link": "https://www.theguardian.com/x"}, key="") is None
    assert newsbody.from_guardian_api({"link": "https://example.org/x"}, key="k") is None


BODY = "Global emissions rose 1.1% in 2024 to a record 37.4 billion tonnes, the report said. Scientists warn the 1.5C limit is slipping. " * 8


EN_GOOD = "- Global emissions rose 1.1% in 2024 to a record 37.4 billion tonnes.\n- Scientists warn the 1.5C limit is slipping.\n- The report calls for faster cuts.\nWhy: today's choices set the climate students will live in."
KO = ["2024년 세계 배출량이 1.1% 늘어 374억 톤으로 최고였습니다.", "과학자들은 1.5도 한계가 멀어지고 있다고 경고합니다.", "보고서는 감축 속도가 더 빨라야 한다고 봅니다.", "오늘의 선택이 학생들이 살아갈 기후를 정합니다."]


def test_영어_줄_파싱은_기호와_Why_를_가른다():
    d = fetch_news.parse_digest_lines(EN_GOOD)
    assert d["bullets"][0].startswith("Global") and len(d["bullets"]) == 3 and d["why"].startswith("today")
    assert fetch_news.parse_digest_lines("1. one\n2) two\n• three")["why"] == ""                   # Why 는 없어도 된다
    assert fetch_news.parse_digest_lines("only one line") is None and fetch_news.parse_digest_lines(None) is None
    assert fetch_news.check_english(BODY, fetch_news.parse_digest_lines(EN_GOOD)) is None
    assert fetch_news.check_english(BODY, fetch_news.parse_digest_lines(EN_GOOD.replace("1.1%", "5.6%"))) == "en:numbers"   # 지어낸 수치는 영어 단계에서 걸린다


def test_한국어_검증은_스키마_길이_한국어():
    good = {"bullets": KO[:3], "why": KO[3]}
    d, why = fetch_news.validate_digest(BODY, good)
    assert why == "ok" and len(d["bullets"]) == 3                                            # '374억' 은 번역이 바꾼 단위 — 숫자 검사는 끈다
    assert fetch_news.validate_digest(BODY, {"bullets": ["a", "b"], "why": "w"})[1] == "schema"
    assert fetch_news.validate_digest(BODY, {**good, "bullets": [KO[0], "English sentence here", KO[2]]})[1] == "bullet:hangul"
    assert fetch_news.validate_digest(BODY, {**good, "why": "가" * 81})[1] == "why:length"
    assert fetch_news.validate_digest(BODY, {"bullets": KO[:3]})[1] == "ok"                   # why 없음 허용


def fake(text, why="Why: it shapes the climate students will live in."):
    def factory():                                              # Why 후속 질문(WHY_SYSTEM)에는 why 를, 요약 요청에는 text 를
        return LocalLLM(hef="fake.hef", backend=lambda s, u, mt, t, to: why if s == fetch_news.WHY_SYSTEM else text)
    return factory


def test_Why_줄이_없으면_후속_질문으로_채운다():
    m = fake("- Global emissions rose 1.1% in 2024.
- Scientists warn the 1.5C limit is slipping.
- The report calls for faster cuts.")()
    with m:
        d, why = fetch_news.digest_with(m, BODY, translate_fn=fake_translate)
    assert why == "ok" and d["why"] == KO[3]


def fake_translate(texts, log=None):
    return KO[:len(texts)]


def test_digest_all_은_성공한_항목에만_digest(monkeypatch):
    items = [{"source": "A", "title": "t", "summary": "s"}, {"source": "B", "title": "t2", "summary": "s2"}]
    model = fetch_news.digest_all(items, [(BODY, "html"), ("short", "description")], fake(EN_GOOD), log=lambda *a: None, translate_fn=fake_translate)
    assert model == "fake + DeepL" and items[0]["digest"]["bullets"] == KO[:3] and items[0]["digest"]["why"] == KO[3]
    assert items[0]["digest"]["body_source"] == "html" and items[0]["digest"]["chars_in"] == len(BODY) and "digest" not in items[1]
    items3 = [{"source": "A", "title": "t", "summary": "s"}]
    fetch_news.digest_all(items3, [(BODY, "html")], fake(EN_GOOD), log=lambda *a: None, translate_fn=lambda t, log=None: None)
    assert "digest" not in items3[0]                                                          # DeepL 이 없으면 요약도 없다(도입부 폴백)

    def none_factory():
        raise LLMUnavailable("no hef")
    items2 = [{"source": "A", "title": "t", "summary": "s"}]
    assert fetch_news.digest_all(items2, [(BODY, "html")], none_factory, log=lambda *a: None) is None and "digest" not in items2[0]


def test_번역기_폴백_체인(monkeypatch):
    items = [{"title": "Hello world", "summary": "Sum", "digest": {"bullets": ["a", "b", "c"], "why": "w"}}, {"title": "Second", "summary": "Sum two"}]
    monkeypatch.setenv("TRANSLATOR", "none")
    assert translators.translate(items, fetch_news.clean, log=lambda *a: None) is None
    monkeypatch.setenv("TRANSLATOR", "deepl")
    monkeypatch.setattr(translators, "deepl_texts", lambda texts, **k: ["안녕 세계", "두 번째", "요약 둘"])
    assert translators.translate(items, fetch_news.clean, log=lambda *a: None) == "deepl"
    assert items[0]["title_ko"] == "안녕 세계" and "summary_ko" not in items[0] and items[1]["summary_ko"] == "요약 둘"     # digest 있는 항목은 요약 번역 안 함
    monkeypatch.setattr(translators, "deepl_texts", lambda texts, **k: None)
    assert translators.translate(items, fetch_news.clean, log=lambda *a: None) is None
    monkeypatch.setenv("TRANSLATOR", "local")
    assert translators.translate([{"title": "Ice melts faster"}], fetch_news.clean, log=lambda *a: None, llm_factory=fake("얼음이 더 빨리 녹습니다")) == "local"


def test_build_는_본문을_저장하지_않는다(monkeypatch):
    cfg = {"max_items": 2, "feeds": [{"name": "F", "url": "x", "body": ["rss_content", "description"]}]}
    monkeypatch.setattr(fetch_news, "collect", lambda cfg, log: [{"title": "T", "summary": "s" * 80, "link": "https://e/1", "source": "F", "date": "09-03",
                                                                  "_content": "<p>" + ("Body text here. " * 40) + "</p>", "_order": ["rss_content", "description"]}])
    monkeypatch.setenv("TRANSLATOR", "none")
    doc = fetch_news.build(cfg, log=lambda *a: None, llm_factory=lambda: (_ for _ in ()).throw(LLMUnavailable("x")))
    x = doc["items"][0]
    assert doc["engine"] == "none" and "digest" not in x and "_content" not in x and "_order" not in x and "Body text" not in str(doc)

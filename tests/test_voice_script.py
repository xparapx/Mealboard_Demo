"""자동 시연 아나운서 대본(static/media/voice/narration.json, 10-19) — guide.js 의 클립 id 와 1:1 인지, 글이 비지 않았는지"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = json.loads((ROOT / "static/media/voice/narration.json").read_text(encoding="utf-8"))
GUIDE = (ROOT / "static/js/guide.js").read_text(encoding="utf-8")


def test_클립_id_는_인트로_단계_엔드와_일대일():
    ids = [c["id"] for c in DOC["clips"]]
    n_intro = GUIDE.count("{ title:", 0, GUIDE.index("const OUTRO")) - len(re.findall(r"\{ screen: ", GUIDE))
    n_steps = len(re.findall(r"\{ screen: \"", GUIDE))
    assert n_steps == 15 and n_intro == 4
    assert ids == [f"intro{k}" for k in range(n_intro)] + [f"s{k}" for k in range(n_steps)] + ["outro"]
    assert len(set(ids)) == len(ids)


def test_대본은_비지_않고_길이가_적당하다():
    for c in DOC["clips"]:
        assert 40 <= len(c["text"]) <= 260, (c["id"], len(c["text"]))     # 150ms/자 → 6~40초
        assert "\n" not in c["text"]
    assert DOC["voice"]["provider"] == "openai" and DOC["voice"]["instructions"]

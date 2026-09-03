"""로컬 LLM 공용 라이브러리 — Hailo-10H GenAI (PLAN §5.2). 소비자는 jobs/report.py(리포트)·jobs/fetch_news.py(기사 요약)뿐이다.

원칙(CLAUDE.md §2 해석 AI): 입력은 숫자·정제된 메뉴명·(기사 요약에 한해) 본문뿐 — 프레임·좌표는 절대 넣지 않는다. 출력은 여기의 검증기
(`valid_korean`, `numbers_subset`)를 통과한 것만 저장하고, 실패·미설치·busy 는 호출자가 규칙 템플릿/DeepL 로 물러선다.
점심시간 밖에서만 부른다(HAT·CPU 경합 회피) — 타이머가 그렇게 잡혀 있다.

장치 API(학교 Pi HailoRT 5.1.1 에서 09-04 확인): `genai.LLM(vdevice, model_path, lora_name='', optimize_memory_on_device=False)`,
`generate_all(prompt, temperature, top_p, top_k, frequency_penalty, max_generated_tokens, do_sample, seed, timeout_ms=600000) -> str`,
prompt 는 문자열(원문 그대로) 또는 chat 리스트 `[{"role","content"}]`. `generate` 는 스트리밍. 모델 파일은 공개 경로
`https://dev-public.hailo.ai/v<HailoRT>/blob/<모델>.hef` (예: v5.1.1/blob/Qwen2.5-1.5B-Instruct.hef, 2.36 GB) — 로그인 없이 받는다.
`hailo_platform.genai` 는 apt 시스템 패키지라 `--system-site-packages` venv 에서만 보인다. 모양이 다르면 LLMUnavailable 로 물러선다
(아무것도 깨지지 않는다). `LLM_HEF` 가 비어 있으면 아예 시도하지 않는다."""
import json
import os
import re
import time

from app.config import LLM_HEF

HANGUL = re.compile(r"[가-힣]")
LETTER = re.compile(r"[A-Za-z가-힣]")
NUM = re.compile(r"\d+(?:[.,]\d+)*")
URL = re.compile(r"https?://|www\.", re.I)
MARKERS = ("```", "<", ">", "system:", "assistant:", "user:")


class LLMUnavailable(RuntimeError):
    """설치 안 됨·.hef 없음·API 모양 다름 — 호출자는 템플릿으로"""


class LLMBusy(LLMUnavailable):
    """장치가 다른 프로세스(vision·rollup)에 잡혀 있다 — 잠시 뒤 재시도 가치 있음"""


# ---------------- 검증기 (순수) ----------------
def numbers(s):
    """문자열의 숫자 집합. '1,234' 와 '1234', '3.0' 과 '3' 은 같은 수로 본다"""
    out = set()
    for m in NUM.findall(str(s)):
        v = m.replace(",", "")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(str(int(f)) if f == int(f) else str(f))
    return out


def numbers_subset(src, out):
    """출력의 숫자 집합 ⊆ 입력의 숫자 집합 — 모델이 숫자를 지어내지 못하게 하는 핵심 규칙"""
    return numbers(out) <= numbers(src)


def valid_korean(src, out, min_hangul=0.6, len_ratio=None, max_len=None, check_numbers=True):
    """→ (ok, reason). 한글 비율(문자 중) ≥ min_hangul, URL·개행·마커 없음, 숫자 부분집합, (선택) 길이비·최대 길이.
    check_numbers=False 는 번역기가 옮긴 문장용 — DeepL 은 '37.4 billion' 을 '374억' 으로 바꾸므로 숫자 검사는 번역 전 영어 단계에서 한다"""
    if not isinstance(out, str) or not out.strip():
        return False, "empty"
    if "\n" in out or URL.search(out) or any(m in out for m in MARKERS):
        return False, "format"
    letters = LETTER.findall(out)
    if not letters or len(HANGUL.findall(out)) / len(letters) < min_hangul:
        return False, "hangul"
    if max_len is not None and len(out) > max_len:
        return False, "length"
    if len_ratio is not None and src:
        r = len(out) / max(1, len(str(src)))
        if not (len_ratio[0] <= r <= len_ratio[1]):
            return False, "ratio"
    if check_numbers and not numbers_subset(src, out):
        return False, "numbers"
    return True, "ok"


def parse_json_object(text):
    """모델 출력에서 첫 JSON 객체만 뽑는다(앞뒤 잡담·코드펜스 무시). 못 찾으면 None"""
    if not isinstance(text, str):
        return None
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        return None
    try:
        v = json.loads(text[s:e + 1])
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


# ---------------- 장치 ----------------
def _hailo_backend(hef):
    """→ (complete(system, user, max_tokens, temperature, timeout_s) -> str, close()). 모양이 다르면 LLMUnavailable"""
    try:
        from hailo_platform import VDevice                     # noqa: F401  (apt: hailo-h10-all)
        from hailo_platform import genai
    except Exception as e:                                     # ImportError 외에도 드라이버 없음 등
        raise LLMUnavailable(f"hailo_platform.genai 없음: {e} — venv 는 --system-site-packages 여야 한다")
    try:
        vdev = VDevice()
        llm = genai.LLM(vdev, hef)
    except Exception as e:
        msg = str(e).lower()
        raise (LLMBusy if "busy" in msg or "in use" in msg else LLMUnavailable)(f"LLM 로드 실패: {e}")
    try:
        stops = list(llm.get_stop_tokens() or [])                # Qwen: <|im_end|> <|endoftext|> — generate_all 이 문자열 끝에 남긴다(09-04 확인)
    except Exception:
        stops = []
    stops = list(dict.fromkeys(stops + ["<|im_end|>", "<|endoftext|>", "<|im_start|>"]))

    def complete(system, user, max_tokens, temperature, timeout_s):
        prompt = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        # 온도 0 = 탐욕 디코딩(do_sample=False). 검증기가 숫자·형식을 보므로 결정적 출력이 맞다
        kw = {"max_generated_tokens": max_tokens, "do_sample": temperature > 0}
        if temperature > 0:
            kw["temperature"] = temperature
        if hasattr(llm, "generate_all"):
            out = llm.generate_all(prompt, timeout_ms=int(timeout_s * 1000), **kw)
        elif hasattr(llm, "generate"):
            out = llm.generate(prompt, **kw)
        else:
            raise LLMUnavailable("genai.LLM 에 generate_all/generate 가 없다 — check_llm.py 로 API 확인")
        try:
            llm.clear_context()                                 # 호출마다 독립 — 앞 대화가 다음 요약에 새지 않게
        except Exception:
            pass
        out = out if isinstance(out, str) else "".join(str(t) for t in out)
        for s in stops:                                         # 종료 토큰과 그 뒤는 버린다
            out = out.split(s)[0]
        return out.strip()

    def close():
        for o in (llm, vdev):
            try:
                o.release()
            except Exception:
                pass
    return complete, close


class LocalLLM:
    """컨텍스트 매니저. `with LocalLLM() as m: m.complete(system, user)`. 없으면 __enter__ 가 LLMUnavailable.
    backend 인자는 테스트·스파이크용(complete 호출자 하나)."""

    def __init__(self, hef=None, backend=None):
        self.hef = LLM_HEF if hef is None else hef
        self.model = os.path.splitext(os.path.basename(self.hef))[0] if self.hef else None
        self._backend = backend
        self._complete = self._close = None

    def __enter__(self):
        if self._backend is not None:
            self._complete, self._close = self._backend, (lambda: None)
            return self
        if not self.hef:
            raise LLMUnavailable("LLM_HEF 가 비어 있다")
        if not os.path.exists(self.hef):
            raise LLMUnavailable(f"LLM_HEF 파일이 없다: {self.hef}")
        self._complete, self._close = _hailo_backend(self.hef)
        return self

    def __exit__(self, *exc):
        if self._close:
            self._close()
        return False

    def complete(self, system, user, max_tokens=256, temperature=0.0, timeout_s=60):
        t0 = time.monotonic()
        out = self._complete(system, user, max_tokens, temperature, timeout_s)
        self.last_ms = round((time.monotonic() - t0) * 1000)
        return out

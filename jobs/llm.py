"""로컬 LLM 공용 라이브러리 — Hailo-10H GenAI (PLAN §5.2). 소비자는 jobs/report.py(리포트)·jobs/fetch_news.py(기사 요약)뿐이다.

원칙(CLAUDE.md §2 해석 AI): 입력은 숫자·정제된 메뉴명·(기사 요약에 한해) 본문뿐 — 프레임·좌표는 절대 넣지 않는다. 출력은 여기의 검증기
(`valid_korean`, `numbers_subset`)를 통과한 것만 저장하고, 실패·미설치·busy 는 호출자가 규칙 템플릿/DeepL 로 물러선다.
점심시간 밖에서만 부른다(HAT·CPU 경합 회피) — 타이머가 그렇게 잡혀 있다.

장치 API(학교 Pi HailoRT 5.1.1 에서 09-04 확인): `genai.LLM(vdevice, model_path, lora_name='', optimize_memory_on_device=False)`,
`generate_all(prompt, temperature, top_p, top_k, frequency_penalty, max_generated_tokens, do_sample, seed, timeout_ms=600000) -> str`,
prompt 는 문자열(원문 그대로) 또는 chat 리스트 `[{"role","content"}]`. `generate` 는 스트리밍. 모델 파일은 공개 경로
`https://dev-public.hailo.ai/v<HailoRT>/blob/<모델>.hef` (예: v5.1.1/blob/Qwen2.5-1.5B-Instruct.hef, 2.36 GB) — 로그인 없이 받는다.
`hailo_platform` 은 5.1.1 까지는 apt 시스템 패키지(`--system-site-packages` venv 로 보임), 5.3.0 부터는 Hailo 휠을 venv 에 직접 설치(09-04). 모양이 다르면 LLMUnavailable 로 물러선다
(아무것도 깨지지 않는다). `LLM_HEF` 가 비어 있으면 아예 시도하지 않는다."""
import json
import os
import re
import time

from app import llm_overlay
from app.config import LLM_API_KEY, LLM_BACKEND, LLM_BASE_URL, LLM_HEF, LLM_MODEL

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


THINK = re.compile(r"<think>.*?</think>\s*", re.S)


def strip_think(text):
    """추론 모드 모델(Qwen3·EXAONE 4·Gemma 4 thinking)이 앞에 붙이는 <think>…</think> 를 떼어 낸다. 닫히지 않은 think 는 통째로 버린다"""
    if not isinstance(text, str):
        return text
    out = THINK.sub("", text)
    if "<think>" in out:
        out = out.split("<think>")[0]
    return out.strip()


def resolve_backend(backend=LLM_BACKEND, hef=LLM_HEF, model=LLM_MODEL):
    """.env 의 LLM_BACKEND 를 실제 엔진 이름으로: auto → hailo(.hef 있음) | openai(모델 이름 있음) | none"""
    if backend == "auto":
        return "hailo" if hef else ("openai" if model else "none")
    return backend


# ---------------- 장치 ----------------
def _openai_backend(base_url, model, key="", session_timeout=None):
    """OpenAI 호환 chat/completions 백엔드(10-20) — 표준 라이브러리만. Ollama(/v1)·hailo-ollama·공통기반 게이트웨이·OpenAI 가 같은 요청 모양이다.
    → (complete(system, user, max_tokens, temperature, timeout_s) -> str, close()). 연결 거부·404 는 LLMUnavailable, 429·503 은 LLMBusy"""
    import urllib.error
    import urllib.request
    if not model:
        raise LLMUnavailable("LLM_MODEL 이 비어 있다(openai 백엔드는 모델 이름이 필요)")
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    def complete(system, user, max_tokens, temperature, timeout_s):
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": int(max_tokens), "temperature": float(temperature), "stream": False}
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as r:
                doc = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:200]
            if e.code in (429, 503):
                raise LLMBusy(f"{model}: HTTP {e.code} {msg}")
            raise LLMUnavailable(f"{model}: HTTP {e.code} {msg}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise LLMUnavailable(f"{url}: {e}")
        try:
            text = doc["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMUnavailable(f"{model}: 응답 모양이 다르다 {str(doc)[:120]}")
        return strip_think(text or "")

    return complete, (lambda: None)


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

    def __init__(self, hef=None, backend=None, engine=None, base_url=None, model=None, api_key=None):
        """engine: None 이면 .env(LLM_BACKEND) 위에 관리 앱 오버레이(data/llm.local.json)를 덮은 값으로 정한다. hef 를 직접 주면(테스트·스파이크) hailo 로 본다"""
        eff = llm_overlay.effective() if (engine is None and hef is None and model is None) else None
        self.hef = LLM_HEF if hef is None else hef
        self.base_url = (eff["base_url"] if eff else LLM_BASE_URL) if base_url is None else base_url
        self.api_key = LLM_API_KEY if api_key is None else api_key
        self._backend = backend
        self._complete = self._close = None
        if engine is None:
            if hef is not None:
                engine = "hailo"
            elif eff:
                engine = resolve_backend(eff["backend"], self.hef, eff["model"])
            else:
                engine = resolve_backend(model=model)
        self.engine = engine                                          # hailo | openai | none — reports.db engine 열에 그대로
        if engine == "openai":
            self.model = (eff["model"] if eff else LLM_MODEL) if model is None else model
        else:
            self.model = os.path.splitext(os.path.basename(self.hef))[0] if self.hef else None

    def __enter__(self):
        if self._backend is not None:
            self._complete, self._close = self._backend, (lambda: None)
            return self
        if self.engine == "none":
            raise LLMUnavailable("LLM_BACKEND=none(또는 LLM_HEF·LLM_MODEL 둘 다 비어 있다)")
        if self.engine == "openai":
            self._complete, self._close = _openai_backend(self.base_url, self.model, self.api_key)
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


# ---------------- 점검 CLI(10-20) ----------------
CHECK_NEWS = ("Summarize the article in exactly 4 short English lines. Use only numbers that appear in the article.",
              "The school cafeteria serves 720 students in 70 minutes at lunch. A Raspberry Pi 5 counts the queue with a camera and "
              "stores only numbers, never video. On Tuesday the longest wait was 7.5 minutes at 12:40, and the average was 1.5 minutes. "
              "Staff said two serving lines could cut the peak to 4 minutes.")
CHECK_REPORT = ("너는 학교 급식실 안내문 작성자다. 주어진 숫자만 써서 JSON 하나만 출력한다: "
                "{\"headline\": 40자 이내 한국어, \"body\": 120자 이내 한국어, \"tone\": \"calm\"}. 입력에 없는 숫자는 절대 쓰지 않는다.",
                "오늘 중식 집계: 평균 대기 1.5분, 최고 대기 7.5분(12:40), 식수 약 720명, 병목 1회(12:41~12:44), 황금 구간 11:32~11:35.")


def check_summary(n=1, log=None):
    """엔진 하나로 뉴스 요약(영어, 숫자 부분집합)·리포트 문장(한국어 JSON) 두 과제를 n 번 돌려 통과율·속도를 잰다 — 모델 비교표의 재료.
    → {ok, engine, model, base_url, at, news:{n,pass,ms,cps}, report:{...}, samples:[…짧은 출력…], error}. 저장은 호출자(관리 앱)가. 급식 창 밖에서 돌린다"""
    import datetime as _dt
    import statistics
    log = log or (lambda s: None)
    m = LocalLLM()
    res = {"ok": False, "engine": m.engine, "model": m.model, "base_url": m.base_url if m.engine == "openai" else None,
           "at": _dt.datetime.now().isoformat(timespec="seconds"), "news": {"n": 0, "pass": 0}, "report": {"n": 0, "pass": 0}, "samples": [], "error": None}
    log(f"백엔드 {m.engine}  모델 {m.model or '-'}  주소 {res['base_url'] or '-'}")
    rows = []
    try:
        with m:
            for k in range(n):
                t = m.complete(*CHECK_NEWS, max_tokens=160)
                ok1 = numbers_subset(CHECK_NEWS[1], t) and 2 <= t.count("\n") + 1 <= 6
                rows.append(("news", ok1, m.last_ms, len(t)))
                res["samples"].append({"kind": "news", "ok": ok1, "ms": m.last_ms, "text": t[:200]})
                log(f"[news {k + 1}] {m.last_ms} ms  {'PASS' if ok1 else 'FAIL'}  {t[:140].replace(chr(10), ' / ')}")
                t2 = m.complete(*CHECK_REPORT, max_tokens=160)
                obj = parse_json_object(t2) or {}
                ok2 = bool(obj) and valid_korean(CHECK_REPORT[1], str(obj.get("headline", "")), max_len=40)[0] \
                    and valid_korean(CHECK_REPORT[1], str(obj.get("body", "")), max_len=120)[0]
                rows.append(("report", ok2, m.last_ms, len(t2)))
                res["samples"].append({"kind": "report", "ok": ok2, "ms": m.last_ms, "text": t2[:200]})
                log(f"[report {k + 1}] {m.last_ms} ms  {'PASS' if ok2 else 'FAIL'}  {t2[:140].replace(chr(10), ' / ')}")
    except LLMUnavailable as e:
        res["error"] = str(e)[:300]
        log(f"사용 불가: {e}")
        return res
    for kind in ("news", "report"):
        rs = [r for r in rows if r[0] == kind]
        if rs:
            ms = statistics.median(r[2] for r in rs)
            chars = statistics.median(r[3] for r in rs)
            res[kind] = {"n": len(rs), "pass": sum(1 for r in rs if r[1]), "ms": round(ms), "cps": round(chars / max(1, ms / 1000), 1)}
            log(f"{kind}: 통과 {res[kind]['pass']}/{len(rs)}  중앙값 {ms:.0f} ms  ≈{res[kind]['cps']} 자/초")
    res["ok"] = res["news"]["pass"] > 0 or res["report"]["pass"] > 0
    return res


def check(n=1):
    """CLI 용 — check_summary 를 화면에 찍고 0/1"""
    res = check_summary(n, log=print)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="LLM 백엔드 점검 — .env 의 LLM_BACKEND·LLM_MODEL·LLM_HEF 로 두 과제를 돌린다")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("-n", type=int, default=1)
    a = ap.parse_args()
    sys.exit(check(a.n) if a.check else 0)

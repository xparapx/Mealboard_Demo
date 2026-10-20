# LLM 백엔드 실측 비교 — Pi 5에서 바꿔 끼울 수 있는 모델들

> 2026-10-20 저녁(석식 창 뒤), 급식실 Pi 5 16 GB에서 `uv run python -m jobs.llm --check -n 2` 로 잰 값. 공모전 공통 개발 규칙 "특정 모델에 종속되지 않는 교체 구조 + 2종 이상 모델 구동 입증"의 증빙이자, 운영 기본 모델을 고르는 근거.
> 재현: `.env LLM_BACKEND=…`(또는 관리 화면 'AI 모델 선택') → `--check`. 두 과제는 실제 파이프라인과 같은 검증기를 지난다 — 뉴스 요약(영어 4줄, **입력에 없는 숫자 금지**), 리포트 문장(한국어 JSON headline≤40·body≤120, 한글 비율·숫자 부분집합).

## 결과

| 엔진 · 모델 | 실행 위치 | 크기 | 뉴스 요약 | 리포트 문장 | 뉴스 응답 | 리포트 응답 | 한국어 품질 |
|---|---|---|---|---|---|---|---|
| **hailo · Qwen3-1.7B-Instruct**(현재 운영) | Hailo-10H 칩(HEF, Q4) | 2.9 GB | 2/2 통과 | 2/2 통과 | 10.5 s | 14.2 s | 검증은 통과하나 본문에 한자 혼입("平均待取1.5분, 最高7.5분, 720名食客") — 사람이 읽을 문장으로는 부적합(09-04 이래 같은 증상, 그래서 리포트는 규칙 템플릿 유지) |
| **openai · gemma4:e2b**(Ollama) | Pi 5 CPU 4코어(Q4_K_M) | 4.6 GB | 2/2 통과 | 2/2 통과 | 3.7 s | 8.8 s | **자연스러운 한국어** — "평균 대기 시간은 1.5분이나 최고 7.5분이 발생했습니다. 식수 약 720명이 이용했으며…" 숫자 정확, 지시 준수 |
| openai · ingu627/exaone4.0:1.2b(Ollama 커뮤니티 빌드) | Pi 5 CPU | 0.8 GB | 0/2 | 0/2 | 18.0 s | 16.7 s | 생각 과정이 본문으로 새어 나옴("Alright, let's tackle this…", "오늘의 중식 집계 결과를 분석해 보겠습니다 ### 주요 지표"). 커뮤니티 모델 템플릿이 `think=false` 를 받지 않는 탓 — 공식 GGUF·템플릿으로 다시 시험할 가치는 있음 |
| none · 규칙 템플릿 | — | 0 | (LLM 없음) | 항상 통과 | 0 | 0 | 정해진 문장. 지금 리포트 운영값(`LLM_REPORT=0`) |

응답 시간은 모델이 이미 메모리에 올라 있을 때의 중앙값. Hailo 는 호출마다 프로세스가 모델을 올리므로(≈11 s) 실제 작업 시간은 더 길고, Ollama 는 마지막 사용 뒤 5분간 메모리에 유지(4.6 GB)했다가 내린다.

## 해석

1. **교체 구조는 입증됐다**: 같은 코드·같은 검증기로 세 엔진(Hailo HEF · Ollama CPU · 템플릿)이 돈다. 전환은 `.env` 한 줄 또는 관리 화면.
2. **Gemma 4 E2B 가 우리 과제에서 가장 낫다** — 공통기반 지원 모델이면서 한국어를 직접 쓰고, Pi 5 CPU 에서 Hailo 칩보다 빠르다(모델이 올라 있을 때). 채택하면 09-04 이래 막혀 있던 **리포트 LLM 문장(`LLM_REPORT=1`)과 뉴스 요약의 한국어 직접 생성(DeepL 생략)** 이 가능해진다.
3. 첫 시도(OpenAI 호환 경로)에서 Gemma 4·EXAONE 둘 다 0/4 였던 원인은 '생각 모드' — Ollama 네이티브 `/api/chat` + `think=false` 로 바꿔 Gemma 4 는 4/4. 모델 성능이 아니라 호출 방식 문제였다는 기록.
4. 제약: Ollama 의 Gemma 4 는 메모리 4.6 GB 를 쓰고 CPU 4코어를 점유한다 → **급식 창 안에서는 부르지 않는다**(기존 규칙 그대로: 뉴스 06:10·리포트 05:45/14:20). 관리 화면 점검도 창 안에는 거부(강행 가능).

## 운영 전환 절차(선택 시)

1. 관리 화면 → AI 모델 선택 → 엔진 'OpenAI 호환 서버' · 모델 `gemma4:e2b` · 주소 `http://127.0.0.1:11434/v1` → 적용 → 점검 실행으로 4/4 확인.
2. `.env LLM_REPORT=1` 로 리포트 문장도 LLM 에 맡길지 결정(규칙 템플릿 폴백은 그대로).
3. 며칠 뒤 reports.db 의 `engine='openai'` 행과 news.json 의 요약을 읽어 보고 유지 여부 판단. 되돌리기는 관리 화면 '.env 로 되돌리기' 한 번.

## 환경

- Pi: Raspberry Pi 5 16 GB, Debian 13, Ollama 0.40.6(CPU 전용, `127.0.0.1:11434` 만 수신, systemd `ollama` enabled), HailoRT 5.3.0 + Hailo-10H.
- 모델: `gemma4:e2b`(Ollama 라이브러리, Q4_K_M 4.6 GB), `ingu627/exaone4.0:1.2b`(커뮤니티, 812 MB), `data/models/Qwen3-1.7B-Instruct.hef`.
- 코드: `jobs/llm.py`(`LLM_BACKEND`, `_openai_backend` — Ollama 판별 시 네이티브 API), `app/llm_overlay.py`·`app/admin/llm_store.py`·`app/admin/routers/llm.py`(관리 화면 선택), 테스트 `tests/test_llm_backend.py`·`tests/test_llm_select.py`.

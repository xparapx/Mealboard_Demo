# 제3자 구성요소 라이선스 목록 (공모전 N2 — 재배포 제한 구성요소 명시)

> 2026-11-05 기준, `uv.lock` 의 고정 버전. 이 저장소 자체 코드는 MIT(`LICENSE`).
> 「2026 공공 AI 대전환 챌린지」 안내서의 "오픈소스 라이선스 준수 책임은 참가팀, 재배포가 제한되는 구성요소는 구동안내서에 명시" 조항에 대한 답이다.

## 1. 한눈에 — 재배포 제한이 있는 것

| 구성요소 | 라이선스 | 어디에 쓰나 | 제한·대응 |
|---|---|---|---|
| **ultralytics 8.4** (YOLO11 코드·ByteTrack 구현) | **AGPL-3.0** | `vision/counter.py` — 카메라 노드만(선택 사양 `--extra vision`) | 파생물·네트워크 서비스도 소스 공개 의무. **본 산출물은 전체 소스를 공개해 조건을 충족**한다. 수상 후 기관이 **비공개로 재구성·재배포**하려면 Ultralytics 상용 라이선스를 받거나 검출기를 Apache 계열(ONNX Runtime + RT-DETR 등)로 교체해야 한다. 공개 웹 앱(`app/`)·집계(`jobs/`)·관리 앱은 ultralytics 를 import 하지 않는다 |
| **YOLO11n 가중치** `yolo11n.pt` | AGPL-3.0 (Ultralytics 배포) | 같은 곳 | 저장소에 포함하지 않는다 — 첫 실행 시 ultralytics 가 내려받는다. 위와 같은 조건 |
| **Hailo HEF 모델**(YOLO·Qwen3-1.7B 등) · HailoRT 5.3.0 | Hailo Model Zoo / HailoRT 라이선스(공개 내려받기, **재배포 제한 가능**) | Pi 의 AI HAT(선택 사양) | 저장소에 포함하지 않는다(내려받기 URL 만, 매뉴얼). **Hailo 가속은 선택 사양** — 없으면 CPU 경로(ultralytics CPU · Ollama)로 같은 기능이 돈다 |
| **Gemma 4 E2B**(Ollama, 운영 LLM) | Gemma Terms of Use(Google) | `jobs/llm.py` openai 백엔드(Ollama) | 사용·수정·재배포 허용이나 금지 용도 정책 수반. 모델 파일은 저장소에 없고 `ollama pull` 로 받는다. 교체 가능(`LLM_BACKEND`, 관리 화면) — `docs/LLM-BACKENDS.md` |
| **Qwen3 / Qwen2.5 1.5B~1.7B**(Hailo HEF·예비) | Apache-2.0 | 같은 곳(hailo 백엔드) | 제한 없음(모델 파일은 Hailo 가 재컴파일해 배포 → 위 Hailo 행도 함께 적용) |
| **DeepL API Free** | DeepL 이용약관 | `jobs/translators.py`(뉴스 번역) | API 키는 운영자 각자 발급(`.env`), 결과 텍스트 재배포 제한 없음. 키 없으면 영어 원문으로 동작 |
| **OpenAI TTS**(시연 음성 `static/media/voice/*.mp3`) | OpenAI 이용약관(출력물 권리는 이용자) | 앱 안내 자동 시연 | 음성 파일은 저장소에 포함(약 3분, 아나운서 대본은 자체 작성). 키 없이도 브라우저 Web Speech 로 같은 대본을 읽는다 |
| **NEIS 급식 식단 정보 Open API** | 공공데이터 이용약관(교육부·나이스) | `jobs/fetch_neis.py` | 인증키는 운영자 각자 발급. 출처 표기 유지 |
| **해외 기후·기술 매체 RSS**(Carbon Brief 등 8곳) | 각 매체 약관 | `jobs/fetch_news.py` | 제목·짧은 자체 요약·출처 링크만 표시, 본문은 저장하지 않는다 |

저장소에 **포함된** 제3자 자산은 없다 — 아이콘(`setup_icons.py` 생성)·평면도(`data/plan_bg.png`, 자체 작도)·도면·음성 대본·모의 데이터 생성기는 모두 자체 제작이며, 외부 폰트·CDN 스크립트를 쓰지 않는다(시스템 글꼴만).

## 2. 파이썬 의존성 전체(uv.lock 고정 버전)

### 2-1. 기본(공개 앱 · 관리 앱 · 집계 · 데모 — Pi 없이 심사위원이 돌리는 범위)

| 패키지 | 버전 | 라이선스 |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| starlette | 1.6.0 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| uvicorn[standard] | 0.52.4 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httptools | 0.8.0 | MIT |
| websockets | 17.1 | BSD-3-Clause |
| uvloop | 0.22.1 | MIT / Apache-2.0 |
| watchfiles | 1.2.0 | MIT |
| anyio | 4.14.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| idna | 3.19 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| PyJWT[crypto] | 2.13.0 | MIT |
| cryptography | 50.0.1 | Apache-2.0 / BSD-3-Clause |
| cffi · pycparser | 2.1.1 · 3.0 | MIT · BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| pytest(개발) | 9.1.1 | MIT |
| iniconfig · pluggy · packaging · pygments(개발) | 2.3.0 · 1.6.0 · 26.3 · 2.21.0 | MIT · MIT · Apache-2.0/BSD · BSD-2-Clause |

### 2-2. 선택 사양 `vision`(카메라 노드 — Pi 또는 웹캠 PC 에서만)

| 패키지 | 버전 | 라이선스 |
|---|---|---|
| **ultralytics** | 8.4.147 | **AGPL-3.0** |
| ultralytics-thop | 2.1.6 | AGPL-3.0 |
| torch | 2.14.0 | BSD-3-Clause |
| torchvision | 0.29.0 | BSD-3-Clause |
| opencv-python | 5.0.0.93 | Apache-2.0 |
| numpy | 2.4.6 / 2.5.3 | BSD-3-Clause |
| pillow | 12.3.0 | MIT-CMU |
| scipy | (torch 의존) | BSD-3-Clause |
| matplotlib · contourpy · cycler · fonttools · kiwisolver · pyparsing · python-dateutil · six | 3.11.1 등 | PSF 계열 · BSD-3 · BSD-3 · MIT · BSD-3 · MIT · BSD/Apache · MIT |
| pandas · polars | (ultralytics 의존) | BSD-3-Clause · MIT |
| requests · urllib3 · certifi · charset-normalizer | 2.34.2 · 2.7.0 · 2026.7.22 · 3.5.1 | Apache-2.0 · MIT · MPL-2.0 · MIT |
| psutil | 7.2.2 | BSD-3-Clause |
| tqdm | (ultralytics 의존) | MIT / MPL-2.0 |
| filelock · fsspec · sympy · mpmath · networkx · jinja2 · markupsafe | 3.32.6 · 2026.7.0 · 1.14.0 · 1.3.0 · 3.6.1 · 3.1.6 · 3.0.3 | Unlicense · BSD-3 · BSD-3 · BSD-3 · BSD-3 · BSD-3 · BSD-3 |
| hailort(휠, Pi 전용) | 5.3.0 | Hailo 라이선스(HailoRT 라이브러리 소스는 MIT, 펌웨어·드라이버는 Hailo 약관) |
| picamera2(시스템 apt, Pi 전용) | Debian 13 | BSD-2-Clause |

## 3. 시스템·서비스

| 구성요소 | 라이선스 | 비고 |
|---|---|---|
| Raspberry Pi OS / Debian 13 | 각 패키지 라이선스 | — |
| uv | MIT / Apache-2.0 | 패키지 관리 |
| Ollama 0.40 | MIT | Pi 의 CPU LLM 서버 |
| cloudflared | Apache-2.0 | 외부 공개 터널(선택) |
| Tailscale | BSD-3-Clause(클라이언트) | 예비 경로(선택) |
| qrencode | LGPL-2.1 | 접속 QR 생성(별도 실행, 코드에 링크 안 함) |

## 4. 요약 문장(구동안내서 '알려진 제약' 에 그대로 옮긴다)

> 본 산출물의 자체 코드는 MIT 로 공개한다. 카메라 노드가 선택적으로 쓰는 **ultralytics(YOLO11 코드·가중치)는 AGPL-3.0** 이며, 본 산출물은 전체 소스를 공개하므로 조건을 충족한다. 다만 기관이 이를 **비공개로 재구성·재배포**하려면 Ultralytics 상용 라이선스 취득 또는 Apache 계열 검출기로의 교체가 필요하다. Hailo 가속(HEF·HailoRT)과 Gemma 4 모델은 각 공급사 약관을 따르는 **선택 사양**으로 저장소에 포함하지 않으며, 없어도 CPU 경로로 동일 기능이 동작한다. 공개 웹 앱·집계·관리 앱·심사위원 구동 경로(`jobs/demo.py`)는 AGPL 구성요소를 전혀 사용하지 않는다.

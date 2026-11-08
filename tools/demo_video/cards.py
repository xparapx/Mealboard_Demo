"""시연영상 정지 카드(1920×1080 PNG) — 제목·LLM 교체 실측표·마무리. Pillow + 맑은 고딕"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
F = "C:/Windows/Fonts/malgun.ttf"; FB = "C:/Windows/Fonts/malgunbd.ttf"
BG, CARD, INK, TEAL, MUTE, CHAR = "#F5F2E9", "#FFFCF6", "#26262A", "#1F8A85", "#6B6B70", "#2B2B30"


def font(sz, bold=False):
    return ImageFont.truetype(FB if bold else F, sz)


def card(name, draw_fn, bg=BG):
    im = Image.new("RGB", (1920, 1080), bg); d = ImageDraw.Draw(im)
    draw_fn(d, im); im.save(OUT / f"{name}.png"); print("card", name)


def text(d, xy, s, sz, fill=INK, bold=False, anchor="la", spacing=10):
    d.multiline_text(xy, s, font=font(sz, bold), fill=fill, anchor=anchor if "\n" not in s else "la", spacing=spacing)


def pill(d, xy, s, sz=26, fg="#fff", bg=TEAL):
    f = font(sz, True); w = d.textlength(s, font=f); x, y = xy
    d.rounded_rectangle((x, y, x + w + 40, y + sz + 26), radius=(sz + 26) // 2, fill=bg); d.text((x + 20, y + 11), s, font=f, fill=fg)


def title(d, im):
    d.rounded_rectangle((160, 150, 1760, 930), radius=36, fill=CARD)
    d.ellipse((230, 230, 330, 330), fill=TEAL); d.ellipse((252, 252, 308, 308), fill="#FFFCF6"); d.ellipse((268, 268, 292, 292), fill="#F2B544")
    text(d, (370, 236), "헤아림 · Hearim", 56, bold=True)
    text(d, (370, 312), "급식실 대기시간 예측 · 급식 정보 안내 서비스", 40, fill=MUTE)
    text(d, (230, 440), "급식실 카메라가 영상 없이 줄 선 인원만 세어", 46)
    text(d, (230, 506), "예상 대기시간 · 밀집도 · 영양 · 운영 리포트를 한 화면에", 46)
    pill(d, (230, 620), "2026 공공 AI 대전환 챌린지 · 세션 1 자유주제"); pill(d, (870, 620), "공주고등학교", bg=CHAR)
    text(d, (230, 692), "수를 헤아려, 기다림을 헤아립니다", 34, fill=TEAL, bold=True)
    text(d, (230, 760), "실운영 https://kjhs-meal.com      상시 시연 https://demo.kjhs-meal.com", 32, fill=MUTE)
    text(d, (230, 812), "공공 GitLab https://gitlab.aigov.go.kr/kongju-hs/mealboard      자체 코드 MIT", 32, fill=MUTE)
    text(d, (1690, 880), "코드명 Mealboard  ·  시연영상 약 5분", 26, fill=MUTE, anchor="ra")


def three(d, im):
    text(d, (160, 120), "핵심 기능 셋 — 기능의 수가 아니라, 셋이 안정적으로 돕니다", 48, bold=True)
    items = [("①", "예상 대기시간", "대기 인원 L ÷ 배식 속도 λ\n(Little's law)\n\n줄 선 사람의 실제 체류시간을\nFIFO 누적곡선으로 재어\n스스로 보정 — 보정계수 K 공개\n\n여유 · 보통 · 혼잡 판정\n예보 · 황금 시간대\n요일×시각 히트맵 · 병목 로그\n측정 품질 카드"),
             ("②", "급식실 밀집도", "평면도 위 익명 위치 마커\n(5초 순간 상태)\n\n육각 타일 밀집도 · 구역 비율\n\n최근 7일 평소 밀집도 ①②③\n\n개별 좌표 · 궤적은\n저장하지 않습니다"),
             ("③", "영양 · 운영 리포트", "NEIS 중식 · 석식 식단\n에너지 충족률 · 적정비율 · MAR\n내 알레르기 경고(기기에만 저장)\n잔반 탄소\n\n통계(밴드 · 요일 · 메뉴)\n통행로 키오스크\n\n로컬 LLM 리포트 —\n입력에 없는 숫자는 검증기가 차단")]
    for k, (n, h, body) in enumerate(items):
        x = 160 + k * 545
        d.rounded_rectangle((x, 240, x + 500, 900), radius=30, fill=CARD)
        d.ellipse((x + 36, 280, x + 116, 360), fill=TEAL); d.text((x + 76, 320), n, font=font(44, True), fill="#fff", anchor="mm")
        text(d, (x + 140, 296), h, 38, bold=True)
        d.multiline_text((x + 40, 400), body, font=font(26), fill=CHAR, spacing=12)
    text(d, (160, 960), "영상 프레임은 저장 · 전송하지 않습니다 — 10초마다 숫자만 SQLite 에 남깁니다", 30, fill=TEAL, bold=True)


def llm(d, im):
    text(d, (160, 110), "LLM 은 갈아 끼웁니다 — 모델 비종속 (.env 한 줄 또는 관리 화면)", 48, bold=True)
    d.rounded_rectangle((160, 200, 1760, 330), radius=24, fill="#26262A")
    mono = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 32)
    d.text((200, 222), "LLM_BACKEND=openai   LLM_BASE_URL=http://127.0.0.1:11434/v1   LLM_MODEL=gemma4:e2b", font=mono, fill="#D7F3EF")
    d.text((200, 276), "uv run python -m jobs.llm --check -n 2", font=mono, fill="#9fd8d2")
    d.text((900, 278), "← 뉴스 요약 · 리포트 문장 두 과제를 같은 검증기로 점검", font=font(28), fill="#9fd8d2")
    cols = [("엔진 · 모델", 560), ("실행 위치", 300), ("뉴스 요약", 200), ("리포트", 200), ("응답(뉴스/리포트)", 300), ("한국어", 0)]
    rows = [("hailo · Qwen3-1.7B (HEF)", "Hailo-10H 칩", "2/2", "2/2", "10.5 s / 14.2 s", "한자 혼입"),
            ("openai · Gemma 4 E2B (Ollama)  ★ 운영", "Pi 5 CPU", "2/2", "2/2", "3.7 s / 8.8 s", "자연스러움"),
            ("openai · EXAONE 4.0 1.2B (커뮤니티 빌드)", "Pi 5 CPU", "0/2", "0/2", "18.0 s / 16.7 s", "생각 누출"),
            ("openai · Qwen 3.5 2B / 4B", "Pi 5 CPU", "0/2 · 2/2", "2/2 · 0/2", "10 s / 20 s", "부분 통과"),
            ("none · 규칙 템플릿", "—", "—", "항상 통과", "0 s", "정해진 문장")]
    y = 380; x0 = 160
    d.rounded_rectangle((160, y, 1760, y + 70), radius=16, fill="#E7E2D3")
    x = x0 + 24
    for h, w in cols:
        d.text((x, y + 18), h, font=font(28, True), fill=INK); x += w
    y += 86
    for r in rows:
        bold = "★" in r[0]
        if bold: d.rounded_rectangle((160, y - 10, 1760, y + 56), radius=14, fill="#DDEFEC")
        x = x0 + 24
        for v, (h, w) in zip(r, cols):
            d.text((x, y), v, font=font(28, bold), fill=INK if not bold else "#0F5F5B"); x += w
        y += 78
    text(d, (160, 860), "Pi 5 16 GB 실측 2026-10-20 (docs/LLM-BACKENDS.md). 같은 코드 · 같은 검증기로 세 엔진(Hailo HEF · Ollama CPU · 템플릿)이 돕니다.", 28, fill=MUTE)
    text(d, (160, 905), "공통기반 지원 모델(Gemma · EXAONE 등)과 OpenAI 호환 게이트웨이가 같은 모양 — 심사위원 PC 에서는 Ollama 로 2종 교체 확인", 28, fill=MUTE)
    text(d, (160, 965), "시연 모드에서는 LLM_REPORT=0 — 모델이 없어도 운영 화면과 같은 구성이 보입니다", 28, fill=TEAL, bold=True)


def ending(d, im):
    d.rounded_rectangle((160, 150, 1760, 930), radius=36, fill=CARD)
    text(d, (230, 220), "생활 공간의 작은 불편 하나를 끝까지 숫자로 따라가면, 공공의 가치가 됩니다.", 40, bold=True)
    text(d, (1690, 170), "헤아림 · Hearim", 30, fill=TEAL, bold=True, anchor="ra")
    text(d, (230, 300), "발견 → 공익 → 측정 → 진단 → 해결", 36, fill=TEAL, bold=True)
    lines = [("저장되는 영상", "0장"), ("필요한 장비", "Raspberry Pi 5 + 카메라 1대 (약 20~30만 원)"), ("급식 정보", "전국 공통 NEIS Open API"),
             ("다른 학교 이식", "평면도 보정 · 영양 기준 · 학교 설정 — 설정 파일 3개"), ("심사위원 구동", "uv sync  →  uv run python -m jobs.demo  (Pi · 카메라 없이 5분)"),
             ("소스 · 라이선스", "MIT · 테스트 238건 · 작업 이력 전부 공개")]
    y = 400
    for k, v in lines:
        d.text((230, y), k, font=font(30, True), fill=MUTE); d.text((560, y), v, font=font(30), fill=INK); y += 62
    text(d, (230, 820), "https://kjhs-meal.com   ·   https://demo.kjhs-meal.com   ·   https://gitlab.aigov.go.kr/kongju-hs/mealboard", 30, fill=TEAL)
    text(d, (1690, 880), "공주고등학교 · 2026 공공 AI 대전환 챌린지 세션 1", 26, fill=MUTE, anchor="ra")


def stamp(n, head, sub):
    def f(d, im):
        d.rectangle((0, 0, 1920, 1080), fill="#26262A")
        d.rounded_rectangle((120, 440, 136, 640), radius=8, fill=TEAL)
        d.text((190, 420), n, font=font(96, True), fill=TEAL)
        d.text((400, 440), head, font=font(84, True), fill="#FFFCF6")
        d.text((404, 560), sub, font=font(40), fill="#CFE7E4")
        d.text((1800, 980), "헤아림 · Hearim", font=font(28), fill="#8A8A90", anchor="ra")
    return f


card("title", title); card("three", three); card("llm", llm); card("ending", ending)
card("stamp2", stamp("02", "심사위원 구동", "Pi · 카메라 없이, 노트북 한 대에서 한 줄"), bg="#26262A")
card("stamp3", stamp("03", "LLM 교체", "모델 비종속 — 드롭다운 한 번, .env 한 줄"), bg="#26262A")
card("stamp4", stamp("04", "실제 운영 화면", "2026년 9월 11일부터 공주고 급식실에서"), bg="#26262A")

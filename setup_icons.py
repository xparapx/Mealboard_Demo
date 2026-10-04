"""PWA·iOS 홈 화면 아이콘 생성 — 사람이 디자인을 바꿀 때 1회 실행(10-04).

크림 바탕 + 틸 밥그릇 + 김(브랜드 톤, static/css/base.css 변수와 같은 값)을 1024 캔버스에 그려
static/icons/ 에 apple-touch-icon.png(180)·icon-192.png·icon-512.png 를 뽑는다.
관리자판(static/icons/admin/)은 같은 그림 오른쪽 아래에 공구(스패너) 배지를 얹는다 —
관리 앱(8101)이 /icons/* 를 이 폴더로 덮어써서 관리 주소의 홈 화면 아이콘만 배지가 붙는다(app/admin/server.py).

실행: uv run --with pillow python setup_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

CREAM = (245, 242, 233)    # --ground #F5F2E9
CARD = (255, 252, 246)     # #FFFCF6
TEAL = (18, 151, 147)      # --teal #129793
TEAL_INK = (12, 109, 106)  # --teal-ink
INK = (51, 49, 45)         # --ink #33312D

SIZES = [("apple-touch-icon.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)]


def base_icon():
    img = Image.new("RGB", (1024, 1024), CREAM)
    d = ImageDraw.Draw(img)
    d.ellipse([252, 768, 772, 828], fill=(226, 221, 208))          # 접시 그림자
    d.pieslice([280, 300, 744, 640], 180, 360, fill=CARD)          # 밥(돔)
    d.ellipse([392, 368, 444, 410], fill=CREAM)                    # 밥알 음영
    d.ellipse([540, 350, 588, 390], fill=CREAM)
    d.pieslice([212, 140, 812, 800], 0, 180, fill=TEAL)            # 그릇(입구 y=470, 바닥 y=800)
    d.rounded_rectangle([196, 440, 828, 500], radius=30, fill=TEAL_INK)   # 입구 띠
    for cx in (392, 512, 632):                                     # 김 세 줄
        d.arc([cx - 34, 110, cx + 34, 200], 90, 270, fill=INK, width=26)
        d.arc([cx - 34, 175, cx + 34, 265], 270, 90, fill=INK, width=26)
    return img


def wrench_badge(img):
    """오른쪽 아래 공구 배지 — 작게, iOS 모서리 마스크에 잘리지 않게 안쪽으로"""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([648, 668, 952, 972], radius=64, fill=INK)
    d.rounded_rectangle([648, 668, 952, 972], radius=64, outline=CREAM, width=10)
    # 스패너: 수직으로 그려 45° 돌려 얹는다 — 머리(원 + V 홈) + 손잡이
    w = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    wd = ImageDraw.Draw(w)
    wd.ellipse([62, 10, 158, 106], fill=CREAM + (255,))            # 머리
    wd.rounded_rectangle([92, 70, 128, 200], radius=16, fill=CREAM + (255,))   # 손잡이
    wd.rectangle([92, 0, 128, 58], fill=(0, 0, 0, 0))              # V 홈(입)
    wd.ellipse([92, 40, 128, 76], fill=(0, 0, 0, 0))
    w = w.rotate(45, expand=False, resample=Image.BICUBIC)
    img.paste(w, (690, 710), w)
    return img


def emit(img, out):
    out.mkdir(parents=True, exist_ok=True)
    for name, size in SIZES:
        img.resize((size, size), Image.LANCZOS).save(out / name)
        print(out / name, size)


if __name__ == "__main__":
    icons = Path(__file__).parent / "static" / "icons"
    emit(base_icon(), icons)
    emit(wrench_badge(base_icon()), icons / "admin")

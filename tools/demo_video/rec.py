"""시연영상 소재 녹화 — Playwright(설치된 Edge, 1920×1080, 화면 녹화 webm) + 시연 타임라인(JSON)

    python rec.py <out_dir> <scene> [...]     scene: tour app admin live kiosk term
환경: 로컬 데모 http://127.0.0.1:8810 (jobs.demo --with-admin), 관리 앱 URL 은 ADMIN_URL 환경변수.
tour: #wait 에서 자홍색 동기 마커(0.5초) → MB.tour.start() → 단계·클립 시각을 performance.now() 로 기록(tour.json)
"""
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SCENES = sys.argv[2:] or ["tour"]
LOCAL = os.environ.get("LOCAL", "http://127.0.0.1:8812")
W, H = 1920, 1080
HOOK = """
window.__ev = [];
(() => { const p = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function() { try { window.__ev.push({k:'play', src: this.currentSrc || this.src, t: performance.now(), rate: this.playbackRate}); } catch {} return p.apply(this, arguments); }; })();
"""
CAPTION_CSS = """
#__cap{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;display:flex;justify-content:center;pointer-events:none}
#__cap span{display:inline-block;max-width:1500px;margin:0 0 34px;padding:14px 28px;border-radius:14px;background:rgba(38,38,42,.90);color:#fff;
 font:600 30px/1.35 'Malgun Gothic','맑은 고딕',sans-serif;letter-spacing:-.01em;box-shadow:0 8px 30px rgba(0,0,0,.25)}
#__cap span small{display:block;font-weight:400;font-size:22px;color:#cfe7e4;margin-top:4px}
"""


def caption(page, text, sub=""):
    page.evaluate("""([t,s,css]) => {
      if (!document.getElementById('__capcss')) { const st = document.createElement('style'); st.id='__capcss'; st.textContent = css; document.head.appendChild(st); }
      let c = document.getElementById('__cap'); if (!c) { c = document.createElement('div'); c.id='__cap'; document.body.appendChild(c); }
      c.innerHTML = '<span>' + t + (s ? '<small>' + s + '</small>' : '') + '</span>';
    }""", [text, sub, CAPTION_CSS])


def marker(page):
    t = page.evaluate("""() => { const d = document.createElement('div'); d.id='__mk'; d.style.cssText='position:fixed;inset:0;background:#ff00ff;z-index:2147483647';
      document.body.appendChild(d); const t = performance.now(); setTimeout(() => d.remove(), 500); return t; }""")
    time.sleep(0.8)
    return t


def new_ctx(b, name):
    ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, record_video_dir=str(OUT / name), record_video_size={"width": W, "height": H},
                        locale="ko-KR", timezone_id="Asia/Seoul", reduced_motion="no-preference")
    ctx.add_init_script(HOOK)
    pg = ctx.new_page()
    return ctx, pg


def finish(ctx, pg, name):
    v = pg.video.path(); ctx.close()
    dst = OUT / f"{name}.webm"
    if dst.exists(): dst.unlink()
    Path(v).rename(dst)
    print(f"{name}: {dst} {dst.stat().st_size/1e6:.1f} MB")


def scene_tour(b):
    ctx, pg = new_ctx(b, "tour")
    pg.goto(f"{LOCAL}/#wait", wait_until="load")
    time.sleep(3.0)                                   # 첫 폴링·카드 등장
    t_mk = marker(pg)
    time.sleep(1.0)
    ev = {"marker_perf": t_mk, "steps": [], "clips": []}
    pg.evaluate("MB.tour.start()")
    t_start = pg.evaluate("performance.now()")
    ev["start_perf"] = t_start
    last = None; n_play = 0; done_at = None
    while True:
        s = pg.evaluate("""() => { const st = window.MB.tour.step(); const card = document.getElementById('tourcard'); const dots = [...document.querySelectorAll('#tourdots i')];
          const intro = card && !card.hidden && card.dataset.kind === 'intro' ? dots.findIndex(x => x.classList.contains('on')) : -1;
          const outro = card && !card.hidden && card.dataset.kind === 'outro'; return [performance.now(), st, intro, outro, window.__ev.length]; }""")
        t, st, intro, outro, nev = s
        key = f"intro{intro}" if intro >= 0 else ("outro" if outro else (f"s{int(st)}" if st is not None and st >= 0 and st == int(st) else None))
        if key and key != last:
            ev["steps"].append({"id": key, "t": t}); last = key; print(f"  {t/1000:7.2f}s step {key}", flush=True)
            if key == "outro": done_at = time.time() + 20.5
        if nev > n_play:
            evs = pg.evaluate("window.__ev.slice(%d)" % n_play); n_play = nev
            for e in evs:
                cid = e["src"].rsplit("/", 1)[-1].replace(".mp3", "")
                ev["clips"].append({"id": cid, "t": e["t"], "rate": e["rate"]}); print(f"  {e['t']/1000:7.2f}s play {cid} x{e['rate']}", flush=True)
        if done_at and time.time() > done_at: break
        if time.time() - time.time() > 0: pass
        time.sleep(0.04)
    ev["end_perf"] = pg.evaluate("performance.now()")
    (OUT / "tour.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
    finish(ctx, pg, "tour")


def scene_app(b):
    ctx, pg = new_ctx(b, "app")
    pg.goto(f"{LOCAL}/#wait", wait_until="load")
    caption(pg, "uv sync &amp;&amp; uv run python -m jobs.demo", "한 줄 → 모의 데이터 8주치 생성(2초) → http://127.0.0.1:8800 에 여섯 화면 — Pi·카메라 없이")
    time.sleep(5.0)
    for h, cap in (("room", "실시간뷰 — 평면도 위 익명 마커·육각 타일 밀집도"), ("stats", "통계 — 시각별 분포 밴드·요일·메뉴별 대기"), ("today", "오늘급식 — 영양 지표 3종·알레르기·잔반 탄소")):
        pg.evaluate(f"MB.go('{h}')"); caption(pg, cap, "가상 시계 2026-10-14(수) 12:44 · 시연 모드 띠가 모의 데이터임을 밝힙니다"); time.sleep(4.0)
    finish(ctx, pg, "app")


def scene_admin(b):
    url = os.environ.get("ADMIN_URL")
    if not url: print("ADMIN_URL 없음 — admin 장면 생략"); return
    ctx, pg = new_ctx(b, "admin"); t_ctx = time.time()
    pg.goto(url, wait_until="load"); time.sleep(3.5)          # whoami → admin.js 동적 import → '관리' 탭 등록
    # 지난 녹화에서 '적용' 한 선택이 남아 있으면 처음부터 openai 로 보인다 → .env 상태로 되돌리고 다시 연다(데모 데이터 폴더의 llm.local.json 만; 게이트가 JSON Content-Type 을 요구)
    print("reset:", pg.evaluate("async () => (await fetch('/api/admin/llm', {method: 'DELETE', cache: 'no-store', headers: {'Content-Type': 'application/json'}})).status"))
    pg.reload(wait_until="load"); time.sleep(3.5)
    pg.evaluate("MB.go('admin')"); time.sleep(1.8)
    found = pg.evaluate("() => { const c = document.querySelector('#llmcard'); if (!c) return false; c.scrollIntoView({block:'center'}); return true; }")
    print("llmcard:", found); time.sleep(0.6)
    (OUT / "admin.json").write_text(json.dumps({"start": round(time.time() - t_ctx - 0.4, 2)}), encoding="utf-8")   # 조립은 여기부터(앞의 로딩·되돌리기 장면 제외)
    # 카드를 눈에 띄게(시연의 스포트라이트와 같은 틸 테두리) + 드롭다운 실제 조작: 엔진 → OpenAI 호환 서버(Ollama), 모델 → gemma4:e2b, 적용
    # 카드가 1080p 에서 작아 글자가 안 읽힌다 → 시연의 줌처럼 1.5배 확대(오른쪽 열이라 왼쪽으로 당김) + 틸 테두리
    pg.evaluate("""() => { const c = document.querySelector('#llmcard'); c.style.position = 'relative'; c.style.zIndex = '20'; c.style.transformOrigin = 'center';
      c.style.transition = 'transform .5s cubic-bezier(.2,.8,.2,1)'; c.style.outline = '4px solid #1F8A85'; c.style.outlineOffset = '6px'; c.style.boxShadow = '0 24px 60px rgba(0,0,0,.25)';
      requestAnimationFrame(() => { c.style.transform = 'translateX(-140px) scale(1.5)'; }); }""")
    caption(pg, "관리 화면 'AI 모델(LLM) 선택' — 드롭다운으로 엔진 · 모델을 고릅니다", "엔진: Hailo 칩(.hef) · OpenAI 호환 서버(Ollama·공통기반 게이트웨이) · 없음(규칙 문장)")
    time.sleep(2.2)
    pg.select_option("#llmbackend", "openai"); time.sleep(1.6)
    try:
        pg.select_option("#llmmodel", "gemma4:e2b")
    except Exception as e:
        print("모델 선택 실패:", e)
    caption(pg, "엔진 ▾ OpenAI 호환 서버 → 모델 ▾ gemma4:e2b → 적용", "다음 뉴스·리포트 작업부터 이 모델이 씁니다 · 키는 .env 에만 · '.env 로 되돌리기' 한 번이면 원복")
    time.sleep(1.8)
    pg.click("#llmapply"); time.sleep(3.2)
    pg.evaluate("document.querySelector('#llmresult')?.scrollIntoView({block:'center'})")
    time.sleep(4.2)
    finish(ctx, pg, "admin")


def scene_live(b):
    ctx, pg = new_ctx(b, "live")
    pg.goto("https://kjhs-meal.com/#wait", wait_until="load"); time.sleep(3.0)
    caption(pg, "실제 운영 화면 kjhs-meal.com — 2026년 9월 11일부터 공주고 급식실", "급식 시간 밖에는 실측값 대신 '급식 시간이 아닙니다 · 다음 창' 안내")
    time.sleep(4.0)
    pg.evaluate("document.querySelector('#heatcard')?.scrollIntoView({block:'center'})"); caption(pg, "요일 × 시각 히트맵 — 지난 4주 실측 집계", "어두울수록 오래 기다린 시간대 · 오늘 행은 실황으로 차오릅니다"); time.sleep(6.0)
    pg.evaluate("MB.go('stats')"); time.sleep(1.5); caption(pg, "통계 — 시각별 평균·변동 띠, 요일·일별, 줄이 길어지는 메뉴", "4~12주 실측 집계 · 급식 시정표를 조정할 때 보는 그림"); time.sleep(7.0)
    pg.evaluate("MB.go('room')"); time.sleep(1.2); pg.evaluate("document.querySelector('#typcard')?.scrollIntoView({block:'center'})"); caption(pg, "평소 밀집도 · 최근 7일 — 사람이 늘 모이는 자리 ①②③", "영상이 아니라 숫자(육각 타일 인원수)로 만든 그림"); time.sleep(6.0)
    finish(ctx, pg, "live")


def scene_kiosk(b):
    ctx, pg = new_ctx(b, "kiosk")
    pg.goto("https://demo.kjhs-meal.com/kiosk?interval=6", wait_until="load"); time.sleep(1.0)
    caption(pg, "통행로 송출 화면 kiosk.kjhs-meal.com — 42인치 모니터, 10초 회전 7장", "휴대폰이 없는 학생도 지나가며 봅니다")
    time.sleep(21.0)
    finish(ctx, pg, "kiosk")


def scene_term(b):
    ctx, pg = new_ctx(b, "term")
    pg.goto((Path(__file__).parent / "term.html").resolve().as_uri(), wait_until="load")
    time.sleep(float(os.environ.get("TERM_SEC", "16")))
    finish(ctx, pg, "term")


with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=False, args=["--autoplay-policy=no-user-gesture-required", "--window-position=0,0", "--hide-scrollbars", "--mute-audio" if os.environ.get("MUTE") else "--disable-features=none"])
    for sc in SCENES:
        print("==", sc, flush=True)
        globals()[f"scene_{sc}"](b)
    b.close()

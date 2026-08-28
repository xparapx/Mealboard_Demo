"""docs/manual.html 의 코드 블록과 실제 파일 대조 (CLAUDE.md §6 코드-매뉴얼 동기화 규칙).

  uv run python check_manual.py            # 대조만. 불일치가 있으면 목록을 찍고 exit 1
  uv run python check_manual.py --update   # 파일 내용으로 매뉴얼 블록을 다시 쓴다 (파일이 원본, 매뉴얼은 파생)

대상: <figcaption><span class="path">경로</span> 의 '경로' 가 저장소에 실제로 있는 파일인 블록만.
'jobs/x.py 에 추가할 부분' 처럼 파일이 아닌 캡션(발췌·터미널)은 건너뛴다.
"""
import html
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MANUAL = ROOT / "docs" / "manual.html"
FIG = re.compile(r'(<figcaption><span class="path">([^<]+)</span>.*?<pre><code class="lang-[a-z]+">)(.*?)(</code></pre>)', re.S)


def escape(text):
    return html.escape(text, quote=True).replace("&#x27;", "'")


def main():
    update = "--update" in sys.argv
    src = MANUAL.read_text(encoding="utf-8")
    checked, mismatched, out, pos = 0, [], [], 0
    for m in FIG.finditer(src):
        path = ROOT / m.group(2).strip()
        if not path.is_file():
            continue
        checked += 1
        real = path.read_text(encoding="utf-8").rstrip("\n")
        block = html.unescape(m.group(3)).rstrip("\n")
        if real != block:
            mismatched.append(m.group(2).strip())
            if update:
                out.append(src[pos:m.start(3)]); out.append(escape(real)); pos = m.end(3)
    if update:
        out.append(src[pos:])
        MANUAL.write_text("".join(out), encoding="utf-8", newline="\n")
    print(f"대조 {checked}개 블록, 불일치 {len(mismatched)}개" + (" → 갱신함" if update and mismatched else ""))
    for p in mismatched:
        print("  -", p)
    return 1 if (mismatched and not update) else 0


if __name__ == "__main__":
    sys.exit(main())

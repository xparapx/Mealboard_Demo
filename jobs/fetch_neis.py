"""NEIS 급식 API → data/meal.json  (하루 1회, systemd timer 가 실행)
프론트는 이 파일만 읽는다. NEIS 를 직접 호출하지 않는다 (키 노출·호출 제한 방지).

실행:  uv run python -m jobs.fetch_neis
"""
import datetime as dt
import json
import os
import re
import urllib.parse
import urllib.request

from dotenv import load_dotenv
from app.config import BASE, DATA, MEAL_JSON

load_dotenv(BASE / ".env")
STD = json.loads((DATA / "nutrition_std.json").read_text(encoding="utf-8"))
URL = "https://open.neis.go.kr/hub/mealServiceDietInfo"

# NEIS 항목명 → 우리 키.  앞글자 일치로 찾아 "비타민A(R.E)" 같은 표기 변동에 견딘다
KEYMAP = [("탄수화물", "carb_g"), ("단백질", "protein_g"), ("지방", "fat_g"),
          ("비타민A", "vitA"), ("티아민", "b1"), ("리보플라빈", "b2"),
          ("비타민C", "vitC"), ("칼슘", "ca"), ("철", "fe")]


def parse_ntr(s):
    """'탄수화물(g) : 90.6<br/>단백질(g) : 30.1 ...' → {'carb_g': 90.6, ...}"""
    out = {}
    for name, val in re.findall(r"([^<>:]+?)\s*:\s*([\d.]+)", s):
        for prefix, key in KEYMAP:
            if name.strip().startswith(prefix):
                out[key] = float(val)
                break
    return out


def parse_kcal(s):
    m = re.search(r"[\d.]+", s or "")
    return float(m.group()) if m else None


def assess(kcal, n):
    """법정 기준과 비교해 세 지표를 낸다: 에너지 충족률 · 에너지 적정비율 · 미량영양소 충족(MAR)"""
    std = STD["per_meal"]
    energy_pct = round(kcal / std["energy_kcal"] * 100) if kcal else None

    macro = {"carb": n.get("carb_g", 0) * 4,
             "protein": n.get("protein_g", 0) * 4,
             "fat": n.get("fat_g", 0) * 9}                    # g → kcal
    total = sum(macro.values()) or 1
    ratio = {k: round(v / total * 100) for k, v in macro.items()}
    rng = STD["energy_ratio"]
    ratio_ok = all(rng[k][0] <= ratio[k] <= rng[k][1] for k in ratio)

    items, nars = [], []
    for key, ref in std["micro"].items():
        v = n.get(key)
        if v is None:
            continue
        nars.append(min(v / ref["rni"], 1.0))                 # NAR: 넘치는 건 1 로 자른다
        if v < ref["ear"]:
            band = "부족"
        elif v > ref["rni"] * STD["upper_factor"]:
            band = "과다"
        else:
            band = "적정"
        items.append({"key": key, "label": ref["label"], "value": v,
                      "ear": ref["ear"], "rni": ref["rni"],
                      "pct": round(v / ref["rni"] * 100), "band": band})
    mar = round(sum(nars) / len(nars) * 100) if nars else None
    protein_pct = round(n["protein_g"] / std["protein_g"] * 100) if "protein_g" in n else None
    return {"energy_pct": energy_pct, "protein_pct": protein_pct,
            "macro_ratio": ratio, "macro_ratio_ok": ratio_ok,
            "mar": mar, "micro": items}


def fetch(from_ymd, to_ymd):
    q = urllib.parse.urlencode({
        "KEY": os.environ["NEIS_KEY"], "Type": "json",
        "ATPT_OFCDC_SC_CODE": os.environ["NEIS_ATPT_CODE"],
        "SD_SCHUL_CODE": os.environ["NEIS_SCHOOL_CODE"],
        "MMEAL_SC_CODE": "2",                                 # 2 = 중식
        "MLSV_FROM_YMD": from_ymd, "MLSV_TO_YMD": to_ymd})
    with urllib.request.urlopen(URL + "?" + q, timeout=20) as r:
        data = json.load(r)
    if "mealServiceDietInfo" not in data:                     # INFO-200(급식 없음) 등
        return [], data.get("RESULT", {}).get("CODE", "?")
    return data["mealServiceDietInfo"][1]["row"], "INFO-000"


def main():
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    friday = monday + dt.timedelta(days=4)
    rows, code = fetch(monday.strftime("%Y%m%d"), friday.strftime("%Y%m%d"))

    week = []
    for r in rows:
        n = parse_ntr(r.get("NTR_INFO", ""))
        kcal = parse_kcal(r.get("CAL_INFO"))
        menu = [m.strip() for m in r.get("DDISH_NM", "").split("<br/>") if m.strip()]
        week.append({"date": r["MLSV_YMD"], "menu": menu, "kcal": kcal,
                     "nutrients": n, "assess": assess(kcal, n)})

    def avg(key):
        vals = [d["assess"][key] for d in week if d["assess"][key] is not None]
        return round(sum(vals) / len(vals)) if vals else None

    today_s = today.strftime("%Y%m%d")
    out = {"fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
           "result_code": code,
           "state": "ok" if week else "no_meal",
           "std": {"school": STD["school"], "group": STD["group"], "source": STD["source"]},
           "today": next((d for d in week if d["date"] == today_s), None),
           "week_avg": {"energy_pct": avg("energy_pct"), "mar": avg("mar")},
           "week": week}
    MEAL_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장 {MEAL_JSON}  {len(week)}일치  {code}")


if __name__ == "__main__":
    main()

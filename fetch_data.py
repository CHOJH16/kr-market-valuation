# -*- coding: utf-8 -*-
"""한국 버핏지수 / CAPE 자동 수집기 (한국은행 ECOS)"""
import os, json, sys
from datetime import datetime, timezone, timedelta
import requests

KEY  = os.environ.get("ECOS_KEY", "").strip()
BASE = "https://ecos.bok.or.kr/api"
KST  = timezone(timedelta(hours=9))
START, END = "199001", "209912"

if not KEY:
    sys.exit("ECOS_KEY 시크릿이 비어 있습니다. 3단계를 확인하세요.")

def api(path):
    r = requests.get(f"{BASE}/{path}", timeout=120)
    r.raise_for_status()
    j = r.json()
    if "RESULT" in j:
        raise RuntimeError(j["RESULT"].get("MESSAGE", "알 수 없는 오류"))
    return j

def tables():
    return api(f"StatisticTableList/{KEY}/json/kr/1/3000")["StatisticTableList"]["row"]

def items(stat):
    try:
        return api(f"StatisticItemList/{KEY}/json/kr/1/2000/{stat}")["StatisticItemList"]["row"]
    except Exception:
        return []

def fetch(stat, cycle, item):
    j = api(f"StatisticSearch/{KEY}/json/kr/1/100000/{stat}/{cycle}/{START}/{END}/{item}")
    rows = j.get("StatisticSearch", {}).get("row", [])
    return {r["TIME"]: float(r["DATA_VALUE"])
            for r in rows if r.get("DATA_VALUE") not in ("", "-", None)}

# ── 통계표 자동 탐색 ──────────────────────────────
def find_table(must, cycle):
    best = None
    for t in tables():
        nm = t.get("STAT_NAME", "")
        if t.get("CYCLE") != cycle:
            continue
        if all(k in nm for k in must):
            if best is None or len(nm) < len(best["STAT_NAME"]):
                best = t
    return best

def find_item(stat, cycle, must, avoid=()):
    for it in items(stat):
        nm = it.get("ITEM_NAME", "")
        if any(a in nm for a in avoid):
            continue
        if all(k in nm for k in must):
            return it.get("ITEM_CODE"), nm
    return None, None

def resolve(label, table_kw, item_kw, cycle, avoid=()):
    t = find_table(table_kw, cycle)
    if not t:
        print(f"  [{label}] 통계표 못 찾음 (키워드 {table_kw})")
        return None
    stat = t["STAT_CODE"]
    code, nm = find_item(stat, cycle, item_kw, avoid)
    if not code:
        print(f"  [{label}] 항목 못 찾음. 표={stat} {t['STAT_NAME']}")
        for it in items(stat)[:25]:
            print(f"       후보 {it.get('ITEM_CODE')} | {it.get('ITEM_NAME')}")
        return None
    print(f"  [{label}] 표={stat} 항목={code} ({nm})")
    try:
        d = fetch(stat, cycle, code)
    except Exception as e:
        print(f"  [{label}] 조회 실패: {e}")
        return None
    print(f"       {len(d)}건 · {min(d) if d else '-'} ~ {max(d) if d else '-'}")
    return d or None

print("통계 탐색 시작")
gdp    = resolve("명목GDP",   ["국내총생산"], ["국내총생산"], "Q", avoid=["실질","계절","디플"])
mktcap = resolve("시가총액",   ["주식"],      ["시가총액"],   "M", avoid=["코스닥"])
kospi  = resolve("KOSPI",     ["주식"],      ["코스피"],     "M", avoid=["코스닥","선물"])
per    = resolve("PER",       ["주식"],      ["PER"],       "M", avoid=["코스닥"])
cpi    = resolve("소비자물가", ["소비자물가"], ["총지수"],     "M")

# ── 버핏지수 ─────────────────────────────────────
def rolling4(ym):
    """해당 월이 속한 분기까지 직전 4개 분기 명목GDP 합"""
    y, m = int(ym[:4]), int(ym[4:6])
    q = (m - 1) // 3 + 1
    keys, yy, qq = [], y, q
    for _ in range(4):
        keys.append(f"{yy}Q{qq}")
        qq -= 1
        if qq == 0:
            qq, yy = 4, yy - 1
    got = [gdp[k] for k in keys if k in gdp]
    return sum(got) * 4 / len(got) if got else None

buffett = []
if gdp and mktcap:
    for ym in sorted(mktcap):
        g = rolling4(ym)
        if g and g > 0:
            buffett.append({"d": f"{ym[:4]}-{ym[4:6]}",
                            "v": round(mktcap[ym] / g * 100, 2)})

# ── CAPE ────────────────────────────────────────
cape = []
if kospi and per and cpi:
    base = cpi[max(cpi)]
    real = {}
    for ym in sorted(set(kospi) & set(per) & set(cpi)):
        if per[ym] > 0:
            real[ym] = (kospi[ym] / per[ym]) * (base / cpi[ym])
    ms = sorted(real)
    for i, ym in enumerate(ms):
        if i < 119:
            continue
        avg = sum(real[m] for m in ms[i-119:i+1]) / 120
        if avg > 0:
            cape.append({"d": f"{ym[:4]}-{ym[4:6]}",
                         "v": round(kospi[ym] / avg, 2)})

out = {
    "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
    "buffett": buffett,
    "cape": cape,
}
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

print(f"\n완료 · 버핏지수 {len(buffett)}건 · CAPE {len(cape)}건")
if not buffett and not cape:
    sys.exit("둘 다 비었습니다. 위 후보 목록을 보고 CONFIG를 조정하세요.")

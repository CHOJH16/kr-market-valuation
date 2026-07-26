# -*- coding: utf-8 -*-
"""한국 버핏지수 / CAPE 자동 수집기 (한국은행 ECOS)"""
import os, sys, json, re, bisect
from datetime import datetime, timezone, timedelta
import requests

KEY  = os.environ.get("ECOS_KEY", "").strip()
BASE = "https://ecos.bok.or.kr/api"
KST  = timezone(timedelta(hours=9))
INCLUDE_KOSDAQ = False

if not KEY:
    sys.exit("ECOS_KEY 시크릿이 비어 있습니다.")

S = requests.Session()

def api(path):
    r = S.get(f"{BASE}/{path}", timeout=120)
    r.raise_for_status()
    j = r.json()
    if "RESULT" in j:
        raise RuntimeError(j["RESULT"].get("MESSAGE", "오류"))
    return j

# ── 단위 자동 환산 ────────────────────────────────
UNITS = [("조원",1e12), ("십억원",1e9), ("억원",1e8),
         ("백만원",1e6), ("만원",1e4), ("천원",1e3), ("원",1.0)]

def unit_factor(name):
    if not name:
        return None
    n = str(name).replace(" ", "")
    for k, f in UNITS:
        if k in n:
            return f
    return None

# ── 주기별 날짜 형식 ──────────────────────────────
def periods(cycle):
    if cycle == "Q":
        return [("1990Q1", "2099Q4"), ("19901", "20994")]
    if cycle == "A":
        return [("1990", "2099")]
    return [("199001", "209912")]

def norm_time(t, cycle):
    t = str(t).strip().upper()
    if cycle == "M":
        return t if re.fullmatch(r"\d{6}", t) else None
    if cycle == "Q":
        m = re.fullmatch(r"(\d{4})Q([1-4])", t) or re.fullmatch(r"(\d{4})([1-4])", t)
        return f"{m.group(1)}Q{m.group(2)}" if m else None
    return t

def fetch(stat, cycle, item):
    err = None
    for st, en in periods(cycle):
        try:
            j = api(f"StatisticSearch/{KEY}/json/kr/1/100000/"
                    f"{stat}/{cycle}/{st}/{en}/{item}")
        except Exception as e:
            err = e
            continue
        rows = j.get("StatisticSearch", {}).get("row", [])
        data, unit = {}, None
        for r in rows:
            v = r.get("DATA_VALUE")
            if v in (None, "", "-"):
                continue
            t = norm_time(r.get("TIME", ""), cycle)
            if not t:
                continue
            try:
                data[t] = float(v)
            except ValueError:
                continue
            unit = unit or r.get("UNIT_NAME")
        if data:
            return data, unit
        err = err or RuntimeError("빈 응답")
    raise err or RuntimeError("조회 실패")

def item_list(stat):
    try:
        rows = api(f"StatisticItemList/{KEY}/json/kr/1/5000/{stat}")\
               ["StatisticItemList"]["row"]
    except Exception:
        return []
    seen, out = set(), []
    for r in rows:
        c = r.get("ITEM_CODE")
        if c and c not in seen:
            seen.add(c)
            out.append(r)
    return out

def table_list():
    try:
        return api(f"StatisticTableList/{KEY}/json/kr/1/5000")\
               ["StatisticTableList"]["row"]
    except Exception:
        return []

# ── 로그에서 확인된 확정 코드 ──────────────────────
KNOWN = {
    "mktcap_kospi":  ("901Y014", "M", "1040000"),
    "mktcap_kosdaq": ("901Y014", "M", "2040000"),
    "kospi":         ("901Y014", "M", "1070000"),
    "per":           ("901Y014", "M", "1110000"),
    "cpi":           ("901Y009", "M", "0"),
}

def grab(label, key, required=True):
    stat, cyc, item = KNOWN[key]
    try:
        d, u = fetch(stat, cyc, item)
    except Exception as e:
        print(f"  [{label}] 실패: {e}")
        if required:
            return None, None
        return None, None
    print(f"  [{label}] {stat}/{item} · {len(d)}건 · "
          f"{min(d)}~{max(d)} · 단위 {u}")
    return d, u

print("── 월별 지표 수집 ──")
cap_k,  cap_ku  = grab("KOSPI 시가총액",  "mktcap_kospi")
cap_q,  cap_qu  = grab("KOSDAQ 시가총액", "mktcap_kosdaq", required=False) \
                  if INCLUDE_KOSDAQ else (None, None)
kospi,  _       = grab("KOSPI 종가",      "kospi")
per,    _       = grab("KOSPI PER",       "per")
cpi,    _       = grab("소비자물가",       "cpi")

# 시가총액을 '원' 단위로 통일
mktcap = {}
if cap_k:
    fk = unit_factor(cap_ku) or 1e8
    for t, v in cap_k.items():
        mktcap[t] = v * fk
    if cap_q:
        fq = unit_factor(cap_qu) or fk
        for t, v in cap_q.items():
            if t in mktcap:
                mktcap[t] += v * fq
        print(f"  → KOSPI + KOSDAQ 합산 사용")
    else:
        print(f"  → KOSPI 단독 사용")

# ── 명목 GDP 탐색 ────────────────────────────────
print("\n── 명목 GDP 탐색 ──")
def find_gdp():
    tabs = [t for t in table_list()
            if t.get("CYCLE") == "Q"
            and ("국내총생산" in t.get("STAT_NAME", "")
                 or "국민소득" in t.get("STAT_NAME", ""))]

    def score(t):
        n = t.get("STAT_NAME", "")
        s = 0
        if "명목" in n:   s -= 10
        if "원계열" in n: s -= 5
        if "실질" in n:   s += 10
        if "계절조정" in n: s += 3
        if any(x in n for x in ("디플", "성장률", "증감")): s += 99
        return s
    tabs.sort(key=score)

    best = None
    for t in tabs[:15]:
        stat, nm = t["STAT_CODE"], t.get("STAT_NAME", "")
        for it in item_list(stat):
            inm = it.get("ITEM_NAME", "")
            if "국내총생산" not in inm:
                continue
            if any(x in inm for x in ("실질", "디플", "증감", "성장", "기여")):
                continue
            try:
                d, u = fetch(stat, "Q", it["ITEM_CODE"])
            except Exception:
                continue
            f = unit_factor(u) or 1e9
            vals = [v * f for _, v in sorted(d.items())[-8:]]
            if not vals:
                continue
            med = sorted(vals)[len(vals) // 2]
            if not (1e14 <= med <= 2e15):      # 분기 100조~2000조 범위
                continue
            print(f"  후보 {stat}/{it['ITEM_CODE']} | {nm[:28]} | "
                  f"{inm[:22]} | 최근 {med/1e12:,.0f}조 | {len(d)}건")
            if best is None or med > best[0]:
                best = (med, {k: v * f for k, v in d.items()}, stat, inm)
            break
    return best

g = find_gdp()
gdp = g[1] if g else None
if g:
    print(f"  → 채택: {g[2]} ({g[3]}) · 분기 {g[0]/1e12:,.0f}조원")
else:
    print("  → GDP를 찾지 못했습니다.")

# ── 버핏지수 ─────────────────────────────────────
buffett = []
if gdp and mktcap:
    qs = sorted(gdp)
    sum4 = {}
    for i, k in enumerate(qs):
        if i >= 3:
            sum4[k] = sum(gdp[qs[j]] for j in range(i - 3, i + 1))
    ready = sorted(sum4)

    for ym in sorted(mktcap):
        y, m = int(ym[:4]), int(ym[4:6])
        qk = f"{y}Q{(m - 1) // 3 + 1}"
        if qk in sum4:
            g4 = sum4[qk]
        else:
            i = bisect.bisect_right(ready, qk) - 1
            if i < 0:
                continue
            g4 = sum4[ready[i]]
        if g4 > 0:
            buffett.append({"d": f"{ym[:4]}-{ym[4:6]}",
                            "v": round(mktcap[ym] / g4 * 100, 2)})

# ── CAPE ────────────────────────────────────────
cape = []
if kospi and per and cpi:
    base = cpi[max(cpi)]
    real = {}
    for ym in sorted(set(kospi) & set(per) & set(cpi)):
        if per[ym] > 0 and cpi[ym] > 0:
            real[ym] = (kospi[ym] / per[ym]) * (base / cpi[ym])
    ms = sorted(real)
    for i, ym in enumerate(ms):
        if i < 119:
            continue
        avg = sum(real[m] for m in ms[i - 119:i + 1]) / 120
        if avg > 0:
            cape.append({"d": f"{ym[:4]}-{ym[4:6]}",
                         "v": round(kospi[ym] / avg, 2)})

# ── 저장 ─────────────────────────────────────────
print(f"\n완료 · 버핏지수 {len(buffett)}건 · CAPE {len(cape)}건")
if buffett:
    print(f"  버핏지수 최신 {buffett[-1]['d']} = {buffett[-1]['v']}%")
if cape:
    print(f"  CAPE 최신 {cape[-1]['d']} = {cape[-1]['v']}")

if not buffett and not cape:
    sys.exit("데이터가 비었습니다. data.json은 그대로 둡니다.")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump({"updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
               "buffett": buffett, "cape": cape},
              f, ensure_ascii=False, separators=(",", ":"))
print("data.json 저장 완료")

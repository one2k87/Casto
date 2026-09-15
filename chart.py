"""주간 유행템 차트 — 순위·상태 태그·지난 회차 대비 변동.

사용자가 말한 콕픽의 정체는 이것이다(2026-09-13):

    "일주일동안 자주 언급되는 상품들을 한곳에 모아서 유행템으로 소개하고,
     유행이 언제까지 가는지 체크할 수 있도록 유행 추이 변화표를 마지막에 넣어서"

그리고 실측이 그 판단을 뒷받침한다(2026-09-13, 유튜브 8종 검색):
「유행 끝난템」172만 · 「지금 사기 아깝? vs 괜찮?」106만 · 「완전히 끝난 아우터」96만.
반면 검색량·차트 **자체**를 본문으로 만든 영상은 6.6천 · 828 · 76으로 전부 죽었다.

   → 사람들은 **목록이 아니라 판정을 본다.** 그래서 이 모듈이 내놓는 1차 산출물은
     순위가 아니라 **상태 태그**(🔥 예감 / ✅ 유행중 / 🍂 끝물 / 🔁 재점화)다.
   → 차트(▲▼)는 마지막 스코어보드로만 쓴다. 본문으로 끌어올리면 죽는다.

⚠️ 데이터가 없으면 태그를 붙이지 않는다. 그럴듯한 판정은 상품을 AI로 재현하는 것과
   같은 종류의 거짓말이다 — 한 번 틀리면 "심사 채널"이라는 정체성 자체가 무너진다.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os

import catalog
import evidence as E

DAILY_DIR = "data/trends_daily"
CHART_DIR = "data/chart"
TOP_N = 5
# 차트가 성립하는 최소 칸 수. 2칸짜리 순위표는 순위가 아니라 비교다.
# 이 아래로 떨어지면 그 주는 차트를 내지 않는다 — 빈칸을 그림으로 메우지 않는다.
MIN_N = 3

# 상태 태그 — 라벨은 화면에, note는 대본이 쓰는 한 줄.
# 젊은 세대/기성세대 양쪽 문장을 같이 들고 다닌다(보고서 §3-5): 한 편 안에
# "먼저 사면 앞서감"과 "몰라도 아직 안 늦었다"가 최소 하나씩 나와야 둘 다 남는다.
TAGS = {
    "hot":    {"emoji": "🔥", "label": "예감",   "young": "아직 다들 모릅니다",
               "old": "지금 알면 빠른 편이에요"},
    "now":    {"emoji": "✅", "label": "유행중", "young": "지금이 정점입니다",
               "old": "아직 안 늦었어요"},
    "fading": {"emoji": "🍂", "label": "끝물",   "young": "이제 새로 살 필요는 없어요",
               "old": "이건 몰라도 됩니다"},
    "again":  {"emoji": "🔁", "label": "재점화", "young": "돌아왔습니다",
               "old": "예전에 보셨던 그거예요"},
}

# 순위 산식의 가중치. 신뢰도 순이다(전략 5-4-9): 사람이 **찾는** 신호가 가장 무겁고,
# 크리에이터가 **만드는** 신호는 서로를 보고 따라 만드는 자기참조 거품이라 가장 가볍다.
WEIGHTS = {"demand": 3.0, "reach": 2.0, "channels": 2.0, "mentions": 1.0}


# ---------------------------------------------------------------- 신호 추출
def signals(p: dict) -> dict:
    """스냅샷 한 줄에서 순위에 쓰는 원신호를 뽑는다. 없는 건 None으로 남긴다."""
    vids = p.get("videos") or []
    sp = E.spike(p.get("demand"))
    return {
        # 수요: 언제부터 몇 배 — 인과를 가장 크게 좁히는 신호
        "demand": (sp or {}).get("ratio") if (sp or {}).get("trend") == "up" else (
            (sp or {}).get("ratio") if sp else None),
        # 노출(재인): 관련 영상 조회수 **합계**. 중앙값이 아니다 — 시청자가 그 물건을
        # 봤을 확률은 효율이 아니라 총 노출량에 비례한다(전략 5-4-10).
        "reach": sum(int(v.get("views") or 0) for v in vids) or None,
        # 한 채널이 10개 만든 것보다 10개 채널이 하나씩 만든 게 피드 도달이 훨씬 넓다
        "channels": len({v.get("channel_id") for v in vids if v.get("channel_id")}) or None,
        "mentions": p.get("mentions") or None,
        "spike": sp,
        "videos": len(vids),
    }


def _ranked(values: list[float | None]) -> list[float | None]:
    """값 목록 → 0~1 정규화 순위. 스케일이 제각각인 신호를 섞기 위한 것.

    배수(1.5)와 조회수(40만)를 그대로 더하면 조회수가 전부를 먹는다. 순위로 바꾸면
    단위가 사라지고, 한 신호가 통째로 결측이어도 나머지가 그대로 작동한다.
    """
    have = sorted({v for v in values if v is not None})
    if not have:
        return [None] * len(values)
    if len(have) == 1:
        return [None if v is None else 1.0 for v in values]
    pos = {v: i / (len(have) - 1) for i, v in enumerate(have)}
    return [None if v is None else pos[v] for v in values]


def score_all(rows: list[dict]) -> list[float]:
    """유행 지수 — 가중 평균. 있는 신호만으로 계산하고, 없는 축은 분모에서도 뺀다."""
    sigs = [signals(p) for p in rows]
    cols = {k: _ranked([s[k] for s in sigs]) for k in WEIGHTS}
    out = []
    for i in range(len(rows)):
        num = den = 0.0
        for k, w in WEIGHTS.items():
            v = cols[k][i]
            if v is not None:
                num += w * v
                den += w
        out.append(round(100 * num / den, 1) if den else 0.0)
    return out


# ---------------------------------------------------------------- 상태 태그
def status(p: dict, was_fading: bool = False) -> str | None:
    """🔥 예감 / ✅ 유행중 / 🍂 끝물 / 🔁 재점화. 판단 근거가 없으면 None.

    `was_fading`은 지난 회차에서 끝물이었는지 — 재점화는 과거를 알아야만 나온다.
    """
    sg = signals(p)
    sp = sg["spike"]
    if not sp:
        return None                       # 수요 시계열이 없으면 단계를 말하지 않는다

    trend, days = sp.get("trend"), sp.get("days_ago")

    if trend == "down":
        return "fading"
    if trend == "up":
        if was_fading:
            return "again"                # 식었다가 다시 오른다 — 가장 이야기가 되는 자리
        # 아직 만든 사람이 적으면 '예감'. 많으면 이미 피드에 깔린 것이라 '유행중'.
        if days is not None and days <= 7 and sg["videos"] < 5:
            return "hot"
        return "now"
    # flat: 영상이 충분히 많으면 이미 퍼진 상태로 본다. 아니면 판정을 보류한다.
    return "now" if sg["videos"] >= 5 else None


# ---------------------------------------------------------------- 화면에 나갈 숫자 하나
def headline(p: dict) -> str | None:
    """"얼마나 유행인지"를 **숫자 하나**로. 추상어("요즘 난리난")는 쓰지 않는다.

    실측(2026-09-13): 「듀프」「가성비 대체템」처럼 추상어를 쓴 영상은 825·678회로 죽고,
    "백화점 20만원, 다이소 5천원"처럼 숫자를 놓은 영상은 200만을 넘었다.
    """
    sg = signals(p)
    sp = sg["spike"]
    if sp and sp.get("trend") == "up" and sp.get("ratio", 0) >= 1.3:
        when = E._fmt_when(sp.get("days_ago"))
        return f"{when}부터 검색 {sp['ratio']:g}배" if when else f"검색 {sp['ratio']:g}배"
    if sg["reach"] and sg["channels"] and sg["channels"] >= 2:
        return f"{sg['channels']}개 채널 · 합계 {sg['reach']:,}회"
    if sg["mentions"]:
        return f"최근 언급 {sg['mentions']:,}건"
    if sg["videos"]:
        return f"관련 영상 {sg['videos']}개"
    return None


# ---------------------------------------------------------------- 회차 조립
def _snapshots() -> list[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(DAILY_DIR, "*.json"))):
        try:
            out.append(json.load(open(f, encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def week_id(d: dt.date | None = None) -> str:
    d = d or dt.date.today()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def previous(week: str) -> dict | None:
    """직전 회차. 파일명이 곧 시간순이라 정렬해서 현재 회차 앞의 마지막 것을 고른다."""
    files = sorted(glob.glob(os.path.join(CHART_DIR, "*.json")))
    prev = [f for f in files if os.path.basename(f)[:-5] < week]
    if not prev:
        return None
    try:
        return json.load(open(prev[-1], encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _delta(key: str, rank: int, prev: dict | None) -> dict:
    """지난 회차 대비 변동. 첫 회차는 전부 NEW다 — 없는 변동을 지어내지 않는다."""
    if not prev:
        return {"move": "new", "text": "NEW", "prev_rank": None}
    old = {e["key"]: e["rank"] for e in prev.get("entries", [])}
    if key not in old:
        return {"move": "new", "text": "NEW", "prev_rank": None}
    diff = old[key] - rank                      # 순위는 작을수록 위
    if diff > 0:
        return {"move": "up", "text": f"▲{diff}", "prev_rank": old[key]}
    if diff < 0:
        return {"move": "down", "text": f"▼{-diff}", "prev_rank": old[key]}
    return {"move": "same", "text": "—", "prev_rank": old[key]}


def shootable(name: str, cat: dict | None = None) -> dict | None:
    """이 상품을 **실사진으로** 화면에 띄울 수 있는가. 없으면 None.

    ⚠️ 절대 규칙: 제품을 가상으로 재현하지 않는다. 그 즉시 시청자는 돌아선다.
       그래서 사진이 없는 상품은 차트에 올릴 수 없다 — 순위가 높아도 뺀다.
       5개가 안 모이면 3개로 줄여 나간다(보고서 §6). 빈칸을 그림으로 메우지 않는다.
    """
    cat = cat if cat is not None else catalog.load()
    prods = cat.get("products", {})
    entry = prods.get(catalog.slugify(name))
    if entry is None:                       # 발굴 이름과 카탈로그 키가 다를 수 있다
        flat = name.replace(" ", "")
        for k, v in prods.items():
            full = f"{v.get('brand', '')}{v.get('model', '')}".replace(" ", "")
            if k.replace("-", "") == flat or (full and full == flat):
                entry = v
                break
    return entry if (entry or {}).get("image") else None


def build(week: str | None = None, top: int = TOP_N, today: dt.date | None = None,
          require_photo: bool = True) -> dict:
    """이번 회차 차트를 만든다. 스냅샷이 없으면 빈 차트를 돌려준다(지어내지 않는다)."""
    snaps = _snapshots()
    if not snaps:
        return {"week": week or week_id(today), "entries": [], "out": [], "note": "스냅샷 없음"}

    latest = snaps[-1]
    rows = latest.get("products", [])
    week = week or week_id(today)
    prev = previous(week)
    fading_before = {e["key"] for e in (prev or {}).get("entries", [])
                     if e.get("status") == "fading"}

    scores = score_all(rows)
    order = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)

    cat = catalog.load()
    entries, seen, no_photo = [], set(), []
    for i in order:
        p = rows[i]
        shot = shootable(p["name"], cat)
        # ⚠️ 중복은 **카탈로그 기준**으로 걸러야 한다. 발굴 경로가 둘이라 같은 물건이
        #    `laser_guide_scissors`와 `레이저_가이드_가위` 두 키로 들어오고, 키로만
        #    거르면 같은 상품이 4위·5위에 나란히 선다(2026-09-15 실측).
        ident = (shot or {}).get("display") or p["key"]
        if ident in seen:
            continue
        seen.add(ident)
        if require_photo and not shot:
            no_photo.append(p["name"])
            continue
        st = status(p, was_fading=p["key"] in fading_before)
        entries.append({
            "rank": len(entries) + 1,
            "key": p["key"],
            "name": p["name"],
            # 화면에 나가는 이름은 **카탈로그의 정식 상품명**이다. 발굴 키워드
            # ("코에서 계란 흰자 나오는 주방용품")를 그대로 띄우면 검색이 안 된다.
            "display": (shot or {}).get("display") or p["name"],
            "image": (shot or {}).get("image"),
            "price": (shot or {}).get("price"),
            "coupang_url": (shot or {}).get("coupang_url") or "",
            "score": scores[i],
            "status": st,
            "tag": TAGS.get(st or "", {}),
            "headline": headline(p),
            "signals": {k: v for k, v in signals(p).items() if k != "spike"},
            "spike": signals(p)["spike"],
            "delta": _delta(p["key"], len(entries) + 1, prev),
        })
        if len(entries) >= top:
            break

    # 지난 회차에 있었는데 이번에 빠진 것 — "이건 이제 안 사도 돼요"의 자리다
    now_keys = {e["key"] for e in entries}
    dropped = [{"key": e["key"], "name": e["name"], "prev_rank": e["rank"]}
               for e in (prev or {}).get("entries", []) if e["key"] not in now_keys]

    return {"week": week, "date": latest.get("date"), "source_days": len(snaps),
            "prev_week": (prev or {}).get("week"), "entries": entries, "out": dropped,
            # 순위는 높은데 사진이 없어 못 올린 것들 — 다음 캡처 우선순위가 된다
            "needs_photo": no_photo[:8]}


def save(chart: dict) -> str:
    os.makedirs(CHART_DIR, exist_ok=True)
    path = os.path.join(CHART_DIR, f"{chart['week']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False, indent=1)
    return path


def report(chart: dict) -> str:
    lines = [f"[chart] {chart['week']} · 스냅샷 {chart.get('source_days')}일"
             + (f" · 직전 {chart['prev_week']}" if chart.get("prev_week") else " · 첫 회차")]
    for e in chart["entries"]:
        tag = e["tag"].get("emoji", "") + e["tag"].get("label", "판정보류")
        won = f"{e['price']:,}원" if e.get("price") else "가격❌"
        lines.append(f"[chart]  {e['rank']}위 {e['delta']['text']:>4}  {e['display'][:20]:22}"
                     f" {tag:8} {won:10} {e['headline'] or '-'}")
    for o in chart["out"]:
        lines.append(f"[chart]   OUT  {o['name'][:20]} (지난주 {o['prev_rank']}위)")
    if chart.get("needs_photo"):
        lines.append(f"[chart] 📷 순위는 높은데 실사진이 없어 뺀 것: {', '.join(chart['needs_photo'][:5])}")
    missing = [e["display"] for e in chart["entries"] if not e.get("price")]
    if missing:
        lines.append(f"[chart] 💰 가격이 빈 항목: {', '.join(missing)} — 앱에서 캡처할 때 넣어주세요")
    if len(chart["entries"]) < TOP_N:
        lines.append(f"[chart] ⚠ {len(chart['entries'])}개만 올라간다 — 빈칸은 그림으로 메우지 않는다")
    return "\n".join(lines)


if __name__ == "__main__":
    c = build()
    print(report(c))
    if c["entries"]:
        print("[chart] 저장:", save(c))
    else:
        print("[chart] ⚠ 항목이 없다 — 스냅샷을 먼저 쌓아야 한다")

"""인과 근거 — "왜 유행인가"를 **데이터로 좁힌다**.

2판을 처음 붙였을 때 인과를 쓰는 LLM에게 **상품 이름 말고는 아무것도 주지 않았다.**
그러니 "자취 가구 급증" 같은 아무 데나 갖다 붙는 문장이 나왔다. 이유가 뜬구름인 건
모델 탓이 아니라 입력 탓이다.

이 모듈은 이미 모아 둔 것을 인과에 쓸 수 있는 형태로 바꾼다.

| 신호 | 어디서 | 인과에 주는 것 |
|---|---|---|
| 수요 시계열(데이터랩) | trends_daily[].demand | **언제부터** 몇 배 (가장 좁히는 신호) |
| 작년 같은 기간 | demand_last_year | 계절성인가 진짜 신규인가 |
| 영상 수·조회수·최신일 | trends_daily[].videos | 확산 속도 |
| 언급량 | mentions | 규모 |
| 발굴 근거 문장 | evidence | 어떤 맥락에서 튀어나왔나 |
| 같이 뜬 다른 상품 | 같은 스냅샷 | 공통 원인 후보 |

`brief()`가 만드는 것은 **사실만 적힌 한 덩어리**다. 해석(왜)은 LLM이 하되,
여기 없는 숫자는 쓰지 못하게 프롬프트가 막는다.
"""
import datetime as dt
import glob
import io
import json
import os
import re

DAILY_DIR = "data/trends_daily"
WEEK = 7


def _load(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                        # noqa: BLE001
        return default


def snapshots(dir_=DAILY_DIR, limit=14):
    """최신 스냅샷부터 최대 limit개."""
    return [_load(p, {}) for p in sorted(glob.glob(f"{dir_}/*.json"))[-limit:][::-1]]


def _norm(s):
    return re.sub(r"[^0-9a-z가-힣]+", "", (s or "").lower())


def find(name, snaps=None):
    """스냅샷에서 이 상품의 최신 기록을 찾는다(느슨한 이름 매칭)."""
    key = _norm(name)
    if not key:
        return None, None
    for snap in (snaps if snaps is not None else snapshots()):
        for p in snap.get("products", []):
            n = _norm(p.get("name"))
            if n and (n == key or n in key or key in n):
                return p, snap.get("date")
    return None, None


def spike(series, window=WEEK):
    """수요 시계열이 **오르는 중인지 식는 중인지**, 오른다면 언제부터 몇 배인지.

    "8월 말부터 6배"처럼 영상에 그대로 쓸 수 있는 문장이 여기서 나온다 —
    인과를 좁히는 건 결국 시점이다.

    ⚠️ 내려가는 것도 반드시 내려간다고 말해야 한다. 처음엔 0.3배(하락)를 두고도
    "상승 시작"이라고 적어서, 식어가는 물건을 '지금 뜬다'고 소개할 뻔했다.
    """
    s = [float(x) for x in (series or []) if x is not None]
    if len(s) < window * 2:
        return None
    recent = s[-window:]
    before = s[:-window]
    base = sum(before) / len(before)
    now = sum(recent) / len(recent)
    if base <= 0:
        return None
    ratio = now / base
    trend = "up" if ratio >= 1.3 else ("down" if ratio <= 0.8 else "flat")
    out = {"ratio": round(ratio, 1), "trend": trend,
           "peak": round(max(s), 1), "base": round(base, 1),
           "peak_days_ago": len(s) - 1 - s.index(max(s))}
    if trend == "up":
        # 상승이 시작된 지점 — 뒤에서부터 기준선 아래로 내려가는 첫 지점
        start = -1                     # 기준선 아래로 내려가는 마지막 지점
        for i in range(len(s) - 1, -1, -1):
            if s[i] < base * 1.2:
                start = i
                break
        # 오른 건 start **다음** 지점부터다. len(s)-start로 세면 하루가 길어진다.
        out["days_ago"] = len(s) - 1 - start
    return out


def _fmt_when(days_ago):
    if days_ago is None:
        return ""
    d = dt.date.today() - dt.timedelta(days=days_ago)
    wk = (d.day - 1) // 7 + 1
    return f"{d.month}월 {['첫','둘','셋','넷','다섯'][min(wk,5)-1]}째 주"


def brief(name, snaps=None, live=False) -> dict:
    """한 상품의 근거 묶음. `lines`는 프롬프트에 그대로 넣는 사실 목록이다.

    `live=True`면 네이버 글·유튜브 댓글을 **그 자리에서** 모아 붙인다(reasons).
    숫자는 "얼마나·언제"를 말하지만 "왜"는 사람이 쓴 글에만 있다.
    """
    snaps = snaps if snaps is not None else snapshots()
    p, date = find(name, snaps)
    out = {"name": name, "date": date, "lines": [], "has_data": bool(p)}
    if not p:
        out["lines"].append("(수집 데이터 없음 — 숫자를 지어내지 말 것)")
        return out

    vids = p.get("videos") or []
    if vids:
        views = sum(v.get("views", 0) for v in vids)
        newest = min((v.get("age_days", 99) for v in vids), default=None)
        out["videos"] = len(vids)
        out["views"] = views
        out["lines"].append(
            f"유튜브: 관련 영상 {len(vids)}개 · 합계 조회 {views:,}회"
            + (f" · 가장 최근 것은 {newest:.0f}일 전" if newest is not None else ""))
        if len(vids) >= 5 and (newest or 99) <= 3:
            out["lines"].append("→ 최근 며칠 사이에 여러 채널이 동시에 다뤘다(확산 중)")

    sp = spike(p.get("demand"))
    if sp and sp["trend"] == "up":
        out["spike"] = sp
        out["lines"].append(
            f"네이버 쇼핑 검색 수요: 최근 {WEEK}일 평균이 그 전보다 **{sp['ratio']}배**"
            f" · 상승 시작은 약 {sp['days_ago']}일 전({_fmt_when(sp['days_ago'])})")
    elif sp and sp["trend"] == "down":
        out["spike"] = sp
        out["lines"].append(
            f"네이버 쇼핑 검색 수요: 정점을 {sp['peak_days_ago']}일 전에 지나 "
            f"지금은 그 전 평균의 {sp['ratio']}배로 **식는 중**"
            " → ‘지금 뜬다’고 말하면 안 된다(‘다음콕’ 후보)")
    elif sp:
        out["lines"].append("네이버 쇼핑 검색 수요: 뚜렷한 변화 없음(수요 이야기는 쓰지 말 것)")
    elif p.get("demand"):
        out["lines"].append("네이버 수요 데이터가 짧아 추세를 못 잰다(수요 이야기는 쓰지 말 것)")

    ly = spike(p.get("demand_last_year"))
    if sp and sp["trend"] == "up" and ly:
        out["lines"].append(
            f"작년 같은 기간에도 {ly['ratio']}배 올랐다 → **계절 요인일 가능성**"
            if ly["trend"] == "up" else
            "작년 같은 기간엔 이런 상승이 없었다 → **올해 새로 생긴 이유**가 있다")

    ov = p.get("overseas") or {}
    if ov.get("verdict") == "overseas_first":
        out["overseas"] = ov
        m = round(ov["lead_days"] / 30, 1)
        out["lines"].append(
            f"해외 선행: 영어권에서 {ov['en']['earliest']}부터 보이기 시작 · 한국은 {ov['ko']['earliest']}"
            f" → **약 {m}개월 늦게 들어왔다**(영어권 영상 {ov['en']['count']}개)")
        if ov["en"].get("titles"):
            out["lines"].append("   영어권 영상 제목: " + " / ".join(ov["en"]["titles"][:2]))
    elif ov.get("verdict") == "korea_only":
        out["lines"].append("해외 선행: 영어권에는 관련 영상이 없다 → **국내에서 생긴 유행**")
    elif ov.get("verdict") == "korea_first":
        out["lines"].append("해외 선행: 오히려 한국이 먼저다 → ‘해외에서 난리난’이라고 쓰면 안 된다")

    if p.get("mentions"):
        out["mentions"] = p["mentions"]
        out["lines"].append(f"네이버 블로그·카페 언급 {p['mentions']:,}건")

    if p.get("evidence"):
        out["lines"].append(f"발굴 맥락: {p['evidence']}")
    if p.get("keyword"):
        out["lines"].append(f"검색된 표현: 「{p['keyword']}」")

    if live:
        try:
            import reasons
            g = reasons.gather(name, keyword=p.get("keyword") or "",
                               en_keyword=p.get("en_keyword") or "",
                               video_ids=[v.get("id") for v in (p.get("videos") or [])
                                          if v.get("id")])
            out["reasons"] = g
            out["lines"].append("── 사람들이 실제로 쓴 말 ──")
            out["lines"].extend(reasons.lines(g))
        except Exception as e:                               # noqa: BLE001
            print(f"[evidence] 사람 글 수집 실패({name}):", e)

    return out


def co_risers(names, snaps=None, top=6):
    """같은 스냅샷에서 함께 뜬 다른 품목 — **공통 원인**의 실마리가 된다.

    피스타치오가 왜 뜨는지는 피스타치오만 봐서는 안 나온다. 같이 뜬 게 무엇인지
    봐야 "두쫀쿠"가 보인다.
    """
    snaps = snaps if snaps is not None else snapshots()
    if not snaps:
        return []
    mine = {_norm(n) for n in names}
    rows = []
    for p in (snaps[0].get("products") or []):
        if _norm(p.get("name")) in mine:
            continue
        v = sum(x.get("views", 0) for x in (p.get("videos") or []))
        rows.append((v, p.get("name"), len(p.get("videos") or [])))
    rows.sort(reverse=True)
    return [{"name": n, "views": v, "videos": c} for v, n, c in rows[:top] if n]


VAGUE = ("인기가", "인기라", "유행이라", "유행해서", "많이 팔려", "많이 사서",
         "편리해서", "편해서", "좋아서", "가성비", "실용적", "화제가", "관심이",
         "수요가 늘어", "찾는 사람이 늘")


def too_vague(cause: str) -> str:
    """동어반복·뜬구름 인과를 잡아낸다. 문제면 이유 문자열, 괜찮으면 빈 문자열.

    "인기가 많아서 유행이다"는 아무것도 설명하지 않는다. 유행의 원인은
    **바깥에서** 와야 한다 — 다른 유행, 방송, 계절, 물가, 제도 같은 것.
    """
    t = (cause or "").strip()
    if len(t) < 4:
        return "너무 짧다"
    for w in VAGUE:
        if w in t:
            return f"동어반복에 가깝다(‘{w}’) — 바깥에서 온 계기가 필요하다"
    # 고유명사·숫자·시점 중 하나는 있어야 구체적이다
    concrete = bool(re.search(r"\d", t)) or bool(re.search(r"(월|주|여름|겨울|봄|가을|방송|뉴스|틱톡|유튜브|인스타)", t))
    if not concrete:
        return "시점·숫자·고유명사가 없다 — 구체적인 계기를 짚어야 한다"
    return ""

"""요일 편성 엔진 — 오늘 무엇을 만들지 결정한다.

설계 근거: `docs/콕픽_채널_전략.md` 5-2-2(쇼츠 3포맷) · 5-3-2(요일 고정) · 5-4-5(브리핑=소재 창고)

축이 넷(가격대·포맷·카테고리·소재)이라 조합이 21가지인데 발행은 주 4편이다.
그래서 **소재를 1차 축으로 두고 나머지를 요일에 종속**시킨다. 고정 케이던스 자체가
구독 이유이므로(5-1E), 요일이 흔들리지 않는 것이 중요하다.

| 요일 | 소재 | 포맷 | 가격대 | 노리는 것 |
|---|---|---|---|---|
| 월 | 트렌드 | 콕 브리핑(차트) | 저가 위주 | 신규 유입·재인 |
| 화 | 심층① | 콕 열리는 상자 | 중가 | 검색 자산·수익 |
| 목 | 심층②/상시 | 판정 또는 콕 관리 | 중가·고가 | 검색·보유자 |
| 토 | 시즌 | 판정 또는 콕 관리 | 중가 | 매년 복리 |

이 모듈은 IO를 최소화하고(파일 읽기만) 결정 로직은 순수 함수로 둔다 — 테스트 가능해야 하기 때문.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

PUBLISH_LOG = "data/publish_log.json"   # 발행 이력(판정 쿼터·중복 방지의 근거)
SNAPSHOT_DIR = "data/trends_daily"      # 일별 스냅샷 — 델타(증감)의 유일한 출처
NEXT_KOK_RATIO = 0.25                   # '다음콕' 최소 비율(5-3 ③) — 매번 열리면 완주 장치가 죽는다
QUOTA_WINDOW = 12                       # 최근 몇 편을 기준으로 판정 비율을 볼지
MAX_PER_WEEK = 4                        # 양산형 콘텐츠 정책 대응 상한(5-2 발행량 상한)

# ── 램프업(2026-09-09 결정) ─────────────────────────────────────────────────
# 사용자 판단: "며칠은 지켜봐야 정확도가 늘지 않을까? 빨리 많이보다 제대로 올리는 게 낫지 않나."
# 맞다. 다만 이유는 '천천히 하자'가 아니라 **데이터 구조상 지금은 판정이 불가능**하다는 것이다.
#   · 트렌드 점수의 핵심 입력은 **델타(어제 대비 증감)**인데 깨끗한 스냅샷이 오늘부터 쌓인다.
#   · 재인(再認) 모델은 "며칠째 피드에 보이는가"가 전제다 — 하루짜리 스파이크는 재인이 아니다.
#   · 브리핑(주간 유행 모음)은 최소 7일이 있어야 상승·하락을 말할 수 있다.
# 반대로 **발행을 0으로 두는 것도 틀렸다**: 채널이 0편이면 알고리즘이 분류조차 못 하고,
# 8주 컷오프 시계가 시작되지 않으며, 무엇이 먹히는지는 발행해야만 알 수 있다.
# → 그래서 "관측은 매일, 발행은 확정된 것만 주 2편"으로 간다.
RAMP_SLOT = {1: "deep1", 5: "season"}   # 화·토 2편
BRIEFING_MIN_DAYS = 7                   # 브리핑에 필요한 최소 스냅샷 일수
RAMP_MAX_PER_WEEK = 2

# 요일 → 슬롯. 월=0 … 일=6
WEEKDAY_SLOT = {0: "trend", 1: "deep1", 3: "deep2", 5: "season"}

SLOT_SPEC = {
    "trend":  {"format": "briefing",  "ranking": "briefing",  "price_band": "저가",
               "why": "월요일 브리핑 — 그 주의 소재 창고이자 신규 유입 창구"},
    "deep1":  {"format": "kok_open",  "ranking": "deep_dive", "price_band": "중가",
               "why": "월요일 브리핑에서 발굴한 1건을 콕 3번으로 심층 심사"},
    "deep2":  {"format": "kok_open",  "ranking": "deep_dive", "price_band": "고가",
               "why": "두 번째 심층 — 고가 편은 수익원이 아니라 신뢰·구독 엔진"},
    "season": {"format": "kok_open",  "ranking": "season",    "price_band": "중가",
               "why": "시즌 편 — 매년 재점화되는 복리 자산"},
}

# 월간 카테고리 순환(5-3-2). 주 4편이면 주간 묶음이 얇아 월 단위로 묶는다.
MONTH_CATEGORY = {
    1: "주방", 2: "청소", 3: "공기·환기", 4: "냉방·여름준비", 5: "제습·방충", 6: "냉방·물놀이",
    7: "여름가전", 8: "정리수납", 9: "주방", 10: "청소", 11: "난방·방한", 12: "정리·연말",
}

# 시즌 소재는 **수요 피크 3~4주 전에 발행**해야 검색이 오를 때 이미 색인돼 있다(5-3-4①).
# 따라서 이 표는 "그 달에 발행할 것"이며, 실제 피크는 다음 달이다.
SEASON_CALENDAR = {
    1: ["전기요", "가습기 필터", "실내 건조대"],
    2: ["공기청정기", "황사 마스크", "봄맞이 청소기"],
    3: ["미세먼지 차단망", "캠핑 준비물", "이사 수납"],
    4: ["선풍기", "자외선 차단", "돗자리"],
    5: ["제습기", "모기 퇴치기", "쿨매트"],
    6: ["에어컨 청소", "아이스박스", "휴대용 선풍기"],
    7: ["냉풍기", "물놀이 용품", "제빙기"],
    8: ["정리수납함", "책상 정리", "가을 이불"],
    9: ["건조기", "환절기 가습", "김장 준비물"],
    10: ["전기장판", "가습기", "손난로"],
    11: ["방한용품", "온수매트", "크리스마스 소품"],
    12: ["새해 다이어리", "정리 수납", "설 선물세트"],
}


# ------------------------------------------------------------------ 이력
def _load(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def record_publish(date: str, slot: str, key: str, verdict: str, path: str = PUBLISH_LOG,
                   **meta) -> None:
    """발행 이력을 남긴다 — 판정 쿼터·중복 편성 + **성과 학습의 유일한 입력**.

    2026-09-09까지 이 함수는 아무도 호출하지 않았다. 즉 무엇을 왜 만들었는지 기록이 없었고,
    그래서 "어떤 영상이 잘 됐나"를 나중에 물어볼 수가 없었다. 학습 루프(learn.py)는
    여기 남는 메타(제목·제품·판정·가격대·포맷·사진유무)를 성과와 조인해서 돌아간다.
    """
    log = _load(path, [])
    row = {"date": date, "slot": slot, "key": key, "verdict": verdict}
    row.update({k: v for k, v in meta.items() if v not in (None, "")})
    log.append(row)
    _save(path, log[-400:])


def next_kok_due(log: list[dict], window: int = QUOTA_WINDOW, ratio: float = NEXT_KOK_RATIO) -> bool:
    """'다음콕'을 써야 할 때인가(5-3 ③).

    매번 열리면 시청자가 3편 만에 "어차피 열리네"를 학습해 **완주 유도 장치 자체가 무력화**된다.
    최근 window편에서 다음콕 비율이 기준 아래면 이번 편은 탈락 쪽으로 기울인다.
    """
    recent = [e for e in log if e.get("verdict")][-window:]
    if len(recent) < 4:              # 표본이 적으면 강제하지 않는다
        return False
    nexts = sum(1 for e in recent if e["verdict"] == "later")
    return (nexts / len(recent)) < ratio


# ------------------------------------------------------------------ 편성
def snapshot_days(dir_: str = SNAPSHOT_DIR) -> int:
    """깨끗한 일별 스냅샷이 며칠치인가 — 램프업 해제와 브리핑 가능 여부의 기준."""
    if not os.path.isdir(dir_):
        return 0
    return len([f for f in os.listdir(dir_) if f.endswith(".json")])


def ramping(days: int | None = None) -> bool:
    """아직 램프업 구간인가. 스냅샷이 7일 미만이면 델타를 신뢰할 수 없다."""
    return (snapshot_days() if days is None else days) < BRIEFING_MIN_DAYS


def slot_for(date: dt.date, ramp: bool | None = None) -> str | None:
    """오늘의 슬롯. 발행일이 아니면 None.

    램프업 중에는 **화·토 2편**만 편성한다. 월요일 브리핑은 7일치 데이터가 모이기 전엔
    '이번 주 유행'을 말할 근거가 없어 만들지 않는다(빈약한 브리핑은 채널 정체성을 흐린다).
    """
    ramp = ramping() if ramp is None else ramp
    return (RAMP_SLOT if ramp else WEEKDAY_SLOT).get(date.weekday())


def _has_photo(name: str, ready: list[str] | None) -> bool:
    """이 이름이 **실사진까지 확보된 상품**인가. catalog.find와 같은 느슨한 매칭을 쓴다."""
    if ready is None:
        return True
    import catalog
    return catalog.render_mode(catalog.find(catalog.load(), name=name)) == "exact"


def _unused(ready: list[str], log: list[dict]) -> str:
    """실사진 상품 중 **최근에 안 쓴 것**을 고른다 — 램프업 폴백이 같은 상품만 반복하지 않게."""
    used = [e.get("product") or e.get("key") for e in log]
    for n in ready:
        if n not in used:
            return n
    return ready[0]


def pick_product(slot: str, board: dict, log: list[dict], month: int,
                 ready: list[str] | None = None) -> dict | None:
    """슬롯에 맞는 제품을 고른다.

    **슬롯마다 다른 랭킹을 쓴다**(5-4-10): 브리핑은 재인 랭킹(이미 봤을 확률),
    심층은 구매가치 랭킹(사도 되는가). 같은 데이터로 다른 질문에 답하는 것이 설계의 핵심이다.
    """
    spec = SLOT_SPEC[slot]
    if spec["ranking"] == "season":
        names = [n for n in SEASON_CALENDAR.get(month, []) if _has_photo(n, ready)] \
                if ready is not None else SEASON_CALENDAR.get(month, [])
        if names:
            return {"name": names[0], "season": True, "keyword": names[0]}
        if ready is None:
            return None
        # 시즌 키워드 중 실사진 있는 게 없다 — 램프업에는 시즌을 포기하고
        # 손에 든 실사진 상품으로 간다. 사진 없는 편을 내보내는 것보다 낫다.
        pick = _unused(ready, log)
        return {"name": pick, "season": True, "keyword": pick, "photo_fallback": True}
    rows = [r for r in board.get(spec["ranking"], []) if not r.get("blocked")]
    if ready is not None:
        # 램프업 구간에는 **실사진이 있는 것만** 후보다. 하나도 없으면 랭킹을 포기하고
        # 손에 든 실사진 상품으로 간다 — 사진 없는 편을 내보내는 것보다 낫다.
        rows = [r for r in rows if _has_photo(r.get("name") or r.get("key", ""), ready)]
    if not rows:
        if ready:
            pick = _unused(ready, log)
            return {"name": pick, "key": pick, "photo_fallback": True}
        return None
    used = {e["key"] for e in log[-QUOTA_WINDOW:]}
    fresh = [r for r in rows if r["key"] not in used] or rows   # 최근 다룬 건 뒤로
    band = spec["price_band"]
    same_band = [r for r in fresh if r.get("price_band") == band]
    return (same_band or fresh)[0]


def revisit_candidate(board: dict) -> dict | None:
    """재심콕 트리거(5-1A) — 가격 급락이나 노출 재상승으로 8주 차단이 풀린 제품.

    요일 편성 밖의 **보너스 편**이다. 미결 서사(내가 찜한 게 언제 열릴까)와 특가 전환이
    일치하는 유일한 포맷이라 우선순위가 높다.
    """
    for r in board.get("all", []):
        if not r.get("blocked") and r.get("delta") == "up" and r.get("quadrant") in ("peak", "blue_ocean"):
            return r
    return None


def plan(date: dt.date, board: dict, log: list[dict] | None = None,
         ready: list[str] | None = None) -> dict:
    """오늘의 편성안. 발행일이 아니면 `publish: False`.

    `ready`는 **실사진까지 확보된 상품 이름 목록**이다(catalog에서 온다). 램프업 구간에는
    이게 비면 발행하지 않는다 — 제품 사진 없는 영상은 재인을 못 만들고, 재인이 구독의 동력이다.
    """
    log = log or []
    ramp = ramping()
    days = snapshot_days()
    slot = slot_for(date, ramp)
    if slot is None:
        pace = "주 2편: 화·토(램프업)" if ramp else "주 4편: 월·화·목·토"
        return {"date": date.isoformat(), "publish": False, "ramp": ramp, "snapshot_days": days,
                "reason": f"{'월화수목금토일'[date.weekday()]}요일은 발행일이 아니다({pace})"}
    if ramp and ready is not None and not ready:
        return {"date": date.isoformat(), "publish": False, "ramp": ramp, "snapshot_days": days,
                "reason": ("램프업 중 발행 게이트 — 실사진이 확보된 상품이 없다. "
                           "캡처를 먼저 등록할 것(앱 📷)")}
    spec = SLOT_SPEC[slot]
    product = pick_product(slot, board, log, date.month, ready if ramp else None)
    out = {
        "date": date.isoformat(), "publish": True, "slot": slot,
        "ramp": ramp, "snapshot_days": days, "ready": ready or [],
        "format": spec["format"], "price_band": spec["price_band"],
        "category": MONTH_CATEGORY.get(date.month), "why": spec["why"],
        "product": product,
        "prefer_next_kok": next_kok_due(log),
    }
    if slot != "trend":
        rev = revisit_candidate(board)
        if rev:
            out["revisit_available"] = rev["name"]
    if product is None:
        out["publish"] = False
        out["reason"] = f"{slot} 슬롯에 쓸 제품이 없다 — 수집(trend_products)을 먼저 확인할 것"
    return out


def describe(p: dict) -> str:
    """사람이 읽는 편성 요약 — 워크플로 로그에 그대로 찍는다."""
    if not p.get("publish"):
        return f"[편성] {p['date']} 발행 없음 — {p.get('reason')}"
    prod = p.get("product") or {}
    lines = [
        f"[편성] {p['date']} · {p['slot']} · {p['format']}"
        + (f"  (램프업 · 스냅샷 {p.get('snapshot_days')}일)" if p.get("ramp") else ""),
        f"[편성]   이유: {p['why']}",
        f"[편성]   이달 카테고리: {p.get('category')} · 가격대: {p['price_band']}",
        f"[편성]   제품: {prod.get('name')}",
    ]
    if p.get("prefer_next_kok"):
        lines.append("[편성]   ⚠️ 최근 '다음콕' 비율이 낮다 — 이번 편은 탈락 쪽을 우선 검토")
    if p.get("revisit_available"):
        lines.append(f"[편성]   ♻️ 재심콕 후보: {p['revisit_available']}")
    return "\n".join(lines)


def ready_products() -> list[str]:
    """실사진까지 확보돼 **정확한 상품으로 만들 수 있는** 소재 목록."""
    try:
        import catalog
        cat = catalog.load()
        return [e.get("display") or slug for slug, e in cat.get("products", {}).items()
                if catalog.render_mode(dict(e, slug=slug)) == "exact"]
    except Exception:                                      # noqa: BLE001
        return []


if __name__ == "__main__":
    day = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    board = _load("data/trend_board.json", {})
    print(describe(plan(day, board, _load(PUBLISH_LOG, []), ready_products())))

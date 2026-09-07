"""제품 트렌드 수집 오케스트레이터 — 매일 스냅샷을 쌓고, 주간에 **랭킹 2벌**을 산출한다.

파이프라인
1. **후보 발굴**: 유튜브에서 니치 검색어로 최근 유행 영상을 훑어 LLM이 *제품명*을 뽑는다.
   (네이버 데이터랩은 인기검색어를 주지 않으므로 발굴이 아니라 판정용이다 — 5-4-10)
2. **후보별 신호 수집**: 유튜브(노출·공급·효율) / 데이터랩(수요) / 검색 API(언급량) / 쿠팡(거래).
3. **일별 스냅샷 저장**: `data/trends_daily/YYYY-MM-DD.json`. 리뷰 증가·가격 변동은
   어제 스냅샷과 비교해야 나오므로 **매일 쌓는 것이 전제**다.
4. **주간 집계**: 재인 랭킹(월 브리핑용) / 구매가치 랭킹(심층 편용)을 `data/trend_board.json`으로.
5. **중복 방지**: `data/covered.json`에 다룬 제품을 기록하고 **8주간 재등장 금지**.
   단 **가격 급락·순위 급등은 예외**(재심콕 논리 — 상태가 바뀌면 새 정보다).

실행: `python trend_products.py collect`(매일) / `python trend_products.py board`(주간)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

from common import cfg, llm_json
import trend_sources as src
from trend_score import ProductSignals, VideoStat, rank

DAILY_DIR = "data/trends_daily"
BOARD = "data/trend_board.json"
COVERED = "data/covered.json"
COVER_BLOCK_WEEKS = 8
PRICE_DROP_EXEMPT = 0.15   # 15% 이상 하락하면 8주 차단을 무시하고 다시 다룬다(재심콕)


# ------------------------------------------------------------------ 저장소
def _load(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"[store] {path} 읽기 실패({e}) — 기본값 사용")
        return default


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def snapshots(limit: int = 60) -> list[dict]:
    """최근 스냅샷을 오래된 것 → 최신 순으로. 시계열 축은 여기서 만들어진다."""
    if not os.path.isdir(DAILY_DIR):
        return []
    files = sorted(f for f in os.listdir(DAILY_DIR) if f.endswith(".json"))[-limit:]
    out = []
    for f in files:
        d = _load(os.path.join(DAILY_DIR, f), None)
        if d:
            out.append(d)
    return out


# ------------------------------------------------------------------ 1. 후보 발굴
def discover(c: dict, per_query: int = 25) -> list[str]:
    """유튜브 최근 인기 영상 제목에서 **제품명**을 추출한다.

    제목은 사람이 부르는 이름으로 쓰여 있으므로, 여기서 나온 표현이 곧
    '유행 시점의 통칭'이다(5-4-10의 재인 규칙에 그대로 쓰인다).
    """
    titles: list[str] = []
    for q in c["trends"]["queries"]:
        vids = src.youtube_videos(q, days=14, max_items=per_query)
        if vids is None:
            continue
        found = src._get(src.YT_SEARCH, params={  # 제목은 search 응답에 있으므로 재활용
            "key": os.getenv("YT_API_KEY", ""), "q": q, "part": "snippet", "type": "video",
            "order": "viewCount", "regionCode": "KR", "relevanceLanguage": "ko",
            "publishedAfter": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "maxResults": min(per_query, 50)}) or {}
        titles += [i["snippet"]["title"] for i in found.get("items", []) if i.get("snippet")]
    if not titles:
        print("[discover] 유튜브 소스 없음 — 후보 발굴 건너뜀(YT_API_KEY 확인)")
        return []
    sample = "\n".join(f"- {t}" for t in titles[:60])
    data = llm_json(f"""아래는 최근 2주 한국 쇼츠 인기 영상 제목입니다. 니치: {c['niche']}.
{sample}

여기서 **반복적으로 등장하는 실제 제품**만 골라 JSON으로 주세요.
{{"products": [
  {{"key": "영문소문자_스네이크케이스_식별자",
    "name": "제품 통칭 — **영상에서 사람들이 부르는 이름 그대로**(정식 상품명 아님, 12자 이내)",
    "search_keyword": "네이버·쿠팡에서 검색할 대표 키워드",
    "price_band": "저가|중가|고가"}}
  ... 최대 15개
]}}
규칙: 특정 브랜드·모델명이 아니라 **품목**으로. 채널명·유행어·비제품 단어는 제외.""")
    out = []
    for p in data.get("products", [])[:15]:
        if p.get("key") and p.get("name"):
            out.append(p)
    print(f"[discover] 후보 {len(out)}개")
    return out


# ------------------------------------------------------------------ 2~3. 일별 수집
def collect() -> dict:
    c = cfg()
    avail = src.available()
    print("[collect] 소스 가용성:", avail)
    cands = discover(c)
    today = dt.date.today().isoformat()
    rows = []
    for p in cands:
        kw = p.get("search_keyword") or p["name"]
        vids = src.youtube_videos(kw, days=14) or []
        coupang = src.coupang_product(kw)
        rows.append({
            "key": p["key"], "name": p["name"], "keyword": kw,
            "price_band": p.get("price_band"),
            "videos": [{"views": v.views, "age_days": round(v.age_days, 2), "channel_id": v.channel_id}
                       for v in vids],
            "mentions": src.naver_mentions(kw),
            "demand": src.naver_demand(kw),
            "demand_last_year": src.naver_demand(kw, last_year=True),
            "price": (coupang or {}).get("price"),
            "review_count": (coupang or {}).get("review_count"),
            "coupang_url": (coupang or {}).get("url"),
        })
    snap = {"date": today, "sources": avail, "products": rows}
    _save(os.path.join(DAILY_DIR, f"{today}.json"), snap)
    print(f"[collect] {today} 스냅샷 저장 — 제품 {len(rows)}개")
    return snap


# ------------------------------------------------------------------ 4~5. 주간 집계
def _prev_values(hist: list[dict], key: str) -> tuple[int | None, float | None, int | None]:
    """직전(오늘 제외) 스냅샷에서 리뷰 수·가격·언급량을 찾는다. 증가율 계산의 기준점."""
    for snap in reversed(hist[:-1]):
        for p in snap.get("products", []):
            if p["key"] == key:
                return p.get("review_count"), p.get("price"), p.get("mentions")
    return None, None, None


def _is_blocked(covered: dict, key: str, price: float | None, today: dt.date) -> bool:
    """8주 내 다뤘으면 차단 — **단 가격이 15% 이상 내렸으면 예외**(상태가 바뀌면 새 정보)."""
    rec = covered.get(key)
    if not rec:
        return False
    try:
        last = dt.date.fromisoformat(rec["date"])
    except Exception:  # noqa: BLE001
        return False
    if (today - last).days >= COVER_BLOCK_WEEKS * 7:
        return False
    old = rec.get("price")
    if price and old and old > 0 and (old - price) / old >= PRICE_DROP_EXEMPT:
        print(f"[board] {key}: 가격 {old}→{price} 급락 — 8주 차단 예외(재심콕 후보)")
        return False
    return True


def board() -> dict:
    """재인 랭킹과 구매가치 랭킹을 산출해 `data/trend_board.json`에 쓴다."""
    hist = snapshots()
    if not hist:
        print("[board] 스냅샷이 없다 — 먼저 `collect`를 실행할 것")
        return {}
    today_snap = hist[-1]
    today = dt.date.fromisoformat(today_snap["date"])
    covered = _load(COVERED, {})

    signals: list[ProductSignals] = []
    meta: dict[str, dict] = {}
    for p in today_snap.get("products", []):
        rc_prev, price_prev, men_prev = _prev_values(hist, p["key"])
        signals.append(ProductSignals(
            key=p["key"], name=p["name"],
            videos=[VideoStat(v["views"], v["age_days"], v.get("channel_id", "")) for v in p.get("videos", [])],
            demand_series=p.get("demand"),
            demand_series_last_year=p.get("demand_last_year"),
            mentions_recent=p.get("mentions"), mentions_prev=men_prev,
            review_count=p.get("review_count"), review_count_prev=rc_prev,
            price=p.get("price"), price_prev=price_prev,
        ))
        meta[p["key"]] = p

    rows = rank(signals)
    for r in rows:
        m = meta.get(r["key"], {})
        r["price_band"] = m.get("price_band")
        r["keyword"] = m.get("keyword")
        r["coupang_url"] = m.get("coupang_url")
        r["blocked"] = _is_blocked(covered, r["key"], m.get("price"), today)

    fresh = [r for r in rows if not r["blocked"]]
    out = {
        "updated": today_snap["date"],
        "sources": today_snap.get("sources", {}),
        "snapshot_days": len(hist),
        # 월요일 「콕 브리핑」 — 시청자가 이미 봤을 확률 순(5-4-10)
        "briefing": sorted(fresh, key=lambda r: r["recognition"], reverse=True)[:10],
        # 화·목 심층 판정 — 실제로 사도 되는가 순(5-4-9)
        "deep_dive": sorted(fresh, key=lambda r: r["value"], reverse=True)[:5],
        "blocked": [r["key"] for r in rows if r["blocked"]],
        "all": rows,
    }
    _save(BOARD, out)
    print(f"[board] 재인 상위: {[r['name'] for r in out['briefing'][:5]]}")
    print(f"[board] 구매가치 상위: {[r['name'] for r in out['deep_dive'][:3]]}")
    return out


def mark_covered(key: str, price: float | None = None) -> None:
    """영상으로 다룬 제품을 기록 — 8주 중복 방지의 기준. 발행 스크립트가 호출한다."""
    covered = _load(COVERED, {})
    covered[key] = {"date": dt.date.today().isoformat(), "price": price}
    _save(COVERED, covered)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"
    if cmd == "collect":
        collect()
    elif cmd == "board":
        board()
    else:
        print("사용법: python trend_products.py [collect|board]")
        sys.exit(1)

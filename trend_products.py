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
import discover_terms as dterms
import product_links as plinks
import trend_sources as src
from trend_score import ProductSignals, VideoStat, rank

DAILY_DIR = "data/trends_daily"
WATCHLIST = "data/watchlist.json"
WATCH_DAYS = 21          # 한 번 발굴한 제품을 며칠간 계속 추적할지(델타 계산의 전제)
WATCH_MAX = 20           # 추적 목록 상한 — 유튜브 할당량(search 100유닛/제품)을 지킨다
BOARD = "data/trend_board.json"
COVERED = "data/covered.json"
COVER_BLOCK_WEEKS = 8
PRICE_DROP_EXEMPT = 0.15   # 15% 이상 하락하면 8주 차단을 무시하고 다시 다룬다(재심콕)
REVISIT_MIN_WEEKS = 4      # 노출 재상승으로 재등장할 때의 최소 쿨다운(가격 소스가 없을 때의 대체 트리거)


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
def discover(c: dict, per_query: int = 50) -> list[dict]:
    """후보 발굴 — **링크로 특정된 실제 상품**을 찾는다.

    순서가 핵심이다: **수집 → 통계 → LLM**. LLM에게 먼저 물으면 그럴듯한 제품명을 지어낸다.
      1) 유행 특화 검색어로 최근 영상을 모으고 **설명란까지** 받는다
      2) 설명란의 제휴 링크를 상품 ID로 묶어(product_links) **여러 채널이 링크한 상품**만 남긴다
         → 이게 "정확한 상품" + "진짜 유행"을 동시에 만족하는 유일한 신호다
      3) 링크가 없는 영상은 제목 n-gram으로 보조 후보를 만든다(discover_terms)
      4) LLM은 **정규화만** 한다 — 통칭·검색 키워드·카테고리 정리. 없는 제품을 만들지 못하게
         근거(채널 수·예시 제목)를 함께 넘긴다

    ⚠️ 남의 제휴 링크는 상품 식별에만 쓰고 **게시에는 절대 재사용하지 않는다**(수수료가 그쪽으로 간다).
    """
    videos: list[dict] = []
    seen = set()
    for q in c["trends"]["queries"]:
        got = src.youtube_search_rich(q, days=14, max_items=per_query)
        if got is None:
            continue
        for v in got:
            if v["id"] not in seen:
                seen.add(v["id"])
                videos.append(v)
    if not videos:
        print("[discover] 유튜브 수집 0건 — YT_API_KEY를 확인할 것")
        return []
    print(f"[discover] 영상 {len(videos)}편 수집(설명란 포함)")

    linked = plinks.cluster(videos, min_channels=2)
    with_link = sum(1 for v in videos if plinks.links_in(v))
    print(f"[discover] 제휴 링크가 있는 영상 {with_link}편 → 여러 채널이 링크한 상품 {len(linked)}개")
    for r in linked[:8]:
        print(f"[discover]   · {r['name'] or '(미상)'} — 채널 {r['channels']}개 · 조회 {r['views']:,}")

    terms = dterms.candidates(videos, min_videos=3, min_channels=2)
    data = llm_json(f"""당신은 한국 커머스 트렌드 분석가입니다. 니치: {c['niche']}.
아래는 **최근 2주 쇼츠에서 통계로 확인된 것들**입니다. 없는 정보를 추가하지 말고 정리만 하세요.

[A. 여러 채널이 제휴 링크를 건 실제 상품] ← 가장 신뢰도 높음. 우선 채택
{plinks.summary(linked)}

[B. 제목에 반복 등장한 표현] ← A에 없는 것만 보조로
{dterms.evidence_block(terms)}

아래 JSON만 출력하세요.
{{"products": [
  {{"key": "영문소문자_스네이크케이스_식별자",
    "name": "**사람들이 부르는 이름 그대로**(12자 이내). 위 근거에 나온 표현을 쓸 것",
    "search_keyword": "네이버·쿠팡에서 이 상품을 찾을 검색어 — **구체적일수록 좋다**",
    "brand": "근거에 브랜드명이 보이면 적고, 없으면 빈 문자열. **추측 금지**",
    "product_id": "A에서 왔으면 그 platform:id, B에서 왔으면 빈 문자열",
    "category": "네이버 쇼핑 카테고리 — 50000000 패션의류/50000001 패션잡화/50000002 화장품미용/50000003 디지털가전/50000004 가구인테리어/50000005 출산육아/50000006 식품/50000007 스포츠레저/50000008 생활건강. **가전은 반드시 50000003**",
    "price_band": "저가|중가|고가",
    "evidence": "왜 유행으로 판단했는지 한 줄 — 근거의 채널 수·조회수를 인용"}}
  ... 최대 12개, **A 항목을 먼저**
]}}

규칙
- **위 근거에 없는 제품을 만들어내지 마세요.** 브랜드도 근거에 없으면 비워두세요
- `프라이팬`·`청소기`처럼 1년 내내 영상이 나오는 **일반 카테고리 단독은 제외**합니다.
  유행이 아니라 상수이기 때문입니다. 수식어가 붙어 특정되는 경우만 채택하세요
- 채널명·유행어·비제품 표현은 제외합니다""")

    out = []
    for p in data.get("products", [])[:12]:
        if p.get("key") and p.get("name"):
            out.append(p)
    print(f"[discover] 최종 후보 {len(out)}개: {', '.join(p['name'] for p in out)}")
    return out


# ------------------------------------------------------------------ 2~3. 일별 수집
def merge_watchlist(found: list[dict], today: dt.date) -> list[dict]:
    """신규 발굴 결과를 **추적 목록과 합친다.**

    ⚠️ 이게 없으면 파이프라인이 성립하지 않는다: `discover`는 매 실행 LLM 샘플링으로 서로 다른
    제품을 뽑기 때문에(run #4 프라이팬·철수세미 → run #5 코팅팬·종이호일), 같은 제품이 이틀 연속
    잡히지 않아 **델타(NEW/↑/↓)와 리뷰 증가가 영원히 계산되지 않는다.**
    한 번 발굴한 제품은 WATCH_DAYS 동안 계속 추적해 시계열을 만든다.
    """
    wl = _load(WATCHLIST, {})
    for p in found:                       # 신규 발굴은 갱신 또는 추가
        rec = wl.get(p["key"], {})
        rec.update({k: p[k] for k in ("name", "search_keyword", "category", "price_band") if k in p})
        rec["last_found"] = today.isoformat()
        rec.setdefault("first_seen", today.isoformat())
        wl[p["key"]] = rec
    alive, dropped = {}, []
    for key, rec in wl.items():
        try:
            age = (today - dt.date.fromisoformat(rec.get("last_found", "1970-01-01"))).days
        except ValueError:
            age = 999
        (alive.__setitem__(key, rec) if age <= WATCH_DAYS else dropped.append(key))
    # 최근 발굴된 것부터 상한까지 — 할당량을 넘기지 않으면서 신선도를 유지
    ordered = sorted(alive.items(), key=lambda kv: kv[1].get("last_found", ""), reverse=True)[:WATCH_MAX]
    alive = dict(ordered)
    _save(WATCHLIST, alive)
    if dropped:
        print(f"[watch] {WATCH_DAYS}일 넘게 재발굴 안 됨 — 추적 종료: {dropped}")
    new_keys = {p["key"] for p in found} - set(wl.keys() - alive.keys())
    print(f"[watch] 추적 {len(alive)}개 (이번 신규 {len([p for p in found if p['key'] in alive])}개)")
    return [{"key": k, **v} for k, v in alive.items()]


def collect() -> dict:
    c = cfg()
    avail = src.available()
    for axis, state in src.axis_report().items():
        print(f"[collect] {axis}: {state}")
    today_d = dt.date.today()
    cands = merge_watchlist(discover(c), today_d)
    today = today_d.isoformat()
    rows = []
    for p in cands:
        kw = p.get("search_keyword") or p["name"]
        # 카테고리를 고정하면 가전(미니 세탁기·식기세척기)이 생활/건강에 안 잡혀 수요가 0이 된다(실측)
        cat = str(p.get("category") or "50000008")
        vids = src.youtube_videos(kw, days=14) or []
        coupang = src.coupang_product(kw)
        # 네이버 쇼핑 검색은 2026-07-31 종료 → 가격 대체 소스가 없다.
        # 가격은 픽담 글의 구조화 블록에서 들어오고(운영 브리프 6-C), 재심콕은 노출 재상승으로 대체한다.
        shop = None
        rows.append({
            "key": p["key"], "name": p["name"], "keyword": kw,
            "price_band": p.get("price_band"),
            "videos": [{"views": v.views, "age_days": round(v.age_days, 2), "channel_id": v.channel_id}
                       for v in vids],
            "category": cat,
            "mentions": src.naver_mentions(kw),
            "demand": src.naver_demand(kw, category=cat),
            "demand_last_year": src.naver_demand(kw, category=cat, last_year=True),
            "price": (coupang or {}).get("price") or (shop or {}).get("price"),
            "review_count": (coupang or {}).get("review_count"),   # 쿠팡 없으면 결측 → 거래 축 제외
            "sellers": (shop or {}).get("sellers"),
            "coupang_url": (coupang or {}).get("url"),
            "price_source": "coupang" if coupang else ("naver_shop" if shop else None),
        })
    snap = {"date": today, "sources": avail, "products": rows}
    _save(os.path.join(DAILY_DIR, f"{today}.json"), snap)
    _print_summary(rows, today)
    return snap


def _print_summary(rows: list[dict], today: str) -> None:
    """축별 수집 성공률을 로그에 남긴다.

    "성공"으로 끝난 실행에서도 특정 축이 통째로 결측일 수 있는데(키는 있지만 API 경로가 틀린 경우 등)
    그게 로그에 안 보이면 몇 주 뒤에야 알아챈다. 매 실행 눈에 띄게 찍는다.
    """
    n = len(rows)
    print(f"\n[collect] {today} 스냅샷 저장 — 제품 {n}개")
    if not n:
        print("[collect] ⚠️ 제품이 0개다 — 발굴(discover) 단계를 확인할 것")
        return
    checks = (
        ("노출(유튜브)", lambda p: bool(p.get("videos"))),
        ("언급량(검색)", lambda p: p.get("mentions") is not None),
        ("수요(데이터랩)", lambda p: bool(p.get("demand"))),
        ("작년(계절성)", lambda p: bool(p.get("demand_last_year"))),
        ("가격", lambda p: p.get("price") is not None),
        ("리뷰(거래)", lambda p: p.get("review_count") is not None),
    )
    print("[collect] 축별 수집 성공률")
    for label, fn in checks:
        ok = sum(1 for p in rows if fn(p))
        mark = "✅" if ok == n else ("⚠️ 부분" if ok else "❌ 전멸")
        print(f"[collect]   {label:<14} {ok}/{n}  {mark}")
    print("[collect] 수집 제품: " + ", ".join(p["name"] for p in rows))


# ------------------------------------------------------------------ 4~5. 주간 집계
def _prev_values(hist: list[dict], key: str) -> tuple[int | None, float | None, int | None]:
    """직전(오늘 제외) 스냅샷에서 리뷰 수·가격·언급량을 찾는다. 증가율 계산의 기준점."""
    for snap in reversed(hist[:-1]):
        for p in snap.get("products", []):
            if p["key"] == key:
                return p.get("review_count"), p.get("price"), p.get("mentions")
    return None, None, None


def _exposure_at(hist: list[dict], key: str, days_ago: int) -> float | None:
    """`days_ago`일 전 스냅샷에서의 노출량(조회수 합). 델타 판정의 기준점."""
    if not hist:
        return None
    target = dt.date.fromisoformat(hist[-1]["date"]) - dt.timedelta(days=days_ago)
    best, best_gap = None, None
    for snap in hist[:-1]:
        try:
            gap = abs((dt.date.fromisoformat(snap["date"]) - target).days)
        except Exception:  # noqa: BLE001
            continue
        if best_gap is None or gap < best_gap:
            for p in snap.get("products", []):
                if p["key"] == key:
                    best, best_gap = sum(v["views"] for v in p.get("videos", [])), gap
                    break
    return best


def delta(hist: list[dict], key: str, current_views: float, days: int = 7,
          threshold: float = 0.15) -> str:
    """주간 델타 — 브리핑 차트의 **NEW / ↑상승 / ↓하락** 섹션(5-4-2).

    단순 나열(TOP10)은 완결형이라 다시 볼 이유가 없다. **변화**를 보여줘야 시리즈성이 생긴다.
    기준 스냅샷에 없던 제품은 `new`, 노출량이 임계 이상 변하면 `up`/`down`, 아니면 `flat`.
    """
    prev = _exposure_at(hist, key, days)
    if prev is None:
        return "new"
    if prev <= 0:
        return "up" if current_views > 0 else "flat"
    change = (current_views - prev) / prev
    if change >= threshold:
        return "up"
    if change <= -threshold:
        return "down"
    return "flat"


def _is_blocked(covered: dict, key: str, price: float | None, today: dt.date,
                delta_state: str | None = None) -> bool:
    """8주 내 다뤘으면 차단. **상태가 바뀌면 새 정보**이므로 두 가지 예외를 둔다.

    1) **가격 15% 이상 하락** — 원래의 재심콕 트리거.
    2) **노출 재상승(delta='up')** + 최소 4주 경과 — 네이버 쇼핑 검색 종료(2026-07-31)로
       가격 소스가 사라진 상황의 대체 트리거. 한 번 식었다 다시 뜨는 것 자체가 새 정보다.
    """
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
    if delta_state == "up" and (today - last).days >= REVISIT_MIN_WEEKS * 7:
        print(f"[board] {key}: 식었다 다시 상승 — 8주 차단 예외(재조명)")
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
        r["delta"] = delta(hist, r["key"], sum(v["views"] for v in m.get("videos", [])))
        r["price"] = m.get("price")
        r["price_source"] = m.get("price_source")
        r["sellers"] = m.get("sellers")
        r["price_band"] = m.get("price_band")
        r["keyword"] = m.get("keyword")
        r["coupang_url"] = m.get("coupang_url")
        r["blocked"] = _is_blocked(covered, r["key"], m.get("price"), today, r.get("delta"))

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

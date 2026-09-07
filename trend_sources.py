"""제품 트렌드 수집 어댑터 — 4개 소스를 **각각 독립적으로** 읽는다.

설계 원칙 (`docs/콕픽_채널_전략.md` 5-4-9 · 5-4-10)
- **키가 없는 소스는 조용히 건너뛴다.** 어떤 소스가 빠져도 파이프라인은 멈추지 않고,
  `trend_score`가 결측 축을 빼고 가중치를 재정규화한다. 특히 쿠팡은 API 승인 조건이 있어
  없을 가능성이 높으므로 **없어도 브리핑이 완성되어야** 한다.
- **결측은 0이 아니라 None**이다. 0은 "재보니 0", None은 "못 쟀다"로 의미가 다르다.

소스와 축의 대응
| 소스 | 축 | 비고 |
|---|---|---|
| YouTube Data API | 공급·효율·**노출(재인)** | 개수보다 조회수 합·중앙값이 중요(5-4-9①) |
| 네이버 데이터랩 쇼핑인사이트 | 수요 | 지정 키워드의 일별 지수. **TOP500 인기검색어는 API로 안 준다** |
| 네이버 검색 API(블로그/카페) | **언급량(재인 보조)** | `total`이 곧 언급량. **데이터랩과 동일 키**라 추가 비용 0 |
| 네이버 쇼핑 검색 API | **가격·셀러 수(거래 대리)** | 쿠팡 API가 없을 때의 대체. 같은 키 |
| 쿠팡 파트너스 오픈API | **거래** | 리뷰 증가 = 위조 불가 신호. **일정 수익 이상이어야 발급**되므로 초기엔 없다 |

⚠️ **쿠팡 오픈API는 초기 운영자에게 사실상 없다**(파트너스 수익 요건). 그래서 거래 축을
네이버 쇼핑 검색 API로 부분 대체한다 — 완전한 대체는 아니지만 **가격 추적이 살아나므로
재심콕(가격 15%↓ 재등장) 트리거가 동작하고**, 셀러 수 증가는 시장이 커지는 신호로 쓸 수 있다.
쿠팡 키가 생기면 자동으로 거래 축이 켜지고 정확도가 올라간다(코드 변경 불필요).
"""
from __future__ import annotations

import base64, datetime as dt, hashlib, hmac, os, time
from typing import Any

import requests

from trend_score import VideoStat

YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
NAVER_DATALAB = "https://openapi.naver.com/v1/datalab/shopping/keywords"
NAVER_SEARCH = "https://openapi.naver.com/v1/search/{kind}.json"
COUPANG_HOST = "https://api-gateway.coupang.com"


def _get(url: str, **kw) -> dict[str, Any] | None:
    """실패해도 예외를 올리지 않는다 — 소스 하나가 죽어도 나머지로 진행해야 하기 때문."""
    try:
        r = requests.get(url, timeout=30, **kw)
        if r.status_code != 200:
            print(f"[src] {url.split('/')[-1]} HTTP {r.status_code}: {r.text[:160]}")
            return None
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[src] {url.split('/')[-1]} 실패: {e}")
        return None


# ------------------------------------------------------------------ YouTube
def youtube_videos(keyword: str, days: int = 14, max_items: int = 50,
                   region: str = "KR") -> list[VideoStat] | None:
    """최근 `days`일 관련 영상의 (조회수, 경과일, 채널) 목록.

    할당량 메모: `search.list`는 호출당 100유닛, `videos.list`는 1유닛(하루 10,000).
    그래서 **검색은 제품당 1회만** 하고 통계는 한 번에 묶어 받는다.
    반환값은 노출(재인)·공급·효율 세 축의 원천이 된다.
    """
    key = os.getenv("YT_API_KEY", "")
    if not key:
        return None
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = _get(YT_SEARCH, params={
        "key": key, "q": keyword, "part": "snippet", "type": "video",
        "order": "viewCount", "regionCode": region, "relevanceLanguage": "ko",
        "publishedAfter": after, "maxResults": min(max_items, 50),
    })
    if not found:
        return None
    ids, meta = [], {}
    for it in found.get("items", []):
        vid = (it.get("id") or {}).get("videoId")
        if not vid:
            continue
        ids.append(vid)
        sn = it.get("snippet", {})
        meta[vid] = (sn.get("channelId", ""), sn.get("publishedAt", ""))
    if not ids:
        return []
    stats = _get(YT_VIDEOS, params={"key": key, "id": ",".join(ids), "part": "statistics"})
    if not stats:
        return []
    now = dt.datetime.now(dt.timezone.utc)
    out: list[VideoStat] = []
    for it in stats.get("items", []):
        vid = it.get("id", "")
        ch, pub = meta.get(vid, ("", ""))
        try:
            age = (now - dt.datetime.fromisoformat(pub.replace("Z", "+00:00"))).total_seconds() / 86400
        except Exception:  # noqa: BLE001
            age = days / 2
        out.append(VideoStat(views=int(it.get("statistics", {}).get("viewCount", 0)),
                             age_days=max(age, 0.0), channel_id=ch))
    return out


# ------------------------------------------------------------------ 네이버 공통
def _naver_headers() -> dict[str, str] | None:
    cid, sec = os.getenv("NAVER_CLIENT_ID", ""), os.getenv("NAVER_CLIENT_SECRET", "")
    if not (cid and sec):
        return None
    return {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec,
            "Content-Type": "application/json"}


def naver_demand(keyword: str, category: str = "50000008",
                 days: int = 120, last_year: bool = False) -> list[float] | None:
    """네이버 데이터랩 쇼핑인사이트 — 키워드의 **일별 클릭량 지수**(수요 축).

    ⚠️ 이 API는 '인기검색어 TOP500'을 주지 않는다(그건 웹 화면 전용). **발굴이 아니라 판정용**이다.
    발굴은 유튜브·쿠팡이 하고, 여기서는 후보 키워드가 오르는 중인지 내리는 중인지를 잰다.
    `last_year=True`면 1년 전 같은 기간을 받아 계절성 제거(5-4-9⑥)에 쓴다 —
    **과거 기간 조회가 되므로 1년을 기다릴 필요가 없다.**
    """
    h = _naver_headers()
    if not h:
        return None
    end = dt.date.today() - (dt.timedelta(days=365) if last_year else dt.timedelta(0))
    start = end - dt.timedelta(days=days)
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "date",
        "category": category,
        "keyword": [{"name": keyword, "param": [keyword]}],
    }
    try:
        r = requests.post(NAVER_DATALAB, json=body, headers=h, timeout=30)
        if r.status_code != 200:
            print(f"[src] datalab HTTP {r.status_code}: {r.text[:160]}")
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        return [float(d.get("ratio", 0)) for d in results[0].get("data", [])]
    except Exception as e:  # noqa: BLE001
        print("[src] datalab 실패:", e)
        return None


def naver_shopping(keyword: str) -> dict[str, Any] | None:
    """네이버 쇼핑 검색 API — **최저가와 등록 상품 수**(거래 축의 부분 대체).

    쿠팡 오픈API는 파트너스 수익 요건이 있어 초기 운영자는 발급받을 수 없다. 그 공백을 메운다.
    - `lprice`(최저가): **가격 추적이 되므로 재심콕 트리거(15% 하락)가 살아난다.** 이게 가장 큰 이득.
    - `total`(등록 상품 수): 셀러가 몰린다 = 시장이 커진다는 신호. 다만 소비자 거래가 아니라
      **공급 측 신호**이므로 리뷰 증가만큼 신뢰할 수는 없다 — 보조 지표로만 쓴다.
    데이터랩·검색 API와 **동일한 Client ID**로 호출된다(추가 발급·비용 0).
    """
    h = _naver_headers()
    if not h:
        return None
    data = _get(NAVER_SEARCH.format(kind="shop"), headers=h,
                params={"query": keyword, "display": 10, "sort": "sim"})
    if data is None:
        return None
    items = data.get("items") or []
    prices = []
    for it in items:
        try:
            v = int(it.get("lprice") or 0)
            if v > 0:
                prices.append(v)
        except (TypeError, ValueError):
            continue
    if not prices:
        return {"price": None, "sellers": data.get("total"), "title": None}
    prices.sort()
    return {
        # 최저가 1건은 미끼상품·오배송일 수 있어 중앙값을 대표가로 쓴다
        "price": prices[len(prices) // 2],
        "price_min": prices[0],
        "sellers": data.get("total"),
        "title": (items[0].get("title") or "").replace("<b>", "").replace("</b>", ""),
    }


def naver_mentions(keyword: str, kind: str = "blog") -> int | None:
    """네이버 검색 API의 `total` — **언급량**(재인 보조 축, 5-4-10).

    인스타 Hashtag Search는 승인 장벽이 높아 쓰지 않는다. 대신 블로그·카페 언급량을
    한국 소셜 노출의 대리 지표로 쓴다. **데이터랩과 같은 Client ID로 호출되어 추가 비용이 없다.**
    """
    h = _naver_headers()
    if not h:
        return None
    data = _get(NAVER_SEARCH.format(kind=kind), headers=h,
                params={"query": keyword, "display": 1, "sort": "date"})
    if data is None:
        return None
    try:
        return int(data.get("total", 0))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ 쿠팡(거래)
def _coupang_auth(method: str, path: str, query: str = "") -> dict[str, str] | None:
    """쿠팡 오픈API HMAC 서명. 접근 권한이 없으면 키 자체가 없으므로 None."""
    ak, sk = os.getenv("COUPANG_ACCESS_KEY", ""), os.getenv("COUPANG_SECRET_KEY", "")
    if not (ak and sk):
        return None
    ts = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    msg = ts + method + path + query
    sig = hmac.new(sk.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": f"CEA algorithm=HmacSHA256, access-key={ak}, "
                             f"signed-date={ts}, signature={sig}"}


def coupang_product(keyword: str) -> dict[str, Any] | None:
    """쿠팡 파트너스 상품 검색 — **거래 축**(리뷰 수·가격)의 원천.

    리뷰는 **구매해야만 남길 수 있어 위조가 불가능**하므로 3축 중 신뢰도가 가장 높다(5-4-9⑤).
    다만 파트너스 오픈API는 계정 등급 조건이 있어 접근이 안 될 수 있다 → 그때는 None을 반환하고
    `trend_score`가 거래 축을 빼고 재정규화한다(브리핑은 그대로 완성된다).
    반환 필드는 승인 후 실측으로 확정할 것 — 지금은 방어적으로 파싱한다.
    """
    path = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
    query = f"keyword={requests.utils.quote(keyword)}&limit=1"
    h = _coupang_auth("GET", path, "?" + query)
    if not h:
        return None
    data = _get(f"{COUPANG_HOST}{path}?{query}", headers=h)
    if not data:
        return None
    items = (data.get("data") or {}).get("productData") or []
    if not items:
        return None
    it = items[0]
    return {
        "name": it.get("productName"),
        "price": it.get("productPrice"),
        "url": it.get("productUrl"),
        "review_count": it.get("reviewCount"),   # 미제공 시 None → 거래 축 결측 처리
    }


def available() -> dict[str, bool]:
    """어떤 소스가 살아 있는지 — 로그와 대시보드에 그대로 노출해 '왜 이 축이 비었는지' 보이게 한다."""
    return {
        "youtube": bool(os.getenv("YT_API_KEY")),
        "naver": bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET")),
        "coupang": bool(os.getenv("COUPANG_ACCESS_KEY") and os.getenv("COUPANG_SECRET_KEY")),
    }


def axis_report() -> dict[str, str]:
    """어떤 축이 살아 있고 무엇으로 대체 중인지 — 로그·대시보드에 그대로 노출한다.
    '왜 이 축이 비었는지'가 보이지 않으면 나중에 원인을 못 찾는다."""
    a = available()
    return {
        "노출(재인)": "유튜브 ✅" if a["youtube"] else "❌ YT_API_KEY 없음 — 재인 랭킹 불가",
        "수요": "네이버 데이터랩 ✅" if a["naver"] else "❌ NAVER_CLIENT_ID/SECRET 없음",
        "언급량": "네이버 검색 ✅" if a["naver"] else "❌ 동일 키 필요",
        "거래": ("쿠팡 리뷰 ✅" if a["coupang"]
                 else ("⚠️ 쿠팡 미발급 — 네이버 쇼핑(가격·셀러수)으로 부분 대체"
                       if a["naver"] else "❌ 대체 소스도 없음")),
    }

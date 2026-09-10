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

import base64, datetime as dt, hashlib, hmac, os, re, time
from typing import Any

import requests

from trend_score import VideoStat

YT_SEARCH = "https://www.googleapis.com/youtube/v3/search"
YT_VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
# ── 네이버 오픈API 이관(2026) ────────────────────────────────────────────────
# 네이버가 개발자센터 오픈API를 **NAVER API HUB(네이버 클라우드)**로 이관 중이다.
#   · 레거시 키(X-Naver-Client-Id/Secret)는 **2027-06-30까지** 사용 가능
#   · 도메인 openapi.naver.com → naverapihub.apigw.ntruss.com
#   · 인증 헤더 X-Naver-Client-Id/Secret → X-NCP-APIGW-API-KEY-ID/KEY
#   · ⛔ **쇼핑 검색·책·전문자료 검색은 2026-07-31 종료(대체 없음)** — HUB에도 없다
# 그래서 두 방식을 모두 지원하고 **HUB 키가 있으면 HUB를 우선**한다.
# HUB 경로는 첫 호출 때 실측으로 확정할 것(문서에 경로 표기가 없어 레거시와 동일 경로로 가정).
NAVER_LEGACY_BASE = "https://openapi.naver.com"
NAVER_HUB_BASE = os.getenv("NAVER_HUB_BASE", "https://naverapihub.apigw.ntruss.com")
# ⚠️ HUB는 도메인·헤더만 바뀐 게 아니라 **경로 구조가 뒤집혔다**(2026-09-07 공식 문서 실측).
#   블로그 검색  레거시 /v1/search/blog.json   → HUB /search/v1/blog        (확장자 없음, format=json 파라미터)
#   쇼핑인사이트 레거시 /v1/datalab/shopping/keywords → HUB /shopping/v1/category/keywords
# 처음엔 "레거시와 같은 경로"로 가정했다가 네이버 두 축이 전멸했다(run #4에서 12/12 결측).
NAVER_PATHS = {
    "hub": {"search": "/search/v1/{kind}", "datalab": "/shopping/v1/category/keywords"},
    "legacy": {"search": "/v1/search/{kind}.json", "datalab": "/v1/datalab/shopping/keywords"},
}
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


def youtube_search_rich(query: str, days: int = 14, max_items: int = 50,
                        region: str = "KR") -> list[dict] | None:
    """발굴용 — 제목뿐 아니라 **설명란(description)까지** 받아온다.

    설명란에 크리에이터의 제휴 링크가 들어 있고, 그 링크가 "정확히 어느 상품인가"를 특정한다
    (product_links 참조). `videos.list`의 part에 snippet을 추가하는 것뿐이라 **할당량은 그대로**다
    (videos.list는 1유닛). 비싼 건 search.list(100유닛)이고 그건 어차피 1회 호출한다.
    """
    key = os.getenv("YT_API_KEY", "")
    if not key:
        return None
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found = _get(YT_SEARCH, params={
        "key": key, "q": query, "part": "snippet", "type": "video",
        "order": "viewCount", "regionCode": region, "relevanceLanguage": "ko",
        "publishedAfter": after, "maxResults": min(max_items, 50),
    })
    if not found:
        return None
    ids = [i["id"]["videoId"] for i in found.get("items", []) if (i.get("id") or {}).get("videoId")]
    if not ids:
        return []
    stats = _get(YT_VIDEOS, params={"key": key, "id": ",".join(ids[:50]),
                                    "part": "snippet,statistics"})
    out = []
    for it in (stats or {}).get("items", []):
        sn = it.get("snippet", {})
        out.append({
            "id": it.get("id"),
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),   # ← 제휴 링크가 여기 있다
            "channel_id": sn.get("channelId", ""),
            "channel": sn.get("channelTitle", ""),
            "published": sn.get("publishedAt", "")[:10],
            "views": int(it.get("statistics", {}).get("viewCount", 0)),
        })
    return out


def youtube_first_seen(query: str, days: int = 180, region: str = "US",
                       lang: str = "en", max_items: int = 25) -> dict | None:
    """이 검색어가 **언제 처음 나타났고 얼마나 퍼졌는지**. 지역·언어를 바꿔 부를 수 있다.

    order를 date로 두면 최신순이라 '처음'을 못 본다. viewCount로 받아 그중 가장
    오래된 것을 본다 — 조회수 있는 영상 중 최초라는 뜻이고, 유행의 시작점 근사로 충분하다.
    """
    key = os.getenv("YT_API_KEY", "")
    if not key or not query:
        return None
    after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"key": key, "q": query, "part": "snippet", "type": "video",
              "order": "viewCount", "publishedAfter": after,
              "maxResults": min(max_items, 50)}
    if region:
        params["regionCode"] = region
    if lang:
        params["relevanceLanguage"] = lang
    found = _get(YT_SEARCH, params=params)
    ids = [i["id"]["videoId"] for i in (found or {}).get("items", [])
           if (i.get("id") or {}).get("videoId")]
    if not ids:
        return {"query": query, "region": region, "count": 0, "views": 0,
                "earliest": None, "titles": []}
    stats = _get(YT_VIDEOS, params={"key": key, "id": ",".join(ids[:50]),
                                    "part": "snippet,statistics"})
    rows = []
    for it in (stats or {}).get("items", []):
        sn = it.get("snippet", {})
        rows.append({"published": sn.get("publishedAt", "")[:10],
                     "title": sn.get("title", ""),
                     "views": int(it.get("statistics", {}).get("viewCount", 0))})
    if not rows:
        return {"query": query, "region": region, "count": 0, "views": 0,
                "earliest": None, "titles": []}
    rows.sort(key=lambda r: r["published"])
    return {"query": query, "region": region, "count": len(rows),
            "views": sum(r["views"] for r in rows),
            "earliest": rows[0]["published"],
            "titles": [r["title"] for r in sorted(rows, key=lambda r: -r["views"])[:3]]}


def overseas_lead(ko_query: str, en_query: str, days: int = 180) -> dict | None:
    """**해외가 얼마나 먼저 떴는가.** 인과를 좁히는 가장 값싼 신호다.

    인스타·틱톡 해시태그 증가량이 이상적이지만 2026 기준 둘 다 막혀 있다
    (틱톡은 무료 경로 없음, 인스타는 앱 심사+7일 30개 제한). 그런데 우리가 알고 싶은 건
    결국 "이게 밖에서 먼저 떴나, 언제부터인가"이고, 그건 **이미 가진 유튜브 키**로
    한국 검색과 영어권 검색의 최초 등장일을 비교하면 나온다.

    덤으로 "해외에서 난리난 ○○ 3가지"는 이 니치에서 실제로 197만을 찍은 제목 틀이다.
    """
    ko = youtube_first_seen(ko_query, days=days, region="KR", lang="ko")
    en = youtube_first_seen(en_query, days=days, region="US", lang="en")
    if not ko or not en:
        return None
    out = {"ko": ko, "en": en, "lead_days": None, "verdict": "unknown"}
    if ko.get("earliest") and en.get("earliest"):
        d_ko = dt.date.fromisoformat(ko["earliest"])
        d_en = dt.date.fromisoformat(en["earliest"])
        out["lead_days"] = (d_ko - d_en).days
        if out["lead_days"] >= 21 and en["count"] >= 3:
            out["verdict"] = "overseas_first"      # 해외가 먼저 — "해외에서 난리난"
        elif out["lead_days"] <= -21:
            out["verdict"] = "korea_first"
        else:
            out["verdict"] = "simultaneous"
    elif en.get("count") == 0:
        out["verdict"] = "korea_only"              # 국내 한정 유행
    return out


# ------------------------------------------------------------------ 네이버 공통
def _naver_auth() -> tuple[str, dict[str, str], str] | None:
    """(베이스 URL, 인증 헤더). **HUB 키가 있으면 HUB 우선**, 없으면 레거시로 폴백한다.

    이관 기간 동안 둘 다 살아 있으므로 코드가 양쪽을 알고 있어야 키 교체가 무중단으로 된다.
    레거시 키는 2027-06-30에 끊기므로 그 전에 HUB 키만 넣으면 자동 전환된다.
    """
    kid, key = os.getenv("NAVER_HUB_KEY_ID", ""), os.getenv("NAVER_HUB_KEY", "")
    if kid and key:
        return NAVER_HUB_BASE, {"X-NCP-APIGW-API-KEY-ID": kid, "X-NCP-APIGW-API-KEY": key,
                                "Content-Type": "application/json"}, "hub"
    cid, sec = os.getenv("NAVER_CLIENT_ID", ""), os.getenv("NAVER_CLIENT_SECRET", "")
    if cid and sec:
        return NAVER_LEGACY_BASE, {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec,
                                   "Content-Type": "application/json"}, "legacy"
    return None


def naver_url(mode: str, api: str, kind: str = "") -> str:
    """모드별 엔드포인트 URL. HUB와 레거시는 **경로 구조가 다르므로** 한곳에서 관리한다."""
    base = NAVER_HUB_BASE if mode == "hub" else NAVER_LEGACY_BASE
    return base + NAVER_PATHS[mode][api].format(kind=kind)


def naver_mode() -> str:
    """현재 어느 방식으로 호출 중인지 — 로그에 남겨 이관 상태를 눈으로 확인한다."""
    if os.getenv("NAVER_HUB_KEY_ID") and os.getenv("NAVER_HUB_KEY"):
        return "hub"
    if os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"):
        return "legacy(2027-06-30 만료)"
    return "none"


def naver_demand(keyword: str, category: str | None = None,
                 days: int = 120, last_year: bool = False) -> list[float] | None:
    """네이버 데이터랩 쇼핑인사이트 — 키워드의 **일별 클릭량 지수**(수요 축).

    ⚠️ 이 API는 '인기검색어 TOP500'을 주지 않는다(그건 웹 화면 전용). **발굴이 아니라 판정용**이다.
    발굴은 유튜브·쿠팡이 하고, 여기서는 후보 키워드가 오르는 중인지 내리는 중인지를 잰다.
    `last_year=True`면 1년 전 같은 기간을 받아 계절성 제거(5-4-9⑥)에 쓴다 —
    **과거 기간 조회가 되므로 1년을 기다릴 필요가 없다.**
    """
    auth = _naver_auth()
    if not auth:
        return None
    base, h, mode = auth
    category = category or "50000008"   # 미지정 시 생활/건강
    end = dt.date.today() - (dt.timedelta(days=365) if last_year else dt.timedelta(0))
    start = end - dt.timedelta(days=days)
    body = {
        "startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "date",
        "category": category,
        "keyword": [{"name": keyword, "param": [keyword]}],
    }
    try:
        r = requests.post(naver_url(mode, "datalab"), json=body, headers=h, timeout=30)
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


def demand_ladder(keyword: str, name: str = "", category: str | None = None,
                  last_year: bool = False) -> list[float] | None:
    """수요 조회를 **키워드를 좁혀 가며** 다시 시도한다.

    데이터랩 쇼핑인사이트는 '쇼핑 키워드'를 받는다. 그런데 발굴 키워드는
    「미국 유행 늘어나는 밀폐용기」, 「코에서 계란 흰자 나오는 주방용품」처럼
    문장에 가깝다 — 그런 건 결과가 빈다. 실제로 20개 중 6개만 수요가 잡혔고,
    그중 4개는 점 1~2개라 추세를 못 쟀다(2026-09-10 실측).

    그래서 긴 것부터 짧은 것까지 사다리로 내려간다. 수요 시계열은 "언제부터
    몇 배"를 만들어 내는 **인과를 가장 크게 좁히는 신호**라, 비워 두면 손해가 크다.
    """
    tried, best = [], None
    for kw in _ladder(keyword, name):
        if kw in tried:
            continue
        tried.append(kw)
        got = naver_demand(kw, category=category, last_year=last_year)
        if got and len(got) > len(best or []):
            best = got
            if len(best) >= 30:                              # 추세를 재기 충분하다
                print(f"[src] 수요 키워드 확정: 「{kw}」 ({len(best)}일)")
                return best
    if best:
        print(f"[src] 수요 키워드 부분 확보: {tried} ({len(best)}일)")
    return best


def _ladder(keyword: str, name: str = "") -> list[str]:
    """긴 표현 → 상품명 → 뒤쪽 두 어절 → 핵심 명사 순."""
    out = []
    for base in (keyword, name):
        b = (base or "").strip()
        if not b:
            continue
        out.append(b)
        w = b.split()
        if len(w) >= 3:
            out.append(" ".join(w[-2:]))
        if len(w) >= 2:
            out.append(w[-1])
    return [x for x in dict.fromkeys(out) if len(x) >= 2]


def naver_shopping(keyword: str) -> dict[str, Any] | None:
    """⛔ **폐기됨** — 네이버 쇼핑 검색 API는 **2026-07-31 종료**(대체 없음, API HUB에도 미포함).

    한때 쿠팡 오픈API가 없는 초기 운영자의 '거래 축' 대체재로 최저가·셀러 수를 받으려 했으나
    이관 공지 확인 결과 이미 종료된 API였다. 호출하지 않고 항상 None을 반환한다.

    **가격 정보의 새 경로**: 픽담 글의 구조화 블록(`<!--KOKPICK ... -->`)에 쿠팡 가격이 들어오므로
    거기서 읽는다(운영 브리프 6-C). 재심콕 트리거는 가격 하락 외에 **노출 재상승**도 인정하도록
    `trend_products._is_blocked`에서 보완했다.
    """
    return None


def naver_mentions(keyword: str, kind: str = "blog") -> int | None:
    """네이버 검색 API의 `total` — **언급량**(재인 보조 축, 5-4-10).

    인스타 Hashtag Search는 승인 장벽이 높아 쓰지 않는다. 대신 블로그·카페 언급량을
    한국 소셜 노출의 대리 지표로 쓴다. **데이터랩과 같은 Client ID로 호출되어 추가 비용이 없다.**
    """
    auth = _naver_auth()
    if not auth:
        return None
    base, h, mode = auth
    # HUB 검색은 경로에 .json이 없고 format 파라미터로 응답 형식을 지정한다
    params = {"query": keyword, "display": 1, "sort": "date"}
    if mode == "hub":
        params["format"] = "json"
    data = _get(naver_url(mode, "search", kind), headers=h, params=params)
    if data is None:
        return None
    try:
        return int(data.get("total", 0))
    except (TypeError, ValueError):
        return None


def naver_texts(keyword: str, kind: str = "blog", n: int = 10,
                sort: str = "sim") -> list[dict] | None:
    """네이버 검색 **본문까지** 받아온다.

    naver_mentions는 `display=1`로 불러 `total`만 읽고 본문을 버렸다. 그런데 유행의
    이유는 사람들이 직접 써 놓는다 — "두바이 초콜릿 만들려고 샀다"처럼. 개수는
    규모를 말할 뿐 이유를 말하지 않는다. 같은 키·같은 호출에서 본문을 안 읽을 이유가 없다.

    kind: blog | news | cafearticle
      - news는 **인과를 직접 설명**하는 경우가 많다(품귀·가격·방송)
      - blog/cafe는 **구매 동기**가 사람 말로 적혀 있다
    """
    auth = _naver_auth()
    if not auth:
        return None
    base, h, mode = auth
    params = {"query": keyword, "display": min(n, 30), "sort": sort}
    if mode == "hub":
        params["format"] = "json"
    data = _get(naver_url(mode, "search", kind), headers=h, params=params)
    if data is None:
        return None
    out = []
    for it in data.get("items", []) or []:
        out.append({
            "kind": kind,
            "title": _strip_tags(it.get("title", "")),
            "text": _strip_tags(it.get("description", "")),
            "date": (it.get("postdate") or it.get("pubDate") or "")[:11],
            "link": it.get("link", ""),
        })
    return out


def _strip_tags(t: str) -> str:
    """네이버는 검색어를 <b>로 감싸 돌려준다."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t or "")).strip()


def youtube_comments(video_id: str, n: int = 20) -> list[str] | None:
    """영상 댓글 — **유입 경로가 사람 말로 적혀 있는 유일한 곳**이다.

    "OO 보고 왔어요", "이거 그 방송에서 본 거네" 같은 문장이 인과의 직접 증거가 된다.
    commentThreads.list는 1유닛이라 search.list(100유닛)에 비하면 사실상 공짜다.
    """
    key = os.getenv("YT_API_KEY", "")
    if not (key and video_id):
        return None
    data = _get("https://www.googleapis.com/youtube/v3/commentThreads", params={
        "key": key, "videoId": video_id, "part": "snippet",
        "order": "relevance", "maxResults": min(n, 100), "textFormat": "plainText"})
    if data is None:
        return None
    out = []
    for it in data.get("items", []) or []:
        sn = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet") or {})
        t = (sn.get("textDisplay") or "").strip()
        if t:
            out.append(re.sub(r"\s+", " ", t)[:300])
    return out


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
        "naver": bool((os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"))
                      or (os.getenv("NAVER_HUB_KEY_ID") and os.getenv("NAVER_HUB_KEY"))),
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
                 else "⚠️ 쿠팡 미발급 + 네이버 쇼핑 종료(2026-07-31) — 가격은 픽담 구조화 필드에서, "
                      "재심콕은 노출 재상승으로 대체"),
        "네이버 인증": naver_mode(),
    }

"""제품 트렌드 점수 모델 — **랭킹 2벌**(재인 / 구매가치)을 산출하는 순수 함수 모음.

설계 근거: `docs/콕픽_채널_전략.md` 5-4-9(구매가치=예측 모델) · 5-4-10(재인 모델).

한 줄 요약: **같은 수집 데이터로 목적함수가 다른 두 랭킹을 만든다.**
- **재인 랭킹**(월 「콕 브리핑」용) — "시청자가 **이미 봤을** 확률"
  주 신호는 **총 노출량**(조회수 합 × 채널 다양성 × 최신성). 개수도 중앙값도 아니다.
  1개 채널이 10개 만든 것보다 10개 채널이 하나씩 만든 쪽이 피드 도달이 넓으므로 채널 수에 가중한다.
- **구매가치 랭킹**(화·목 심층 판정용) — "실제로 **사도 되는가**"
  주 신호는 **거래**(쿠팡 리뷰 증가). 공급은 크리에이터 자기참조 거품이 흔해 가중치가 가장 낮다.

이 모듈은 네트워크·파일 IO를 하지 않는다(전부 순수 함수) — 키 없이 단위 테스트가 가능해야 하기 때문.
수집은 `trend_sources.py`, 오케스트레이션은 `trend_products.py`가 맡는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# 구매가치 랭킹의 축별 가중치(5-4-9④). 결측 축은 제외하고 **남은 축의 합으로 재정규화**한다
# — 키가 없어도(예: 쿠팡 API 미승인) 파이프라인이 멈추지 않아야 하기 때문.
VALUE_WEIGHTS = {
    "transaction": 3.0,   # 거래: 리뷰 증가 — 구매해야만 남으므로 위조 불가, 신뢰 최고
    "demand": 2.0,        # 수요: 검색 지수 가속도
    "efficiency": 2.0,    # 효율: 신규 영상 조회수 중앙값(제작 대비 반응)
    "supply": 1.0,        # 공급: 신규 영상 수 증가 — 후행·거품 가능성이 커 최저
}
SEASONAL_PENALTY = 2.0      # 계절 성분은 트렌드가 아니므로 감점(5-4-9⑥)
PERSISTENCE_PENALTY_Z = 0.5  # 지속성 미충족 시 감점(z 단위).
# ⚠️ 배수(×0.5)가 아니라 **뺄셈**인 이유: 점수가 음수일 때 배수를 곱하면 오히려 점수가
# 올라가 순위가 뒤집힌다(0에 가까워짐). 단위 테스트에서 실제로 잡힌 결함이라 뺄셈으로 고정한다.

# 재인 랭킹 배분(5-4-10). 영상 노출이 주, 텍스트 언급량이 보조.
RECOGNITION_WEIGHTS = {"exposure": 0.7, "mentions": 0.3}
RECENCY_HALFLIFE_DAYS = 7.0   # 기억은 최근일수록 선명 — 반감기 감쇠
CHANNEL_DIVERSITY_COEF = 0.2  # 채널 수 가중 계수


@dataclass
class VideoStat:
    """관련 영상 1편의 관측치."""
    views: int
    age_days: float
    channel_id: str = ""


@dataclass
class ProductSignals:
    """제품 1개에 대해 수집된 원시 신호. **없는 소스는 None으로 두고 0으로 채우지 않는다**
    — 0은 '측정했더니 0'이고 None은 '측정 못 함'이라 의미가 다르기 때문."""
    key: str
    name: str
    videos: list[VideoStat] = field(default_factory=list)   # 공급·효율·노출의 원천
    demand_series: list[float] | None = None                # 수요: 일별 검색 지수(오래된 것 → 최신)
    demand_series_last_year: list[float] | None = None      # 작년 동기(계절성 제거용)
    mentions_recent: int | None = None                      # 언급량: 네이버 검색 API total(최근)
    mentions_prev: int | None = None                        # 직전 동기간 언급량
    review_count: int | None = None                         # 거래: 현재 리뷰 수
    review_count_prev: int | None = None                    # 직전 스냅샷 리뷰 수
    price: float | None = None
    price_prev: float | None = None


# ------------------------------------------------------------------ 통계 유틸
def median(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def zscores(values: Sequence[float]) -> list[float]:
    """표본 내 z-score. 표준편차가 0이면(전부 같은 값) 전부 0 — 순위 정보가 없다는 뜻."""
    n = len(values)
    if n == 0:
        return []
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n
    sd = math.sqrt(var)
    if sd < 1e-12:
        return [0.0] * n
    return [(v - mu) / sd for v in values]


def growth_rate(cur: float | None, prev: float | None) -> float | None:
    """증가율. prev가 0이면 비율이 정의되지 않으므로 cur>0일 때만 1.0(신규 진입)으로 본다."""
    if cur is None or prev is None:
        return None
    if prev <= 0:
        return 1.0 if cur > 0 else 0.0
    return (cur - prev) / prev


# ------------------------------------------------------------------ 파생 지표
def exposure(videos: Iterable[VideoStat], halflife: float = RECENCY_HALFLIFE_DAYS) -> float:
    """**총 노출량** — 조회수를 최신성으로 감쇠해 합산(5-4-10).
    시청자가 그 제품을 봤을 확률은 개수가 아니라 노출 총량에 비례한다."""
    total = 0.0
    for v in videos:
        decay = 0.5 ** (max(v.age_days, 0.0) / halflife)
        total += max(v.views, 0) * decay
    return total


def channel_diversity(videos: Sequence[VideoStat]) -> float:
    """채널 다양성 배수. 같은 총 조회수라도 **여러 채널에 흩어져 있을수록 피드 도달이 넓다**.
    한 채널이 도배한 경우를 눌러주기 위해 '고유 채널 수'와 '채널당 편중'을 함께 본다."""
    if not videos:
        return 1.0
    uniq = len({v.channel_id for v in videos if v.channel_id})
    if uniq == 0:
        return 1.0
    spread = uniq / len(videos)                       # 1.0이면 전부 다른 채널
    return 1.0 + CHANNEL_DIVERSITY_COEF * math.log1p(uniq) * spread


def acceleration(series: Sequence[float] | None, window: int = 7) -> float | None:
    """**가속도(증가율의 변화)** — 5-4-9③.
    절대값이나 1차 증가율만 보면 '이미 정점을 지난 것'을 NEW로 올리는 오류가 난다.
    최근 window 평균, 직전 window 평균, 그 이전 window 평균으로 2차 차분을 낸다."""
    if not series or len(series) < window * 3:
        return None
    a = sum(series[-window:]) / window            # 최근
    b = sum(series[-2 * window:-window]) / window  # 직전
    c = sum(series[-3 * window:-2 * window]) / window
    d1, d2 = a - b, b - c
    scale = max(abs(c), 1e-9)
    return (d1 - d2) / scale


def persistence_ok(series: Sequence[float] | None, days: int = 3) -> bool:
    """지속성 게이트 — days일 연속 상승했는가(5-4-9⑦). 단발 급등(방송 1회 노출 등)을 거른다."""
    if not series or len(series) < days + 1:
        return False
    tail = series[-(days + 1):]
    return all(tail[i + 1] > tail[i] for i in range(days))


def seasonal_excess(series: Sequence[float] | None,
                    last_year: Sequence[float] | None,
                    window: int = 7) -> float:
    """계절 성분(5-4-9⑥). 작년 같은 시기에도 똑같이 올랐다면 그건 트렌드가 아니라 계절이다.
    반환값이 클수록 '계절 탓'이며 구매가치 점수에서 감점된다. 작년 데이터가 없으면 0(감점 없음)."""
    if not series or not last_year:
        return 0.0
    if len(series) < window or len(last_year) < window:
        return 0.0
    cur = sum(series[-window:]) / window
    ly = sum(last_year[-window:]) / window
    base = sum(series) / len(series)
    if base <= 1e-9:
        return 0.0
    # 작년 같은 주가 평시보다 높았던 만큼이 '계절 성분'
    return max(0.0, (ly - base) / base) if cur > base else 0.0


# ------------------------------------------------------------------ 랭킹 산출
def recognition_scores(products: Sequence[ProductSignals]) -> dict[str, float]:
    """**재인 랭킹**(5-4-10) — 시청자가 이미 봤을 확률.
    노출량과 언급량을 각각 로그 변환 후 표본 내 z-score로 합성한다(스케일이 크게 다르므로)."""
    if not products:
        return {}
    exp_raw, men_raw = [], []
    for p in products:
        exp_raw.append(math.log1p(exposure(p.videos)) * channel_diversity(p.videos))
        men_raw.append(math.log1p(max(p.mentions_recent or 0, 0)))
    has_mentions = any(p.mentions_recent is not None for p in products)
    ze, zm = zscores(exp_raw), zscores(men_raw)
    out: dict[str, float] = {}
    for i, p in enumerate(products):
        if has_mentions:
            s = RECOGNITION_WEIGHTS["exposure"] * ze[i] + RECOGNITION_WEIGHTS["mentions"] * zm[i]
        else:
            s = ze[i]  # 언급량 소스가 없으면 노출량만으로(가중치 재정규화)
        out[p.key] = round(s, 4)
    return out


def value_scores(products: Sequence[ProductSignals]) -> dict[str, float]:
    """**구매가치 랭킹**(5-4-9④) — 실제로 사도 되는가.
    축별 z-score를 가중 합성하되, **결측 축은 빼고 남은 축의 가중치 합으로 재정규화**한다."""
    if not products:
        return {}
    axes: dict[str, list[float | None]] = {
        "transaction": [growth_rate(p.review_count, p.review_count_prev) for p in products],
        "demand": [acceleration(p.demand_series) for p in products],
        # 효율 = 신규 영상 조회수 중앙값(제작 대비 반응). 평균은 이상치 1편에 흔들리므로 쓰지 않는다.
        "efficiency": [median([v.views for v in p.videos]) if p.videos else None for p in products],
        # 공급 = 최근 신규 영상 수. 절대 개수는 부정확하나(5-4-9①) 축 내 상대 비교에만 쓴다.
        "supply": [float(len(p.videos)) if p.videos else None for p in products],
    }

    z_by_axis: dict[str, list[float | None]] = {}
    for axis, vals in axes.items():
        if all(v is None for v in vals):
            z_by_axis[axis] = []          # 축 전체가 결측 → 이 축은 아예 쓰지 않는다
            continue
        # 결측은 z 계산에서 표본 평균(=0)으로 취급하되, 합성 단계에서 가중치에서 빠진다
        zs = zscores([v if v is not None else 0.0 for v in vals])
        z_by_axis[axis] = [zs[i] if vals[i] is not None else None for i in range(len(vals))]

    out: dict[str, float] = {}
    for i, p in enumerate(products):
        tx_col = z_by_axis.get("transaction") or []
        tx = tx_col[i] if tx_col and tx_col[i] is not None else None
        # 🫧 거품 클리핑: 거래 신호가 있고 그것이 **음수**(안 팔림)라면, 노출계 축(공급·효율)의
        # 양(+) 기여를 0으로 자른다. 많이 만들어지고 많이 보였는데 리뷰가 안 늘었다는 건
        # 구매가치의 근거가 아니라 **거품의 증거**이기 때문이다(5-4-9② bubble 사분면).
        # 이게 없으면 공급(1)+효율(2)이 거래(3)를 상쇄해 바이럴 제품이 심층 편으로 올라간다.
        bubble = tx is not None and tx < 0
        num, den = 0.0, 0.0
        for axis, w in VALUE_WEIGHTS.items():
            col = z_by_axis.get(axis) or []
            if not col or col[i] is None:
                continue                   # 이 제품에서 해당 축이 결측 → 가중치에서 제외
            z = float(col[i])
            if bubble and axis in ("supply", "efficiency") and z > 0:
                z = 0.0
            num += w * z
            den += w
        base = (num / den) if den > 0 else 0.0
        base -= SEASONAL_PENALTY * seasonal_excess(p.demand_series, p.demand_series_last_year) / max(sum(VALUE_WEIGHTS.values()), 1)
        if not persistence_ok(p.demand_series):
            base -= PERSISTENCE_PENALTY_Z
        out[p.key] = round(base, 4)
    return out


def quadrant(recognition: float, value: float, r_cut: float = 0.0, v_cut: float = 0.0) -> str:
    """수요×공급 4사분면(5-4-9②)을 재인/구매가치 축으로 옮긴 편성 힌트.
    - blue_ocean: 살 만한데 아직 덜 보임 → 심층 판정 1순위
    - peak: 많이 보이고 살 만도 함 → 브리핑 상단
    - bubble: 많이 보이는데 살 이유가 약함 → 하락↓ 섹션·역행 편
    - ignore: 둘 다 낮음 → 제외"""
    high_r, high_v = recognition >= r_cut, value >= v_cut
    if high_r and high_v:
        return "peak"
    if high_r and not high_v:
        return "bubble"
    if not high_r and high_v:
        return "blue_ocean"
    return "ignore"


def rank(products: Sequence[ProductSignals]) -> list[dict]:
    """두 랭킹을 한 번에 산출해 제품별로 합친다. 정렬은 호출자가 목적에 맞게 한다."""
    rec, val = recognition_scores(products), value_scores(products)
    rows = []
    for p in products:
        r, v = rec.get(p.key, 0.0), val.get(p.key, 0.0)
        rows.append({
            "key": p.key,
            "name": p.name,
            "recognition": r,
            "value": v,
            "quadrant": quadrant(r, v),
            "exposure": round(exposure(p.videos), 1),
            "videos": len(p.videos),
            "channels": len({x.channel_id for x in p.videos if x.channel_id}),
            "median_views": round(median([x.views for x in p.videos])) if p.videos else None,
            "mentions": p.mentions_recent,
            "review_growth": growth_rate(p.review_count, p.review_count_prev),
            "persistent": persistence_ok(p.demand_series),
        })
    return rows

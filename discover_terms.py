"""후보 발굴 1단계 — **통계로 반복 등장을 찾는다**(LLM보다 먼저).

문제(2026-09-07 사용자 지적): 수집 결과가 '코팅팬·김치통' 같은 **일반 품목**으로 나왔다.
프라이팬은 1년 내내 영상이 많아 **유행이 아니라 상수**다. 그리고 쿠팡 링크를 걸려면
"정확히 어느 브랜드의 어떤 제품"이어야 하는데 품목명으로는 링크도 재인도 성립하지 않는다.

원인 셋:
  1) 검색어가 일반적이라 상시 콘텐츠가 반환됐다
  2) 프롬프트가 "브랜드·모델이 아니라 품목으로"라고 **일부러 구체성을 배제**하고 있었다
  3) '여러 영상에 반복 등장하는가'를 재지 않았다

핵심 원칙: **LLM보다 통계가 먼저다.** LLM에게 먼저 물으면 그럴듯한 제품명을 지어낸다.
제목에서 n-gram을 뽑아 **여러 영상·여러 채널에 반복 등장하는 표현**만 후보로 올리고,
LLM은 그 후보를 정규화하는 역할만 맡는다. 근거(등장 횟수·예시 제목)를 함께 남겨 검증 가능하게 한다.
"""
from __future__ import annotations

import re
from collections import defaultdict

# 채널·포맷 관용어. 제품이 아니므로 후보에서 뺀다.
STOPWORDS = {
    "쇼츠", "shorts", "리뷰", "추천", "브이로그", "언박싱", "내돈내산", "협찬", "광고",
    "꿀템", "살림템", "자취템", "필수템", "아이템", "제품", "상품", "구매", "구입", "가성비",
    "top", "best", "vs", "비교", "정리", "모음", "총정리", "후기", "사용법", "꿀팁", "팁",
    "이거", "그거", "진짜", "완전", "너무", "정말", "레전드", "미쳤", "실화", "충격", "역대급",
    "요즘", "요즘에", "올해", "최신", "신상", "화제", "인기", "유행", "대박", "강추",
    "만원", "천원", "원대", "할인", "특가", "세일", "쿠팡", "다이소", "이케아", "올리브영",
    "주방", "생활", "집들이", "인테리어", "청소", "수납",   # 카테고리 일반명(단독으로는 제품 아님)
}
JOSA = re.compile(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|까지|부터|랑|이랑)$")
CLEAN = re.compile(r"[^\w가-힣ㄱ-ㅎ]+")
HANGUL = re.compile(r"[가-힣]")


def tokenize(title: str) -> list[str]:
    """제목을 토큰으로. 조사를 떼고 관용어를 버린다(형태소 분석기 없이 최소한만)."""
    out = []
    for raw in CLEAN.sub(" ", title.lower()).split():
        t = JOSA.sub("", raw)
        if len(t) < 2 or t in STOPWORDS or t.isdigit():
            continue
        out.append(t)
    return out


def ngrams(tokens: list[str], lo: int = 1, hi: int = 3) -> list[str]:
    out = []
    for n in range(lo, hi + 1):
        for i in range(len(tokens) - n + 1):
            out.append(" ".join(tokens[i:i + n]))
    return out


def candidates(videos: list[dict], min_videos: int = 3, min_channels: int = 2,
               top: int = 30) -> list[dict]:
    """제목에서 **반복 등장하는 표현**을 뽑는다.

    `videos`: [{"title": ..., "channel_id": ...}]
    - `min_videos`: 최소 몇 개 영상에 나와야 후보인가(1회 등장은 유행이 아니다)
    - `min_channels`: **서로 다른 채널** 수. 한 채널이 도배한 건 유행이 아니라 그 채널의 소재다
    """
    seen_v, seen_c, samples = defaultdict(set), defaultdict(set), defaultdict(list)
    for i, v in enumerate(videos):
        title = v.get("title") or ""
        for g in set(ngrams(tokenize(title))):
            seen_v[g].add(i)
            seen_c[g].add(v.get("channel_id") or f"?{i}")
            if len(samples[g]) < 3:
                samples[g].append(title)
    rows = []
    for term, vids in seen_v.items():
        if len(vids) < min_videos or len(seen_c[term]) < min_channels:
            continue
        if not HANGUL.search(term):          # 영문 채널명 등 노이즈 제거
            continue
        rows.append({"term": term, "videos": len(vids), "channels": len(seen_c[term]),
                     "words": len(term.split()), "samples": samples[term]})
    # 같은 뜻의 짧은 표현이 항상 이기지 않도록, 구체적(단어 수 많은) 표현에 가산점을 준다.
    # "코팅팬"보다 "눌어붙지 않는 코팅팬"이 제품 특정에 가깝기 때문.
    rows.sort(key=lambda r: (r["channels"], r["words"], r["videos"]), reverse=True)
    return dedupe(rows)[:top]


def dedupe(rows: list[dict]) -> list[dict]:
    """포함 관계 정리 — 긴 표현이 살아남으면 그 안에 포함된 짧은 표현은 뺀다."""
    out: list[dict] = []
    for r in rows:
        if any(r["term"] != k["term"] and r["term"] in k["term"] for k in out):
            continue
        out.append(r)
    return out


def evidence_block(rows: list[dict], limit: int = 25) -> str:
    """LLM에 넘길 근거 블록. **통계로 확인된 것만** 보여줘 환각의 여지를 줄인다."""
    lines = []
    for r in rows[:limit]:
        lines.append(f'- "{r["term"]}" — 영상 {r["videos"]}개 / 채널 {r["channels"]}개'
                     f' | 예: {" / ".join(s[:38] for s in r["samples"][:2])}')
    return "\n".join(lines)

"""쇼츠 제목에 **사람들이 실제로 치는 검색어**를 쓴다 — 픽담 Search Console 실측에서 가져온다.

famto 2026-10-01 승인(픽토 9/16 제안): 구글 SERP에 「비데 자가설치」 같은 검색어는 동영상 팩이
떠 있고 틱톡이 2건씩 올라와 있다. 글로는 못 먹고 영상으로만 먹는 자리다. 쇼츠 제목이 그 검색어
**그대로**이면 구글 동영상 팩과 유튜브 검색 두 군데에 동시에 붙는다.

출처: 픽토가 매일 갱신해 공개 레포에 두는 `dashboard/data/insights.json`(search_console.queries).
읽기만 한다(공유_경계). 네트워크가 막히면 조용히 None — 제목 관문(clean_title)이 그대로 간다.
"""
from __future__ import annotations

import re
import unicodedata

INSIGHTS = "https://raw.githubusercontent.com/one2k87/Picto/main/dashboard/data/insights.json"
MAX_LEN = 40          # 유튜브 제목은 100자지만 쇼츠 피드에서 잘리지 않는 건 40자 안쪽이다
NOISE = {"네", "예", "응"}


def _compact(s: str) -> str:
    return re.sub(r"[\s\-_·,./()?!]+", "", unicodedata.normalize("NFKC", s or "")).lower()


def _tokens(name: str) -> list[str]:
    """상품명에서 **품목 토큰**(2자 이상)만 — 브랜드·모델번호는 검색어와 안 맞는다."""
    out = []
    for t in re.split(r"[\s\-_·,./()]+", unicodedata.normalize("NFKC", name or "")):
        t = t.strip()
        if len(t) >= 2 and not re.fullmatch(r"[A-Za-z0-9×x]+", t):
            out.append(t)
    return out


def fetch(url: str = INSIGHTS, timeout: int = 15) -> list[dict]:
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        if r.status_code != 200:
            return []
        return list((r.json().get("search_console") or {}).get("queries") or [])
    except Exception:                                      # noqa: BLE001
        return []


def match(items: list[str], queries: list[dict]) -> str | None:
    """이번 편 상품의 품목 토큰이 **들어 있는** 검색어 중 노출이 가장 큰 것. 없으면 None."""
    best, best_imp = None, -1
    for q in queries:
        text = (q.get("query") or "").strip()
        if not text or text in NOISE or len(text) > MAX_LEN:
            continue
        cq = _compact(text)
        hit = any(_compact(t) in cq for it in items for t in _tokens(it))
        if not hit:
            continue
        imp = int(q.get("impressions") or 0) + 5 * int(q.get("clicks") or 0)
        if imp > best_imp:
            best, best_imp = text, imp
    return best


def best_for(items: list[str]) -> str | None:
    return match(items, fetch())


def title_with(query: str, title: str) -> str:
    """검색어를 제목 **앞**에 그대로 두고, 원래 제목은 뒤에 붙인다(겹치면 생략)."""
    q = query.strip().rstrip("?.!")
    t = (title or "").strip()
    if not t or _compact(q) in _compact(t):
        return q[:80]
    return f"{q}, {t}"[:80]

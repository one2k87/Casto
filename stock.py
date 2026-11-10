"""무료 실사 스톡 — Pexels 사진(상황 배경용). 2026-11-09 famto 지시(사용자 승인: 이미지 무료화).

용도는 **시청자의 상황**(겨울 침실·좁은 주방 같은 장면)뿐이다. 상품 자체를 스톡으로 보여주면
"그 물건"처럼 보이는 가짜 컷이 되므로 금지 — 상품은 지금처럼 실제 판매 사진으로만 나간다.

API(2026-11-10 공식 문서 확인):
  GET https://api.pexels.com/v1/search  · 헤더 `Authorization: <키>`(접두어 없음)
  params query·orientation(portrait)·size·locale·per_page(≤80) → photos[].src.portrait·photographer·url
  한도 200회/시간·2만회/월. 약관: Pexels 링크를 눈에 띄게 + 작가·사진 페이지 크레딧 권장.
키(PEXELS_API_KEY)가 없으면 조용히 None — 호출부는 기존 바탕으로 간다.
"""
from __future__ import annotations

import os
import re

import requests

SEARCH = "https://api.pexels.com/v1/search"


def _clean(query: str) -> str:
    q = re.sub(r"[^0-9A-Za-z ,'-]+", " ", query or "").strip()
    return re.sub(r"\s+", " ", q)[:60]


def photo(query: str, out_path: str, orientation: str = "portrait", timeout: int = 20) -> dict | None:
    """검색 1회 → 첫 사진을 받아 저장. 반환 {path, photographer, photographer_url, url} 또는 None."""
    key = os.getenv("PEXELS_API_KEY", "").strip()
    q = _clean(query)
    if not key or not q:
        return None
    try:
        r = requests.get(SEARCH, params={"query": q, "orientation": orientation, "per_page": 5},
                         headers={"Authorization": key}, timeout=timeout)
    except Exception as e:                                   # noqa: BLE001
        print(f"[stock] pexels 예외: {e}")
        return None
    if r.status_code != 200:
        print(f"[stock] pexels 실패 {r.status_code}: {r.text[:120]}")
        return None
    photos = (r.json() or {}).get("photos") or []
    if not photos:
        print(f"[stock] pexels 결과 없음: {q}")
        return None
    p = photos[0]
    src = p.get("src") or {}
    link = src.get("portrait") or src.get("large2x") or src.get("large")
    if not link:
        return None
    try:
        img = requests.get(link, timeout=timeout)
        img.raise_for_status()
    except Exception as e:                                   # noqa: BLE001
        print(f"[stock] 사진 다운로드 실패: {e}")
        return None
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(img.content)
    got = {"path": out_path, "photographer": p.get("photographer", ""),
           "photographer_url": p.get("photographer_url", ""), "url": p.get("url", "")}
    print(f"[stock] ✅ pexels 사진(무료): '{q}' — {got['photographer']}")
    return got


def credit_lines(credits: list[dict] | None) -> list[str]:
    """설명란 크레딧 — Pexels 링크 + 작가 이름 + 사진 페이지(API 약관 권장 형식)."""
    credits = [c for c in (credits or []) if c and c.get("url")]
    if not credits:
        return []
    lines = ["📷 Photos provided by Pexels (https://www.pexels.com)"]
    for c in credits:
        lines.append(f"   Photo by {c.get('photographer') or 'Pexels'} on Pexels: {c['url']}")
    return lines

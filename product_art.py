"""상품 이미지 자동 확보 — **사람 손을 거치지 않고** 카탈로그의 빈칸을 채운다.

왜 이게 필요한가(2026-09-08 실측):
  - 쿠팡 상품 페이지: 데이터센터 IP에서 **403**. 깃허브 액션에서 스크래핑 불가.
  - 쿠팡 오픈 API: 파트너스 수익 조건 미달로 발급 불가.
  - 네이버 쇼핑 검색 API: 2026-07-31 종료.
  - 픽담 글: 현재 쿠팡 링크·상품 이미지가 들어있지 않다(wp-json 실측).
  - 남의 유튜브 썸네일·릴스 캡처: 저작권 위반이라 애초에 선택지가 아니다.

→ 그래서 **자동으로 얻을 수 있는 것**만 자동으로 한다.
  ① 상품 **이름·브랜드·상품ID**: 이미 자동이다. 여러 채널의 설명란 링크가 합의로 알려준다(product_links).
  ② 상품 **이미지**: 제품명을 근거로 **AI가 형태를 재현**한다(Gemini 이미지 생성).
     실사진은 아니지만 "어떤 물건인지 모양이 보인다"는 목적은 달성하고, 차단·저작권 문제가 없다.
     실사진이 확보되면(픽담 KOKPICK 블록 또는 파트너스 수동 등록) **그쪽이 항상 우선**한다.

이미지 우선순위: 실사진(coupang_partners/pickdam) > AI 재현(ai_clay) > 클레이 콕이 폴백.
AI 재현 이미지에는 화면에 **"AI 재현 이미지"**를 표기한다 — 시청자를 속이지 않기 위해서다.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import requests

import catalog

REAL_SOURCES = ("pickdam", "coupang_partners", "maker")
AI_SOURCE = "ai_render"
MAX_PER_RUN = int(os.getenv("ART_MAX_PER_RUN", "4"))       # 비용·시간 상한
IMAGE_MODELS = [os.getenv("IMAGE_MODEL", ""), "gemini-3-pro-image-preview",
                "gemini-2.5-flash-image"]


def prompt_for(name: str, category: str = "") -> str:
    """제품 형태가 정확히 읽히는 것이 목적. 브랜드 로고·문자는 넣지 않는다(상표 문제 + 오탈자)."""
    what = name if not category or category in name else f"{name} ({category})"
    return (
        f"A single product photo of: {what}. Korean e-commerce style product shot.\n"
        "REQUIREMENTS:\n"
        "- Pure white seamless background, no floor, no props, no hands, no text anywhere.\n"
        "- The product only, centered, full body in frame, realistic proportions and "
        "materials so the shape is immediately recognizable.\n"
        "- Soft studio lighting, gentle shadow, clean and modern.\n"
        "- Do NOT draw any brand logo, brand name, model number, letters or numbers.\n"
        "- Square image."
    )


def generate(prompt: str, out_path: str, key: str = "") -> str | None:
    """Gemini 이미지 생성 → 파일 저장. 모델이 없으면 다음 후보로 내려간다."""
    key = key or os.getenv("LLM_API_KEY", "")
    if not key:
        print("[art] LLM_API_KEY 없음 — 건너뜀")
        return None
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    for model in [m for m in IMAGE_MODELS if m]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, json=body, timeout=180,
                              headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        except Exception as e:                                # noqa: BLE001
            print(f"[art] {model} 호출 실패: {e}")
            continue
        if r.status_code == 404:
            print(f"[art] {model} 없음 — 다음 모델 시도")
            continue
        if r.status_code != 200:
            print(f"[art] {model} {r.status_code}: {r.text[:160]}")
            time.sleep(3)
            continue
        for part in (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", []):
            blob = part.get("inlineData") or part.get("inline_data")
            if not blob or not blob.get("data"):
                continue
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(blob["data"]))
            print(f"[art] 생성 — {out_path} ({model})")
            return out_path
        print(f"[art] {model} 응답에 이미지가 없음 — 다음 모델 시도")
    return None


# ------------------------------------------------------------------ 카탈로그 자동 채움
def autofill(cat: dict, watchlist: dict, today: str = "") -> list[str]:
    """추적 중인 상품을 카탈로그에 **자동 등록**한다.

    발굴이 준 이름·브랜드·상품ID를 그대로 옮긴다. 브랜드는 발굴 단계에서 '추측 금지'로 뽑은
    값이라 없으면 빈 문자열이고, 그때는 카테고리명으로 안전하게 폴백한다.
    """
    touched = []
    for slug, w in (watchlist or {}).items():
        name = (w.get("name") or slug.replace("_", " ")).strip()
        if not name:
            continue
        if catalog.find(cat, name=name, product_id=w.get("product_id", "")):
            continue
        s = catalog.put(cat, name=name, brand=w.get("brand", ""),
                        category=w.get("name", name), product_id=w.get("product_id", ""),
                        price_band=w.get("price_band", ""), updated=today)
        touched.append(s)
    return touched


def fill_images(cat: dict, limit: int = MAX_PER_RUN, today: str = "") -> list[str]:
    """이미지가 없는 상품에 AI 재현 이미지를 붙인다. 실사진이 있으면 절대 덮지 않는다."""
    made = []
    for slug, e in cat.get("products", {}).items():
        if len(made) >= limit:
            break
        if catalog.image_path(e):
            continue                                  # 이미 이미지가 있다(실사진이든 AI든)
        if e.get("image_source") in REAL_SOURCES:
            continue                                  # 실사진 경로가 붙는 중이면 기다린다
        name = e.get("display") or e.get("category") or slug
        out = os.path.join(catalog.IMAGE_DIR, f"{slug}.png")
        if generate(prompt_for(name, e.get("category", "")), out):
            e["image"], e["image_source"], e["updated"] = out, AI_SOURCE, today
            made.append(slug)
    return made


def main():
    today = __import__("datetime").date.today().isoformat()
    cat = catalog.load()
    wl = {}
    if os.path.exists("data/watchlist.json"):
        with open("data/watchlist.json", encoding="utf-8") as f:
            wl = json.load(f)
    added = autofill(cat, wl, today)
    made = fill_images(cat, today=today)
    cat["updated"] = today
    catalog.save(cat)
    total = len(cat.get("products", {}))
    have = sum(1 for e in cat["products"].values() if catalog.image_path(e))
    real = sum(1 for e in cat["products"].values() if e.get("image_source") in REAL_SOURCES)
    print(f"[art] 카탈로그 {total}건 · 이미지 {have}건(실사진 {real}건) "
          f"· 이번 실행 신규등록 {len(added)} / 이미지생성 {len(made)}")
    if have < total:
        print(f"[art] 남은 {total - have}건은 다음 실행에서 채운다(1회 상한 {MAX_PER_RUN})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

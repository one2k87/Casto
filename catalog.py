"""상품 카탈로그 — **"정확히 어떤 물건인가"를 확정해서 보관하는 단 하나의 장소**.

사용자 요구(2026-09-08): "정확한 상품의 브랜드명이 나오면 그거 사진 정확하게 넣을 수 있어?
채널을 보는 사람에게 어떤 상품인지 모양 제대로 보여야 하고 정보를 제대로 전달해야 해."

발굴(product_links.py)이 알려주는 것은 **상품 ID와 사람들이 부르는 이름**까지다. 영상에 띄울
브랜드·모델·사진은 여기서 확정한다. 둘을 분리한 이유는 명확하다 —
**틀린 사진을 띄우는 것은 사진이 없는 것보다 나쁘다.** 그래서 카탈로그에 확정된 상품만
실사진·브랜드명을 노출하고, 확정 전에는 카테고리명 + 클레이 아트로 나간다(render_mode 참고).

사진이 들어오는 경로는 둘뿐이다.
  A) **픽담 글의 KOKPICK 블록**(자동) — 픽담이 자체 파트너스 계정으로 만든 이미지·링크.
     쿠팡 파트너스는 자사 상품 이미지를 파트너 홍보용으로 제공하므로 이 경로가 정당하다.
  B) **수동 등록**(반자동) — 쿠팡 파트너스 웹에서 링크·이미지를 받아 assets/products/에 넣고
     이 파일에 등록. `python catalog.py`가 무엇이 필요한지 요청서를 뽑아준다.

절대 하지 않는 것:
  ✗ 다른 크리에이터의 썸네일·릴스 캡처를 가져다 쓰는 것(저작권 침해)
  ✗ 남의 파트너스 링크를 게시용으로 재사용하는 것(수수료 탈취 + 정책 위반)
  ✗ 확인되지 않은 브랜드명을 추정해서 자막에 쓰는 것(오정보)
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

CATALOG_PATH = "data/catalog.json"
IMAGE_DIR = "assets/products"

# 우리가 이미지를 내려받아도 되는 출처. 픽담(우리 사이트)과 쿠팡 상품 이미지 CDN만 허용한다.
ALLOWED_IMAGE_HOSTS = ("pickdam.com", "coupangcdn.com", "ads-partners.coupang.com")

# 남의 제휴 코드가 붙은 링크의 지문. 게시용 링크로 들어오면 거부한다.
FOREIGN_AFFILIATE = re.compile(r"(?:link\.coupang\.com/a|coupa\.ng)/", re.I)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").strip().lower()
    s = re.sub(r"[^0-9a-z가-힣]+", "-", s).strip("-")
    return s[:60] or "unknown"


def _key(name: str) -> str:
    """이름 비교용 정규화 — 공백·기호·대소문자를 무시한다."""
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", name or "").lower())


# ------------------------------------------------------------------ 저장소
def load(path: str = CATALOG_PATH) -> dict:
    if not os.path.exists(path):
        return {"updated": "", "products": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("products", {})
    return data


def save(cat: dict, path: str = CATALOG_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
    return path


# ------------------------------------------------------------------ 조회
def find(cat: dict, name: str = "", product_id: str = "") -> dict | None:
    """상품 ID가 있으면 그것이 정답이다(고유). 없으면 이름으로 찾는다.

    이름 매칭은 완전일치 → 포함관계 순. 포함관계는 "코팅팬"으로 "테팔 코팅팬"을 찾기 위한 것이지만,
    **여러 개가 걸리면 특정 실패로 보고 None**을 준다(엉뚱한 제품 사진을 띄우지 않기 위해서다).
    """
    prods = cat.get("products", {})
    if product_id:
        for slug, p in prods.items():
            if p.get("product_id") == product_id:
                return dict(p, slug=slug)
    if not name:
        return None
    k = _key(name)
    if not k:
        return None
    exact = [(s, p) for s, p in prods.items()
             if k in (_key(p.get("display", "")), _key(p.get("model", "")),
                      _key(p.get("category", "")), _key(s))]
    if len(exact) == 1:
        return dict(exact[0][1], slug=exact[0][0])
    partial = [(s, p) for s, p in prods.items()
               if k and (k in _key(p.get("display", "")) or _key(p.get("category", "")) == k)]
    if len(partial) == 1:
        return dict(partial[0][1], slug=partial[0][0])
    return None


def image_path(entry: dict | None) -> str | None:
    """실제 파일이 있을 때만 경로를 준다. 없으면 None → 렌더러가 클레이로 폴백."""
    if not entry:
        return None
    p = entry.get("image") or ""
    return p if p and os.path.exists(p) else None


def display_name(entry: dict | None, fallback: str = "") -> str:
    """영상 자막에 쓸 이름. **확정된 것만** 브랜드·모델로 나간다."""
    if entry and entry.get("display"):
        return entry["display"]
    if entry and entry.get("brand") and entry.get("model"):
        return f"{entry['brand']} {entry['model']}"
    return fallback


def render_mode(entry: dict | None) -> str:
    """이 상품을 어떻게 그릴지 한 단어로 답한다.

    exact  : 브랜드·모델 확정 + 실사진 보유 → 실제 상품 사진을 띄운다
    named  : 브랜드·모델은 확정, 사진 없음 → 이름만 정확히 쓰고 클레이 아트
    generic: 아무것도 확정 안 됨 → 카테고리명 + 클레이 아트 (현재 기본값)
    """
    if not entry:
        return "generic"
    named = bool(entry.get("display") or (entry.get("brand") and entry.get("model")))
    if named and image_path(entry):
        return "exact"
    return "named" if named else "generic"


# ------------------------------------------------------------------ 등록
def put(cat: dict, *, name: str, brand: str = "", model: str = "", category: str = "",
        product_id: str = "", image: str = "", image_source: str = "", coupang_url: str = "",
        price_band: str = "", updated: str = "") -> str:
    """카탈로그에 한 건 등록/갱신하고 slug를 돌려준다.

    게시용 링크는 **우리 링크만** 받는다. 남의 제휴 코드가 붙은 URL은 조용히 버리고
    상품 ID만 남긴다(그게 우리가 그 링크에서 취할 유일한 정보다).
    """
    slug = slugify(brand and model and f"{brand} {model}" or name)
    prev = cat.setdefault("products", {}).get(slug, {})
    if coupang_url and FOREIGN_AFFILIATE.search(coupang_url):
        coupang_url = ""          # 남의 추적 코드 — 게시에 쓰지 않는다
    entry = {
        "display": (f"{brand} {model}".strip() if brand and model else name).strip(),
        "brand": brand or prev.get("brand", ""),
        "model": model or prev.get("model", ""),
        "category": category or prev.get("category", "") or name,
        "product_id": product_id or prev.get("product_id", ""),
        "image": image or prev.get("image", ""),
        "image_source": image_source or prev.get("image_source", ""),
        "coupang_url": coupang_url or prev.get("coupang_url", ""),
        "price_band": price_band or prev.get("price_band", ""),
        "updated": updated or prev.get("updated", ""),
    }
    cat["products"][slug] = entry
    return slug


# ------------------------------------------------------------------ 픽담 구조화 블록
KOKPICK_BLOCK = re.compile(r"<!--\s*KOKPICK\s*(.*?)\s*KOKPICK\s*-->", re.S | re.I)


def parse_kokpick_block(html_text: str) -> dict | None:
    """픽담 글 본문의 `<!--KOKPICK {...} KOKPICK-->` 블록을 읽는다(브리프 6-C).

    이 블록이 오면 **완전 자동**이다 — 픽담이 자기 파트너스 계정으로 확정한 브랜드·모델·
    공식 이미지·자체 링크가 그대로 들어오므로 사람이 손댈 일이 없다.
    """
    m = KOKPICK_BLOCK.search(html_text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def adopt_block(cat: dict, block: dict, updated: str = "") -> str | None:
    """KOKPICK 블록 → 카탈로그 등록. 이름조차 없으면 등록하지 않는다."""
    if not block:
        return None
    p = block.get("product")
    p = p if isinstance(p, dict) else {"name": p} if isinstance(p, str) else {}
    name = (p.get("name") or block.get("name") or "").strip()
    brand = (p.get("brand") or block.get("brand") or "").strip()
    model = (p.get("model") or block.get("model") or "").strip()
    if not (name or (brand and model)):
        return None
    return put(cat, name=name or f"{brand} {model}", brand=brand, model=model,
               category=(p.get("category") or block.get("category") or "").strip(),
               product_id=str(p.get("product_id") or block.get("product_id") or ""),
               image=block.get("image_local", ""),
               image_source="pickdam" if (p.get("image_url") or block.get("image_url")) else "",
               coupang_url=(block.get("coupang_url") or p.get("coupang_url") or "").strip(),
               updated=updated)


def block_image_url(block: dict) -> str:
    """블록이 준 이미지 URL 중 **허용 출처만** 통과시킨다."""
    p = block.get("product") if isinstance(block.get("product"), dict) else {}
    url = (block.get("image_url") or p.get("image_url") or "").strip()
    if not url.lower().startswith("https://"):
        return ""
    host = url.split("/")[2].lower()
    return url if any(host == h or host.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS) else ""


def cache_image(url: str, slug: str, session=None, dir_: str = IMAGE_DIR) -> str | None:
    """허용 출처 이미지를 로컬에 캐시한다. 실패해도 파이프라인은 계속(클레이 폴백)."""
    if not url:
        return None
    import requests
    os.makedirs(dir_, exist_ok=True)
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    out = os.path.join(dir_, f"{slug}{ext}")
    try:
        r = (session or requests).get(url, timeout=20)
        r.raise_for_status()
        with open(out, "wb") as f:
            f.write(r.content)
        return out
    except Exception as e:                                    # noqa: BLE001
        print("[catalog] 이미지 캐시 실패(무시):", e)
        return None


# ------------------------------------------------------------------ 요청서
def needs(cat: dict, watchlist: dict) -> list[dict]:
    """지금 추적 중인 상품 중 **아직 사진·브랜드가 확정 안 된 것**을 뽑는다."""
    rows = []
    for slug, w in (watchlist or {}).items():
        name = w.get("name") or slug.replace("_", " ")
        e = find(cat, name=name, product_id=w.get("product_id", ""))
        mode = render_mode(e)
        if mode == "exact":
            continue
        rows.append({"name": name, "mode": mode, "product_id": w.get("product_id", ""),
                     "brand": (e or {}).get("brand", "") or w.get("brand", ""),
                     "evidence": w.get("evidence", "")})
    return rows


def request_sheet(rows: list[dict]) -> str:
    """사람이 쿠팡 파트너스에서 채워 올 목록. 한 줄씩 그대로 처리하면 된다."""
    if not rows:
        return "# 콕픽 상품 이미지 요청서\n\n필요한 항목 없음 — 추적 중인 상품 전부 사진·브랜드 확정됨.\n"
    out = ["# 콕픽 상품 이미지 요청서", "",
           "쿠팡 파트너스 → 상품 검색 → **내 링크 생성** 화면에서 (1) 상품 이미지 저장 (2) 내 링크 복사.",
           f"이미지는 `{IMAGE_DIR}/` 에 넣고, 아래 표를 `{CATALOG_PATH}`에 등록한다.",
           "남의 링크·남의 썸네일은 절대 쓰지 않는다(수수료 탈취·저작권).", "",
           "| 상품 | 상태 | 상품 ID | 확인할 것 |", "|---|---|---|---|"]
    label = {"named": "이름만 확정(사진 없음)", "generic": "미확정"}
    for r in rows:
        out.append(f'| {r["name"]} | {label.get(r["mode"], r["mode"])} | {r["product_id"] or "-"} '
                   f'| 브랜드·모델명 / 공식 상품 이미지 / 내 파트너스 링크 |')
    out += ["", "등록 예시 (`data/catalog.json` products 항목):", "```json",
            '"테팔-티타늄-언리미티드-28cm": {',
            '  "display": "테팔 티타늄 언리미티드 28cm",',
            '  "brand": "테팔", "model": "티타늄 언리미티드 28cm", "category": "코팅팬",',
            '  "product_id": "coupang:1234567",',
            '  "image": "assets/products/테팔-티타늄-언리미티드-28cm.jpg",',
            '  "image_source": "coupang_partners",',
            '  "coupang_url": "https://(내 파트너스 링크)"',
            "}", "```"]
    return "\n".join(out)


def main():
    cat = load()
    wl = {}
    if os.path.exists("data/watchlist.json"):
        with open("data/watchlist.json", encoding="utf-8") as f:
            wl = json.load(f)
    rows = needs(cat, wl)
    sheet = request_sheet(rows)
    os.makedirs("out", exist_ok=True)
    with open("out/이미지_요청서.md", "w", encoding="utf-8") as f:
        f.write(sheet)
    print(sheet)
    print(f"\n[catalog] 등록 {len(cat.get('products', {}))}건 · 사진 필요 {len(rows)}건 "
          f"→ out/이미지_요청서.md")


if __name__ == "__main__":
    main()

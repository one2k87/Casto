"""「콕픽 링크 투입」 아티팩트와 레포를 잇는다 — 사람은 붙여넣기만, 반영은 코드가.

아티팩트: https://claude.ai/artifact/B8wXdJBAtLnd4EwcUiGYGZ (db: `queue/<id>` · `links/<id>`)

왜 이 파일이 있나(2026-10-06): 쿠팡 파트너스 사이트는 자동화에서 차단돼 링크는 사람만 만들 수
있다. 그런데 대시보드 📋 붙여넣기는 폰에 GitHub 토큰을 넣어야 했고, 10/1~10/6 링크 0건이었다.
아티팩트는 로그인만 돼 있으면 되니 붙여넣는 손이 가장 짧다. 반영은 캐스토 세션이 「시작/반영」때
`ArtifactData`로 읽어 이 파일로 레포에 쓴다.

    python link_intake.py queue  > out/link_queue.json   # 링크 없는 항목 → 아티팩트에 올릴 시드
    python link_intake.py apply  <links_dir>              # 아티팩트에서 받은 links/*.json → 대장 반영
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import unicodedata

import catalog

ARTIFACT = "https://claude.ai/artifact/B8wXdJBAtLnd4EwcUiGYGZ"
PARTNER = re.compile(r"^https?://(link\.coupang\.com/a/[A-Za-z0-9]+|coupa\.ng/[A-Za-z0-9]+)(\?.*)?$", re.I)
BAND = {"저가": "low", "중가": "mid", "고가": "high"}

# 사용자가 1차로 넣을 6종(famto 10/6) — 큐 맨 위. 대장에 없는 핫이슈 품목은 여기서 정의한다.
TOP = [
    {"id": "c-kkultem", "product": "쿠팡 꿀템 (차트용 간편 링크)", "query": "쿠팡 꿀템", "kind": "간편",
     "note": "검색 결과 페이지 간편 링크", "band": ""},
    {"slug": "레이저가이드가위"},
    {"slug": "얼음틀-얼음보관통"},
    {"slug": "씨밀렉스-라이스키퍼-쌀통-10kg"},
    {"id": "c-scrubdaddy", "product": "스크럽대디", "query": "스크럽대디 수세미", "kind": "상품", "band": "low",
     "note": "사진 없음 — 링크 후 캡처 필요"},
    {"id": "c-heatpad", "product": "전기장판 (1~3만)", "query": "전기장판 1인용", "kind": "상품", "band": "low",
     "note": "시즌(10~11월) · 사진 없음 — 링크 후 캡처 필요"},
]
# 같은 물건의 옛 일반 항목(사진 없음) — 브랜드 확정본이 따로 있으므로 큐에서 뺀다.
# 브랜드 확정본은 price_band가 비어 있다 — 옛 일반 항목의 가격대와 품목 상식으로 채운다(표시용).
BAND_HINT = {"쌀통": "mid", "세탁기": "mid", "무드등": "low", "정리대": "mid", "식기세척기": "high",
             "회전냄비": "high", "도마": "low", "신발장": "mid", "분리기": "low", "수화기": "low",
             "방지가드": "low", "스프레이": "low", "트레이": "low"}
SUPERSEDED = {"쌀통-쌀보관", "미니세탁기", "무드등", "그릇정리대", "싱크대-식기세척기", "자동회전냄비",
              "접이식-플러스도마", "이케아-트로네스-신발장"}


def _id(slug: str) -> str:
    """아티팩트 문서 id는 ASCII만 — 한글 슬러그는 해시로."""
    import hashlib
    return "c-" + hashlib.md5(slug.encode()).hexdigest()[:10]


def _band_hint(name: str) -> str:
    for k, v in BAND_HINT.items():
        if k in name:
            return v
    return ""


def _load_plan() -> dict:
    try:
        with open("data/next_plan.json", encoding="utf-8") as f:
            return {it.get("slug") or it.get("product"): it for it in json.load(f).get("items", [])}
    except Exception:                                      # noqa: BLE001
        return {}


def build_queue(cat: dict | None = None) -> list[dict]:
    """링크 없는 항목 전부. 순서: famto 6종 → 사진 있는 대장(차트 5종 먼저) → 사진 없는 대장."""
    cat = cat or catalog.load()
    prods = cat.get("products", {})
    plan = _load_plan()
    chart5 = ["에그크래커", "늘어나는-밀폐용기", "레이저가이드가위", "레트로-수화기", "손끼임-방지가드"]
    out, seen = [], set()

    def row(slug: str | None, spec: dict | None = None) -> dict | None:
        spec = spec or {}
        if slug:
            e = prods.get(slug)
            if not e or e.get("coupang_url") or slug in seen:
                return None
            seen.add(slug)
            p = plan.get(slug, {})
            return {"id": _id(slug), "slug": slug, "product": e.get("display") or slug,
                    "query": e.get("display") or e.get("category") or slug,
                    "date": p.get("date", ""), "slot": p.get("slot", ""),
                    "band": BAND.get(e.get("price_band", ""), "") or _band_hint(e.get("display", "")),
                    "kind": "상품",
                    "app": "C", "channel": "kokpicktube", "photo": bool(e.get("image")),
                    "note": "" if e.get("image") else "사진 없음 — 링크만으로는 영상 불가(캡처 필요)"}
        if spec["id"] in seen:
            return None
        seen.add(spec["id"])
        return {"id": spec["id"], "slug": "", "product": spec["product"], "query": spec["query"],
                "date": "", "slot": "", "band": spec.get("band", ""), "kind": spec.get("kind", "상품"),
                "app": "C", "channel": "kokpicktube", "photo": False, "note": spec.get("note", "")}

    for t in TOP:
        r = row(t.get("slug"), t if "id" in t else None)
        if r:
            out.append(r)
    for s in chart5:
        r = row(s)
        if r:
            out.append(r)
    for s, e in prods.items():
        if e.get("image") and s not in SUPERSEDED:
            r = row(s)
            if r:
                out.append(r)
    for s, e in prods.items():
        if not e.get("image") and s not in SUPERSEDED:
            r = row(s)
            if r:
                out.append(r)
    for i, r in enumerate(out, 1):
        r["order"] = i
    return out


def _compact(s: str) -> str:
    return re.sub(r"[\s\-_·,./()|]+", "", unicodedata.normalize("NFKC", s or "")).lower()


def apply_links(docs: list[dict], cat: dict | None = None, today: str | None = None,
                fetch_images: bool = True) -> dict:
    """아티팩트 `links/*` 중 pending을 대장에 쓴다. 돌려주는 값: {applied: [id…], skipped: {id: 이유}}.

    규칙: 파트너스 링크 형식만(남의 추적 코드 차단은 catalog.register가 한 번 더 본다),
    가격은 100원~5천만원. 대장에 없는 품목(스크럽대디 등)은 **대장에 새로 등록**한다 — 사진은 없으니
    영상은 못 만들지만 링크·가격은 보존된다(캡처가 들어오면 바로 쓸 수 있게).
    """
    cat = cat or catalog.load()
    prods = cat.setdefault("products", {})
    today = today or dt.date.today().isoformat()
    by_id = {_id(s): s for s in prods}
    applied, skipped = [], {}
    for d in docs:
        did = d.get("_id") or d.get("id")
        if (d.get("status") or "pending") == "applied":
            continue
        url = (d.get("url") or "").strip()
        if not PARTNER.match(url):
            skipped[did] = "파트너스 링크 형식 아님"
            continue
        price = d.get("price")
        try:
            price = int(price) if price not in (None, "", 0) else None
        except (TypeError, ValueError):
            price = None
        if price is not None and not (100 <= price <= 50_000_000):
            price = None
        slug = by_id.get(did)
        if not slug:
            # 대장 밖 품목 — 이름으로 한 번 더 찾고, 없으면 새로 등록(사진 없음).
            name = (d.get("product") or "").strip()
            for s, e in prods.items():
                if _compact(e.get("display", "")) == _compact(name):
                    slug = s
                    break
            if not slug and name:
                slug = catalog.register(cat, name, coupang_url=url, price=price, updated=today) \
                    if hasattr(catalog, "register") else None
                if not slug:
                    slug = catalog.slugify(name)
                    prods[slug] = {"display": name, "brand": "", "model": "", "category": name,
                                   "product_id": "", "image": "", "image_source": "",
                                   "coupang_url": url, "price_band": "", "price": price, "updated": today}
        if not slug:
            skipped[did] = "대장에서 품목을 찾지 못함"
            continue
        e = prods[slug]
        e["coupang_url"] = url
        if price is not None:
            e["price"] = price
        # 파트너스 「링크 생성 → 이미지+텍스트」가 준 **쿠팡 제공 이미지**(ads-partners/coupangcdn)만
        # 받는다. 타인 후기·캡처 이미지는 가이드 금지 항목이고, 다른 호스트는 block_image_url이 버린다.
        img = catalog.block_image_url({"image_url": (d.get("image") or "").strip()})
        if img and not e.get("image") and fetch_images:
            local = catalog.cache_image(img, slug)
            if local:
                e["image"], e["image_source"] = local, "coupang_partners"
        e["updated"] = today
        applied.append(did)
    return {"applied": applied, "skipped": skipped}


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "queue"
    if cmd == "queue":
        q = build_queue()
        print(json.dumps(q, ensure_ascii=False, indent=1))
        print(f"[intake] 큐 {len(q)}건 (사진 있음 {sum(1 for r in q if r['photo'])})", file=sys.stderr)
    elif cmd == "apply":
        d = sys.argv[2]
        docs = []
        for p in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            doc["_id"] = os.path.splitext(os.path.basename(p))[0]
            docs.append(doc)
        cat = catalog.load()
        res = apply_links(docs, cat)
        if res["applied"]:
            catalog.save(cat)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        raise SystemExit("usage: link_intake.py queue | apply <dir>")


if __name__ == "__main__":
    main()

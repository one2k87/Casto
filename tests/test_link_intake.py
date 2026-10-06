"""링크 투입 — 아티팩트에서 받은 링크를 대장에 쓰는 관문. 남의 링크·엉뚱한 가격이 들어오면 안 된다."""
import link_intake


def _cat():
    return {"products": {
        "에그크래커": {"display": "에그크래커", "category": "에그크래커", "image": "a.jpg", "coupang_url": "", "price": None, "price_band": "저가"},
        "레트로-수화기": {"display": "레트로 수화기", "category": "수화기", "image": "b.jpg", "coupang_url": "", "price": None},
        "무드등": {"display": "무드등", "category": "무드등", "image": "", "coupang_url": ""},
    }}


def test_큐는_링크_없는_것만_famto_6종부터(monkeypatch):
    monkeypatch.setattr(link_intake, "_load_plan", lambda: {})
    cat = _cat()
    cat["products"]["에그크래커"]["coupang_url"] = "https://link.coupang.com/a/x"
    q = link_intake.build_queue(cat)
    names = [r["product"] for r in q]
    assert "에그크래커" not in names                       # 링크 있으면 안 올린다
    assert names[0].startswith("쿠팡 꿀템") and "스크럽대디" in names
    assert "무드등" not in names                           # 브랜드 확정본이 따로 있는 옛 일반 항목
    assert [r["order"] for r in q] == list(range(1, len(q) + 1))
    assert all(r["id"].isascii() for r in q)              # 아티팩트 문서 id는 ASCII


def test_반영은_파트너스_링크만_받는다():
    cat = _cat()
    eid = link_intake._id("에그크래커")
    docs = [{"_id": eid, "url": "https://www.coupang.com/vp/products/123", "price": 8900},
            {"_id": link_intake._id("레트로-수화기"), "url": "https://link.coupang.com/a/ABC", "price": "25,900"}]
    res = link_intake.apply_links(docs, cat, today="2026-10-06")
    assert eid in res["skipped"] and cat["products"]["에그크래커"]["coupang_url"] == ""
    assert res["applied"] == [link_intake._id("레트로-수화기")]
    assert cat["products"]["레트로-수화기"]["coupang_url"] == "https://link.coupang.com/a/ABC"
    assert cat["products"]["레트로-수화기"]["price"] is None    # "25,900"은 숫자가 아니다 — 버린다


def test_대장에_없는_품목은_새로_등록된다():
    cat = _cat()
    docs = [{"_id": "c-scrubdaddy", "product": "스크럽대디", "url": "https://coupa.ng/cZZZ", "price": 12900}]
    res = link_intake.apply_links(docs, cat, today="2026-10-06")
    assert res["applied"] == ["c-scrubdaddy"]
    e = next(v for v in cat["products"].values() if v["display"] == "스크럽대디")
    assert e["coupang_url"] == "https://coupa.ng/cZZZ" and e["price"] == 12900 and not e.get("image")


def test_이미_반영된_문서는_건너뛴다():
    cat = _cat()
    docs = [{"_id": link_intake._id("에그크래커"), "url": "https://link.coupang.com/a/A", "status": "applied"}]
    assert link_intake.apply_links(docs, cat)["applied"] == []


def test_쿠팡_제공_이미지만_캐시한다(monkeypatch):
    """파트너스 배너 이미지(ads-partners/coupangcdn)는 홍보용 제공물. 다른 호스트는 버린다."""
    cat = _cat()
    cat["products"]["레트로-수화기"]["image"] = ""            # 사진이 없던 상품에만 들어간다
    calls = []
    monkeypatch.setattr(link_intake.catalog, "cache_image", lambda url, slug: calls.append(url) or f"assets/products/{slug}.jpg")
    docs = [{"_id": link_intake._id("레트로-수화기"), "url": "https://link.coupang.com/a/A",
             "image": "https://ads-partners.coupang.com/image1/x.jpg"},
            {"_id": link_intake._id("에그크래커"), "url": "https://link.coupang.com/a/B",
             "image": "https://evil.example.com/x.jpg"}]
    link_intake.apply_links(docs, cat, today="2026-10-06")
    assert calls == ["https://ads-partners.coupang.com/image1/x.jpg"]
    assert cat["products"]["레트로-수화기"]["image_source"] == "coupang_partners"
    assert cat["products"]["에그크래커"]["image"] == "a.jpg"       # 기존 캡처 유지, 외부 이미지 무시

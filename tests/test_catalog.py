"""카탈로그 테스트 — **틀린 상품 정보를 내보내지 않는다**는 규칙을 코드로 고정한다."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import catalog  # noqa: E402


def test_남의_제휴링크는_게시용으로_저장되지_않는다():
    """발굴 과정에서 본 남의 링크가 카탈로그에 들어오면 수수료가 그쪽으로 간다."""
    cat = {"products": {}}
    slug = catalog.put(cat, name="코팅팬", brand="테팔", model="티타늄 28cm",
                       coupang_url="https://link.coupang.com/a/ABCDE")
    assert cat["products"][slug]["coupang_url"] == ""
    slug2 = catalog.put(cat, name="코팅팬2", coupang_url="https://pickdam.com/go/abc")
    assert cat["products"][slug2]["coupang_url"] == "https://pickdam.com/go/abc"


def test_이름이_여러개_걸리면_특정_실패로_본다():
    """엉뚱한 제품 사진을 띄우느니 못 찾은 것으로 처리한다."""
    cat = {"products": {}}
    catalog.put(cat, name="코팅팬", brand="테팔", model="A 28cm", category="코팅팬")
    catalog.put(cat, name="코팅팬", brand="락앤락", model="B 28cm", category="코팅팬")
    assert catalog.find(cat, name="테팔 A 28cm") is not None
    # 카테고리만으로는 둘 중 하나를 고를 수 없다
    assert catalog.find(cat, name="코팅팬") is None


def test_상품ID가_이름보다_우선한다():
    cat = {"products": {}}
    catalog.put(cat, name="코팅팬", brand="테팔", model="A 28cm", product_id="coupang:111")
    e = catalog.find(cat, name="전혀 다른 이름", product_id="coupang:111")
    assert e and e["brand"] == "테팔"


def test_render_mode는_사진이_있어야_exact(tmp_path):
    cat = {"products": {}}
    slug = catalog.put(cat, name="코팅팬", brand="테팔", model="A 28cm")
    e = dict(cat["products"][slug])
    assert catalog.render_mode(e) == "named"          # 이름만 확정 → 클레이
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    e["image"] = str(img)
    assert catalog.render_mode(e) == "named"          # 출처 불명 이미지는 쓰지 않는다
    e["image_source"] = "coupang_partners"
    assert catalog.render_mode(e) == "exact"          # 실사진
    assert catalog.render_mode(None) == "generic"


def test_확정_안된_상품은_브랜드명을_만들어내지_않는다():
    assert catalog.display_name(None, "코팅팬") == "코팅팬"
    assert catalog.display_name({"category": "코팅팬"}, "코팅팬") == "코팅팬"


def test_KOKPICK_블록_파싱과_등록():
    body = ('<p>본문</p><!--KOKPICK\n'
            '{"product": {"name": "코팅팬", "brand": "테팔", "model": "티타늄 28cm",'
            ' "product_id": "coupang:222"},'
            ' "image_url": "https://thumbnail7.coupangcdn.com/x.jpg",'
            ' "coupang_url": "https://pickdam.com/go/pan"}\n'
            'KOKPICK--><p>이어지는 본문</p>')
    block = catalog.parse_kokpick_block(body)
    assert block and block["product"]["brand"] == "테팔"
    cat = {"products": {}}
    slug = catalog.adopt_block(cat, block)
    e = cat["products"][slug]
    assert e["display"] == "테팔 티타늄 28cm"
    assert e["product_id"] == "coupang:222"
    assert e["coupang_url"] == "https://pickdam.com/go/pan"


def test_블록이_없거나_깨졌으면_None():
    assert catalog.parse_kokpick_block("<p>그냥 글</p>") is None
    assert catalog.parse_kokpick_block("<!--KOKPICK {깨진 json KOKPICK-->") is None


def test_이미지_출처_화이트리스트():
    """남의 사이트·유튜브 썸네일을 내려받지 않는다(저작권)."""
    ok = {"image_url": "https://thumbnail9.coupangcdn.com/a.jpg"}
    assert catalog.block_image_url(ok)
    assert catalog.block_image_url({"image_url": "https://i.ytimg.com/vi/x/hq.jpg"}) == ""
    assert catalog.block_image_url({"image_url": "http://pickdam.com/a.jpg"}) == ""   # https만
    assert catalog.block_image_url({"image_url": "https://evil-coupangcdn.com.attacker.io/a.jpg"}) == ""


def test_요청서는_확정된_상품을_다시_묻지_않는다(tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    cat = {"products": {}}
    catalog.put(cat, name="코팅팬", brand="테팔", model="A 28cm", image=str(img),
                image_source="coupang_partners")
    wl = {"코팅팬": {"name": "테팔 A 28cm"}, "가습기": {"name": "가습기"}}
    rows = catalog.needs(cat, wl)
    assert [r["name"] for r in rows] == ["가습기"]
    assert "가습기" in catalog.request_sheet(rows)


def test_AI_재현_이미지는_절대_노출하지_않는다(tmp_path):
    """가상 재현은 시청자가 즉시 알아챈다 — 사진이 없으면 아무것도 넣지 않는다."""
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    e = {"display": "테팔 A 28cm", "image": str(img), "image_source": "ai_render"}
    assert catalog.render_mode(e) == "named"       # exact 아님 → 제품 이미지 미사용


def test_캡처는_실사진으로_인정된다(tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"x")
    e = {"display": "테팔 A 28cm", "image": str(img), "image_source": "capture"}
    assert catalog.render_mode(e) == "exact"

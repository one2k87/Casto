"""캡처 반입 테스트 — 파일 이름이 곧 제품 이름이다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import capture_import  # noqa: E402
import catalog  # noqa: E402


def test_파일명에서_브랜드와_모델을_나눈다():
    assert capture_import.split_name("락앤락 접이식 밀폐용기 800ml") == ("락앤락", "접이식 밀폐용기 800ml")
    assert capture_import.split_name("쌀통") == ("", "쌀통")   # 브랜드를 지어내지 않는다


def test_반입하면_실사진으로_등록되고_파일이_옮겨진다(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "IMAGE_DIR", str(tmp_path / "products"))
    inbox = tmp_path / "products" / "캡처_넣는곳"
    inbox.mkdir(parents=True)
    src = inbox / "락앤락 접이식 밀폐용기 800ml.png"
    src.write_bytes(b"x")
    cat = {"products": {}}
    slug = capture_import.import_one(cat, str(src))
    e = cat["products"][slug]
    assert e["brand"] == "락앤락"
    assert e["image_source"] == "capture"
    assert catalog.render_mode(e) == "exact"
    assert not src.exists() and os.path.exists(e["image"])


def test_번호만_적어도_번호표의_제품으로_들어간다(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "IMAGE_DIR", str(tmp_path / "products"))
    q = {"next": 1, "items": {}}
    n = catalog.number_for(q, "락앤락 접이식 밀폐용기 800ml")
    assert n == 1
    inbox = tmp_path / "products" / "캡처_넣는곳"
    inbox.mkdir(parents=True)
    src = inbox / f"{n}.png"
    src.write_bytes(b"x")
    cat = {"products": {}}
    slug = capture_import.import_one(cat, str(src), q=q)
    assert cat["products"][slug]["display"] == "락앤락 접이식 밀폐용기 800ml"
    assert q["items"]["1"]["done"] is True


def test_번호는_재사용되지_않는다():
    """어제 3번을 보고 캡처한 게 오늘 다른 제품의 3번이 되면 엉뚱한 사진이 붙는다."""
    q = {"next": 1, "items": {}}
    a = catalog.number_for(q, "A 제품")
    catalog.mark_done(q, a)
    b = catalog.number_for(q, "B 제품")
    assert b != a and b == a + 1
    assert catalog.number_for(q, "A 제품") == a      # 기존 번호는 유지된다


def test_번호_뒤에_이름을_적으면_이름이_우선한다():
    q = {"next": 1, "items": {}}
    catalog.number_for(q, "가습기")
    assert capture_import.read_stem("1 락앤락 밀폐용기 800ml", q) == ("락앤락 밀폐용기 800ml", 1)
    assert capture_import.read_stem("1", q) == ("가습기", 1)
    assert capture_import.read_stem("3번", q)[1] == 3


def test_번호표에_브랜드가_확정돼_있으면_그_이름으로_등록된다():
    """영상 자막에 '쌀통'이 아니라 '씨밀렉스 라이스키퍼 쌀통 10kg'이 나가야 한다."""
    q = {"next": 1, "items": {}}
    n = catalog.number_for(q, "쌀통 쌀보관")
    catalog.set_details(q, n, brand="씨밀렉스", model="라이스키퍼 쌀통 10kg",
                        search="씨밀렉스 라이스키퍼 쌀통", confidence="높음")
    assert capture_import.read_stem(str(n), q) == ("씨밀렉스 라이스키퍼 쌀통 10kg", n)


def test_보류_항목은_번호표_본문에_섞이지_않는다(tmp_path):
    q = {"next": 1, "items": {}}
    catalog.number_for(q, "지금 유행")
    n2 = catalog.number_for(q, "옛날 아이템")
    catalog.set_details(q, n2, hold=True)
    path = tmp_path / "list.md"
    catalog.write_list(q, str(path))
    body, hold = path.read_text(encoding="utf-8").split("## 보류")
    assert "지금 유행" in body and "옛날 아이템" not in body
    assert "옛날 아이템" in hold


# ── 가격 반입 (2026-09-15) ──────────────────────────────────────────────────
# 쿠팡 오픈 API 미발급 + 네이버 쇼핑 검색 API 종료(2026-07-31)로 가격을 자동으로
# 가져올 경로가 전부 닫혔다. 카드의 「정확한 상품명 + 가격」과 대체재의 「더 싸다」가
# 둘 다 이 값에 걸려 있어, 사람이 캡처할 때 파일명으로 같이 올린다.
def test_가격은_골뱅이로_명시해야_읽는다():
    import capture_import as C
    assert C.read_price("3 락앤락 밀폐용기 @32900") == ("3 락앤락 밀폐용기", 32900)
    assert C.read_price("7 @12,900") == ("7", 12900)


def test_모델명_숫자를_가격으로_읽지_않는다():
    """끝자리 숫자를 가격으로 보면 800ml·10kg·MNDW-110이 전부 가격이 된다."""
    import capture_import as C
    for stem in ("3 락앤락 밀폐용기 800ml", "5 미닉스 식기세척기 MNDW-110",
                 "9 씨밀렉스 라이스키퍼 쌀통 10kg", "12"):
        assert C.read_price(stem) == (stem, None), stem


def test_자릿수가_터무니없으면_가격을_버린다():
    """0원·9억원짜리 주방템은 오타다. 틀린 가격은 없느니만 못하다."""
    import capture_import as C
    assert C.read_price("3 도마 @9")[1] is None
    assert C.read_price("3 도마 @999999999")[1] is None


def test_가격이_카탈로그에_남는다(tmp_path):
    import catalog
    cat = {}
    slug = catalog.put(cat, name="락앤락 밀폐용기", brand="락앤락", model="밀폐용기", price=32900)
    assert cat["products"][slug]["price"] == 32900
    # 가격 없이 다시 등록해도 이미 넣은 값이 지워지지 않는다
    catalog.put(cat, name="락앤락 밀폐용기", brand="락앤락", model="밀폐용기")
    assert cat["products"][slug]["price"] == 32900

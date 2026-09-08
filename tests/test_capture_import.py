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

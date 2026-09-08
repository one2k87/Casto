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

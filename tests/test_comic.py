"""인과 만화가 **상품을 그리려 하면 터지는지** 확인한다.

2026-09-08에 AI로 상품을 재현하는 모듈(product_art)을 통째로 삭제했다.
만화를 도입하면서 같은 구멍이 다시 열릴 수 있다 — LLM이 원인 문장에 상품명을
그대로 넣으면("피스타치오 분태기가 많이 팔린다") 그 문장이 그림 프롬프트가 되고,
모델은 그 물건을 그린다. 실물과 다른 그림이 화면에 나가는 것이 정확히 금지 대상이다.
"""
import pytest

import comic


def test_상품명이_프롬프트에_들어가면_터진다():
    with pytest.raises(comic.ProductDrawAttempt):
        comic._prompt("a clay scene of 밀폐용기 on a shelf", "밀폐용기")


def test_상품_지시어도_막는다():
    for bad in ("a clay render of the product", "상품이 매대에 놓여 있다"):
        with pytest.raises(comic.ProductDrawAttempt):
            comic._prompt(bad, "밀폐용기")


def test_상황만_묘사하면_통과한다():
    p = comic._prompt("a crowded bakery shelf, people reaching for chocolate bars", "밀폐용기")
    assert "clay" in p and "밀폐용기" not in p


def test_scrub가_상품명을_미리_지운다():
    out = comic.scrub("밀폐용기 수요가 폭증했다", "밀폐용기")
    assert "밀폐용기" not in out and "이것" in out


def test_생성이_막히면_None을_돌려준다(monkeypatch):
    """터뜨리되 **발행은 멈추지 않는다** — 호출부가 폴백 카드로 간다."""
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    assert comic.generate("a shelf of 밀폐용기", "밀폐용기", "/tmp/x.png") is None


def test_키가_없으면_조용히_폴백한다(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert comic.generate("a busy street", "밀폐용기", "/tmp/x.png") is None


def test_폴백_카드는_파일을_만든다(tmp_path):
    brand = {"cream": [251, 246, 236], "mint": [176, 224, 210], "sage": [47, 93, 78]}
    p = comic.fallback("두쫀쿠가 유행", brand, str(tmp_path / "f.png"))
    assert (tmp_path / "f.png").exists() and p.endswith("f.png")


def test_panels는_상품명이_섞여도_두_컷을_돌려준다(tmp_path, monkeypatch):
    """LLM이 규칙을 어겨도 영상은 나가야 한다(컷은 폴백으로 대체된다)."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    brand = {"cream": [251, 246, 236], "mint": [176, 224, 210], "sage": [47, 93, 78]}
    got = comic.panels({"name": "밀폐용기",
                        "cause": "밀폐용기가 방송에 나옴",
                        "cause_scene": "a 밀폐용기 on tv",
                        "effect": "품절 대란",
                        "effect_scene": "empty store shelves"},
                       brand, out_dir=str(tmp_path))
    assert len(got) == 2
    assert all(not g["generated"] for g in got)   # 키가 없으니 전부 폴백

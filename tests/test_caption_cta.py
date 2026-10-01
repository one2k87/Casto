"""설명란 CTA — 수익이 들어오는 유일한 문. 2026-10-01 실측으로 잡은 구멍 두 개를 막는다.

① 발행 4편의 설명란에 쿠팡 링크가 0줄이었고, 있어도 접힌 설명란의 첫 줄은 제목이었다.
② 픽담 줄이 **무관한 글**(최신 1편)로 가고 있었다 — 흰자분리기 영상 → 음식물처리기 필터 글.
"""
import json

import make_short
import roundup

ITEMS = ["계란 흰자 분리기", "레트로 수화기", "손끼임 방지가드"]


def _c():
    return json.load(open("casto.json", encoding="utf-8"))


def _v():
    return {"key": "오늘의 콕", "emoji": "👆", "caption": "콕", "card": "콕", "voice": "콕"}


def _s():
    return {"title": "제목", "winner": 0, "items": [{"cause": "", "use": ""} for _ in ITEMS],
            "hashtags": []}


def test_설명란_첫_줄은_승자_링크다():
    entries = [{"coupang_url": "https://link.coupang.com/a/WIN"}, {}, {}]
    cap = roundup.build_caption(_s(), _v(), ITEMS, entries, _c(), 24)
    first = cap.splitlines()[0]
    assert first.startswith("🛒") and "link.coupang.com/a/WIN" in first and ITEMS[0] in first


def test_링크가_없으면_첫_줄은_제목이다():
    """'링크 준비 중' 같은 가짜 줄을 만들지 않는다."""
    cap = roundup.build_caption(_s(), _v(), ITEMS, [{}, {}, {}], _c(), 24)
    assert cap.splitlines()[0] == "📦 제목"
    assert "준비 중" not in cap and "🛒" not in cap


def test_픽담_줄은_상품이_맞는_글일_때만():
    s, v, c = _s(), _v(), _c()
    wrong = {"link": "https://pickdam.com/food-waste-filter/", "title": "음식물처리기 필터"}
    cap = roundup.build_caption(s, v, ITEMS, [{}, {}, {}], c, 24, post=wrong)
    assert "pickdam.com" not in cap
    right = {"link": "https://pickdam.com/egg/", "title": "계란 흰자 분리기 비교", "matched": ITEMS[0]}
    cap = roundup.build_caption(s, v, ITEMS, [{}, {}, {}], c, 24, post=right)
    assert "pickdam.com/egg/" in cap and f"📄 {ITEMS[0]}" in cap


def test_글_매칭은_상품명이_들어_있을_때만():
    """KOKPICK product나 제목에 상품명이 포함돼야 같은 물건. 띄어쓰기·기호는 무시."""
    post = {"title": "음식물처리기 탈취필터 3개월마다", "block": {"product": "음식물처리기 탈취 필터"}}
    assert make_short.post_matches(post, ITEMS) is None
    post = {"title": "침실 무드등, 수면등 vs 수유등", "block": {}}
    assert make_short.post_matches(post, ["무아스 마그넷 무선 LED 무드등 MLL37", "에그크래커"]) is None
    # 대장 표시명은 브랜드·모델까지 길다 — 카테고리명(별칭)으로도 같은 물건을 알아본다
    assert make_short.post_matches(post, ["무아스 마그넷 무선 LED 무드등 MLL37", "에그크래커"],
                                   {"무아스 마그넷 무선 LED 무드등 MLL37": ["무드등"]}) \
        == "무아스 마그넷 무선 LED 무드등 MLL37"
    assert make_short.post_matches(post, ["무드등", "에그크래커"]) == "무드등"
    post = {"title": "1인 가구 미니세탁기 3kg vs 5kg", "block": {"product": "미니세탁기"}}
    assert make_short.post_matches(post, ["미니 세탁기"]) == "미니 세탁기"

"""사람이 쓴 글에서 원인을 뽑는다 — 빈도가 답을 주게 하는 것이 요점."""
import reasons as R

DOCS = [
    "두바이 초콜릿 만들려고 피스타치오 분태 샀어요 요즘 품절이라 힘드네요",
    "피스타치오 가격이 두바이초콜릿 유행 이후로 두 배가 됐대요",
    "두바이초콜릿 홈베이킹 재료 정리 - 카다이프랑 피스타치오 스프레드",
    "요즘 디저트 카페마다 두바이 초콜릿이라 재료값이 난리",
    "이거 그냥 맛있어서 샀어요 추천합니다",
]


def test_바깥_원인이_1위로_올라온다():
    got = R.common_terms(DOCS, exclude=("피스타치오 분태기", "피스타치오"))
    assert got and got[0][0] == "두바이초콜릿"


def test_서술어는_원인으로_세지_않는다():
    """'샀어요'가 원인 2위에 올라와 있었다 — 말투지 계기가 아니다."""
    words = [w for w, _ in R.common_terms(DOCS, exclude=("피스타치오",))]
    assert not any(R._verbish(w) for w in words), words


def test_짧은_말은_긴_말로_합친다():
    """'두바이'와 '두바이초콜릿'이 따로 잡히면 둘 다 약해 보인다."""
    got = dict(R.common_terms(DOCS, exclude=("피스타치오",)))
    assert "두바이" not in got or "두바이초콜릿" not in got


def test_한_글에서_도배해도_한_번으로_센다():
    """한 사람이 반복한 건 근거가 아니다 — 여러 사람이 각자 말해야 근거다."""
    got = dict(R.common_terms(["폭염 폭염 폭염 폭염 폭염", "다른 이야기"]))
    assert got.get("폭염") is None          # min_docs=2 미달


def test_상품명_자체는_원인에서_뺀다():
    got = dict(R.common_terms(["밀폐용기 좋아요", "밀폐용기 샀다"], exclude=("밀폐용기",)))
    assert "밀폐용기" not in got


def test_수집_실패시_지어내지_말라고_적는다():
    assert any("지어내지" in l for l in R.lines({"quotes": [], "sources": {}, "terms": []}))


def test_인용은_요약하지_않고_그대로_넘긴다():
    g = {"sources": {"뉴스": 1}, "terms": [("폭염", 3)],
         "quotes": [{"src": "뉴스", "text": "역대급 폭염에 얼음 수요 폭증", "date": "20260901"}]}
    joined = "\n".join(R.lines(g))
    assert "역대급 폭염에 얼음 수요 폭증" in joined and "폭염(3)" in joined

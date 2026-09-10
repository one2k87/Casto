"""인과 근거 — 숫자를 잘못 읽으면 영상이 거짓말을 한다."""
import evidence as E


def test_식는_중인_것을_상승이라고_말하지_않는다():
    """처음엔 0.3배(하락)를 두고도 '상승 시작 1일 전'이라 적었다.
    식어가는 물건을 '지금 뜬다'고 소개할 뻔한 버그다."""
    up = [1] * 30 + [8] * 7
    down = [8] * 30 + [1] * 7
    assert E.spike(up)["trend"] == "up"
    assert E.spike(down)["trend"] == "down"
    assert "days_ago" not in E.spike(down)      # 하락엔 '상승 시작'이 없다


def test_표본이_적으면_추세를_말하지_않는다():
    assert E.spike([5, 6, 7]) is None
    assert E.spike([]) is None
    assert E.spike(None) is None


def test_변화가_없으면_flat():
    assert E.spike([10] * 40)["trend"] == "flat"


def test_상승_배수와_시작시점():
    s = [2] * 40 + [10] * 7
    got = E.spike(s)
    assert got["trend"] == "up" and got["ratio"] >= 3
    assert got["days_ago"] == 7


def test_동어반복_인과를_반려한다():
    for bad in ("인기가 많아서", "요즘 유행이라", "편리해서", "가성비가 좋아서"):
        assert E.too_vague(bad)


def test_계기가_구체적이면_통과():
    for good in ("두쫀쿠가 8월부터 유행", "7월 방송에 나온 뒤", "올여름 최장 폭염"):
        assert E.too_vague(good) == "", good


def test_시점도_숫자도_없으면_반려():
    assert E.too_vague("자취 가구가 늘어남")


def test_데이터가_없으면_지어내지_말라고_적는다():
    b = E.brief("존재하지않는상품xyz", snaps=[])
    assert b["has_data"] is False
    assert any("지어내지" in l for l in b["lines"])


def test_brief는_관측한_숫자만_담는다():
    snap = [{"date": "2026-09-09", "products": [{
        "name": "테스트템", "keyword": "테스트템",
        "videos": [{"views": 1000, "age_days": 1}, {"views": 2000, "age_days": 2}],
        "mentions": 50, "demand": [1] * 30 + [9] * 7, "evidence": "제목에 언급"}]}]
    b = E.brief("테스트템", snaps=snap)
    joined = " ".join(b["lines"])
    assert "3,000회" in joined and "50건" in joined
    assert b["spike"]["trend"] == "up"


def test_같이_뜬_품목에서_자기_자신은_빠진다():
    snap = [{"products": [
        {"name": "가", "videos": [{"views": 10}]},
        {"name": "나", "videos": [{"views": 99}]}]}]
    got = E.co_risers(["가"], snaps=snap)
    assert [x["name"] for x in got] == ["나"]


def test_해외가_먼저면_그렇게_말한다():
    snap = [{"products": [{"name": "테스트템", "overseas": {
        "verdict": "overseas_first", "lead_days": 150,
        "en": {"earliest": "2026-04-01", "count": 7, "titles": ["viral kitchen gadget"]},
        "ko": {"earliest": "2026-08-29", "count": 3}}}]}]
    lines = " ".join(E.brief("테스트템", snaps=snap)["lines"])
    assert "5.0개월" in lines and "2026-04-01" in lines


def test_한국이_먼저면_해외에서_난리났다고_쓰지_말라고_한다():
    """'해외에서 난리난'은 197만짜리 제목 틀이라 유혹이 크다 — 사실이 아닐 때 막아야 한다."""
    snap = [{"products": [{"name": "테스트템",
                           "overseas": {"verdict": "korea_first", "lead_days": -60}}]}]
    lines = " ".join(E.brief("테스트템", snaps=snap)["lines"])
    assert "한국이 먼저" in lines and "쓰면 안 된다" in lines


def test_영어권에_없으면_국내_유행이라고_적는다():
    snap = [{"products": [{"name": "테스트템", "overseas": {"verdict": "korea_only"}}]}]
    assert "국내에서 생긴 유행" in " ".join(E.brief("테스트템", snaps=snap)["lines"])

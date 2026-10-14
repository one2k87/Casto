"""「콕이네 집」 대본 — 판정은 근거로만, 정직 검사는 코드로, 폴백은 거짓이 없다."""
import clay_script as cs
import render_clay as rc

P = {"slug": "계란-흰자-분리기", "display": "계란 흰자 분리기", "category": "흰자 분리기",
     "coupang_url": "https://link.coupang.com/a/x", "image": "assets/products/계란-흰자-분리기.jpg"}


def test_상황은_상품명으로_고른다():
    assert cs.pick_situation(P)["id"] == 1
    assert cs.pick_situation({"display": "미니 세탁기", "category": "세탁기"})["id"] == 5
    s = cs.pick_situation({"display": "정체불명", "category": ""})
    assert s in cs.SITUATIONS                      # 억지로 맞추지 않고 무작위


def test_판정은_근거_개수로():
    assert cs.decide({})[0] == "글쎄" and "데이터 부족" in cs.decide({})[1]
    assert cs.decide({"search_trend": "up", "blog_verdict": "positive"})[0] == "콕"
    assert cs.decide({"search_trend": "down"})[0] == "패스"
    assert cs.decide({"mentions": 900, "search_trend": "up"})[0] == "콕"
    stamp, reason = cs.decide({"mentions": 900})
    assert stamp == "글쎄" and "900" in reason


def test_정직_검사_금지어_가격_숫자():
    sit = cs.SITUATIONS[0]
    good = cs.fallback(P, sit, "글쎄", "데이터 부족")
    assert cs.check(good, P, {}) == []
    bad = cs.fallback(P, sit, "글쎄", "데이터 부족")
    bad["cuts"][3]["line"] = "써 보니 최고야"
    bad["cuts"][5]["line"] = "계란 흰자 분리기, 9,900원. 판정은—"
    bad["reason"] = "검색 3배 상승"
    errs = cs.check(bad, P, {})
    assert any("금지어" in e for e in errs)
    assert any("원화" in e for e in errs)
    assert any("출처 없는 숫자" in e for e in errs)
    # 가격을 알면 원화는 허용, 근거 숫자는 evidence 것이면 허용
    bad["cuts"][3]["line"] = "어, 되네?"
    bad["reason"] = "언급 900건"
    assert cs.check(bad, {**P, "price": 9900}, {"mentions": 900}) == []


def test_폴백_대본은_8컷이고_LLM_없이도_만들어진다():
    s = cs.build(P, {}, use_llm=False)
    assert s["fallback"] is True and len(s["cuts"]) == 8
    assert s["cuts"][5]["who"] == "guide" and s["cuts"][5]["line"].endswith("판정은—")
    assert s["stamp"] == "글쎄" and s["product"] == "계란 흰자 분리기"


def test_이름_치환은_중괄호를_남기지_않는다():
    s = cs.fallback(P, cs.SITUATIONS[0], "콕", "검색 상승")
    s["cuts"][0]["line"] = "{husband}! 또 터졌어"
    out = cs.substitute_names(s, None)
    assert out["cuts"][0]["line"] == "남편! 또 터졌어"
    out = cs.substitute_names(s, {"husband": "라비"})
    assert out["cuts"][0]["line"] == "라비! 또 터졌어"
    assert "{" not in "".join(c["line"] for c in out["cuts"])


def test_컷_길이_계획은_25초_캡을_지킨다():
    cuts = [{"n": n} for n in range(1, 9)]
    d = rc.plan_durations(cuts, {n: 1.0 for n in range(1, 9)})
    assert sum(d.values()) <= rc.HARD_CAP and all(d[n] >= 1.0 for n in d)
    # 대사가 길어 넘치면 컷 2 축소 → 컷 5 제거, 6·7·8은 유지
    d = rc.plan_durations(cuts, {n: 4.5 for n in range(1, 9)})
    assert sum(d.values()) <= rc.HARD_CAP + 0.05
    assert d[5] == 0.0 and all(d[n] >= 0.75 * rc.MIN_CUT[n] for n in (6, 7, 8))   # 6·7·8은 빠지지 않는다


def test_캡션은_고지_첫줄_링크_둘째줄_구독은_캡션에():
    s = cs.fallback(P, cs.SITUATIONS[0], "패스", "검색 하락")
    s["alt_url"] = "https://link.coupang.com/a/alt"
    cap = rc.caption(s, P, "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 수수료를 제공받습니다.")
    ln = cap.splitlines()
    assert ln[0].startswith("이 포스팅은") and ln[1].startswith("🛒")
    assert "🔁 대신 이거" in cap and "구독은 여기서" in cap
    assert cap.count("#") <= 5

"""정체성 실험(3개월) 추적 — 배정은 회전하고, 판정은 중앙값이고, 빈칸은 빈칸으로 남는다."""
import json

import experiments as ex

B1 = ex.BLOCKS[0]


def _ep(vid, date, value, views7=None, views24=None, views72=None, ret=None, fmt="clay"):
    r = {"kind": "episode", "video_id": vid, "date": date, "title": vid, "format": fmt,
         "block": 1, "variables": {**ex.DEFAULTS, "narrative": value}}
    if views7 is not None:
        r["views_7d"] = views7
        r["grade"] = ex.grade(views7)
    if views24 is not None:
        r["views_24h"] = views24
    if views72 is not None:
        r["views_72h"] = views72
        r["growth_72h"] = round(views72 / views24 - 1, 3)
    if ret is not None:
        r["retention"] = ret
    return r


def test_블록_변수는_회전_배정되고_나머지는_기본값이다():
    rows = []
    seen = []
    for i in range(6):
        v = ex.assign("2026-10-14", rows)
        seen.append(v["narrative"])
        rows.append(_ep(f"v{i}", "2026-10-14", v["narrative"]))
    # 1라운드 A B C, 2라운드 B C A — 같은 값이 같은 자리에 반복되지 않는다
    assert seen == ["A_사고해결", "B_판정", "C_비교", "B_판정", "C_비교", "A_사고해결"]
    assert ex.assign("2026-10-14", rows)["hook"] == ex.DEFAULTS["hook"]


def test_파일럿과_실험_전_편은_회전과_집계에서_빠진다():
    rows = [_ep("p", "2026-10-13", "A_사고해결", fmt="pilot")]
    assert ex.assign("2026-10-13", rows)["narrative"] == "A_사고해결"     # 파일럿은 안 센다
    rows.append(_ep("a", "2026-10-13", "A_사고해결", views7=100))
    res = ex.review(rows, B1)
    assert res["values"]["A_사고해결"]["n"] == 1


def test_승자는_중앙값_20퍼센트_차이_표본_3편부터():
    rows = [_ep("a1", "2026-10-13", "A_사고해결", 5000, ret=55), _ep("a2", "2026-10-14", "A_사고해결", 6000, ret=52),
            _ep("b1", "2026-10-15", "B_판정", 4000, ret=40), _ep("b2", "2026-10-16", "B_판정", 3000, ret=38),
            _ep("c1", "2026-10-17", "C_비교", 2000, ret=35), _ep("c2", "2026-10-18", "C_비교", 2500, ret=33)]
    res = ex.review(rows, B1)
    assert res["winner"] is None and "표본 부족" in res["reason"]
    rows += [_ep("a3", "2026-10-19", "A_사고해결", 90000, ret=50), _ep("b3", "2026-10-20", "B_판정", 3500, ret=41),
             _ep("c3", "2026-10-21", "C_비교", 2200, ret=36)]
    res = ex.review(rows, B1)
    assert res["winner"] == "A_사고해결"
    # 1편이 9만을 찍어도 중앙값이라 6000 — 평균이었다면 3만이 됐을 것
    assert res["values"]["A_사고해결"]["views_7d"] == 6000


def test_무승부면_승자를_내지_않는다():
    rows = []
    for i, (v, ret) in enumerate([("A_사고해결", 50), ("B_판정", 45), ("C_비교", 20)] * 3):
        rows.append(_ep(f"v{i}", f"2026-10-{13 + i:02d}", v, 3000, ret=ret))
    res = ex.review(rows, B1)
    assert res["winner"] is None and "무승부" in res["reason"]


def test_지속률이_비면_판정하지_않고_비었다고_말한다():
    rows = []
    for i, v in enumerate(["A_사고해결", "B_판정", "C_비교"] * 3):
        rows.append(_ep(f"v{i}", f"2026-10-{13 + i:02d}", v, 3000 + i))
    res = ex.review(rows, B1)
    assert res["winner"] is None and "사람 입력 필요" in res["reason"]
    assert res["missing_manual"] == 9
    assert "미입력" in ex.render_review(res, B1)


def test_조기_탈락은_3편_연속_C_와_낮은_지속률():
    rows = [_ep(f"c{i}", f"2026-10-{13 + i:02d}", "C_비교", 500, ret=20) for i in range(3)]
    assert ex.review(rows, B1)["early_drop"] == ["C_비교"]
    rows = [_ep(f"c{i}", f"2026-10-{13 + i:02d}", "C_비교", 500, ret=45) for i in range(3)]
    assert ex.review(rows, B1)["early_drop"] == []


def test_스냅샷에서_24h_72h_7d_와_테스트_배치_통과를_읽는다(tmp_path):
    rows = [_ep(f"p{i}", "2026-10-01", "A_사고해결") for i in range(3)] + [_ep("x", "2026-10-13", "B_판정")]
    snaps = {}
    for i in range(3):
        snaps.setdefault("2026-10-02", {})[f"p{i}"] = {"views": 1000}
    snaps["2026-10-14"] = {"x": {"views": 2000}}
    snaps["2026-10-17"] = {"x": {"views": 3000}}           # +3일 자리가 없어 +4일 허용
    snaps["2026-10-20"] = {"x": {"views": 12000, "likes": 30}}
    ex.enrich(rows, snaps)
    x = rows[-1]
    assert (x["views_24h"], x["views_72h"], x["views_7d"]) == (2000, 3000, 12000)
    assert x["growth_72h"] == 0.5 and x["pushed"] is True
    assert x["grade"] == "A" and x["passed_24h"] is True


def test_예측은_틀린_기록을_남기려는_단순식이다():
    assert ex.predict({"search_volume": 0}) == "B"
    assert ex.predict({"search_volume": 5000, "hot": True}) == "S"
    assert ex.predict({"price_band": "고가"}) == "C"
    rows = [_ep("a", "2026-10-13", "B_판정", 20000), _ep("b", "2026-10-14", "B_판정", 15000)]
    ctx = {"date": "2026-10-15", "variables": {"narrative": "B_판정"}}
    assert ex.predict(ctx, rows) == "A"


def test_등록과_수동_입력(tmp_path):
    rows = []
    r = ex.register(rows, video_id="v1", date="2026-10-14", title="t", predicted="B")
    assert r["block"] == 1 and r["variables"]["narrative"] == "A_사고해결"
    r["views_7d"] = 4000
    ex.set_manual(rows, "v1", retention=52.0, clicks=20)
    assert rows[0]["ctr"] == 0.5
    # 같은 video_id 재등록은 갱신
    ex.register(rows, video_id="v1", date="2026-10-14", title="t2")
    assert len(rows) == 1 and rows[0]["title"] == "t2"
    p = tmp_path / "e.json"
    ex.save(rows, str(p))
    assert json.load(open(p, encoding="utf-8"))[0]["video_id"] == "v1"

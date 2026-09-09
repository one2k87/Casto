"""학습 루프 테스트 — **표본이 적을 때 결론 내지 않는 것**이 이 모듈의 핵심 계약이다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import learn  # noqa: E402


def snap(videos):
    return [{"date": "2026-09-20", "videos": videos}]


def vid(title, views, likes=0, comments=0, vid_="x"):
    return {"id": vid_, "title": title, "views": views, "likes": likes, "comments": comments}


def test_제목으로_발행과_성과를_잇는다():
    log = [{"title": "쌀통 이거 하나면 끝", "product": "쌀통"}]
    rows = learn.join(log, snap([vid("쌀통 이거 하나면 끝", 1200, 30, 5)]))
    assert rows[0]["matched"] and rows[0]["views"] == 1200
    assert rows[0]["engagement"] == round(35 / 1200, 4)


def test_제목이_달라지면_조인_실패를_숨기지_않는다():
    """업로드할 때 제목을 바꾸면 학습이 조용히 멈춘다 — 그걸 드러내야 한다."""
    rows = learn.join([{"title": "원래 제목"}], snap([vid("완전 다른 제목", 100)]))
    assert rows[0]["matched"] is False
    a = learn.analyze(rows)
    assert a["matched"] == 0 and a["videos"] == 1


def test_표본이_최소치_미만이면_축_판단을_하지_않는다():
    log = [{"title": f"t{i}", "price_band": "고가"} for i in range(2)]
    rows = learn.join(log, snap([vid(f"t{i}", 100) for i in range(2)]))
    a = learn.analyze(rows)
    assert a["axes"] == {} and a["notes"]


def test_충분히_모이면_축별_lift를_낸다():
    log = ([{"title": f"h{i}", "price_band": "저가"} for i in range(3)]
           + [{"title": f"l{i}", "price_band": "고가"} for i in range(3)])
    vids = ([vid(f"h{i}", 1000, 50) for i in range(3)]
            + [vid(f"l{i}", 100, 1) for i in range(3)])
    a = learn.analyze(learn.join(log, snap(vids)))
    band = a["axes"]["price_band"]
    assert list(band)[0] == "저가"                  # 잘 된 쪽이 앞에 온다
    assert band["저가"]["lift"] > band["고가"]["lift"]
    assert any("가격대" in h for h in learn.hints(a))


def test_차이가_미미하면_힌트를_만들지_않는다():
    """근거 없는 조언은 대본을 흔들기만 한다."""
    log = ([{"title": f"a{i}", "verdict": "buy"} for i in range(3)]
           + [{"title": f"b{i}", "verdict": "cond"} for i in range(3)])
    vids = [vid(f"a{i}", 500, 10) for i in range(3)] + [vid(f"b{i}", 505, 10) for i in range(3)]
    assert learn.hints(learn.analyze(learn.join(log, snap(vids)))) == []


def test_조회수만_높고_참여가_없으면_점수가_깎인다():
    """조회수만 보면 낚시가 이긴다 — 참여율을 함께 본다."""
    log = [{"title": f"t{i}", "verdict": "buy"} for i in range(3)]
    rows = learn.join(log, snap([vid("t0", 3000, 0, 0), vid("t1", 900, 90), vid("t2", 900, 90)]))
    a = learn.analyze(rows)
    assert a["best"][0]["title"] != "t0"

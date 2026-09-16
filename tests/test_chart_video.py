"""주간 차트 편 — 카드 규격과 장면 순서. 틀린 화면은 채널 신뢰를 깎는다."""
import os

import pytest
from PIL import Image

import cards
import chart
import make_chart


def _entry(rank=1, **kw):
    e = {"rank": rank, "key": f"k{rank}", "name": f"상품{rank}", "display": f"상품{rank}",
         "image": "assets/koki/koki_idle.png", "price": None, "coupang_url": "",
         "status": None, "tag": {}, "headline": "6개 채널 · 합계 1,234회",
         "delta": {"move": "new", "text": "NEW", "prev_rank": None}, "signals": {}}
    e.update(kw)
    return e


def _chart(n=5):
    return {"week": "2026-W38", "source_days": 9,
            "entries": [_entry(rank=i + 1) for i in range(n)]}


# ── 장면 순서 ──────────────────────────────────────────────────────────────
def test_순위는_거꾸로_센다():
    """1위를 먼저 주면 그 뒤를 볼 이유가 사라진다. 카운트다운이 완주 장치다."""
    sc = make_chart.scenes_for(_chart(), {"items": []})
    ranks = [s["entry"]["rank"] for s in sc if s["kind"] == "item"]
    assert ranks == [5, 5, 4, 4, 3, 3, 2, 2, 1, 1]      # 한 칸당 2컷
    assert sc[0]["kind"] == "cover" and sc[-1]["kind"] == "outro"


def test_대본이_비어도_장면은_만들어진다():
    """LLM이 죽어도 발행이 멈추면 안 된다 — headline이 내레이션을 대신한다."""
    sc = make_chart.scenes_for(_chart(3), {})
    assert all(s.get("voice") for s in sc)


def test_칸이_모자라면_차트를_내지_않는다():
    """2칸짜리 순위표는 순위가 아니라 비교다. 빈칸을 그림으로 메우지 않는다."""
    with pytest.raises(SystemExit):
        make_chart.build_script(_chart(chart.MIN_N - 1), {}, llm=lambda *a, **k: {})


# ── 설명란 ────────────────────────────────────────────────────────────────
def test_가격과_링크는_있을_때만_쓴다():
    """없는 가격을 '미정'으로 적으면 화면의 글자가 사실이 아니게 된다."""
    ch = _chart(3)
    ch["entries"][0].update(price=3900, coupang_url="https://link.coupang.com/a/AAA")
    cap = make_chart.build_caption(ch, {"items": []}, {"disclosure": {"coupang": "c", "ai": "a"}}, 58)
    assert "3,900원" in cap and "link.coupang.com" in cap
    assert "미정" not in cap and "None" not in cap and "확인 중" not in cap
    # 가격 없는 칸은 줄 자체가 없다
    assert cap.count("원\n") == 1


def test_상태_태그가_없으면_붙이지_않는다():
    ch = _chart(3)
    ch["entries"][1].update(status="hot", tag={"label": "예감"})
    cap = make_chart.build_caption(ch, {"items": []}, {"disclosure": {"coupang": "", "ai": ""}}, 58)
    assert "· 예감" in cap
    assert "1. 상품1\n" in cap            # 태그 없는 칸은 이름만


# ── 카드 ──────────────────────────────────────────────────────────────────
def test_실사진이_없으면_카드를_만들지_않는다(tmp_path):
    """절대 규칙 — 제품을 가상으로 재현하지 않는다. 그 즉시 시청자가 돌아선다."""
    with pytest.raises(SystemExit):
        cards.card_rank(_entry(image=""), {}, str(tmp_path / "a.png"))
    with pytest.raises(SystemExit):
        cards.card_rank(_entry(image="assets/없는파일.jpg"), {}, str(tmp_path / "b.png"))


def test_카드는_세로_쇼츠_규격(tmp_path):
    p = cards.card_rank(_entry(), {}, str(tmp_path / "c.png"), idx=0, total=5, week="2026-W38")
    assert Image.open(p).size == (1080, 1920)
    assert os.path.getsize(p) > 0


def test_가격이_있으면_카드가_달라진다(tmp_path):
    """빈 줄을 두는 것과 가격을 쓰는 것이 같은 그림이면 가격이 안 나온 것이다."""
    a = cards.card_rank(_entry(), {}, str(tmp_path / "a.png"))
    b = cards.card_rank(_entry(price=3900), {}, str(tmp_path / "b.png"))
    assert list(Image.open(a).getdata()) != list(Image.open(b).getdata())


def test_변동_표기():
    assert cards.delta_text({"move": "new", "text": "NEW"}) == "NEW"
    assert cards.delta_text({"move": "up", "text": "▲3"}) == "▲3"
    assert cards.delta_text(None) == ""


# ── 편성 연결 ──────────────────────────────────────────────────────────────
def test_슬롯_출력은_한_줄이다():
    """워크플로가 이걸로 분기한다. 사람이 읽는 요약을 grep하면 문구가 바뀔 때
    조용히 틀리고, 조용히 틀린 편성은 며칠간 아무도 모른다(2026-09-11 사고)."""
    import subprocess
    out = subprocess.run(["python3", "schedule.py", "--slot", "2026-09-20"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "chart"
    off = subprocess.run(["python3", "schedule.py", "--slot", "2026-09-16"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert off == "none"


# ── 24초 재단 이후 (2026-09-16) ────────────────────────────────────────────
def test_한_칸이_두_컷으로_쪼개진다():
    """잘 되는 쇼츠는 2~4초에 한 번 화면이 바뀐다. 한 칸을 5초 세워두면
    그 정지가 이탈 지점이 된다."""
    sc = make_chart.scenes_for(_chart(5), {"items": []})
    items = [s for s in sc if s["kind"] == "item"]
    assert len(items) == 10
    assert [s["beat"] for s in items[:2]] == ["name", "why"]
    # 진행 점은 상품 수를 센다 — 컷 수를 세면 점이 10개가 된다
    assert {s["idx"] for s in items} == {0, 1, 2, 3, 4}


def test_내레이션은_두_컷에_나눠_실린다():
    """길이는 그대로 두고 컷만 늘린다. 문장을 복제하면 영상이 두 배가 된다."""
    ch = _chart(3)
    script = {"items": [{"key": e["key"], "voice": "앞 문장. 뒤 문장."} for e in ch["entries"]]}
    sc = [s for s in make_chart.scenes_for(ch, script) if s["kind"] == "item"]
    assert sc[0]["voice"] == "앞 문장."
    assert sc[1]["voice"] == "뒤 문장."


def test_첫_컷에는_판정을_안_그린다(tmp_path):
    """읽을 게 하나면 0.5초에 읽힌다. 첫 컷에 다 넣으면 쪼갠 의미가 없다."""
    a = cards.card_rank(_entry(), {}, str(tmp_path / "n.png"), beat="name",
                        reason="이유", verdict="판정")
    b = cards.card_rank(_entry(), {}, str(tmp_path / "w.png"), beat="why",
                        reason="이유", verdict="판정")
    assert list(Image.open(a).getdata()) != list(Image.open(b).getdata())

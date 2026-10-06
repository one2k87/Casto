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
    """첫 컷은 순위·상품명만, 둘째 컷은 상한 안의 한 문장. 문장을 복제하면 영상이 두 배가 된다."""
    ch = _chart(3)
    script = {"items": [{"key": e["key"], "voice": "앞 문장 하나. 뒤 문장."} for e in ch["entries"]]}
    sc = [s for s in make_chart.scenes_for(ch, script) if s["kind"] == "item"]
    assert sc[0]["voice"] == "3위, 상품3."
    assert sc[1]["voice"] == "앞 문장 하나."
    assert "앞 문장" not in sc[0]["voice"]


# ── 60초 사고 이후 (2026-10-01) ────────────────────────────────────────────
def test_차트는_33초를_넘기지_않는다():
    """9/27 차트 편이 60초로 나갔다(Studio 역산). LLM이 45자씩 써도 추정 길이가 상한 안이어야 한다."""
    ch = _chart(5)
    long = "이건 정말 요즘 어디서나 보이는 제품이라서 안 사면 손해라는 말이 나올 정도입니다 정말로요. 두 번째 문장도 깁니다."
    script = {"hook_voice": long, "outro_voice": long,
              "items": [{"key": e["key"], "voice": long, "reason": long} for e in ch["entries"]]}
    sc = make_chart.scenes_for(ch, script)
    assert make_chart.est_seconds(sc) <= make_chart.CHART_MAX_SEC
    assert all(s["voice"] for s in sc)                     # TTS는 빈 문장을 못 읽는다
    assert all(len(s["voice"]) <= 30 for s in sc)


def test_긴_문장은_자르지_않고_대체한다():
    """잘린 문장은 들리는 순간 기계 티가 난다 — 상한을 넘으면 통째로 대체문으로 간다."""
    assert make_chart.fit("짧다.", 10, "대체") == "짧다."
    assert make_chart.fit("이 문장은 분명히 상한보다 길다.", 10, "대체") == "대체"
    assert make_chart.fit("", 10, "대체") == "대체"
    sc = make_chart.scenes_for(_chart(3), {"hook_voice": "이 문장은 열네 자를 훌쩍 넘기는 훅입니다."})
    assert sc[0]["voice"] == make_chart.HOOK_DEFAULT


def test_설명란은_고지_뒤_1위_링크다():
    """접힌 설명란에서 보이는 건 첫 줄뿐이다. 링크가 없으면 첫 줄은 제목이다(가짜 줄 금지)."""
    c = {"disclosure": {"coupang": "c", "ai": "a"}}
    ch = _chart(3)
    cap = make_chart.build_caption(ch, {"title": "제목", "items": []}, c, 24)
    assert cap.splitlines()[0] == "c" and cap.splitlines()[2] == "📊 제목"      # 고지 → (빈 줄) → 제목
    ch["entries"][0]["coupang_url"] = "https://link.coupang.com/a/TOP"
    cap = make_chart.build_caption(ch, {"title": "제목", "items": []}, c, 24)
    assert cap.splitlines()[0] == "c"
    assert cap.splitlines()[1].startswith("🛒") and "link.coupang.com/a/TOP" in cap.splitlines()[1]


def test_차트_제목은_관문을_거친다():
    """공개 4편 중 3편이 같은 제목이었다 — 차트가 제목을 안 남겨 지난 데일리 제목으로 올라갔다."""
    ch = _chart(5)
    t = make_chart.chart_title({"title": "요즘 이거 다시 유행한다는 주방템 3가지"}, ch,
                               recent=["요즘 이거 다시 유행한다는 주방템 3가지"])
    assert "요즘 이거" not in t and "다시 유행한다는" not in t
    assert "상품1" in t
    assert make_chart.chart_title({"title": "에그크래커 vs 밀폐용기, 이번 주 5개"}, ch, []) \
        == "에그크래커 vs 밀폐용기, 이번 주 5개"


def test_차트_기록은_데일리와_같은_두_파일에_남는다(tmp_path, monkeypatch):
    """publish.py는 last_caption.json에서 제목·날짜를 읽는다. 차트가 안 쓰면 지난 편으로 올라간다."""
    import json
    monkeypatch.chdir(tmp_path)
    ch = _chart(3)
    ch["entries"][0]["coupang_url"] = "https://link.coupang.com/a/TOP"
    make_chart.record(ch, {"hook": "훅"}, "제목", "설명", 27.3)
    last = json.load(open("data/last_caption.json", encoding="utf-8"))
    assert last["title"] == "제목" and last["verdict"] == "chart" and last["winner"] == "상품1"
    assert last["coupang_url"].endswith("/TOP")
    log = json.load(open("data/publish_log.json", encoding="utf-8"))
    assert log[-1]["slot"] == "chart" and log[-1]["format"] == "chart5" and log[-1]["links"] == 1


def test_첫_컷에는_판정을_안_그린다(tmp_path):
    """읽을 게 하나면 0.5초에 읽힌다. 첫 컷에 다 넣으면 쪼갠 의미가 없다."""
    a = cards.card_rank(_entry(), {}, str(tmp_path / "n.png"), beat="name",
                        reason="이유", verdict="판정")
    b = cards.card_rank(_entry(), {}, str(tmp_path / "w.png"), beat="why",
                        reason="이유", verdict="판정")
    assert list(Image.open(a).getdata()) != list(Image.open(b).getdata())

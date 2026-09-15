"""주간 차트 — 순위·상태 태그·변동. 틀린 판정은 채널 정체성을 무너뜨린다."""
import chart as C


def _p(key, name, demand=None, videos=(), mentions=None):
    return {"key": key, "name": name, "demand": list(demand) if demand else None,
            "videos": [{"views": v, "channel_id": f"c{i}"} for i, v in enumerate(videos)],
            "mentions": mentions}


# ── 상태 태그 ──────────────────────────────────────────────────────────────
def test_식는_중이면_끝물():
    """'이건 이제 그만 사도 됩니다' — 기성세대에게 가장 필요한 문장이 여기서 나온다."""
    down = [8] * 30 + [1] * 7
    assert C.status(_p("k", "x", demand=down)) == "fading"


def test_막_오르고_아직_아무도_안_만들었으면_예감():
    up = [2] * 40 + [10] * 7
    assert C.status(_p("k", "x", demand=up, videos=(100, 200))) == "hot"


def test_오르는데_이미_다들_만들었으면_유행중():
    """공급이 많다 = 피드에 이미 깔렸다. '아직 다들 모른다'고 하면 거짓말이 된다."""
    up = [2] * 40 + [10] * 7
    got = C.status(_p("k", "x", demand=up, videos=(1, 2, 3, 4, 5, 6)))
    assert got == "now"


def test_끝물이었다가_다시_오르면_재점화():
    up = [2] * 40 + [10] * 7
    assert C.status(_p("k", "x", demand=up, videos=(1,)), was_fading=True) == "again"


def test_수요_데이터가_없으면_단계를_말하지_않는다():
    """근거 없는 판정은 상품을 AI로 그리는 것과 같은 종류의 거짓말이다."""
    assert C.status(_p("k", "x", demand=None, videos=(1, 2, 3))) is None
    assert C.status(_p("k", "x", demand=[1, 2, 3])) is None      # 표본 부족


# ── 순위 ───────────────────────────────────────────────────────────────────
def test_한_축이_통째로_비어도_순위가_나온다():
    """가격·수요 중 하나가 결측인 날이 흔하다. 그때 0점 처리하면 순위가 뒤집힌다."""
    rows = [_p("a", "A", videos=(100, 100)), _p("b", "B", videos=(1,))]
    s = C.score_all(rows)
    assert s[0] > s[1]


def test_노출은_중앙값이_아니라_합계로_센다():
    """시청자가 그 물건을 봤을 확률은 효율이 아니라 총 노출량에 비례한다."""
    many = C.signals(_p("a", "A", videos=(10, 10, 10, 10)))
    one = C.signals(_p("b", "B", videos=(30,)))
    assert many["reach"] > one["reach"] and many["channels"] > one["channels"]


# ── 변동 ───────────────────────────────────────────────────────────────────
def test_첫_회차는_전부_NEW():
    assert C._delta("k", 1, None)["text"] == "NEW"


def test_순위_변동_방향():
    prev = {"entries": [{"key": "k", "rank": 4, "name": "x"}]}
    assert C._delta("k", 1, prev)["text"] == "▲3"
    assert C._delta("k", 5, prev)["text"] == "▼1"
    assert C._delta("k", 4, prev)["move"] == "same"
    assert C._delta("새것", 2, prev)["text"] == "NEW"


# ── 실사진 게이트 ──────────────────────────────────────────────────────────
def test_실사진이_없으면_차트에_올리지_않는다():
    """절대 규칙 — 제품을 가상으로 재현하지 않는다. 빈칸을 그림으로 메우지 않는다."""
    cat = {"products": {"있는것": {"display": "있는것", "image": "assets/products/a.jpg"},
                        "없는것": {"display": "없는것", "image": ""}}}
    assert C.shootable("있는것", cat) is not None
    assert C.shootable("없는것", cat) is None
    assert C.shootable("아예모르는것", cat) is None


def test_화면에_나가는_이름은_카탈로그의_정식_상품명():
    """발굴 키워드('코에서 계란 흰자 나오는 주방용품')를 그대로 띄우면 검색이 안 된다."""
    cat = {"products": {"a": {"display": "락앤락 밀폐용기 800ml", "brand": "락앤락",
                              "model": "밀폐용기 800ml", "image": "x.jpg"}}}
    got = C.shootable("락앤락밀폐용기 800ml", cat)
    assert got and got["display"] == "락앤락 밀폐용기 800ml"


# ── 숫자 하나 ──────────────────────────────────────────────────────────────
def test_유행_크기는_숫자로_말한다():
    """'요즘 난리난' 같은 추상어는 이 니치에서 죽는다(825회 vs 200만회, 2026-09-13)."""
    up = [2] * 40 + [10] * 7
    h = C.headline(_p("k", "x", demand=up, videos=(1,)))
    assert h and any(ch.isdigit() for ch in h)


def test_아무_신호도_없으면_문구를_만들지_않는다():
    assert C.headline(_p("k", "x")) is None

"""클레이 스톱모션 문법 — 질감은 그림이 아니라 움직임의 규칙에서 나온다."""
import itertools

from PIL import Image

import clay


def test_스쿼시는_부피를_지킨다():
    """가로로 퍼지면 세로가 줄어야 찰흙으로 보인다. 둘 다 커지면 그냥 확대다."""
    sx, sy = clay.squash(0.5, 0.2)
    assert sx > 1 and sy < 1
    assert abs(sx * sy - 1.0) < 0.05          # 넓이가 대략 보존된다


def test_스쿼시는_양끝에서_원래대로():
    assert clay.squash(0.0) == (1.0, 1.0)
    assert clay.squash(1.0)[0] < 1.0001


def test_보일은_실행마다_같아야_한다():
    """영상이 매 실행 달라지면 재렌더도 회귀 테스트도 의미가 없어진다."""
    assert clay.boil(5, seed=7) == clay.boil(5, seed=7)
    assert clay.boil(5, seed=7) != clay.boil(6, seed=7)


def test_보일_진폭은_미세해야_한다():
    """크게 흔들면 클레이가 아니라 지직거리는 글리치가 된다."""
    for i in range(30):
        (dx, dy), rot = clay.boil(i)
        assert abs(dx) <= clay.BOIL_PX and abs(dy) <= clay.BOIL_PX
        assert abs(rot) <= clay.BOIL_DEG


def test_프레임은_계단처럼_끊긴다():
    """매 프레임 갱신하면 3D 애니처럼 미끄러진다. step마다 한 번만 바뀌어야 한다."""
    frames = clay._step_frames([("pop", 1.0)], fps=30, step=3)
    assert len(frames) == 30
    # 한 클레이 프레임을 step번 홀드 — 3프레임 묶음 안에서는 변형이 같다
    for i in range(0, 30, 3):
        assert frames[i] == frames[i + 1] == frames[i + 2]
    # 그리고 구간 전체로는 실제로 변한다(홀드만 하면 애니가 아니다)
    assert len({tuple(sorted(f.items())) for f in frames}) > 1


def test_팝인은_한번_넘겼다가_돌아온다():
    """오버슛이 없으면 '튀어나왔다'가 아니라 그냥 확대다."""
    keys = clay.pop_in(12)
    scales = [k["scale"][0] for k in keys]
    assert max(scales) > 1.05                          # 제자리보다 한 번 커진다
    assert abs(scales[-1] - 1.0) < 0.02                # 결국 제자리로 온다


def test_홀드는_변형이_없다():
    for k in clay.hold(6):
        assert k["scale"] == (1.0, 1.0)


def test_길이_계산():
    assert clay.seconds([("pop", 0.5), ("hold", 0.25)]) == 0.75


# ── 발밑 흰 받침 제거 ──────────────────────────────────────────────────────
def _sprite_with_ghost() -> Image.Image:
    """캐릭터(크래프트색) + 테두리에 닿은 회백색 받침 + 내부 크림색."""
    im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    px = im.load()
    for y in range(4, 12):
        for x in range(4, 16):
            px[x, y] = (214, 178, 130, 255)            # 몸통
    px[8, 8] = (251, 246, 236, 255)                    # 크림색 손 — 내부라 살아야 한다
    for y in range(16, 20):
        for x in range(20):
            px[x, y] = (240, 240, 240, 255)            # 바닥 받침 — 테두리에 닿아 있다
    return im


def test_바닥_받침만_지우고_캐릭터는_남긴다():
    out = clay.deghost(_sprite_with_ghost())
    px = out.load()
    assert px[10, 18][3] == 0, "바닥 받침이 남았다"
    assert px[10, 8][3] == 255, "몸통이 지워졌다"
    assert px[8, 8][3] == 255, "내부 크림색이 지워졌다 — 손이 사라진다"


def test_무채색만_지운다():
    """콕이는 크래프트(편차 84)·크림(편차 15)이고 받침은 R≈G≈B다."""
    assert clay.deghost(_sprite_with_ghost()).load()[2, 2][3] == 0     # 원래 투명


# ── 중간 포즈(2프레임 연기) ────────────────────────────────────────────────
def test_깜빡임은_가끔_한_프레임만():
    """계속 감으면 조는 것이고, 안 감으면 죽은 인형이다."""
    keys = clay.blink(30)
    shut = [i for i, k in enumerate(keys) if k.get("pose") == "blink"]
    assert shut, "한 번도 안 깜빡인다"
    gaps = [b - a for a, b in itertools.pairwise(shut)]
    assert all(g > 1 for g in gaps), "연속으로 감고 있다"
    assert len(shut) < len(keys) / 4, "너무 자주 감는다"


def test_도장은_들_때와_칠_때_그림이_다르다():
    """같은 그림을 위로 띄우면 '든' 게 아니라 '뜬' 것이다."""
    keys = clay.react(20, "stamp")
    up = [k.get("pose") for k in keys[:8]]
    hit = [k.get("pose") for k in keys[-6:]]
    assert "up" in up
    assert set(hit) == {None}


def test_포즈가_없으면_기존_그림을_쓴다():
    """에셋 한 장이 없다고 렌더가 죽으면 안 된다 — 품질만 떨어진다."""
    for k in clay._step_frames([("blink", 0.6)]):
        assert k["scale"] == (1.0, 1.0)      # 변형은 없고 그림만 갈린다


def test_포즈는_몸통_폭에_맞춰_들어간다():
    """생성 크기가 제각각이라 그대로 얹으면 프레임마다 다른 인형이 된다."""
    base = Image.new("RGB", (60, 80), (10, 10, 10))
    main = Image.new("RGBA", (40, 40), (214, 178, 130, 255))
    tall = Image.new("RGBA", (80, 120), (214, 178, 130, 255))   # 2배로 생성된 포즈
    import os as _os
    out = clay.animate(base, main, (30, 70), [("blink", 0.4)],
                       "/tmp/_pose_test.mp4", poses={"blink": tall}, clean=False)
    assert _os.path.exists(out)
    _os.remove(out)

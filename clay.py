"""클레이 스톱모션 문법 — 정지 PNG를 손으로 만진 것처럼 움직이게 한다.

콕이 에셋은 정지 이미지 7장뿐이다(bg·idle·magnify·think·idea·stamp·nope).
그런데 **클레이 애니메이션의 질감은 그림이 아니라 움직임의 문법에서 나온다.**
실제 클레이 애니를 보면 공통점이 넷이다.

  ① 낮은 프레임레이트 — 8~12fps. 부드럽지 않고 톡톡 끊긴다. 이게 제1신호다.
  ② 보일(boil)       — 매 프레임 손이 닿아 1~2px씩 흔들린다. "살아 있다"는 느낌의 정체.
  ③ 스쿼시&스트레치  — 부피를 지키며 눌리고 늘어난다(가로 ↑면 세로 ↓).
  ④ 홀드(hold)       — 동작 뒤 완전히 멈춘다. 쉼이 있어야 동작이 읽힌다.

넷 다 **코드로 만들 수 있고 추가 에셋이 0장 든다.** 부드럽게 보간하면 오히려
클레이가 아니라 3D가 되므로, 여기서는 일부러 계단처럼 끊는다.

⚠️ 상품에는 절대 쓰지 않는다. 움직이는 순간 그건 재현이다 — 실사진은 정지로만 둔다.
   이 모듈이 만지는 것은 콕이(브랜드 캐릭터)와 자막·도장뿐이다.
"""
from __future__ import annotations

import math
import os
import random
import shutil
import subprocess

from PIL import Image

W, H = 1080, 1920
FPS = 30
STEP = 3            # 비디오 3프레임 = 클레이 1프레임 → 체감 10fps
BOIL_PX = 2         # 프레임마다 흔들리는 폭(px)
BOIL_DEG = 0.6      # 프레임마다 흔들리는 각도
BLINK_EVERY = 9     # 클레이 프레임 9장(0.9초)마다 한 장 눈을 감는다


# ---------------------------------------------------------------- 에셋 정리
def deghost(im: Image.Image, tol: int = 14, bright: int = 150) -> Image.Image:
    """콕이 발밑에 눌어붙은 **흰 바닥 그림자**를 지운다.

    나노바나나에 "no ground shadow"를 넣어도 불투명한 회백색 받침이 붙어 나온다.
    어두운 상품 사진 위에 얹으면 흰 얼룩으로 보인다(1차 렌더에서 확인). 받침은 단색이
    아니라 241→180으로 흐려지는 그라데이션이라 밝기 하나로는 못 자른다.

    테두리에서 흘러드는 flood fill이라 **캐릭터 안쪽은 건드리지 않는다** —
    콕이의 크림색 손(251,246,236)은 실루엣 안에 있어 테두리와 이어지지 않는다.
    자르는 기준은 밝기가 아니라 **무채색도**다. 받침은 R≈G≈B(편차 ≤6)인데
    콕이는 크래프트(214,178,130·편차 84)·크림(251,246,236·편차 15)이라 갈린다.
    """
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size

    def ghostly(r, g, b):
        return min(r, g, b) >= bright and (max(r, g, b) - min(r, g, b)) <= tol

    stack = [(x, y) for x in range(w) for y in (0, h - 1)]
    stack += [(x, y) for y in range(h) for x in (0, w - 1)]
    seen = bytearray(w * h)
    while stack:
        x, y = stack.pop()
        if not (0 <= x < w and 0 <= y < h) or seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        r, g, b, a = px[x, y]
        if a == 0:                       # 이미 투명 — 계속 흘러간다
            pass
        elif ghostly(r, g, b):
            px[x, y] = (r, g, b, 0)
        else:
            continue                     # 캐릭터 본체에 닿았다 — 여기서 멈춘다
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return im


# ---------------------------------------------------------------- 기본 변형
def _xform(im: Image.Image, scale=(1.0, 1.0), offset=(0, 0), rot=0.0) -> Image.Image:
    """스케일·이동·회전을 한 번에. 알파를 지키려 RGBA로만 다룬다."""
    w, h = im.size
    nw, nh = max(int(w * scale[0]), 1), max(int(h * scale[1]), 1)
    out = im.resize((nw, nh), Image.LANCZOS)
    if rot:
        out = out.rotate(rot, resample=Image.BICUBIC, expand=True)
    return out


def squash(t: float, amount: float = 0.12) -> tuple[float, float]:
    """스쿼시&스트레치 — 부피를 지킨다. 가로로 퍼지면 세로가 줄어든다.

    t: 0~1 진행도. 0.5에서 가장 눌린다.
    """
    k = math.sin(math.pi * max(0.0, min(1.0, t))) * amount
    return (1 + k, 1 - k)


def boil(i: int, seed: int = 0) -> tuple[tuple[int, int], float]:
    """손이 닿은 흔적 — 클레이 프레임마다 미세하게 어긋난다.

    난수를 프레임 번호로 고정해 **매 실행 같은 결과**가 나오게 한다.
    영상이 실행마다 달라지면 회귀 테스트도, 재렌더도 의미가 없어진다.
    """
    r = random.Random(seed * 1000 + i)
    return ((r.randint(-BOIL_PX, BOIL_PX), r.randint(-BOIL_PX, BOIL_PX)),
            r.uniform(-BOIL_DEG, BOIL_DEG))


# ---------------------------------------------------------------- 동작 시퀀스
def pop_in(n: int) -> list[dict]:
    """톡 튀어 등장 — 작게 시작해 살짝 넘겼다가(overshoot) 제자리.

    오버슛이 없으면 그냥 확대이고, 있으면 '튀어나왔다'가 된다.
    """
    keys = [(0.55, 60), (1.14, -22), (0.94, 8), (1.0, 0)]
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        idx = min(int(t * len(keys)), len(keys) - 1)
        s, dy = keys[idx]
        out.append({"scale": (s, s), "offset": (0, dy)})
    return out


def react(n: int, kind: str = "surprise") -> list[dict]:
    """리액션 — 시청자가 느낄 감정을 콕이가 0.5초 먼저 짓는다.

    캐릭터를 주인공으로 세우면 죽지만(의인화 상품소개 실측 1천~2.7천회),
    **관객 대리인**으로 쓰면 다르다. 짧게, 구석에서.
    """
    out = []
    for i in range(n):
        t = i / max(n - 1, 1)
        if kind == "surprise":                      # 위로 튄 뒤 착지하며 눌림
            up = -int(46 * math.sin(math.pi * min(t * 1.4, 1.0)))
            sx, sy = squash(max(0.0, t * 1.4 - 0.4) / 0.6, 0.14) if t > 0.4 else (1.0, 1.0)
            out.append({"scale": (sx, sy), "offset": (0, up)})
        elif kind == "tilt":                        # 갸웃 — 좌우로 기울이며 생각
            out.append({"rot": 9 * math.sin(math.pi * 2 * t), "scale": (1.0, 1.0)})
        elif kind == "idea":                        # 깨달음 — 두 번 통통
            b = abs(math.sin(math.pi * 2 * t))
            out.append({"scale": (1 - 0.06 * b, 1 + 0.08 * b), "offset": (0, -int(30 * b))})
        elif kind == "stamp":                       # 도장 — 들었다가 쾅, 착지에서 크게 눌림
            if t < 0.45:
                # 팔을 든 별도 포즈가 있으면 쓴다 — 없으면 같은 그림이 위로 뜰 뿐이다
                out.append({"scale": (1.0, 1.0), "pose": "up",
                            "offset": (0, -int(38 * (t / 0.45)))})
            else:
                k = (t - 0.45) / 0.55
                sx, sy = squash(k, 0.22)
                out.append({"scale": (sx, sy), "offset": (0, int(10 * math.sin(math.pi * k)))})
        else:
            out.append({"scale": (1.0, 1.0)})
    return out


def hold(n: int) -> list[dict]:
    """정지. 보일만 남는다 — 멈춰 있어도 클레이는 미세하게 떨린다."""
    return [{"scale": (1.0, 1.0)} for _ in range(n)]


def blink(n: int) -> list[dict]:
    """정지하되 이따금 눈을 감는다.

    홀드가 1초를 넘어가면 인형이 살아 있는 게 아니라 **죽어 있는** 것으로 보인다.
    깜빡임 한 장이면 그 인상이 뒤집힌다 — 클레이 애니가 눈만 따로 만드는 이유다.
    깜빡임은 한 클레이 프레임(0.1초)만 지속한다. 길면 조는 것처럼 보인다.
    """
    out = []
    for i in range(n):
        k = {"scale": (1.0, 1.0)}
        if i % BLINK_EVERY == BLINK_EVERY - 1:
            k["pose"] = "blink"
        out.append(k)
    return out


MOVES = {"pop": pop_in, "blink": blink, "surprise": lambda n: react(n, "surprise"),
         "tilt": lambda n: react(n, "tilt"), "idea": lambda n: react(n, "idea"),
         "stamp": lambda n: react(n, "stamp"), "hold": hold}


# ---------------------------------------------------------------- 합성·인코딩
def _step_frames(spec: list[tuple[str, float]], fps: int = FPS,
                 step: int = STEP) -> list[dict]:
    """(동작, 초) 목록 → 프레임별 변형 목록. **step 프레임마다 한 번만** 바뀐다.

    이 계단이 곧 클레이 질감이다. 매 프레임 갱신하면 3D 애니처럼 미끄러진다.
    """
    frames = []
    for name, sec in spec:
        total = max(int(sec * fps), 1)
        clay_n = max(total // step, 2)              # 이 구간의 '클레이 프레임' 수
        keys = MOVES.get(name, hold)(clay_n)
        for i in range(total):
            frames.append(keys[min(i // step, clay_n - 1)])
    return frames


def animate(base: Image.Image, sprite: Image.Image, center: tuple[int, int],
            spec: list[tuple[str, float]], out: str, fps: int = FPS,
            step: int = STEP, seed: int = 7, work: str | None = None,
            clean: bool = True, poses: dict[str, Image.Image] | None = None) -> str:
    """고정 배경 위에서 sprite만 스톱모션으로 움직여 mp4를 만든다.

    base   : 카드(상품 실사진 등) — **절대 움직이지 않는다**
    sprite : 콕이 등 클레이 PNG(투명 배경)
    spec   : [("pop", 0.5), ("hold", 0.3), ("surprise", 0.7)] 처럼 동작·길이
    poses  : {"blink": PNG, "up": PNG} — 특정 키프레임에서 바꿔 끼울 **다른 그림**

    코드 변형(스쿼시·보일)만으로는 표정이 안 바뀐다. 그건 같은 인형을 흔드는 것이다.
    중간 포즈를 한 장 더 넣으면 그때부터 **연기**가 된다 — 2프레임이면 충분하다.
    """
    work = work or f"{out}.frames"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    base = base.convert("RGBA")

    def prep(im: Image.Image) -> Image.Image:
        im = im.convert("RGBA")
        # 발밑 흰 받침 제거 — 어두운 사진 위에서 얼룩으로 보인다
        return deghost(im) if clean else im

    sprite = prep(sprite)
    # 포즈마다 생성 크기가 다르다. **몸통 폭**을 기준으로 맞춘다 —
    # 높이로 맞추면 팔을 든 포즈에서 몸이 쪼그라들어 다른 인형처럼 보인다.
    bank = {}
    for k, v in (poses or {}).items():
        im = prep(v)
        if im.width != sprite.width:
            r = sprite.width / im.width
            im = im.resize((sprite.width, max(int(im.height * r), 1)), Image.LANCZOS)
        bank[k] = im
    frames = _step_frames(spec, fps, step)

    for i, f in enumerate(frames):
        # 보일도 클레이 프레임 단위로 — 매 비디오 프레임 흔들면 지직거린다
        (bx, by), brot = boil(i // step, seed)
        src = bank.get(f.get("pose") or "", sprite)
        s = _xform(src, f.get("scale", (1.0, 1.0)), rot=f.get("rot", 0.0) + brot)
        dx, dy = f.get("offset", (0, 0))
        # 발밑을 기준으로 붙인다 — 스쿼시가 바닥에서 눌려야 무게가 느껴진다
        x = center[0] - s.width // 2 + dx + bx
        y = center[1] - s.height + dy + by
        canvas = base.copy()
        canvas.alpha_composite(s, (x, y))
        canvas.convert("RGB").save(os.path.join(work, f"f{i:04d}.png"))

    subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i",
                    os.path.join(work, "f%04d.png"), "-r", str(fps),
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", out],
                   check=True, capture_output=True)
    shutil.rmtree(work, ignore_errors=True)
    return out


def seconds(spec: list[tuple[str, float]]) -> float:
    return round(sum(s for _, s in spec), 2)

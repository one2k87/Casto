"""표정 프레임을 **에셋에서 직접 만든다** — 생성 모델을 한 번 더 부르지 않는다.

왜 이렇게 하는가(2026-09-15 실측):
  나노바나나로 중간 포즈를 이어 뽑아보니 2번째 그림부터 캐릭터가 **표류**했다.
  "도장을 머리 위로 든" 포즈를 요청하자 도장이 머리에 눌어붙어 이후 14장 전부를
  따라다녔다. 교정 프롬프트로 떼어내면 이번엔 뚜껑 모양과 비율이 달라졌다.
  1/10초마다 갈아 끼우는 짝 그림에서는 이 정도 차이도 **깜빡임으로 보인다.**

  그래서 눈만 바꾸는 프레임은 생성하지 않고 원본 에셋에서 만든다.
  같은 몸, 같은 조명, 같은 위치 — 정합이 어긋날 여지가 원천적으로 없다.
  덤으로 생성 할당량을 한 장도 쓰지 않는다.

콕이의 눈·입은 몸통(크래프트색)에 얹힌 **세이지 그린 점토 조각**이라 색으로
분리된다. 눈 두 개를 지우고 그 자리에 호(∩)를 그리면 감은 눈이 된다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

SS = 4          # 안티에일리어싱 배율 — 점토 표면에 계단이 보이면 붙인 티가 난다


def _is_face(r: int, g: int, b: int, a: int) -> bool:
    """세이지 그린인가. 몸통은 크래프트색이라 초록이 빨강보다 높을 수 없다."""
    return a > 200 and g > r + 12 and g > b + 6 and 90 < g < 210


def _components(im: Image.Image) -> list[list[tuple[int, int]]]:
    px = im.load()
    w, h = im.size
    sel = {(x, y) for y in range(h) for x in range(w) if _is_face(*px[x, y])}
    seen: set[tuple[int, int]] = set()
    out = []
    for s in sel:
        if s in seen:
            continue
        stack, comp = [s], []
        while stack:
            p = stack.pop()
            if p in seen or p not in sel:
                continue
            seen.add(p)
            comp.append(p)
            x, y = p
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1),
                      (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)]
        out.append(comp)
    return out


def _bbox(comp) -> tuple[int, int, int, int]:
    xs = [p[0] for p in comp]
    ys = [p[1] for p in comp]
    return min(xs), min(ys), max(xs), max(ys)


def parts(im: Image.Image) -> dict | None:
    """눈 두 개와 입을 찾는다. 못 찾으면 None — 호출부가 원본을 그대로 쓴다.

    눈은 **높이가 비슷한 두 덩어리**로 고른다. 크기순으로 뽑으면 입이 섞인다.
    """
    comps = [c for c in _components(im) if len(c) > 30]
    if len(comps) < 3:
        return None
    boxed = [(_bbox(c), c) for c in comps]
    # 입: 가장 납작하고 가장 넓다(웃는 호)
    mouth = max(boxed, key=lambda t: (t[0][2] - t[0][0]) / max(t[0][3] - t[0][1], 1))
    rest = [t for t in boxed if t is not mouth]
    if len(rest) < 2:
        return None
    # 눈: 남은 것 중 같은 높이대에 있는 두 개
    rest.sort(key=lambda t: t[0][1])
    eyes = sorted(rest[:2], key=lambda t: t[0][0])
    if abs(eyes[0][0][1] - eyes[1][0][1]) > max(im.height // 20, 4):
        return None
    color = _avg([im.getpixel((x, y)) for x, y in mouth[1]])
    # 입 획의 1/3. 입과 같은 굵기로 그리면 호가 아니라 **반달로 꽉 찬다**.
    stroke = max((mouth[0][3] - mouth[0][1]) // 3, 3)
    return {"eyes": [e[0] for e in eyes], "mouth": mouth[0],
            "color": color, "stroke": stroke}


def _avg(pxs) -> tuple[int, int, int, int]:
    n = len(pxs)
    return tuple(sum(p[i] for p in pxs) // n for i in range(4))


def _clean(im: Image.Image, box) -> bool:
    """이 영역이 초록 없는 온전한 몸통 표면인가."""
    x0, y0, x1, y1 = box
    if x0 < 0 or y0 < 0 or x1 >= im.width or y1 >= im.height:
        return False
    px = im.load()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            p = px[x, y]
            if p[3] < 250 or _is_face(*p):
                return False
    return True


def _patch(im: Image.Image, box) -> Image.Image | None:
    """눈을 덮을 **질감이 있는** 조각을 몸통에서 떠온다.

    단색으로 칠하면 점토 표면 위에 매끈한 원이 생겨 스티커처럼 보인다.
    같은 y(같은 조명 띠)에서 옆으로 옮겨 뜨는 것이 1순위다.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0 + 1, y1 - y0 + 1
    for dx, dy in ((w + 16, 0), (-(w + 16), 0), (0, -(h + 14)), (0, h + 14),
                   (w + 30, 0), (-(w + 30), 0)):
        src = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        if _clean(im, src):
            return im.crop((src[0], src[1], src[2] + 1, src[3] + 1))
    return None


def _erase_eyes(im: Image.Image, eyes) -> Image.Image | None:
    """눈 두 개를 몸통 질감으로 덮은 사본. 덮을 조각을 못 뜨면 None."""
    out = im.convert("RGBA").copy()
    for x0, y0, x1, y1 in eyes:
        # 눈은 도드라진 점토라 **아래쪽에 그림자**가 진다. 초록이 아니라서
        # 성분 검출에 안 잡히고, 안 덮으면 새 표정 밑에 초승달로 남는다.
        m = 4
        grown = (x0 - m, y0 - m, x1 + m, y1 + m + max((y1 - y0) // 2, 6))
        patch = _patch(im, grown)
        if patch is None:
            return None
        mask = Image.new("L", patch.size, 0)
        ImageDraw.Draw(mask).ellipse([0, 0, patch.width - 1, patch.height - 1], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(1.6))      # 경계를 녹인다
        out.paste(patch, (grown[0], grown[1]), mask)
    return out


def wide(im: Image.Image, k: float = 1.55) -> Image.Image | None:
    """눈을 크게 뜬 한 장 — 놀람의 0.1초.

    리액션은 **눈 크기**로 읽힌다. 몸을 튀게 하는 것만으로는 놀란 게 아니라
    그냥 흔들린 것이다. 눈 하나 바꾸면 같은 움직임이 연기가 된다.
    """
    p = parts(im)
    if not p:
        return None
    out = _erase_eyes(im, p["eyes"])
    if out is None:
        return None
    big = out.resize((out.width * SS, out.height * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    for x0, y0, x1, y1 in p["eyes"]:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rx, ry = (x1 - x0) / 2 * k, (y1 - y0) / 2 * k
        d.ellipse([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS],
                  fill=p["color"])
    return big.resize(im.size, Image.LANCZOS)


def blink(im: Image.Image) -> Image.Image | None:
    """눈을 감은 한 장. 원본은 건드리지 않는다.

    감은 눈은 **위로 볼록한 호**다. 아래로 볼록하면 우는 얼굴이 된다.
    """
    p = parts(im)
    if not p:
        return None
    out = _erase_eyes(im, p["eyes"])
    if out is None:
        return None
    big = out.resize((out.width * SS, out.height * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    for box in p["eyes"]:
        x0, y0, x1, y1 = box
        w = x1 - x0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # 뜬 눈보다 **넓고 납작하게**. 좁으면 획 굵기에 먹혀 반달이 된다.
        rx, ry = w * 0.92, w * 0.46
        d.arc([(cx - rx) * SS, (cy - ry) * SS, (cx + rx) * SS, (cy + ry) * SS],
              180, 360, fill=p["color"], width=max(p["stroke"] * SS, SS))
    return big.resize(im.size, Image.LANCZOS)

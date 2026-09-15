"""표정 프레임 — 생성 모델을 부르지 않고 원본 에셋에서 만든다."""
from PIL import Image, ImageDraw

import faces

GREEN = (139, 155, 119, 255)


def _koki() -> Image.Image:
    """몸통(크래프트) + 세이지 그린 눈 두 개 + 입. 최소 재현.

    눈 옆에 **덮을 질감을 뜰 여백**이 있어야 한다 — 실제 에셋도 그렇다.
    """
    im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 280, 280], fill=(214, 178, 130, 255))
    d.ellipse([90, 90, 110, 110], fill=GREEN)        # 왼눈
    d.ellipse([170, 90, 190, 110], fill=GREEN)       # 오른눈
    d.rectangle([120, 190, 180, 202], fill=GREEN)    # 입 — 납작하고 넓다
    return im


def test_눈과_입을_구분한다():
    """크기순으로 뽑으면 입이 눈으로 들어간다 — 납작한 쪽이 입이다."""
    p = faces.parts(_koki())
    assert p and len(p["eyes"]) == 2
    (lx0, _, lx1, _), (rx0, _, _, _) = p["eyes"]
    assert lx0 < rx0                                  # 왼쪽부터
    mw = p["mouth"][2] - p["mouth"][0]
    assert mw > lx1 - lx0                             # 입이 눈보다 넓다


def test_얼굴이_없으면_None():
    """돋보기·별눈 에셋에서도 죽지 않고 None을 준다 — 호출부가 원본을 쓴다."""
    plain = Image.new("RGBA", (80, 80), (214, 178, 130, 255))
    assert faces.parts(plain) is None
    assert faces.blink(plain) is None
    assert faces.wide(plain) is None


def test_감은_눈은_원본을_바꾸지_않는다():
    src = _koki()
    before = list(src.getdata())
    faces.blink(src)
    assert list(src.getdata()) == before


def _green_count(im):
    return sum(1 for p in im.getdata() if faces._is_face(*p))


def test_감은_눈은_점이_아니라_납작한_호():
    out = faces.blink(_koki())
    assert out.size == (300, 300)
    # 눈 자리에서 초록이 줄었다 = 채워진 점이 사라졌다
    box = (84, 84, 118, 130)
    assert _green_count(out.crop(box)) < _green_count(_koki().crop(box))
    # 그런데 완전히 없지는 않다 = 호가 남아 있다
    assert _green_count(out.crop(box)) > 0


def test_감은_눈_아래_그림자까지_덮는다():
    """눈은 도드라진 점토라 아래에 그림자가 진다. 안 덮으면 초승달로 남는다."""
    src = _koki()
    d = ImageDraw.Draw(src)
    d.ellipse([90, 108, 110, 116], fill=(150, 120, 90, 255))  # 눈 밑 그림자
    out = faces.blink(src)
    assert out is not None
    # 그림자 자리가 몸통 색으로 덮였는지 — 어두운 픽셀이 사라졌다
    dark = sum(1 for p in out.crop((88, 108, 112, 117)).getdata() if p[0] < 180 and p[1] < 150)
    assert dark < 10


def test_놀란_눈은_더_크다():
    a = faces.wide(_koki())
    assert a is not None
    box = (84, 84, 118, 130)
    assert _green_count(a.crop(box)) > _green_count(_koki().crop(box))


def test_덮을_조각을_못_뜨면_포기한다():
    """얼굴이 가장자리에 붙어 질감을 뜰 곳이 없으면 억지로 칠하지 않는다."""
    im = Image.new("RGBA", (46, 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 45, 39], fill=(214, 178, 130, 255))
    d.ellipse([2, 2, 16, 16], fill=GREEN)
    d.ellipse([29, 2, 43, 16], fill=GREEN)
    d.rectangle([10, 26, 36, 33], fill=GREEN)
    assert faces.blink(im) is None

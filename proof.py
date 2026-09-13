"""증거 화면 — 실사용 영상을 흉내내는 대신, 그들이 못 보여주는 것을 보여준다.

이 니치에서 100만을 넘는 영상은 전부 실사용 장면이 있다(2026-09-10 실측).
우리는 그걸 못 찍는다. **그래서 흉내내지 않는다.** 어설픈 흉내는 진짜 옆에서 진다.

대신 실사용 채널이 절대 못 보여주는 것을 화면에 띄운다.

    "8월 셋째 주부터 검색 6배"          ← 네이버 데이터랩 시계열
    "영어권 4/1 → 한국 8/30, 5개월 늦게" ← 유튜브 한/영 최초 등장일
    "관련 영상 26개, 합계 4만 회"        ← 유튜브 수집

그리고 이게 핵심이다:

    **실제 데이터 화면은 AI티가 안 난다. 실사이기 때문이다.**

클레이 그림은 AI로 보인다. 하지만 꺾은선 그래프는 그냥 사실이다.
게다가 콕픽은 심사 채널이라, 심사관이 근거 자료를 펼쳐 보이는 게 정체성과 맞는다.

⚠️ 없는 숫자는 그리지 않는다. 데이터가 없으면 None을 돌려주고 씬을 건너뛴다 —
   그럴듯한 가짜 그래프는 상품을 AI로 재현하는 것과 같은 종류의 거짓말이다.
"""
import datetime as dt
import os

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920


def _fonts(font_fn):
    return {"big": font_fn(96), "mid": font_fn(64), "small": font_fn(44),
            "tiny": font_fn(36, bold=False)}


def _bg(brand):
    """종이 질감의 밝은 바탕 — 자료 화면은 밝아야 '자료'로 읽힌다."""
    cream, mint = tuple(brand["cream"]), tuple(brand["mint"])
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = (y / H) ** 1.3
        d.line([(0, y), (W, y)],
               fill=tuple(int(cream[j] + (mint[j] - cream[j]) * t * 0.55) for j in range(3)))
    return img


def _headline(d, text, y, fonts, sage, accent=None):
    d.text((W // 2, y), text, font=fonts["mid"], fill=sage, anchor="mm")


def spark(d, series, box, sage, accent, width=9):
    """꺾은선. 값은 그대로 쓴다 — 보기 좋게 만들려고 곡선을 다듬지 않는다."""
    x0, y0, x1, y1 = box
    pts = [float(v) for v in series if v is not None]
    if len(pts) < 2:
        return None
    lo, hi = min(pts), max(pts)
    rng = (hi - lo) or 1.0
    step = (x1 - x0) / (len(pts) - 1)
    xy = [(x0 + i * step, y1 - (v - lo) / rng * (y1 - y0)) for i, v in enumerate(pts)]

    # 기준선
    for k in range(4):
        yy = y0 + (y1 - y0) * k / 3
        d.line([(x0, yy), (x1, yy)], fill=(255, 255, 255), width=3)
    d.line(xy, fill=sage, width=width, joint="curve")

    # 마지막 점 강조 — 시선이 '지금'에 닿아야 한다
    lx, ly = xy[-1]
    d.ellipse([lx - 22, ly - 22, lx + 22, ly + 22], fill=accent, outline=(255, 255, 255), width=7)
    return xy


def demand_card(brief, brand, font_fn, out_path):
    """수요 급등 카드 — **언제부터 몇 배**. 인과를 가장 크게 좁히는 한 장.

    `brief`는 evidence.brief()의 결과. spike가 없으면 만들지 않는다.
    """
    sp = (brief or {}).get("spike") or {}
    series = (brief or {}).get("demand_series") or []
    if sp.get("trend") != "up" or len(series) < 14:
        return None

    sage, accent = tuple(brand["sage"]), (214, 90, 78)
    fonts = _fonts(font_fn)
    img = _bg(brand)
    d = ImageDraw.Draw(img)

    d.text((W // 2, 300), "네이버 쇼핑 검색량", font=fonts["small"], fill=sage, anchor="mm")

    box = (172, 560, W - 172, 1040)      # 끝점(반지름 22)이 테두리에 물리지 않게
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((box[0] - 26, box[1] - 40, box[2] + 26, box[3] + 40),
                                         radius=40, fill=(60, 70, 64, 45))
    img.paste(Image.alpha_composite(img.convert("RGBA"),
                                    sh.filter(ImageFilter.GaussianBlur(16))).convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((box[0] - 26, box[1] - 40, box[2] + 26, box[3] + 40),
                        radius=40, fill=(255, 255, 255), outline=sage, width=5)
    spark(d, series, box, sage, accent)

    when = _when_label(sp.get("days_ago"))
    d.text((W // 2, 1130), f"{when}부터", font=fonts["mid"], fill=sage, anchor="mm")
    ratio = f"{sp['ratio']:g}배"
    d.text((W // 2, 1265), ratio, font=fonts["big"], fill=accent, anchor="mm",
           stroke_width=9, stroke_fill=(255, 255, 255))
    d.text((W // 2, 1380), "출처: 네이버 데이터랩", font=fonts["tiny"], fill=sage, anchor="mm")
    img.save(out_path)
    return out_path


def overseas_card(brief, brand, font_fn, out_path):
    """해외 선행 타임라인 — "영어권 4/1 → 한국 8/30, 약 5개월".

    '해외에서 난리난'은 이 니치에서 197만을 찍은 제목 틀이다. 그 말을
    **근거와 함께** 쓸 수 있는 채널은 드물다.
    """
    ov = (brief or {}).get("overseas") or {}
    if ov.get("verdict") != "overseas_first":
        return None
    en, ko = ov.get("en") or {}, ov.get("ko") or {}
    if not (en.get("earliest") and ko.get("earliest")):
        return None

    sage, accent = tuple(brand["sage"]), (214, 90, 78)
    fonts = _fonts(font_fn)
    img = _bg(brand)
    d = ImageDraw.Draw(img)

    d.text((W // 2, 300), "어디서 먼저 떴나", font=fonts["small"], fill=sage, anchor="mm")

    ax, bx, y = 200, W - 200, 760
    d.line([(ax, y), (bx, y)], fill=sage, width=10)
    for x, lab, date, col in ((ax, "영어권", en["earliest"], accent),
                              (bx, "한국", ko["earliest"], sage)):
        d.ellipse([x - 34, y - 34, x + 34, y + 34], fill=col, outline=(255, 255, 255), width=8)
        d.text((x, y - 130), lab, font=fonts["small"], fill=sage, anchor="mm")
        d.text((x, y + 120), _md(date), font=fonts["mid"], fill=col, anchor="mm")

    months = round((ov.get("lead_days") or 0) / 30, 1)
    d.text((W // 2, 1120), f"{months:g}개월", font=fonts["big"], fill=accent, anchor="mm",
           stroke_width=9, stroke_fill=(255, 255, 255))
    d.text((W // 2, 1270), "늦게 들어왔다", font=fonts["mid"], fill=sage, anchor="mm")
    if en.get("count"):
        d.text((W // 2, 1430), f"영어권 관련 영상 {en['count']}개",
               font=fonts["small"], fill=sage, anchor="mm")
    d.text((W // 2, 1560), "출처: 유튜브 최초 등장일 비교", font=fonts["tiny"], fill=sage, anchor="mm")
    img.save(out_path)
    return out_path


def spread_card(brief, brand, font_fn, out_path):
    """확산 속도 — 관련 영상 수와 합계 조회수. 가장 흔하게 확보되는 근거."""
    n, views = (brief or {}).get("videos"), (brief or {}).get("views")
    if not (n and views and n >= 3):
        return None
    sage, accent = tuple(brand["sage"]), (47, 143, 104)
    fonts = _fonts(font_fn)
    img = _bg(brand)
    d = ImageDraw.Draw(img)

    d.text((W // 2, 300), "얼마나 퍼졌나", font=fonts["small"], fill=sage, anchor="mm")

    # 영상 개수를 네모로 쌓아 눈에 보이게 한다 — 숫자만 쓰면 안 읽힌다
    cols, size, gap = 6, 92, 22
    rows = (min(n, 24) + cols - 1) // cols
    tw = cols * size + (cols - 1) * gap
    sx, sy = (W - tw) // 2, 560
    for k in range(min(n, 24)):
        r, cc = divmod(k, cols)
        x, yy = sx + cc * (size + gap), sy + r * (size + gap)
        # 한 칸 = 영상 한 개. 예전엔 앞 12칸만 색을 채웠는데 그 12에 아무 의미가 없었다
        # — 근거 화면에서 뜻 없는 장식은 근거를 약하게 만든다.
        d.rounded_rectangle((x, yy, x + size, yy + size), radius=18,
                            fill=accent, outline=sage, width=4)
    if n > 24:
        d.text((W // 2, sy + rows * (size + gap) + 40), f"+{n - 24}",
               font=fonts["small"], fill=sage, anchor="mm")

    d.text((W // 2, 1230), f"관련 영상 {n}개", font=fonts["mid"], fill=sage, anchor="mm")
    d.text((W // 2, 1390), f"{views:,}회", font=fonts["big"], fill=accent, anchor="mm",
           stroke_width=9, stroke_fill=(255, 255, 255))
    d.text((W // 2, 1560), "출처: 유튜브 (최근 14일)", font=fonts["tiny"], fill=sage, anchor="mm")
    img.save(out_path)
    return out_path


BUILDERS = (("demand", demand_card), ("overseas", overseas_card), ("spread", spread_card))


def best_card(brief, brand, font_fn, out_dir="out", slug="x"):
    """이 상품에 대해 만들 수 있는 **가장 강한 증거 한 장**.

    순서가 곧 우선순위다 — 수요 급등(언제부터 몇 배) > 해외 선행 > 확산 속도.
    아무것도 못 만들면 None: 증거가 없으면 증거 씬을 넣지 않는다.
    """
    os.makedirs(out_dir, exist_ok=True)
    for kind, fn in BUILDERS:
        p = fn(brief, brand, font_fn, f"{out_dir}/proof_{slug}_{kind}.png")
        if p:
            return {"path": p, "kind": kind}
    return None


# ---------------------------------------------------------------- 문구 헬퍼
def _when_label(days_ago):
    if not days_ago:
        return "최근"
    d = dt.date.today() - dt.timedelta(days=days_ago)
    wk = (d.day - 1) // 7 + 1
    return f"{d.month}월 {['첫', '둘', '셋', '넷', '다섯'][min(wk, 5) - 1]}째 주"


def _md(iso):
    try:
        y, m, dd = iso.split("-")
        return f"{int(m)}/{int(dd)}"
    except Exception:                                        # noqa: BLE001
        return iso


CAPTION = {
    "demand": "검색량이 갑자기 뛰었어요",
    "overseas": "해외에서 먼저 떴어요",
    "spread": "며칠 새 다들 다뤘어요",
}

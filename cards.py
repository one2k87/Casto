"""상품 카드 규격 — 주간 차트와 데일리가 **같은 카드**를 쓴다.

왜 한 규격으로 묶는가: 시청자가 주간 차트에서 본 카드를 데일리에서 다시 만나야
"아 그 채널"이 된다. 카드가 편마다 다르면 같은 채널로 안 읽힌다.

절대 규칙 — **제품을 가상으로 재현하지 않는다.** 실사진이 없으면 카드를 만들지 않는다.
그림으로 메운 제품컷은 그 즉시 시청자가 돌아선다. 그래서 `photo`는 선택값이 아니다.

실측 근거(2026-09-10, 조회수 100만~473만 주방템 쇼츠 썸네일 해부):
  오려낸 제품컷을 흰 카드에 넣은 화면은 **하나도 없었다.** 전부 실제 장면이 화면을
  꽉 채우고 자막이 그 위에 얹혀 있었다. 그래서 카드는 사진 위에 글씨를 얹는 구조다.

빈칸 규칙: 가격이 없으면 **그 줄을 통째로 비운다.** "가격 미정"도 쓰지 않는다 —
화면에 나온 글자는 전부 사실이어야 하고, 비어 있는 편이 거짓보다 낫다.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

from make_short import H, W, fill_frame, font, punch_text, scrim, wrap

# 상태 태그 색 — 이모지는 쓰지 않는다. 로컬·CI 폰트에 이모지가 없어 ▨로 렌더된다(실측).
# 대신 색 칩으로 구분한다. 색만으로 못 읽는 사람을 위해 라벨을 항상 같이 쓴다.
TAG_COLOR = {
    "hot":    (214, 90, 78),     # 예감 — 붉은색
    "now":    (47, 143, 104),    # 유행중 — 초록
    "fading": (140, 140, 150),   # 끝물 — 회색
    "again":  (196, 140, 60),    # 재점화 — 황토
}
MOVE_COLOR = {"new": (214, 90, 78), "up": (47, 143, 104),
              "down": (120, 125, 135), "same": (150, 150, 150)}
INK = (255, 255, 255)
SHADOW = (20, 30, 26)


def _chip(d: ImageDraw.ImageDraw, x: int, y: int, label: str, color, size: int = 46,
          pad: int = 26) -> int:
    """색 칩 + 라벨. 칩의 오른쪽 끝 x를 돌려준다."""
    f = font(size)
    tw = int(d.textlength(label, font=f))
    h = size + pad
    w = tw + pad * 2 + h // 2
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=color)
    d.ellipse([x + pad // 2, y + h // 2 - 9, x + pad // 2 + 18, y + h // 2 + 9], fill=INK)
    d.text((x + pad + 24, y + h // 2), label, font=f, anchor="lm", fill=INK)
    return x + w


def delta_text(delta: dict | None) -> str:
    """NEW · ▲3 · ▼1 · 유지. 첫 회차는 전부 NEW다 — 지난주가 없으면 변동도 없다."""
    if not delta:
        return ""
    return delta.get("text") or ""


def card_rank(entry: dict, c: dict, path: str, idx: int = 0, total: int = 0,
              reason: str = "", week: str = "", verdict: str = "",
              beat: str = "full") -> str:
    """차트 한 칸. 실사진 전면 + 순위 + 상태 태그 + 상품명 + 가격 + 유행 크기 + 이유.

    entry: chart.build()의 entries 한 개(rank·display·image·price·tag·headline·delta)
    reason: 대본이 만든 **한 줄 이유**(왜 갑자기 보이는가). 없으면 headline이 그 자리를 쓴다.
    verdict: 상태 태그의 한 줄 판정(chart.tag_line). 이 한 줄이 편의 감정을 진다 —
             정보만 있는 차트는 실측에서 828회로 죽었다. 없으면 그리지 않는다.
    beat:    한 상품을 두 컷으로 쪼갠다 — "name"(순위·상품명) → "why"(판정·이유·가격).
             잘 되는 쇼츠는 2~4초에 한 번 화면이 바뀐다. 한 칸을 5초 동안 그대로
             두면 그 정지 자체가 이탈 지점이 된다(2026-09-16 실측·벤치마크).
             "full"은 예전처럼 한 컷에 전부 — 데일리·미리보기용으로 남겨둔다.
    """
    photo = entry.get("image")
    if not photo or not os.path.exists(photo):
        raise SystemExit(f"실사진이 없다: {entry.get('display')} — 재현하지 않는다")

    img = Image.new("RGB", (W, H))
    fill_frame(img, photo, dim=0.14)
    scrim(img, top_h=620, bot_h=980, strength=170)
    d = ImageDraw.Draw(img)

    # ── 순위 — 카드에서 가장 먼저 읽혀야 한다. 차트는 순위가 본문이다
    rank = entry.get("rank", idx + 1)
    d.ellipse([70, 210, 226, 366], fill=(255, 255, 255))
    d.text((148, 288), str(rank), font=font(92), anchor="mm", fill=SHADOW)
    if week:
        # 1위 칸은 이 편의 결승점이다 — 주차 대신 그렇게 말해준다
        top = "이번 주 1위" if rank == 1 else week
        d.text((252, 250), "콕픽 차트", font=font(38), anchor="lm", fill=INK)
        d.text((252, 316), top, font=font(38, bold=(rank == 1)),
               anchor="lm", fill=INK if rank == 1 else (220, 226, 220))

    # ── 변동 — 지난주 대비. 이게 있어야 매주 볼 이유가 생긴다(빌보드 논리)
    dt_ = entry.get("delta") or {}
    txt = delta_text(dt_)
    if txt:
        col = MOVE_COLOR.get(dt_.get("move"), (150, 150, 150))
        f = font(52)
        tw = int(d.textlength(txt, font=f))
        d.rounded_rectangle([W - 70 - tw - 64, 216, W - 70, 340], radius=30, fill=col)
        d.text((W - 70 - (tw + 64) / 2, 278), txt, font=f, anchor="mm", fill=INK)

    # ── 상태 태그 — 없으면 그리지 않는다. 근거 없는 판정은 상품을 그리는 것과 같다
    tag = entry.get("tag") or {}
    if tag.get("label"):
        _chip(d, 70, 410, tag["label"], TAG_COLOR.get(entry.get("status"), (120, 120, 130)))

    # ── 상품명 — 카탈로그의 정식 상품명. 발굴 키워드를 띄우면 검색이 안 된다
    punch_text(d, entry.get("display") or entry.get("name", ""), 1080, size=104,
               accent=TAG_COLOR.get(entry.get("status")))

    # 첫 컷은 순위와 이름만 — 읽을 게 하나면 0.5초에 읽힌다
    if beat == "name":
        img.save(path)
        return path

    y = 1270
    # ── 판정 한 줄 — 태그가 있을 때만. 근거 없는 판정은 붙이지 않는다
    if verdict:
        d.text((W // 2, y), verdict, font=font(64), anchor="mm",
               fill=TAG_COLOR.get(entry.get("status"), INK),
               stroke_width=9, stroke_fill=SHADOW)
        y += 110

    # ── 한 줄 이유 → 없으면 유행 크기가 그 자리를 쓴다
    line = reason or entry.get("headline") or ""
    if line:
        for j, ln in enumerate(wrap(d, line, font(50), W - 200)[:2]):
            d.text((W // 2, y + j * 62), ln, font=font(50), fill=INK, anchor="mm",
                   stroke_width=7, stroke_fill=SHADOW)
        y += 62 * min(len(wrap(d, line, font(50), W - 200)), 2) + 26

    # ── 가격 — **없으면 그 줄을 비운다.** 화면의 글자는 전부 사실이어야 한다
    price = entry.get("price")
    if price:
        d.text((W // 2, max(y, 1500)), f"{int(price):,}원", font=font(78), anchor="mm",
               fill=INK, stroke_width=9, stroke_fill=SHADOW)

    # ── 유행 크기 — 숫자로 말한다. '요즘 난리난' 같은 추상어는 이 니치에서 죽는다
    head = entry.get("headline")
    if head and head != line:
        d.text((W // 2, 1650), head, font=font(44, bold=False), anchor="mm",
               fill=(226, 232, 226), stroke_width=5, stroke_fill=SHADOW)

    # ── 진행 점 — 몇 개 중 몇 번째인지 보이면 이탈이 준다
    if total:
        for k in range(total):
            x = W // 2 + (k - total / 2 + .5) * 34
            d.ellipse([x - 7, 1840, x + 7, 1854],
                      fill=INK if k <= idx else (255, 255, 255, 90))
    img.save(path)
    return path

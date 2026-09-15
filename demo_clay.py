"""데모 — 3단 미스디렉션 한 상품을 클레이 스톱모션으로 렌더한다.

구조(실측 근거는 docs/콕픽_채널구조_보고서.md, 2026-09-15 추가 실측):
  ① 낮춰 부르기 : "그냥 플라스틱 가위예요"        ← 기대를 깎는다
  ② 숫자 충돌   : "그런데 9월 둘째 주부터 검색 1.5배" ← 예상과 어긋난다
  ③ 반전·판정   : "안 사면 후회할 것"               ← 238만짜리 후회 프레임

콕이는 관객 대리인이다 — 시청자가 느낄 감정을 0.5초 먼저 짓는다.
상품은 실사진 그대로 **정지**한다. 움직이는 순간 그건 재현이다.
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, ".")
import clay                                    # noqa: E402
import visuals                                 # noqa: E402
from common import cfg                         # noqa: E402
from make_short import W, H, fill_frame, scrim, punch_text, font   # noqa: E402

OUT = "out/demo_clay"
os.makedirs(OUT, exist_ok=True)


# 콕이는 오른쪽 아래 바닥에 선다. 자막은 그 **위쪽 띠**만 쓴다 —
# 겹치면 "안 사면 후회할 것"이 "안 사면 후회할"로 읽힌다(1차 렌더에서 실제로 잘렸다).
KOKI_FOOT = (W - 240, H - 90)       # 발밑 기준점
TEXT_BAND = (900, 1240)              # 큰 자막 / 보조 자막 y


def chip(d, text: str, y: int, fill=(214, 90, 78)) -> None:
    """상태 태그는 이모지 대신 **색 칩**으로. 로컬에 이모지 폰트가 없으면 ▨로 깨진다."""
    f = font(52)
    tw = d.textlength(text, font=f)
    x0, x1 = int(W / 2 - tw / 2) - 34, int(W / 2 + tw / 2) + 34
    d.rounded_rectangle([x0, y - 44, x1, y + 44], radius=44, fill=fill)
    d.text((W // 2, y), text, font=f, fill=(255, 255, 255), anchor="mm")


def card(photo: str, top: str = "", big: str = "", sub: str = "",
         accent=(214, 90, 78), tag: str = "", tag_fill=(214, 90, 78)) -> Image.Image:
    """상품 실사진 전면 + 자막. 카드 자체는 정지 프레임이다."""
    img = Image.new("RGB", (W, H))
    fill_frame(img, photo, dim=0.12)
    scrim(img, top_h=520, bot_h=1000, strength=170)
    d = ImageDraw.Draw(img)
    if tag:
        chip(d, tag, 250, tag_fill)
    elif top:
        d.text((W // 2, 250), top, font=font(58, bold=False), fill=(235, 240, 236),
               anchor="mm", stroke_width=6, stroke_fill=(20, 30, 26))
    if big:
        punch_text(d, big, TEXT_BAND[0], size=112, accent=accent)
    if sub:
        d.text((W // 2, TEXT_BAND[1]), sub, font=font(64), fill=(255, 255, 255), anchor="mm",
               stroke_width=9, stroke_fill=(20, 30, 26))
    return img


def main() -> None:
    c = cfg()
    photo = "assets/products/레이저가이드가위.jpg"
    if not os.path.exists(photo):
        raise SystemExit(f"실사진이 없다: {photo} — 재현하지 않는다")

    # (카드, 콕이 표정, 동작 시퀀스, 콕이 크기)
    beats = [
        # ① 낮춰 부르기 — 콕이는 무심하게 서 있다
        (card(photo, top="이번 주 4위", big="그냥\n플라스틱 가위", sub="3,900원"),
         "idle", [("pop", 0.45), ("hold", 1.0)], 520),
        # ② 숫자 충돌 — 콕이가 먼저 놀란다
        (card(photo, big="검색 1.5배", sub="9월 둘째 주부터", accent=(47, 143, 104)),
         "magnify", [("surprise", 0.75), ("hold", 0.7)], 620),
        # ③ 이유 — 갸웃하다가 깨닫는다
        (card(photo, top="왜?", big="레이저로\n선이 보인다", sub="손 떨려도 반듯하게"),
         "think", [("tilt", 1.0), ("hold", 0.4)], 560),
        (card(photo, top="그래서", big="아직 다들\n모릅니다", sub="관련 영상 1개"),
         "idea", [("idea", 0.8), ("hold", 0.5)], 560),
        # ④ 판정 — 후회의 언어로(238만짜리 프레임)
        (card(photo, tag="예감", big="안 사면\n후회할 것", sub="지금이 제일 쌉니다"),
         "stamp", [("stamp", 0.9), ("hold", 0.7)], 660),
    ]

    parts = []
    for i, (bg, face, spec, size) in enumerate(beats):
        sprite = visuals.koki(face, box=(size, size))
        if sprite is None:
            raise SystemExit(f"클레이 에셋 없음: {face}")
        p = f"{OUT}/beat{i}.mp4"
        clay.animate(bg, sprite, KOKI_FOOT, spec, p)
        parts.append(p)
        print(f"[demo] {i+1}/{len(beats)} {face} {clay.seconds(spec)}초")

    lst = f"{OUT}/list.txt"
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", "demo.mp4"], check=True, capture_output=True, cwd=OUT)
    print(f"[demo] 완료 → {OUT}/demo.mp4")


if __name__ == "__main__":
    main()

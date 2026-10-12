"""픽이(콕이의 룸메이트) 디자인 후보 3안 + 콕이 레퍼런스 시트 — 파일럿(블록 0) 1회 생성.

    python make_pick.py cands   # assets/pick/cand_{1,2,3}.png + contact.png
    python make_pick.py sheet   # assets/koki/koki_sheet.png (턴어라운드·표정)
    python make_pick.py pick 2  # 2안을 픽이로 확정 → assets/pick/pick_idle.png + pick_sheet.png

왜 1회인가: `faces.py` 주석대로 생성 모델은 두 번째 그림부터 표류한다. 그래서 후보는 한 번만 뽑고,
확정 뒤 **레퍼런스 시트 한 장**을 만들어 이후 모든 장면 생성의 참고 이미지로 고정한다.
콕이 에셋(assets/koki/koki_idle.png)을 참고로 넣어 재질·축척·조명이 같은 세계에 서게 한다.
"""
from __future__ import annotations

import os
import shutil
import sys

from PIL import Image

import imagegen

KOKI = "assets/koki/koki_idle.png"
OUT = "assets/pick"

# 세 후보는 색과 실루엣으로 콕이와 한눈에 갈린다. 성격은 공통(충동구매형·유행 다 사고 싶음).
CANDS = {
    1: "a short round peach/coral-colored clay character with big sparkly eyes, a tiny shopping bag "
       "in one hand, bouncy and excited posture",
    2: "a tall slim lavender-colored clay character with droopy happy eyes, a phone in hand, "
       "leaning forward curiously",
    3: "a fluffy butter-yellow clay character shaped like a rice cake, small blush marks, "
       "holding a credit card, cheerful and a bit sheepish",
}

SHEET = ("a character reference sheet on a plain cream background: the SAME character from the "
         "reference image drawn 6 times in a 3x2 grid — front view, 3/4 view, side view, back view, "
         "then front view surprised (wide eyes, open mouth), front view sulking (eyes closed, pout). "
         "Identical proportions, colors and clay texture in every cell. No text, no labels")


def cands() -> list[str]:
    made = []
    for i, desc in CANDS.items():
        p = os.path.join(OUT, f"cand_{i}.png")
        prompt = (f"{imagegen.STYLE}. Design a new companion character for the clay character in the "
                  f"reference image — same clay material, same lighting, same scale, same simple face style "
                  f"(two small sage-green dot eyes and a tiny mouth), but clearly different: {desc}. "
                  f"Standing alone, front view, full body, centered, plain cream background, no ground shadow")
        if imagegen.generate(prompt, p, refs=[KOKI], aspect="1:1"):
            made.append(p)
    if made:
        _contact(made, os.path.join(OUT, "contact.png"))
    return made


def _contact(paths: list[str], out: str, size: int = 512) -> str:
    ims = [Image.open(p).convert("RGBA").resize((size, size)) for p in paths]
    sheet = Image.new("RGBA", (size * len(ims), size), (251, 246, 236, 255))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * size, 0), im)
    sheet.save(out)
    print(f"[pick] 비교표 → {out}")
    return out


def sheet(ref: str = KOKI, out: str = "assets/koki/koki_sheet.png") -> str | None:
    return imagegen.generate(f"{imagegen.STYLE}. Make {SHEET}.", out, refs=[ref], aspect="3:2")


def pick(n: int) -> None:
    src = os.path.join(OUT, f"cand_{n}.png")
    if not os.path.exists(src):
        raise SystemExit(f"[pick] {src} 없음 — 먼저 cands를 돌릴 것")
    dst = os.path.join(OUT, "pick_idle.png")
    shutil.copyfile(src, dst)
    print(f"[pick] 픽이 확정 ← {src}")
    sheet(dst, os.path.join(OUT, "pick_sheet.png"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "cands"
    if cmd == "cands":
        print(cands())
    elif cmd == "sheet":
        print(sheet())
    elif cmd == "pick":
        pick(int(sys.argv[2]))

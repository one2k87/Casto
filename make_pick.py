"""픽이(콕이의 룸메이트) 디자인 후보 3안 + 콕이 레퍼런스 시트 — 파일럿(블록 0) 1회 생성.

    python make_pick.py cands   # assets/pick/cand_{1,2,3}.png + contact.png
    python make_pick.py sheet   # assets/koki/koki_sheet.png (턴어라운드·표정)
    python make_pick.py cast    # 확정 배역(2026-10-12): 1안=아내, 2안=남편, 3안=안내 캐릭터 → assets/cast/
    python make_pick.py cats    # 실사 고양이 배역(2026-10-15): style.CANDS 로 3마리 + 시트 → assets/cast_photo/

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


# 사용자 확정(2026-10-12): 부부 = 1안(코랄·쇼핑백, 아내)·2안(라벤더·폰, 남편), 3안(버터·카드)은 콕픽 안내 캐릭터
# (설명·상품 안내·판정 도장). 이름은 사용자가 정한다 — 코드는 배역 키로만 부른다.
CAST = {"wife": 1, "husband": 2, "guide": 3}
CAST_DIR = "assets/cast"


def cast() -> list[str]:
    """후보 → 배역 고정 + 배역마다 레퍼런스 시트 1장. 이후 모든 장면 생성이 이 시트를 참고로 받는다."""
    os.makedirs(CAST_DIR, exist_ok=True)
    made = []
    for role, n in CAST.items():
        src = os.path.join(OUT, f"cand_{n}.png")
        if not os.path.exists(src):
            print(f"[cast] {src} 없음 — 건너뜀")
            continue
        idle = os.path.join(CAST_DIR, f"{role}_idle.png")
        shutil.copyfile(src, idle)
        made.append(idle)
        out = sheet(idle, os.path.join(CAST_DIR, f"{role}_sheet.png"))
        if out:
            made.append(out)
    return made


def cats() -> list[str]:
    """실사 컨셉(10/15): style.CANDS 설명으로 고양이 3마리를 한 번 생성하고, 각자 레퍼런스 시트를 만든다.
    참고 이미지 없이 첫 장을 뽑고(실사는 콕이 점토를 참고하면 안 된다), 시트는 그 첫 장을 참고로 만든다."""
    import style
    d = style.PRESETS["photo"]
    out_dir = d["cast_dir"]
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for role, desc in d["cands"].items():
        idle = os.path.join(out_dir, f"{role}_idle.png")
        if not os.path.exists(idle):
            prompt = (f"{d['look']}. A single real cat: {desc}. Sitting upright facing the camera, full body visible, "
                      f"plain light-gray studio background, eye-level, no text, no props other than described")
            if not imagegen.generate(prompt, idle, refs=[], aspect="1:1"):
                print(f"[cats] {role} 생성 실패")
                continue
        made.append(idle)
        sheet_prompt = (f"{d['look']}. A photographic reference sheet of the SAME cat from the reference image, "
                        f"3x2 grid on a plain light-gray background: front view sitting, 3/4 view, side view, back view, "
                        f"then front view surprised (wide eyes, open mouth), front view sulking (narrowed eyes, ears back). "
                        f"Identical breed, coat markings, eye color and collar/accessory in every cell. No text")
        out = imagegen.generate(sheet_prompt, os.path.join(out_dir, f"{role}_sheet.png"), refs=[idle], aspect="3:2")
        if out:
            made.append(out)
    if made:
        _contact([p for p in made if p.endswith("_idle.png")], os.path.join(out_dir, "contact.png"))
    return made


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
    elif cmd == "cast":
        print(cast())
    elif cmd == "cats":
        print(cats())
    elif cmd == "pick":
        pick(int(sys.argv[2]))

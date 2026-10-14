"""키프레임 — 대본 8컷을 장면 그림 8장으로. 모든 컷이 같은 참고 이미지(배역 시트·세트·점토 상품)를 받는다.

캐릭터 표류를 막는 장치가 셋이다. ① 배역 레퍼런스 시트를 매 컷 참고로 넣는다 ② 주방 세트는 한 번만 생성해 두고
(assets/cast/set_kitchen.png) 매 컷 참고로 넣는다 ③ 컷 8은 생성하지 않고 컷 1 그림을 그대로 쓴다(루프).
상품은 승인된 점토 버전(assets/clay/<slug>.png)만 참고로 넣고, 컷 6의 실물 사진은 생성에 넣지 않는다 —
실물은 렌더러가 카드로 얹는다(포맷 3판 컷 6).
"""
from __future__ import annotations

import os

import imagegen

CAST = "assets/cast"
SET = os.path.join(CAST, "set_kitchen.png")
CLAY_DIR = "assets/clay"
WORLD = ("the same cozy handmade clay kitchen set: cream walls, mint green counter, kraft-brown wooden table, "
         "small window with soft daylight, a few clay props (kettle, mug, fruit bowl)")


def ensure_set() -> str | None:
    if os.path.exists(SET):
        return SET
    prompt = (f"{imagegen.STYLE}. An empty stage set for a stop-motion sitcom: {WORLD}. Wide shot, eye level, "
              f"nobody in the scene, no text")
    return imagegen.generate(prompt, SET, refs=[os.path.join(CAST, "wife_idle.png")], aspect="9:16")


def refs_for(cut: dict, clay_product: str | None) -> list[str]:
    who = cut.get("who", "wife")
    refs = [os.path.join(CAST, f"{r}_sheet.png") for r in ("wife", "husband")]
    if who == "guide" or cut.get("n") == 6:
        refs = [os.path.join(CAST, "guide_sheet.png")]
    elif os.path.exists(SET):
        refs.append(SET)
    if cut.get("n") in (3, 4, 5) and clay_product and os.path.exists(clay_product):
        refs.append(clay_product)
    return [r for r in refs if os.path.exists(r)]


def prompt_for(cut: dict) -> str:
    n = cut.get("n")
    base = (f"{imagegen.STYLE}. One frame of a stop-motion clay sitcom. Use EXACTLY the characters from the reference "
            f"sheets (same colors, proportions, clay texture, dot eyes). ")
    if n == 6:
        return (base + "Plain cream studio backdrop (no kitchen). The guide character stands center-right holding up a "
                "blank white rectangular card (leave the card empty for compositing). Presenting pose. "
                f"Scene: {cut.get('scene', '')}. Vertical 9:16, character full body, no text")
    return (base + f"Location: {WORLD}. Scene: {cut.get('scene', '')}. "
            "If 'the clay toy product' appears, draw it exactly like the product reference image (a clay toy), "
            "never as a real photo. Vertical 9:16, medium shot, no text, no speech bubbles")


def build(script: dict, out_dir: str, clay_product: str | None = None) -> dict[int, str]:
    """{컷번호: 그림 경로}. 생성 실패한 컷은 빠진다(렌더러가 직전 컷으로 메운다)."""
    os.makedirs(out_dir, exist_ok=True)
    ensure_set()
    made: dict[int, str] = {}
    for cut in script.get("cuts", []):
        n = int(cut.get("n", 0))
        if n == 8:
            continue
        path = os.path.join(out_dir, f"kf{n}.png")
        if os.path.exists(path):
            made[n] = path
            continue
        if imagegen.generate(prompt_for(cut), path, refs=refs_for(cut, clay_product), aspect="9:16"):
            made[n] = path
    if 1 in made:
        made[8] = made[1]
    return made

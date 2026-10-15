"""키프레임 — 대본 8컷을 장면 그림 8장으로. 모든 컷이 같은 참고 이미지(배역 시트·세트·점토 상품)를 받는다.

캐릭터 표류를 막는 장치가 셋이다. ① 배역 레퍼런스 시트를 매 컷 참고로 넣는다 ② 주방 세트는 한 번만 생성해 두고
(assets/cast/set_kitchen.png) 매 컷 참고로 넣는다 ③ 컷 8은 생성하지 않고 컷 1 그림을 그대로 쓴다(루프).
상품은 승인된 점토 버전(assets/clay/<slug>.png)만 참고로 넣고, 컷 6의 실물 사진은 생성에 넣지 않는다 —
실물은 렌더러가 카드로 얹는다(포맷 3판 컷 6).
"""
from __future__ import annotations

import os

import imagegen

import style

CAST = style.CAST_DIR
SET = os.path.join(CAST, "set_kitchen.png")
WORLD = style.WORLD
# 파일럿 1~3호 실측(10/14~15): 디오라마가 작고 와이드샷이 많았고, 아내가 '동작'하는 컷에서 몸 형태가 표류했다.
# → 프레이밍과 캐릭터를 말로 못 박고(style.CAST_LOCK), 생성 뒤 시각 검사로 거른다. 참고 순서 고정(1=아내, 2=남편).
FRAMING = ("FRAMING: vertical 9:16 phone video. CLOSE framing — show only PART of the kitchen (one counter and a "
           "table edge); cropping furniture is fine. The characters' bodies fill at least 70% of the frame height, "
           "heads in the upper third. Camera at character eye level, standing inside the kitchen. "
           "NO wide shot of the whole room, NO miniature box, NO visible stage edges, NO empty floor area")
CAST_LOCK = style.CAST_LOCK


def ensure_set() -> str | None:
    if os.path.exists(SET):
        return SET
    prompt = (f"{style.LOOK}. An empty set for a sitcom: {WORLD}. Wide shot, eye level, nobody in the scene, no text")
    return imagegen.generate(prompt, SET, refs=[os.path.join(CAST, "wife_idle.png")], aspect="9:16")


def refs_for(cut: dict, clay_product: str | None) -> list[str]:
    who = cut.get("who", "wife")
    # 순서 고정: 1=아내 시트, 2=남편 시트, 3=세트, 4=점토 상품 — 프롬프트가 번호로 가리킨다
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
    base = (f"{style.LOOK}. One frame of a sitcom. Use EXACTLY the characters from the reference sheets "
            f"(same colors, markings, proportions). ")
    if n == 6:
        return (base + f"Plain light-gray studio backdrop (no kitchen). {style.GUIDE_DESC} sits upright in the LOWER "
                "HALF of the frame, full body, holding up a blank white rectangular card above its head with both "
                "front paws (card empty — it will be composited). "
                f"Scene: {cut.get('scene', '')}. Vertical 9:16, no text, no letters, no speech bubbles")
    return (base + f"{CAST_LOCK}. Location: {WORLD}. {FRAMING}. Scene: {cut.get('scene', '')}. "
            f"If '{style.PRODUCT_WORD}' appears, {style.PRODUCT_RULE}. No text, no speech bubbles")


# 일관성 관문(10/15): 3호에서 7컷 중 1컷(컷 3)이 여전히 길쭉한 분홍 캐릭터였다. 프롬프트만으로는 100%가 안 되니
# 생성 뒤 그림을 **검사**하고 틀리면 다시 뽑는다(최대 RETRIES회). 검사 비용은 장당 ₩1 안팎, 재생성은 ₩55.
RETRIES = 2
QA_QUESTION = style.QA_QUESTION


def passes(path: str, cut: dict) -> tuple[bool, str]:
    qa = imagegen.vision_check(path, QA_QUESTION)
    if qa is None:
        return True, "검사 생략"
    n = int(cut.get("n", 0))
    problems = []
    if n != 6:
        if qa.get("wife_ok") is False:
            problems.append("아내 형태")
        if qa.get("husband_ok") is False:
            problems.append("남편 형태")
        if qa.get("extra_person"):
            problems.append("제3 인물")
        if isinstance(qa.get("characters"), int) and qa["characters"] > 2:
            problems.append(f"인물 {qa['characters']}명")
        if qa.get("close_shot") is False:
            problems.append("와이드샷")
        if style.IS_PHOTO and qa.get("photoreal") is False:
            problems.append("실사 아님")
    if qa.get("has_text") and n != 6:          # 컷 6의 카드 글자는 실물 카드 오버레이가 덮는다(4호: 3회 모두 탈락 → 면제)
        problems.append("글자")
    return (not problems), ", ".join(problems) or "통과"


def build(script: dict, out_dir: str, clay_product: str | None = None) -> dict[int, str]:
    """{컷번호: 그림 경로}. 생성 실패한 컷은 빠진다(렌더러가 직전 컷으로 메운다). 검사 결과는 qa.json에 남긴다."""
    import json as _json
    os.makedirs(out_dir, exist_ok=True)
    ensure_set()
    made: dict[int, str] = {}
    qa_log: dict[str, list] = {}
    for cut in script.get("cuts", []):
        n = int(cut.get("n", 0))
        if n == 8:
            continue
        path = os.path.join(out_dir, f"kf{n}.png")
        if os.path.exists(path):
            made[n] = path
            continue
        best = None
        for attempt in range(RETRIES + 1):
            cand = os.path.join(out_dir, f"kf{n}_try{attempt}.png")
            if not imagegen.generate(prompt_for(cut), cand, refs=refs_for(cut, clay_product), aspect="9:16"):
                continue
            ok, why = passes(cand, cut)
            qa_log.setdefault(str(n), []).append({"attempt": attempt, "ok": ok, "why": why})
            print(f"[keyframes] 컷{n} 시도{attempt}: {why}")
            best = best or cand
            if ok:
                best = cand
                break
        if best:
            os.replace(best, path)
            made[n] = path
        for junk in [f for f in os.listdir(out_dir) if f.startswith(f"kf{n}_try")]:
            os.remove(os.path.join(out_dir, junk))          # 탈락한 시도는 남기지 않는다(저장소 부피)
    with open(os.path.join(out_dir, "qa.json"), "w", encoding="utf-8") as f:
        _json.dump(qa_log, f, ensure_ascii=False, indent=1)
    if 1 in made:
        made[8] = made[1]
    return made

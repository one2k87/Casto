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
# 파일럿 1호 실측(10/14): 디오라마가 화면 가운데 작게 앉아 세로 화면의 절반이 비었고, 컷 3·5에서 아내가
# 흰색·길쭉한 캐릭터로 표류했다. → 프레이밍과 캐릭터를 말로 못 박는다. 참고 이미지 순서도 고정(1=아내, 2=남편).
# 2호 실측(10/15): 방은 커졌지만 여전히 와이드샷이 절반, 아내가 '동작'하는 컷(3·4)에서 길쭉한 분홍 원통으로 변함.
# → 몸 형태를 기하로 못 박고("정육면체 vs 원통"), 와이드샷을 금지하고 가구를 잘라도 된다고 말한다.
FRAMING = ("FRAMING: vertical 9:16 phone video. CLOSE framing — show only PART of the kitchen (one counter and a "
           "table edge); cropping furniture is fine. The characters' bodies fill at least 70% of the frame height, "
           "heads in the upper third. Camera at character eye level, standing inside the kitchen. "
           "NO wide shot of the whole room, NO miniature box, NO visible stage edges, NO empty floor area")
CAST_LOCK = ("EXACTLY TWO characters, never a third, never swapped or recolored. "
             "WIFE = a CORAL-PINK CUBE: a boxy body as wide as it is tall, with short stubby arms and legs and big "
             "round glossy eyes (reference image 1). She is NEVER tall, NEVER a cylinder, NEVER slim. "
             "HUSBAND = the ONLY tall slim LAVENDER-PURPLE CYLINDER character with small dot eyes (reference image 2). "
             "Keep each body shape and color identical in every frame, even when they move or hold things")


def ensure_set() -> str | None:
    if os.path.exists(SET):
        return SET
    prompt = (f"{imagegen.STYLE}. An empty stage set for a stop-motion sitcom: {WORLD}. Wide shot, eye level, "
              f"nobody in the scene, no text")
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
    base = (f"{imagegen.STYLE}. One frame of a stop-motion clay sitcom. Use EXACTLY the characters from the reference "
            f"sheets (same colors, proportions, clay texture, dot eyes). ")
    if n == 6:
        return (base + "Plain cream studio backdrop (no kitchen). The GUIDE (butter-yellow boxy clay character, "
                "reference image 1) stands in the LOWER HALF of the frame, full body, holding up a blank white "
                "rectangular card above its head with both hands (card empty — it will be composited). "
                f"Scene: {cut.get('scene', '')}. Vertical 9:16, no text, no letters, no speech bubbles")
    return (base + f"{CAST_LOCK}. Location: {WORLD}. {FRAMING}. Scene: {cut.get('scene', '')}. "
            "If 'the clay toy product' appears, draw it exactly like the product reference image (a clay toy), "
            "never as a real photo. No text, no speech bubbles")


# 일관성 관문(10/15): 3호에서 7컷 중 1컷(컷 3)이 여전히 길쭉한 분홍 캐릭터였다. 프롬프트만으로는 100%가 안 되니
# 생성 뒤 그림을 **검사**하고 틀리면 다시 뽑는다(최대 RETRIES회). 검사 비용은 장당 ₩1 안팎, 재생성은 ₩55.
RETRIES = 2
QA_QUESTION = """이 그림은 클레이 시트콤의 한 컷이다. 다음을 JSON으로 답하라:
{"characters": 등장 캐릭터 수(정수), "wife_ok": 코랄/분홍 캐릭터가 '정육면체(네모 상자) 몸'이면 true, 길쭉하거나 원통이면 false,
 "husband_ok": 보라/라벤더 캐릭터가 '길쭉한 원통 몸'이면 true (없으면 true), "extra_person": 코랄·라벤더 외 다른 인물이 있으면 true,
 "has_text": 그림 안에 글자·숫자가 있으면 true, "close_shot": 캐릭터가 화면 높이의 절반 이상을 차지하면 true}"""


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

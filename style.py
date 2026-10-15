"""비주얼 스타일 프리셋 — 사용자 결정(2026-10-15): "클레이보다는 실사로. 실사지만 현실에선 볼 수 없는 컨셉.
클레이 캐릭터를 실사 고양이로, 제품도 실사에 가깝게."

`CASTO_STYLE=photo`(기본) 또는 `clay`. 키프레임·캐릭터 생성·시각 검사·상품 묘사가 전부 이 프리셋을 읽는다.

⚠️ 정직 규칙 개정(10/15): 상품의 '실사풍 생성 이미지'는 원래 절대 금지였다("가상으로 재현하면 시청자가 돌아선다").
사용자가 실사 컨셉을 지시했으므로 허용하되 **세 가지 안전장치**를 건다.
  ① 생성은 반드시 실제 판매 사진을 참고로 받고, 시각 검사가 "같은 물건(색·형태·부품)"이라고 판정한 것만 쓴다
  ② 컷 6의 실물 카드는 여전히 **실제 판매 사진**이다 — 진실의 닻
  ③ 설명란에 "장면은 AI로 연출, 상품 사진은 실제 판매 이미지" 한 줄 + 유튜브 '변경/합성 콘텐츠' 표시
"""
from __future__ import annotations

import os

NAME = os.getenv("CASTO_STYLE", "photo")

PRESETS = {
    "clay": {
        "cast_dir": "assets/cast",
        "product_dir": "assets/clay",
        "look": ("3D clay / plasticine illustration, soft matte texture, rounded soft edges, kawaii, "
                 "studio soft lighting with gentle shadows, pastel palette: mint #B0E0D2, cream #FBF6EC, "
                 "sage #2F5D4E, kraft brown #D6B282, no text, no letters, no watermark"),
        "world": ("the same cozy handmade clay kitchen set: cream walls, mint green counter, kraft-brown wooden "
                  "table, small window with soft daylight, a few clay props (kettle, mug, fruit bowl)"),
        "cast_lock": ("EXACTLY TWO characters, never a third, never swapped or recolored. WIFE = a CORAL-PINK CUBE "
                      "with short stubby arms and big round glossy eyes (reference image 1); never tall, never a "
                      "cylinder. HUSBAND = the ONLY tall slim LAVENDER-PURPLE CYLINDER character with small dot eyes "
                      "(reference image 2). Keep each body shape and color identical in every frame"),
        "guide_desc": "the GUIDE (butter-yellow boxy clay character, reference image 1)",
        "product_word": "the clay toy product",
        "product_rule": "draw it exactly like the product reference image (a clay toy), never as a real photo",
        "qa": """이 그림은 클레이 시트콤의 한 컷이다. JSON으로 답하라:
{"characters": 등장 캐릭터 수(정수), "wife_ok": 코랄/분홍 캐릭터가 '정육면체(네모 상자) 몸'이면 true, 길쭉하거나 원통이면 false,
 "husband_ok": 보라/라벤더 캐릭터가 '길쭉한 원통 몸'이면 true (없으면 true), "extra_person": 코랄·라벤더 외 다른 인물이 있으면 true,
 "has_text": 그림 안에 글자·숫자가 있으면 true, "close_shot": 캐릭터가 화면 높이의 절반 이상을 차지하면 true}""",
        "cands": {},
    },
    "photo": {
        "cast_dir": "assets/cast_photo",
        "product_dir": "assets/photo_products",
        "look": ("photorealistic, shot on a 35mm full-frame camera, 50mm lens, natural window daylight, shallow depth "
                 "of field, true-to-life fur and skin textures, realistic color, subtle film grain, no text, no letters, "
                 "no watermark, no cartoon, no illustration"),
        "world": ("the same real Korean apartment kitchen: white cabinets, light wood countertop, a window with soft "
                  "morning light over the sink, a small wooden dining table, real everyday props (kettle, mugs, fruit "
                  "bowl, dish rack). The cats live here like people: they stand on their hind legs at the counter, "
                  "hold things with their paws, sit on chairs at the table"),
        "cast_lock": ("EXACTLY TWO cats, never a third animal, never a human, never swapped. "
                      "WIFE = the small ORANGE TABBY cat with big round green eyes and a thin white collar with a tiny "
                      "pink bell (reference image 1). HUSBAND = the bigger GRAY (blue) British Shorthair cat with "
                      "copper-orange eyes and a navy bandana (reference image 2). Keep each cat's breed, coat color, "
                      "eye color and collar identical in every frame"),
        "guide_desc": ("the GUIDE: a fluffy CREAM-WHITE Ragdoll cat with blue eyes wearing small round glasses and a "
                       "mustard-yellow bow tie (reference image 1)"),
        "product_word": "the real product",
        "product_rule": ("render it EXACTLY like the product reference photo — same shape, color, proportions, parts, "
                         "material and branding placement — as a real physical object in the scene; never invent features"),
        "qa": """이 사진은 고양이 부부 시트콤의 한 컷이다. JSON으로 답하라:
{"characters": 등장 동물·사람 수(정수), "wife_ok": '주황색 태비 고양이(흰 목걸이)'가 있고 작은 쪽이면 true, 없거나 색이 다르면 false,
 "husband_ok": '회색 브리티시숏헤어 고양이(남색 반다나)'가 있거나(없으면 true), 다른 색이면 false, "extra_person": 고양이 두 마리 외의 동물이나 사람이 있으면 true,
 "has_text": 사진 안에 글자·숫자가 있으면 true, "close_shot": 고양이가 화면 높이의 절반 이상을 차지하면 true, "photoreal": 실사 사진처럼 보이면 true, 그림/만화면 false}""",
        # 캐릭터 후보(1회 생성). 색·눈·소품이 식별자다 — 시각 검사가 이걸로 같은 고양이인지 본다.
        "cands": {
            "wife": "a small orange tabby cat, big round green eyes, thin white collar with a tiny pink bell, curious lively expression",
            "husband": "a big gray (blue) British Shorthair cat, copper-orange eyes, navy bandana, calm deadpan expression",
            "guide": "a fluffy cream-white Ragdoll cat, blue eyes, small round glasses, mustard-yellow bow tie, tidy presenter look",
        },
    },
}

P = PRESETS.get(NAME, PRESETS["photo"])
CAST_DIR = P["cast_dir"]
PRODUCT_DIR = P["product_dir"]
LOOK = P["look"]
WORLD = P["world"]
CAST_LOCK = P["cast_lock"]
GUIDE_DESC = P["guide_desc"]
PRODUCT_WORD = P["product_word"]
PRODUCT_RULE = P["product_rule"]
QA_QUESTION = P["qa"]
CANDS = P["cands"]
IS_PHOTO = NAME == "photo"

PRODUCT_QA = """두 사진을 비교하라. 첫 번째는 실제 판매 사진, 두 번째는 생성된 장면이다. JSON으로 답하라:
{"same_product": 두 사진의 물건이 같은 제품(같은 형태·색·비율·부품 구성)으로 보이면 true, "diff": 다른 점을 한국어 한 줄(없으면 ""),
 "photoreal": 두 번째가 실사 사진처럼 보이면 true}"""

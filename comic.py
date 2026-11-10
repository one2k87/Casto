"""인과 만화 2컷 — "왜 갑자기 이게 보이지?"를 그림 두 장으로 답한다.

포맷 2판의 심장이다(docs/콕픽_쇼츠_포맷_2판.md 2절).
글로 "피스타치오가 유행입니다"라고 쓰면 아무도 안 본다. **원인 → 결과**를 보여주면
시청자가 "아 그래서"를 경험하고, 그 경험이 묶음 영상이 못 하는 유일한 차별점이다.

  컷1(원인)  두쫀쿠가 유행           컷2(결과)  피스타치오 품귀
             ↓                                  ↓
                        그래서 이게 보인다

━━━ 절대 규칙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    **상품 자체는 절대 그리지 않는다.**

    "절대로 제품을 가상으로 재현하면 안 돼. 그 즉시 시청자는 바로 돌아설 거야."
                                                        — 2026-09-08

상품은 실사진만 쓴다(catalog.render_mode). 만화가 그리는 건 **유행의 원인과 상황**뿐이다
— 다른 유행 음식, 매대, 사람, 계절, 검색 그래프 같은 것. 만화가 상품 모양을 그리는 순간
2026-09-08에 삭제한 ai_render와 같은 위반이 된다. 그래서 프롬프트를 만들 때
상품명이 섞여 들어오면 `ProductDrawAttempt`로 **터뜨린다**(조용히 넘기지 않는다).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

키가 없거나 생성이 실패하면 도형 인과카드로 폴백한다 — 발행은 멈추지 않는다.
"""
import base64
import json
import os
import re

import requests
from PIL import Image, ImageDraw

W, H = 1080, 1920
PANEL = (W, H)                           # 만화 컷은 화면 전체를 채운다(2026-09-10 개편)
# 이미지 생성 API는 형식이 두 가지다. 어느 쪽이 살아 있는지 **여기서 확인할 방법이 없어서**
# (키가 GitHub 시크릿에만 있다) 둘 다 시도하고, 통한 쪽을 로그로 남긴다.
#   ① /v1beta/interactions            + gemini-3.1-flash-image  (신형, 문서 기준)
#   ② /v1beta/models/{}:generateContent + gemini-2.5-flash-image (구형, responseModalities)
IMAGE_MODELS = [m for m in (os.getenv("IMAGE_MODEL"), "gemini-3.1-flash-image",
                            "gemini-2.5-flash-image") if m]
INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"
GENERATE = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

STYLE = (
    "3D clay / plasticine illustration, soft matte texture, rounded soft edges, kawaii, "
    "studio soft lighting with gentle shadows, "
    "pastel palette: mint #B0E0D2, cream #FBF6EC, sage #2F5D4E, kraft brown #D6B282, "
    "flat simple composition, single clear idea, no text, no letters, no numbers, "
    "no watermark, no logo"
)

# 상품을 그리려는 시도를 잡아내는 말들 — 생성 프롬프트에 들어오면 안 된다
_PRODUCT_WORDS = ("상품", "제품", "이 물건", "product shot", "the product")


class ProductDrawAttempt(RuntimeError):
    """만화 프롬프트가 상품 자체를 그리려 했다. 조용히 넘기면 안 되는 위반이다."""


def guard(prompt: str, product: str) -> str:
    """상품명이 프롬프트에 섞였는지 확인한다. 섞였으면 터뜨린다.

    LLM이 원인/결과를 쓰면서 상품명을 그대로 넣는 일이 실제로 잦다
    ("피스타치오 분태기가 많이 팔린다"). 그 문장이 그림 프롬프트가 되면
    모델은 그 물건을 그린다 — 실물과 다른 그림이 화면에 나가는 것이 정확히 금지 대상이다.
    """
    low = prompt.lower()
    name = (product or "").strip()
    if name and name.lower() in low:
        raise ProductDrawAttempt(f"만화 프롬프트에 상품명이 들어 있다: {name!r}")
    for w in _PRODUCT_WORDS:
        if w.lower() in low:
            raise ProductDrawAttempt(f"만화 프롬프트에 상품 지시어가 있다: {w!r}")
    return prompt


def scrub(text: str, product: str) -> str:
    """원인/결과 문장에서 상품명을 지운다 — guard에 걸리기 전에 미리 치운다.

    지우면 문장이 어색해질 수 있지만, 어색한 그림이 틀린 그림보다 낫다.
    """
    out = (text or "").strip()
    name = (product or "").strip()
    if name:
        out = re.sub(re.escape(name), "이것", out, flags=re.I)
    for w in _PRODUCT_WORDS:
        out = re.sub(re.escape(w), "이것", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


def _prompt(scene: str, product: str) -> str:
    p = (f"{STYLE}. A single clay-art scene showing: {scene}. "
         "Do not draw any specific branded merchandise or packaged goods as the subject. "
         "Vertical 4:3 framing, centered, empty margin at the bottom for a subtitle.")
    return guard(p, product)


def _decode(payload: dict) -> str | None:
    """두 응답 형식 모두에서 base64 이미지를 꺼낸다."""
    # ① interactions: steps[].content[] {type:"image", data:...}
    for step in payload.get("steps", []) or []:
        for part in step.get("content", []) or []:
            if part.get("type") == "image" and part.get("data"):
                return part["data"]
    # ② generateContent: candidates[].content.parts[] {inlineData:{data:...}}
    for cand in payload.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
            if data:
                return data
    return None


def _attempts(prompt: str):
    """(설명, URL, 바디) 순서대로 — 앞의 것이 실패하면 다음으로 넘어간다."""
    for model in IMAGE_MODELS:
        if model.startswith("gemini-3"):
            yield (f"interactions/{model}", INTERACTIONS, {
                "model": model,
                "input": [{"type": "text", "text": prompt}],
                # 11/8·11/9 실측: interactions 는 'image/png' 를 400으로 거절한다("Supported values: 'image/jpeg'")
                "response_format": {"type": "image", "mime_type": "image/jpeg",
                                    "aspect_ratio": "4:3", "image_size": "1K"}})
        else:
            yield (f"generateContent/{model}", GENERATE.format(model), {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE"]}})


CF_MODEL = "@cf/black-forest-labs/flux-1-schnell"
CF_RUN = "https://api.cloudflare.com/client/v4/accounts/{}/ai/run/" + CF_MODEL


def paid_allowed() -> bool:
    """Gemini 이미지(유료)는 `IMAGE_ALLOW_PAID=1` 일 때만 — 기본은 끔(2026-11-09 사용자 승인: 이미지 무료화)."""
    return os.getenv("IMAGE_ALLOW_PAID", "").strip().lower() in ("1", "true", "yes", "on")


def _save(raw: bytes, out_path: str) -> str | None:
    """받은 바이트(JPEG/PNG 무엇이든)를 **실제 PNG** 로 저장 — 확장자와 내용이 어긋나지 않게."""
    import io
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception as e:                               # noqa: BLE001
        print(f"[comic] 이미지 디코딩 실패: {e}")
        return None
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    im.convert("RGB").save(out_path)
    return out_path


def cf_generate(prompt: str, out_path: str, timeout: int = 120) -> str | None:
    """Cloudflare Workers AI FLUX-1-schnell(무료 일일 할당) 한 장. 키가 없으면 조용히 None.

    REST: POST /accounts/{id}/ai/run/@cf/black-forest-labs/flux-1-schnell, Bearer 토큰,
    입력 {prompt(≤2048자), steps(≤8)} → 응답 result.image(base64). 2026-11-10 문서 확인.
    """
    acc, tok = os.getenv("CF_ACCOUNT_ID", "").strip(), os.getenv("CF_API_TOKEN", "").strip()
    if not (acc and tok):
        return None
    try:
        r = requests.post(CF_RUN.format(acc), json={"prompt": prompt[:2048], "steps": 4},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=timeout)
    except Exception as e:                               # noqa: BLE001
        print(f"[comic] cf/flux-1-schnell 예외: {e}")
        return None
    if r.status_code != 200:
        print(f"[comic] cf/flux-1-schnell 실패 {r.status_code}: {r.text[:160]}")
        return None
    try:
        j = r.json()
        data = (j.get("result") or {}).get("image") or j.get("image")
    except Exception as e:                               # noqa: BLE001
        print(f"[comic] cf/flux-1-schnell 응답 파싱 실패: {e}")
        return None
    if not data:
        print("[comic] cf/flux-1-schnell 응답에 이미지가 없다")
        return None
    got = _save(base64.b64decode(data), out_path)
    if got:
        print("[comic] ✅ cf/flux-1-schnell 로 생성(무료)")
    return got


def generate(scene: str, product: str, out_path: str, timeout: int = 120) -> str | None:
    """클레이 만화 컷 한 장. 순서: ① CF FLUX(무료) ② IMAGE_ALLOW_PAID=1 일 때만 Gemini(유료) ③ None(호출부 폴백)."""
    try:
        prompt = _prompt(scene, product)
    except ProductDrawAttempt as e:
        print(f"[comic] ⛔ {e} — 이 컷은 만들지 않는다(폴백)")
        return None

    got = cf_generate(prompt, out_path, timeout=timeout)
    if got:
        return got
    if not paid_allowed():
        print("[comic] 무료 생성 실패/키 없음 — 유료 Gemini 이미지는 꺼져 있음(IMAGE_ALLOW_PAID) → 폴백 카드")
        return None
    key = os.getenv("LLM_API_KEY_PAID") or os.getenv("LLM_API_KEY", "")   # 11/9 키 분배: 이미지는 유료 우선
    if not key:
        return None
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    for label, url, body in _attempts(prompt):
        try:
            r = requests.post(url, json=body, timeout=timeout, headers=headers)
        except Exception as e:                               # 네트워크
            print(f"[comic] {label} 예외: {e}")
            continue
        if r.status_code != 200:
            print(f"[comic] {label} 실패 {r.status_code}: {r.text[:160]}")
            continue
        try:
            data = _decode(r.json())
        except Exception as e:
            print(f"[comic] {label} 응답 파싱 실패: {e}")
            continue
        if not data:
            print(f"[comic] {label} 응답에 이미지가 없다")
            continue
        if _save(base64.b64decode(data), out_path):
            print(f"[comic] ✅ {label} 로 생성(유료)")
            return out_path
    return None


# ---------------------------------------------------------------- 폴백(도형 인과카드)
def fallback(scene: str, brand: dict, out_path: str, font=None, badge: str = "") -> str:
    """생성이 안 될 때의 대체 컷 — **그림 자리만 비워 둔다.**

    예전엔 이 카드가 문구를 크게 적었는데, 화면 쪽에서도 같은 문구를 자막으로 얹어
    **같은 말이 두 번** 나왔다(2026-09-10 렌더 실측). 자막은 화면이 책임지므로
    여기서는 글자를 그리지 않는다 — 부드러운 바탕만 둔다.
    """
    cream, mint = tuple(brand["cream"]), tuple(brand["mint"])
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):                                       # 세로 그라데이션(화면 전체용)
        t = y / H
        d.line([(0, y), (W, y)],
               fill=tuple(int(mint[j] + (cream[j] - mint[j]) * t) for j in range(3)))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    return out_path


def panels(item: dict, brand: dict, out_dir: str = "out", font=None) -> list[dict]:
    """한 상품의 인과 2컷. 반환: [{"path", "caption", "badge", "generated"}, ...]

    item = {"name", "cause", "effect", "cause_scene", "effect_scene"}
      - cause/effect      : 화면 자막(사람이 읽는 한 줄)
      - *_scene           : 그림 지시문(영어·상황 묘사, 상품 언급 금지)
    """
    product = item.get("name", "")
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", product)[:40] or "item"
    out = []
    for kind, badge in (("cause", "왜?"), ("effect", "그래서")):
        scene = scrub(item.get(f"{kind}_scene") or item.get(kind, ""), product)
        cap = item.get(kind, "")
        p = f"{out_dir}/comic_{slug}_{kind}.png"
        got = generate(scene, product, p)
        if got is None:
            got = fallback(scrub(cap, product) or scene, brand, p, font=font, badge=badge)
            gen = False
        else:
            gen = True
        out.append({"path": got, "caption": cap, "badge": badge, "generated": gen})
    return out

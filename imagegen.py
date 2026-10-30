"""참고 이미지를 넣는 이미지 생성 — 캐릭터·점토 상품·장면 키프레임의 공통 바닥.

`comic.py`는 글→그림(참고 없음)이고 상품을 그리면 막는다. 여기는 반대다: **참고 이미지를 넣어**
같은 캐릭터를 다시 그리고(픽이·콕이 레퍼런스 시트), 실사진을 참고해 점토 상품을 만들고(2026-10-12
규칙 개정: 점토 버전 허용·실물 컷 필수), 그 둘을 참고로 장면 키프레임을 그린다.

API는 두 형식을 차례로 시도한다(comic.py와 같은 이유 — 키가 시크릿에만 있어 여기서 못 확인한다):
  ① interactions + gemini-3.1-flash-image   ② generateContent + gemini-2.5-flash-image(inline_data)
통한 쪽을 로그로 남긴다. 키가 없으면 None — 호출부가 폴백한다.
"""
from __future__ import annotations

import base64
import os

import requests

import comic

STYLE = comic.STYLE
CLAY_PRODUCT_STYLE = (
    "a cute, simplified clay/plasticine toy version of the object in the reference photo: "
    "keep the SAME overall shape, proportions, main colors and distinctive parts so it is clearly "
    "recognizable as the same object, but render it as soft handmade clay with rounded edges and "
    "fingerprint-like matte texture. Toy-like, charming, not photorealistic. "
    "Single object centered on a plain pastel background, no text, no logo, no hands, no people"
)


def _b64(path: str) -> tuple[str, str]:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    mime = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    return data, mime


def _attempts(prompt: str, refs: list[str], aspect: str):
    parts_i = [{"type": "text", "text": prompt}]
    parts_g = [{"text": prompt}]
    for p in refs:
        data, mime = _b64(p)
        parts_i.append({"type": "image", "data": data, "mime_type": mime})
        parts_g.append({"inline_data": {"mime_type": mime, "data": data}})
    for model in comic.IMAGE_MODELS:
        if model.startswith("gemini-3"):
            yield (f"interactions/{model}", comic.INTERACTIONS, {
                "model": model, "input": parts_i,
                "response_format": {"type": "image", "mime_type": "image/png",
                                    "aspect_ratio": aspect, "image_size": "1K"}})
        else:
            yield (f"generateContent/{model}", comic.GENERATE.format(model), {
                "contents": [{"parts": parts_g}],
                "generationConfig": {"responseModalities": ["IMAGE"],
                                     "imageConfig": {"aspectRatio": aspect}}})


def generate(prompt: str, out_path: str, refs: list[str] | None = None, aspect: str = "1:1",
             timeout: int = 180) -> str | None:
    key = os.getenv("VEO_API_KEY") or os.getenv("LLM_API_KEY", "")   # 이미지 생성은 유료 → 선불 프로젝트 키(10/26 키 분리)
    if not key:
        print("[imagegen] VEO_API_KEY/LLM_API_KEY 없음 — 생성 건너뜀")
        return None
    refs = [p for p in (refs or []) if os.path.exists(p)]
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    for label, url, body in _attempts(prompt, refs, aspect):
        try:
            r = requests.post(url, json=body, timeout=timeout, headers=headers)
        except Exception as e:  # noqa: BLE001
            print(f"[imagegen] {label} 예외: {e}")
            continue
        if r.status_code != 200:
            print(f"[imagegen] {label} 실패 {r.status_code}: {r.text[:200]}")
            continue
        try:
            data = comic._decode(r.json())
        except Exception as e:  # noqa: BLE001
            print(f"[imagegen] {label} 파싱 실패: {e}")
            continue
        if not data:
            print(f"[imagegen] {label} 응답에 이미지 없음")
            continue
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        print(f"[imagegen] ✅ {label} → {out_path} (참고 {len(refs)}장)")
        return out_path
    return None


def clay_product(photo: str, name: str, out_path: str) -> str | None:
    """실사진 → 점토 상품 1장. 이름은 힌트로만 — 글자·로고는 그리지 않는다."""
    prompt = f"{STYLE}. Make {CLAY_PRODUCT_STYLE}. The object is a {name}."
    return generate(prompt, out_path, refs=[photo], aspect="1:1")


# ---------------------------------------------------------------- 시각 검사(키프레임 일관성 관문)
def vision_check(path, question: str, timeout: int = 90) -> dict | None:
    """그림(한 장 또는 여러 장)에 대해 JSON 답을 받는다 — 일관성 관문·상품 대조용. 키 없으면 None(검사 생략)."""
    import json as _json
    key = os.getenv("LLM_API_KEY", "")
    paths = [path] if isinstance(path, str) else list(path)
    if not key or not all(os.path.exists(x) for x in paths):
        return None
    from common import DEFAULT_MODEL
    model = os.getenv("LLM_MODEL") or DEFAULT_MODEL
    parts = [{"text": question + "\n\n[출력] 순수 JSON만."}]
    for x in paths:
        data, mime = _b64(x)
        parts.append({"inline_data": {"mime_type": mime, "data": data}})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0,
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        r = requests.post(comic.GENERATE.format(model), json=body, timeout=timeout,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code != 200:
            print(f"[vision] 실패 {r.status_code}: {r.text[:120]}")
            return None
        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if txt.startswith("```"):
            txt = txt.split("```")[1].lstrip("json").strip()
        return _json.loads(txt)
    except Exception as e:  # noqa: BLE001
        print(f"[vision] 예외: {e}")
        return None


def photo_product(photo: str, name: str, out_path: str, retries: int = 2) -> str | None:
    """실사 컨셉(10/15): 실제 판매 사진을 참고로 '같은 물건'을 실사풍으로 한 장 — 흰 배경 스튜디오 컷.
    시각 검사가 "같은 제품"이라고 해야 채택. 두 번 실패하면 None → 렌더러는 실물 카드만 쓴다."""
    import style
    prompt = (f"{style.LOOK}. A product photo of {name}: {style.PRODUCT_RULE}. Plain white seamless background, "
              f"soft studio light, the object centered and fully visible, no hands, no text")
    for i in range(retries + 1):
        cand = f"{out_path}.try{i}.png"
        if not generate(prompt, cand, refs=[photo], aspect="1:1"):
            continue
        qa = vision_check([photo, cand], style.PRODUCT_QA)
        ok = qa is None or (qa.get("same_product") and qa.get("photoreal", True))
        print(f"[imagegen] 상품 대조 시도{i}: {'통과' if ok else (qa or {}).get('diff') or '불일치'}")
        if ok:
            os.replace(cand, out_path)
            for j in range(retries + 1):
                try: os.remove(f"{out_path}.try{j}.png")
                except OSError: pass
            return out_path
    return None

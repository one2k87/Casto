"""파일럿(블록 0) — 상품 하나로 「콕이네 집」 한 편을 끝까지 만든다.

    python pilot.py <slug> [--no-veo] [--no-llm]

순서: 카탈로그 상품 → 점토 상품(없으면 생성, assets/clay/<slug>.png; 승인은 사람이 보고 한다) → 대본(정직 검사·폴백)
→ 키프레임 7장(+루프) → 렌더(Veo Lite 또는 Ken Burns) → pilot/<date>/ 에 대본·키프레임·영상·캡션·리포트 저장.
발행은 하지 않는다 — 사용자가 보고 "이 정도면 된다"를 말해야 매일 발행 파이프라인에 붙인다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

import clay_script
import imagegen
import keyframes
import render_clay
from common import cfg, op_date

import style

CLAY_DIR = style.PRODUCT_DIR


def product_from_catalog(slug: str) -> dict:
    with open("data/catalog.json", encoding="utf-8") as f:
        cat = json.load(f)
    p = cat["products"].get(slug)
    if not p:
        raise SystemExit(f"[pilot] 카탈로그에 {slug} 없음")
    return {"slug": slug, **p}


def ensure_clay(product: dict) -> str | None:
    path = os.path.join(CLAY_DIR, f"{product['slug']}.png")
    if os.path.exists(path):
        return path
    photo = product.get("image")
    if not photo or not os.path.exists(photo):
        print("[pilot] 실사진이 없어 점토 상품을 만들 수 없다")
        return None
    if style.IS_PHOTO:
        return imagegen.photo_product(photo, product.get("display", ""), path)
    return imagegen.clay_product(photo, product.get("display", ""), path)


def evidence_for(product: dict) -> dict:
    """우리 데이터에서 판정 근거. 없는 건 None — 추정하지 않는다."""
    ev = {"price_band": product.get("price_band") or None, "search_trend": None, "mentions": None,
          "blog_verdict": None}
    try:
        import evidence as evm
        b = evm.brief(product.get("display", ""))
        m = b.get("mentions") or b.get("count")
        if isinstance(m, (int, float)):
            ev["mentions"] = int(m)
        trend = b.get("trend") or b.get("direction")
        if trend in ("up", "down", "flat"):
            ev["search_trend"] = trend
    except Exception as e:  # noqa: BLE001
        print(f"[pilot] 근거 조회 실패(무시): {e}")
    return ev


def main(argv: list[str]) -> None:
    slug = argv[0] if argv else "계란-흰자-분리기"
    allow_veo = "--no-veo" not in argv
    use_llm = "--no-llm" not in argv
    c = cfg()
    today = str(op_date())          # op_date는 date 객체 — 경로엔 문자열
    # 같은 날 두 번 돌리면 키프레임을 재사용해 버린다(10/14 2호 사고 방지) — 실행마다 새 폴더
    run_id = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%H%M")
    out = os.path.join("pilot", f"{today}_{run_id}")
    os.makedirs(out, exist_ok=True)

    product = product_from_catalog(slug)
    clay = ensure_clay(product)
    ev = evidence_for(product)
    script = clay_script.build(product, ev, use_llm=use_llm)
    names = (c.get("cast") or {}).get("names")
    script_named = clay_script.substitute_names(script, names)
    with open(os.path.join(out, "script.json"), "w", encoding="utf-8") as f:
        json.dump(script_named, f, ensure_ascii=False, indent=1)

    frames = keyframes.build(script_named, os.path.join(out, "keyframes"), clay)
    if not frames:
        raise SystemExit("[pilot] 키프레임이 한 장도 없다 — LLM_API_KEY·이미지 생성 로그 확인")
    res = render_clay.render(script_named, frames, product, out_dir=os.path.join(out, "render"), allow_veo=allow_veo)
    shutil.copyfile(res["video"], os.path.join(out, "short.mp4"))
    cap = render_clay.caption(script_named, product, c["disclosure"]["coupang"])
    with open(os.path.join(out, "caption.txt"), "w", encoding="utf-8") as f:
        f.write(cap)
    report = {"date": today, "slug": slug, "product": product.get("display"), "clay": clay,
              "fallback_script": bool(script.get("fallback")), "stamp": script.get("stamp"),
              "reason": script.get("reason"), "keyframes": sorted(frames), "seconds": res["seconds"],
              "sources": res["sources"], "dropped": res["dropped"], "durations": res["durations"],
              "veo_spent_usd": __import__("veo").spent()}
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    try:
        from common import telegram_video
        telegram_video(os.path.join(out, "short.mp4"),
                       f"🎬 파일럿 「콕이네 집」 {product.get('display')} — {res['seconds']}초, 판정 {script.get('stamp')}"
                       f"{' (폴백 대본)' if script.get('fallback') else ''}")
    except Exception as e:  # noqa: BLE001
        print(f"[pilot] 텔레그램 실패(무시): {e}")


if __name__ == "__main__":
    main(sys.argv[1:])

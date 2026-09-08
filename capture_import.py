"""캡처 반입 — 사람이 직접 캡처한 **실제 상품 사진**만 카탈로그에 넣는다.

왜 이 방식인가(2026-09-08 사용자 결정):
  "절대로 제품을 가상으로 재현하면 안 돼. 그 즉시 시청자는 바로 돌아설 거야."

맞는 판단이다. 커머스 채널의 자산은 신뢰 하나뿐이고, 시청자는 실물과 다른 그림을 즉시 알아본다.
그래서 **AI 재현 경로는 폐기**했다. 이미지는 실제 사진만 쓰고, 없으면 그냥 안 쓴다.

자동화의 위치가 바뀐 것이지 사라진 게 아니다 — 사람은 **캡처를 폴더에 넣는 것까지만** 하고,
이름 정리·등록·누끼·배치·자막 반영은 전부 코드가 한다.
"""
from __future__ import annotations

import os
import re
import shutil
import sys

import catalog

INBOX = os.path.join(catalog.IMAGE_DIR, "캡처_넣는곳")
EXTS = (".png", ".jpg", ".jpeg", ".webp")
SOURCE = "capture"          # 사람이 직접 캡처한 실제 상품 사진


def split_name(stem: str) -> tuple[str, str]:
    """파일명 → (브랜드, 나머지). 첫 토큰을 브랜드로 본다.

    "락앤락 접이식 실리콘 밀폐용기 800ml" → ("락앤락", "접이식 실리콘 밀폐용기 800ml")
    토큰이 하나뿐이면 브랜드를 비운다 — **추측해서 브랜드를 만들지 않는다.**
    """
    parts = re.split(r"\s+", stem.strip())
    if len(parts) < 2:
        return "", stem.strip()
    return parts[0], " ".join(parts[1:])


def scan(inbox: str = INBOX) -> list[str]:
    if not os.path.isdir(inbox):
        return []
    return sorted(os.path.join(inbox, f) for f in os.listdir(inbox)
                  if f.lower().endswith(EXTS) and not f.startswith("."))


def import_one(cat: dict, path: str, today: str = "") -> str:
    """캡처 1장을 카탈로그에 등록하고 파일을 assets/products/로 옮긴다."""
    stem = os.path.splitext(os.path.basename(path))[0]
    brand, model = split_name(stem)
    slug = catalog.put(cat, name=stem, brand=brand, model=model, category=model or stem,
                       image_source=SOURCE, updated=today)
    dest = os.path.join(catalog.IMAGE_DIR, slug + os.path.splitext(path)[1].lower())
    os.makedirs(catalog.IMAGE_DIR, exist_ok=True)
    shutil.move(path, dest)
    cat["products"][slug]["image"] = dest
    return slug


def main():
    today = __import__("datetime").date.today().isoformat()
    cat = catalog.load()
    files = scan()
    done = [import_one(cat, f, today) for f in files]
    if done:
        cat["updated"] = today
        catalog.save(cat)
    for s in done:
        print(f"[capture] 등록 — {cat['products'][s]['display']} → {cat['products'][s]['image']}")
    total = len(cat.get("products", {}))
    have = sum(1 for e in cat["products"].values() if catalog.image_path(e))
    print(f"[capture] 반입 {len(done)}건 · 카탈로그 {total}건 중 사진 보유 {have}건")
    if have < total:
        print(f"[capture] 사진이 없는 {total - have}건은 제품 이미지 없이 나간다(가짜를 쓰지 않는다).")
        print(f"[capture] 필요 목록: python catalog.py  →  out/이미지_요청서.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

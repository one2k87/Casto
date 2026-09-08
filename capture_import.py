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

INBOX = catalog.INBOX_DIR
NUMBERED = re.compile(r"^(\d{1,4})\s*번?\s*[-_.]?\s*(.*)$")
EXTS = (".png", ".jpg", ".jpeg", ".webp")
SOURCE = "capture"          # 사람이 직접 캡처한 실제 상품 사진


def read_stem(stem: str, q: dict) -> tuple[str, int | None]:
    """파일명 → (제품명, 번호). **번호만 적어도 동작한다.**

    `3.png` → 번호표 3번의 제품. `3 락앤락 밀폐용기.png` → 번호 3 + 직접 적은 이름(이름 우선).
    번호가 없으면 파일명 전체를 제품명으로 본다.
    """
    m = NUMBERED.match(stem.strip())
    if not m:
        return stem.strip(), None
    n, rest = int(m.group(1)), m.group(2).strip()
    if rest:
        return rest, n
    it = catalog.by_number(q, n)
    # 번호표에 없는 번호를 이름으로 삼으면 "99"라는 이름의 제품이 생긴다 → 빈 이름으로 반려한다
    return ((it or {}).get("name") or ""), n


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


def import_one(cat: dict, path: str, today: str = "", q: dict | None = None) -> str:
    """캡처 1장을 카탈로그에 등록하고 파일을 assets/products/로 옮긴다."""
    q = q if q is not None else catalog.queue_load()
    stem, num = read_stem(os.path.splitext(os.path.basename(path))[0], q)
    if not stem:
        print(f"[capture] ⚠ 번호표에 없는 번호({num}) — 건너뜀: {os.path.basename(path)}")
        return ""
    brand, model = split_name(stem)
    slug = catalog.put(cat, name=stem, brand=brand, model=model, category=model or stem,
                       image_source=SOURCE, updated=today)
    dest = os.path.join(catalog.IMAGE_DIR, slug + os.path.splitext(path)[1].lower())
    os.makedirs(catalog.IMAGE_DIR, exist_ok=True)
    shutil.move(path, dest)
    cat["products"][slug]["image"] = dest
    if num is not None:
        catalog.mark_done(q, num)
    return slug


def main():
    today = __import__("datetime").date.today().isoformat()
    cat = catalog.load()
    q = catalog.queue_load()
    files = scan()
    done = [s for s in (import_one(cat, f, today, q) for f in files) if s]
    if done:
        cat["updated"] = today
        catalog.save(cat)
    wl = {}
    if os.path.exists("data/watchlist.json"):
        import json
        with open("data/watchlist.json", encoding="utf-8") as f:
            wl = json.load(f)
    q = catalog.refresh_queue(cat, wl, q)      # 새로 발굴된 상품에도 번호를 붙인다
    catalog.queue_save(q)
    catalog.write_list(q)
    for s in done:
        print(f"[capture] 등록 — {cat['products'][s]['display']} → {cat['products'][s]['image']}")
    total = len(cat.get("products", {}))
    have = sum(1 for e in cat["products"].values() if catalog.image_path(e))
    print(f"[capture] 반입 {len(done)}건 · 카탈로그 {total}건 중 사진 보유 {have}건")
    todo = [(int(n), it) for n, it in q["items"].items() if not it.get("done")]
    if todo:
        print(f"[capture] 캡처 대기 {len(todo)}건 — 번호로 저장하면 끝(예: 3.png)")
        for n, it in sorted(todo)[:8]:
            print(f"[capture]   {n}. {it['name']}")
        print(f"[capture] 전체 번호표: {catalog.LIST_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

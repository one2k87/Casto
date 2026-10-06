"""무료 재배포 — 같은 영상을 릴스·틱톡·Threads에 올릴 때 쓸 **플랫폼별 캡션**을 만든다(famto 10/1 ⑤).

계정은 아직 없다(사용자가 만들면 famto가 알린다). 그 전까지 코드만 둔다: 매 발행 뒤
`out/redistribute/`에 플랫폼별 캡션 3개와 영상 복사본이 생기고, Make 분기는 계정이 생기면 붙인다.

플랫폼별 링크 규정(2026-10-06 확인, 블로그·Threads 게시물 인용 ❓ — 계정 생기면 각 앱에서 실측):
  · 인스타 릴스 — 캡션의 URL은 클릭되지 않는다(Meta 인증 유료 사용자 일부에게 월 10개 테스트 중).
    → 링크는 **프로필**에, 캡션은 「링크는 프로필에」 + 상품명. 고지 문구는 첫 줄.
  · 틱톡 — 캡션 URL 클릭 불가, 프로필 링크는 팔로워 1,000명부터. → 릴스와 같은 전략. 캡션 상한이
    짧으므로(약 2,200자이나 피드에선 앞 1~2줄만) 고지 → 상품명 → 해시태그 순.
  · Threads — 게시물 안 링크가 클릭된다. → 고지 → 승자 링크 → 상품 3개 순.
어느 플랫폼이든 **고지 문구가 첫 부분**(파트너스 가이드)이고, 링크가 없으면 줄을 만들지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil

PLATFORMS = ("reels", "tiktok", "threads")
TAGS = {"reels": "#콕픽 #살림템 #주방꿀템 #쿠팡추천 #릴스",
        "tiktok": "#콕픽 #살림템 #주방꿀템 #쿠팡추천 #틱톡",
        "threads": "#콕픽 #살림템"}


def captions(last: dict, disclosure: str) -> dict[str, str]:
    """`data/last_caption.json` → {플랫폼: 캡션}. 영상·제목·상품은 유튜브 편과 같다."""
    title = (last.get("title") or "").strip()
    items = [x for x in (last.get("items") or []) if x]
    winner = (last.get("winner") or (items[0] if items else "")).strip()
    url = (last.get("coupang_url") or "").strip()
    names = " · ".join(items) if items else winner
    out = {}
    # 릴스·틱톡: 링크는 프로필. 캡션엔 상품명이 검색을 만든다.
    for p in ("reels", "tiktok"):
        lines = [disclosure, ""]
        if title:
            lines.append(title)
        if names:
            lines.append(names)
        if url:
            lines.append(f"👉 {winner} 쿠팡 링크는 프로필에")
        lines += ["", TAGS[p]]
        out[p] = "\n".join(lines)
    # Threads: 링크가 클릭된다 — 둘째 줄이 링크.
    lines = [disclosure]
    if url:
        lines.append(f"🛒 {winner} 쿠팡 → {url}")
    lines.append("")
    if title:
        lines.append(title)
    if names:
        lines.append(names)
    lines += ["", TAGS["threads"]]
    out["threads"] = "\n".join(lines)
    return out


def write(last: dict, disclosure: str, video: str = "out/short.mp4", out_dir: str = "out/redistribute") -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    made = []
    for p, cap in captions(last, disclosure).items():
        path = os.path.join(out_dir, f"caption_{p}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(cap)
        made.append(path)
    if os.path.exists(video):
        dst = os.path.join(out_dir, os.path.basename(video))
        shutil.copyfile(video, dst)
        made.append(dst)
    return made


def main() -> None:
    from common import cfg
    c = cfg()
    try:
        with open("data/last_caption.json", encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        raise SystemExit("[redistribute] data/last_caption.json 없음 — 발행 뒤에 돌린다")
    video = "out/chart.mp4" if last.get("verdict") == "chart" else "out/short.mp4"
    for p in write(last, c["disclosure"]["coupang"], video):
        print("[redistribute]", p)


if __name__ == "__main__":
    main()

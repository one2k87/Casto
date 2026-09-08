"""픽담에 넘길 **주제 요청서** — 콕픽이 발굴한 유행템을 픽토가 글로 받게 한다.

왜 필요한가(2026-09-08 결정): 콕픽 → 픽담 유입 구조는 **양쪽에 같은 제품이 있을 때만** 작동한다.
지금 픽담 최신 글은 '정수기 필터 교체'인데 콕픽이 다루는 건 '롤팬 자동회전냄비'다. 영상을 보고
픽담에 가도 그 제품 글이 없으니, 낮은 클릭률을 다시 이탈로 날리게 된다.

그래서 **주제를 캐스토가 정해서 넘긴다.** 캐스토는 매일 유행을 관측하고 있고 픽토는 그렇지 않으므로,
이 방향이 자연스럽다. 픽토는 아래 파일만 읽으면 된다(레포가 달라 raw URL로 가져간다):

  https://raw.githubusercontent.com/one2k87/Casto/main/data/topic_requests.json

우선순위 규칙 — **브랜드가 확정된 것이 먼저**다. 픽담 글이 정확한 제품을 지목해야
그 글에 쿠팡 링크를 붙일 수 있고, 그래야 유입이 수익으로 연결된다.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import catalog

OUT_JSON = "data/topic_requests.json"
OUT_MD = "data/topic_requests.md"
CONF_RANK = {"높음": 0, "중간": 1, "낮음": 2, "": 3}


def build(cat: dict, q: dict, limit: int = 12) -> list[dict]:
    rows = []
    for n, it in q.get("items", {}).items():
        if it.get("hold"):
            continue                       # 유행 근거가 없는 항목은 글감으로도 넘기지 않는다
        e = catalog.find(cat, name=it.get("display") or it.get("name", ""))
        rows.append({
            "no": int(n),
            "category": it.get("name", ""),
            "brand": it.get("brand", ""),
            "model": it.get("model", ""),
            "product": it.get("display") or it.get("name", ""),
            "search": it.get("search", ""),
            "url": it.get("url", ""),
            "confidence": it.get("confidence", ""),
            "note": it.get("note", ""),
            "has_photo": catalog.render_mode(e) == "exact",
        })
    rows.sort(key=lambda r: (CONF_RANK.get(r["confidence"], 3), r["no"]))
    return rows[:limit]


def to_md(rows: list[dict], today: str) -> str:
    out = [f"# 픽담 글감 요청 — 콕픽 발굴 유행템 ({today})", "",
           "콕픽이 유튜브에서 관측한 **지금 유행 중인** 제품들입니다. 위에서부터 우선순위입니다.",
           "",
           "**부탁**: 글에 이 제품을 지목해 주시고, 본문에 **픽담 자체 쿠팡 파트너스 링크**와",
           "`<!--KOKPICK ... -->` 블록(브랜드·모델·image_url·coupang_url)을 넣어주세요.",
           "그러면 콕픽 영상이 실제 상품 사진과 정확한 이름으로 나가고, 영상↔글이 같은 제품을 가리킵니다.",
           "", "| 우선 | 제품 | 카테고리 | 확신도 | 쿠팡 | 메모 |", "|---|---|---|---|---|---|"]
    mark = {"높음": "확실", "중간": "유력", "낮음": "브랜드 미확정"}
    for i, r in enumerate(rows, 1):
        link = f'[검색]({r["url"]})' if r["url"] else ""
        out.append(f'| {i} | **{r["product"]}** | {r["category"]} '
                   f'| {mark.get(r["confidence"], "-")} | {link} | {r["note"]} |')
    out += ["", "---", "",
            "브랜드가 '미확정'인 항목은 카테고리 글로 쓰시고, 특정 제품을 고르셨다면",
            "그 브랜드·모델을 KOKPICK 블록에 적어주시면 캐스토가 그대로 따라갑니다."]
    return "\n".join(out) + "\n"


def main():
    today = datetime.date.today().isoformat()
    cat, q = catalog.load(), catalog.queue_load()
    rows = build(cat, q)
    os.makedirs("data", exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"updated": today, "source": "casto/trend_products",
                   "requests": rows}, f, ensure_ascii=False, indent=1)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(to_md(rows, today))
    print(f"[topics] 글감 {len(rows)}건 → {OUT_JSON} / {OUT_MD}")
    for r in rows[:5]:
        print(f"[topics]   {r['product']} ({r['confidence'] or '미상'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

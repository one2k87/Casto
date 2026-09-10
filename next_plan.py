#!/usr/bin/env python3
"""다가오는 발행일과 그날 쓸 상품을 data/next_plan.json에 적는다.

앱의 「🔗 쿠팡 링크 필요」 목록이 17줄이나 되는데 어느 걸 먼저 해야 하는지
알 수 없었다. 링크는 **영상 나가기 전에** 있어야 설명란에 들어가고,
그래야 파트너스 활동 증빙 스크린샷을 찍을 수 있다. 그래서 순서를 앱에 알려준다.
"""
import datetime as dt, io, json, os

import catalog, schedule as sch

OUT = "data/next_plan.json"
WD = "월화수목금토일"


def upcoming(n: int = 3, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    board = json.load(io.open("data/trend_board.json", encoding="utf-8"))
    log = sch._load(sch.PUBLISH_LOG, []) if hasattr(sch, "_load") else []
    ready = sch.ready_products()
    cat = catalog.load()
    out, seen = [], list(log)
    for i in range(0, 21):
        if len(out) >= n:
            break
        d = today + dt.timedelta(days=i)
        p = sch.plan(d, board, seen, ready=ready)
        if not p.get("publish"):
            continue
        name = (p.get("product") or {}).get("name") or ""
        e = catalog.find(cat, name=name)
        out.append({
            "date": d.isoformat(),
            "weekday": WD[d.weekday()],
            "label": f"{d.month}/{d.day}({WD[d.weekday()]})",
            "slot": p.get("slot"),
            "product": name,
            "slug": (e or {}).get("slug") or catalog.slugify(name),
            "photo": catalog.render_mode(e) == "exact",
            "link": bool((e or {}).get("coupang_url")),
        })
        seen = seen + [{"product": name, "key": name}]
    return out


def main():
    rows = upcoming()
    os.makedirs("data", exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": dt.date.today().isoformat(), "items": rows},
                  f, ensure_ascii=False, indent=1)
    for r in rows:
        flag = "✅" if r["link"] else "❌ 링크 없음"
        print(f"[편성예고] {r['label']} {r['slot']} · {r['product']} · "
              f"{'사진O' if r['photo'] else '사진X'} · {flag}")
    return OUT


if __name__ == "__main__":
    main()

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


def upcoming(n: int = 4, today: dt.date | None = None) -> list[dict]:
    """다가오는 발행 n편과 **그날 실제로 만들어질 상품**.

    2026-10-06까지는 `sch.plan()`의 트렌드 보드 1순위(쿠팡꿀템·스크럽대디…)를 적었는데, 실제
    데일리는 `make_short.pick_items`가 **실사진 있는 상품 3개**를 따로 골랐다. 예고와 실제가
    달라 famto·사용자가 엉뚱한 상품의 링크를 준비하게 된다. 그래서 여기서 같은 선택 함수를
    같은 입력으로 돌려 **그날 나갈 3개(차트는 5개)** 를 적는다.
    """
    from common import op_date
    today = today or op_date()
    board = json.load(io.open("data/trend_board.json", encoding="utf-8"))
    log = sch._load(sch.PUBLISH_LOG, []) if hasattr(sch, "_load") else []
    ready = sch.ready_products()
    cat = catalog.load()
    links = {x for x in ready if (catalog.find(cat, name=x) or {}).get("coupang_url")}
    bands = {x: sch.band_of(catalog.find(cat, name=x), x) for x in ready}
    hot = sch.hot_names(board, ready, today)
    try:
        done = io.open("data/last_short.txt", encoding="utf-8").read().strip()
    except OSError:
        done = ""
    out, seen = [], list(log)
    for i in range(0, 21):
        if len(out) >= n:
            break
        d = today + dt.timedelta(days=i)
        slot = sch.slot_for(d)
        if not slot or d.isoformat() == done:      # 오늘 편이 이미 나갔으면 다음 편부터
            continue
        if slot == "chart":
            import chart
            # 다가올 일요일의 차트는 **지금까지 쌓인 이번 주 스냅샷**으로 미리 본다(예고용).
            ch = chart.build(today=min(d, today))
            names = [e["display"] for e in (ch.get("entries") or [])]
            if len(names) < chart.MIN_N:
                continue
            label = f"콕픽 차트 {chart.week_id(d)} ({len(names)}종 · 예고)"
        else:
            if len(ready) < 3:
                continue
            names = sch.choose_items(ready, seen, links, 3, bands=bands, hot=hot)
            label = " · ".join(names)
            seen = seen + [{"products": names, "product": names[0]}]
        prods = []
        for nm in names:
            e = catalog.find(cat, name=nm) or {}
            prods.append({"name": nm, "slug": e.get("slug") or catalog.slugify(nm),
                          "photo": catalog.render_mode(e) == "exact",
                          "link": bool(e.get("coupang_url")), "band": bands.get(nm, "")})
        out.append({
            "date": d.isoformat(), "weekday": WD[d.weekday()],
            "label": f"{d.month}/{d.day}({WD[d.weekday()]})", "slot": slot,
            "product": label, "slug": prods[0]["slug"] if prods else "",
            "products": prods,
            "photo": all(p["photo"] for p in prods),
            "link": all(p["link"] for p in prods),
            "links": f"{sum(1 for p in prods if p['link'])}/{len(prods)}",
            "hot": [p["name"] for p in prods if p["name"] in hot],
        })
    return out


def main():
    rows = upcoming()
    os.makedirs("data", exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        from common import op_date
        json.dump({"updated": op_date().isoformat(), "items": rows},
                  f, ensure_ascii=False, indent=1)
    for r in rows:
        flag = "✅" if r["link"] else f"❌ 링크 {r['links']}"
        print(f"[편성예고] {r['label']} {r['slot']} · {r['product']} · "
              f"{'사진O' if r['photo'] else '사진X'} · {flag}")
    return OUT


if __name__ == "__main__":
    main()

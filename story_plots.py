"""원템포 플롯 순환 (2026-11-17 사용자: "틀을 고정하지 말고 몇 가지 플롯을 랜덤으로, 주기적으로 플롯도 바뀌도록").

data/plot_bank.json
  plots[]   활성 플롯(id·name·how·laugh·heal·weight). 방향 = 힐링 + 잔잔한 웃음.
  history[] {date, plot, episode, metrics?}  — 고른 기록. 게시 뒤 channel_stats 성과를 metrics로 붙인다.
  rotation  exclude_last(최근 N편에 쓴 플롯 제외) · refresh_every_days(교체 주기) · min_uses_before_judge

pick()     최근 exclude_last 편에 나온 플롯을 빼고 weight 비례 랜덤. 시즌(seed)으로 재현 가능.
refresh()  refresh_every_days 마다 1회: 2번 이상 쓴 플롯 중 성과(스와이프 안 함·평균 시청 비율) 최하위를
           은퇴(retired로 이동)시키고, Claude API로 새 플롯 1개를 만들어 넣는다(키 없으면 건너뜀).
           성과 좋은 플롯은 weight를 조금 올린다(1.0 → 최대 2.0).
사용: python story_plots.py pick | refresh | show
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import sys

BANK = "data/plot_bank.json"


def load() -> dict:
    return json.load(open(BANK, encoding="utf-8"))


def save(bank: dict) -> None:
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)


def pick(bank: dict | None = None, seed: int | None = None, record: str | None = None) -> dict:
    bank = bank or load()
    n = bank["rotation"].get("exclude_last", 3)
    recent = [h["plot"] for h in bank["history"][-n:]]
    pool = [p for p in bank["plots"] if p.get("active", True) and p["id"] not in recent] or \
           [p for p in bank["plots"] if p.get("active", True)]
    rng = random.Random(seed)
    chosen = rng.choices(pool, weights=[p.get("weight", 1.0) for p in pool], k=1)[0]
    if record:
        bank["history"].append({"date": dt.date.today().isoformat(), "plot": chosen["id"], "episode": record})
        save(bank)
    return chosen


def _score(h: dict) -> float | None:
    m = h.get("metrics") or {}
    if "viewed_pct" not in m and "avg_view_pct" not in m:
        return None
    return 0.5 * m.get("viewed_pct", 0) + 0.5 * m.get("avg_view_pct", 0)


def refresh(bank: dict | None = None, today: dt.date | None = None) -> str:
    bank = bank or load()
    today = today or dt.date.today()
    last = bank.get("last_refresh")
    every = bank["rotation"].get("refresh_every_days", 28)
    if last and (today - dt.date.fromisoformat(last)).days < every:
        return f"아직 교체 주기 아님(마지막 {last}, {every}일마다)"
    by: dict[str, list[float]] = {}
    for h in bank["history"]:
        s = _score(h)
        if s is not None:
            by.setdefault(h["plot"], []).append(s)
    judged = {k: sum(v) / len(v) for k, v in by.items() if len(v) >= bank["rotation"].get("min_uses_before_judge", 2)}
    msg = []
    if len(judged) >= 3:
        worst = min(judged, key=judged.get)
        best = max(judged, key=judged.get)
        for p in bank["plots"]:
            if p["id"] == best:
                p["weight"] = min(2.0, round(p.get("weight", 1.0) + 0.25, 2))
        keep = [p for p in bank["plots"] if p["id"] != worst]
        bank["retired"] += [dict(p, retired=today.isoformat(), score=round(judged[worst], 1))
                            for p in bank["plots"] if p["id"] == worst]
        bank["plots"] = keep
        msg.append(f"은퇴: {worst}({judged[worst]:.1f}) · 가중치↑: {best}")
    new = new_plot(bank)
    if new:
        bank["plots"].append(new)
        msg.append(f"새 플롯: {new['id']} {new['name']}")
    bank["last_refresh"] = today.isoformat()
    save(bank)
    return " / ".join(msg) or "판정할 성과 부족 — 새 플롯만 시도"


def new_plot(bank: dict) -> dict | None:
    """Claude API로 기존과 겹치지 않는 플롯 1개. 키 없으면 None."""
    try:
        import story_writer
    except Exception:                                            # noqa: BLE001
        return None
    have = [f"{p['id']}: {p['name']} — {p['how'][:60]}" for p in bank["plots"] + bank["retired"]]
    prompt = ("유튜브 쇼츠 「원템포 | 토끼와 늘보 부부」(클레이 애니메이션, 45초)의 새 플롯 형식 1개를 제안해라.\n"
              f"방향: {bank['direction']}\n이미 있는/은퇴한 형식(겹치면 안 됨):\n- " + "\n- ".join(have) +
              "\n\n출력은 JSON 하나만: {\"id\":영문소문자_밑줄, \"name\":한글 8자 이내, \"how\":구조 2~3문장, "
              "\"laugh\":웃음 장치, \"heal\":힐링 포인트, \"ref\":참고한 인기 영상 유형}")
    txt = story_writer.ask(prompt, max_tokens=800)
    if not txt:
        return None
    try:
        j = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
    except Exception:                                            # noqa: BLE001
        return None
    j.update({"weight": 1.0, "active": True, "added": dt.date.today().isoformat()})
    return j


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "pick":
        print(json.dumps(pick(), ensure_ascii=False, indent=1))
    elif cmd == "refresh":
        print(refresh())
    else:
        b = load()
        for p in b["plots"]:
            print(f"{p['id']:16s} w={p.get('weight', 1.0)}  {p['name']}")
        print("최근:", [h["plot"] for h in b["history"][-5:]])

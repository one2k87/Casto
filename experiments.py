"""정체성 실험(3개월) — 편마다 **무엇을 바꿨고, 어떻게 됐는지**를 코드가 기록·판정한다.

근거 문서: `docs/정체성_실험_3개월_2026-10-12.md`. 요지는 셋이다.
  ① 2주 한 블록, 블록마다 변수 **하나**, 값은 번갈아(요일 편향을 피하려고 회전) 배정한다.
  ② 판정은 24h(테스트 배치 통과?) → 72h(계속 밀리나?) → 7d(등급) 순서로, 평균이 아니라 **중앙값**으로 한다.
     쇼츠는 1편이 조회의 90%를 가져가 평균은 그 1편에 끌려간다.
  ③ 사람이 넣어야 하는 값(Studio 계속 시청함, 파트너스 클릭·주문)은 비어 있으면 **비어 있다고 표시**한다.
     추정값으로 채우지 않는다. 빈칸을 채우는 순간 리뷰는 거짓말을 시작한다.

데이터는 `data/experiments.json` 하나(편별 행). 조회 수치는 `data/channel_stats/<date>.json` 스냅샷에서
발행일 +1/+3/+7일 자리를 읽는다 — 스냅샷이 하루 한 번이라 "24시간"은 정확히 24시간이 아니라
**다음 날 스냅샷**이다. 모든 편에 같은 오차가 들어가므로 비교엔 쓸 수 있다.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import statistics
import sys

PATH = "data/experiments.json"
STATS_DIR = "data/channel_stats"
REVIEW_MD = "data/experiments_review.md"

# 실험 변수의 기본값 — 블록에서 돌리지 않는 변수는 직전 승자, 승자가 없으면 이 값으로 고정한다.
DEFAULTS = {"narrative": "A_사고해결", "hook": "문제장면", "length": "22s",
            "ending": "도장서랍", "title": "문제숫자"}   # 2026-10-13 포맷 3판(조합 1) 반영

BLOCKS = [
    {"n": 1, "start": "2026-10-13", "end": "2026-10-26", "var": "narrative",
     "values": ["A_사고해결", "B_판정", "C_비교"], "metric": "retention"},
    {"n": 2, "start": "2026-10-27", "end": "2026-11-09", "var": "hook",
     "values": ["문제장면", "질문자막", "숫자자막"], "metric": "retention"},
    {"n": 3, "start": "2026-11-10", "end": "2026-11-23", "var": "length",
     "values": ["16s", "22s"], "metric": "avg_view_pct"},
    {"n": 4, "start": "2026-11-24", "end": "2026-12-07", "var": "ending",
     "values": ["실물가격", "도장서랍", "픽담예고"], "metric": "ctr"},
    {"n": 5, "start": "2026-12-08", "end": "2026-12-21", "var": "title",
     "values": ["문제숫자", "대사인용", "질문형"], "metric": "views_24h"},
    {"n": 6, "start": "2026-12-22", "end": "2027-01-10", "var": None,
     "values": [], "metric": "ctr"},
]

GRADES = [("S", 50_000), ("A", 10_000), ("B", 3_000), ("C", 0)]
MIN_PER_VALUE = 3          # 값마다 이만큼 쌓이기 전엔 승자를 정하지 않는다
WIN_MARGIN = 0.20          # 1위 중앙값이 2위보다 20% 이상 높아야 승자
EARLY_DROP_RET = 30.0      # 3편 연속 C등급 + 계속 시청함 < 30% → 조기 탈락
PASS_MULT = 1.5            # 24h 조회가 최근 10편 중앙값의 1.5배면 "테스트 배치 통과"
PUSH_GROWTH = 0.30         # 24h→72h 증가율 30% 이상이면 "계속 밀고 있다"

# 집계에서 빼는 포맷 — 파일럿과 실험 전 편
EXCLUDE_FORMATS = {"pilot", "legacy"}


# ---------------------------------------------------------------- 저장소
def load(path: str = PATH) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(rows: list[dict], path: str = PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 블록·배정
def block_for(date: str) -> dict | None:
    for b in BLOCKS:
        if b["start"] <= date <= b["end"]:
            return b
    return None


def winners(rows: list[dict]) -> dict:
    """확정된 승자 {변수: 값}. `review()`가 승자를 행에 남기지 않고 별도 레코드(kind=winner)로 둔다."""
    out = {}
    for r in rows:
        if r.get("kind") == "winner":
            out[r["var"]] = r["value"]
    return out


def assign(date: str, rows: list[dict]) -> dict:
    """오늘 편의 변수 묶음. 현재 블록 변수는 회전 배정, 나머지는 승자→기본값."""
    base = dict(DEFAULTS)
    base.update(winners(rows))
    b = block_for(date)
    if not b or not b["var"]:
        return base
    done = [r for r in rows if r.get("kind", "episode") == "episode"
            and r.get("block") == b["n"] and r.get("format") not in EXCLUDE_FORMATS]
    i, k = len(done), len(b["values"])
    # 회전: 1라운드 A B C, 2라운드 B C A … — 같은 값이 늘 같은 요일에 가지 않게
    base[b["var"]] = b["values"][(i + i // k) % k]
    return base


# ---------------------------------------------------------------- 예측
def predict(ctx: dict, rows: list[dict] | None = None) -> str:
    """발행 전 등급 예측. 맞추기보다 **틀린 기록**을 남기려는 것이라 식은 일부러 단순하다.

    ctx: search_volume(픽담 GSC 월간 노출 등, 없으면 0) · hot(핫이슈 보드) · price_band · variables
    기본 B에서 시작: 검색량 ≥1천 +1, 핫이슈 +1, 고가 −1, 이 값의 지난 중앙값이 A 이상 +1.
    """
    score = 0
    if (ctx.get("search_volume") or 0) >= 1000:
        score += 1
    if ctx.get("hot"):
        score += 1
    if ctx.get("price_band") == "고가":
        score -= 1
    b = block_for(ctx.get("date", "")) if ctx.get("date") else None
    if b and b["var"] and rows:
        v = (ctx.get("variables") or {}).get(b["var"])
        past = [r.get("views_7d") for r in rows if r.get("kind", "episode") == "episode"
                and (r.get("variables") or {}).get(b["var"]) == v and r.get("views_7d")]
        if len(past) >= 2 and statistics.median(past) >= 10_000:
            score += 1
    ladder = ["C", "B", "A", "S"]
    return ladder[max(0, min(3, 1 + score))]


# ---------------------------------------------------------------- 등록
def register(rows: list[dict], *, video_id: str, date: str, title: str, product: str = "",
             fmt: str = "clay", variables: dict | None = None, predicted: str | None = None) -> dict:
    """편 한 행을 추가(같은 video_id면 갱신)."""
    b = block_for(date)
    row = {"kind": "episode", "video_id": video_id, "date": date, "title": title, "product": product,
           "format": fmt, "block": b["n"] if b else None,
           "variables": variables or assign(date, rows), "predicted": predicted}
    for i, r in enumerate(rows):
        if r.get("video_id") == video_id and r.get("kind", "episode") == "episode":
            r.update({k: v for k, v in row.items() if v is not None})
            return r
    rows.append(row)
    return row


# ---------------------------------------------------------------- 스냅샷 → 수치
def snapshots(stats_dir: str = STATS_DIR) -> dict[str, dict[str, dict]]:
    """{날짜: {video_id: {views, likes, comments}}}"""
    out = {}
    for p in sorted(glob.glob(os.path.join(stats_dir, "*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        day = d.get("date") or os.path.basename(p)[:-5]
        out[day] = {v["id"]: v for v in d.get("videos", []) if v.get("id")}
    return out


def _at(snaps: dict, vid: str, date: str, days: int) -> dict | None:
    """발행일 + days 스냅샷. 그 날이 없으면 그 뒤 하루까지 허용(크론 지연)."""
    d0 = dt.date.fromisoformat(date)
    for extra in (0, 1):
        key = (d0 + dt.timedelta(days=days + extra)).isoformat()
        if key in snaps and vid in snaps[key]:
            return snaps[key][vid]
    return None


def grade(views: int | None) -> str | None:
    if views is None:
        return None
    for g, floor in GRADES:
        if views >= floor:
            return g
    return "C"


def enrich(rows: list[dict], snaps: dict) -> list[dict]:
    """24h/72h/7d 조회·증가율·등급·테스트 배치 통과 여부를 채운다. 이미 지난 자리만 채우고 미래는 비운다."""
    eps = [r for r in rows if r.get("kind", "episode") == "episode"]
    for r in eps:
        for key, days in (("views_24h", 1), ("views_72h", 3), ("views_7d", 7)):
            s = _at(snaps, r["video_id"], r["date"], days)
            if s is not None:
                r[key] = s.get("views", 0)
                if key == "views_7d":
                    r["likes_7d"] = s.get("likes", 0)
        if r.get("views_24h") and r.get("views_72h"):
            r["growth_72h"] = round(r["views_72h"] / r["views_24h"] - 1, 3)
            r["pushed"] = r["growth_72h"] >= PUSH_GROWTH
        if r.get("views_7d") is not None:
            r["grade"] = grade(r["views_7d"])
            r["hit"] = (r.get("predicted") == r["grade"]) if r.get("predicted") else None
    # 테스트 배치 통과: 직전 10편(자기 제외)의 24h 중앙값 × 1.5
    eps_sorted = sorted(eps, key=lambda r: r["date"])
    for i, r in enumerate(eps_sorted):
        if r.get("views_24h") is None:
            continue
        prev = [x["views_24h"] for x in eps_sorted[max(0, i - 10):i] if x.get("views_24h")]
        if len(prev) >= 3:
            r["passed_24h"] = r["views_24h"] >= PASS_MULT * statistics.median(prev)
    return rows


def set_manual(rows: list[dict], video_id: str, **fields) -> dict | None:
    """사람이 읽은 값: retention(계속 시청함 %)·avg_view_pct·clicks·orders. 클릭률은 7d 조회로 계산."""
    for r in rows:
        if r.get("video_id") == video_id and r.get("kind", "episode") == "episode":
            for k, v in fields.items():
                if v is not None:
                    r[k] = v
            if r.get("clicks") is not None and r.get("views_7d"):
                r["ctr"] = round(100.0 * r["clicks"] / r["views_7d"], 3)
            return r
    return None


# ---------------------------------------------------------------- 리뷰
def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def review(rows: list[dict], block: dict) -> dict:
    """블록의 값별 중앙값과 승자 판정. 표본이 모자라면 winner=None, reason에 이유."""
    eps = [r for r in rows if r.get("kind", "episode") == "episode" and r.get("block") == block["n"]
           and r.get("format") not in EXCLUDE_FORMATS]
    var, metric = block["var"], block["metric"]
    out = {"block": block["n"], "var": var, "metric": metric, "values": {}, "winner": None,
           "reason": "", "early_drop": [], "missing_manual": 0}
    if not var:
        out["reason"] = "고정 포맷 블록 — 변수 없음"
        return out
    out["missing_manual"] = sum(1 for r in eps if r.get("views_7d") is not None and r.get("retention") is None)
    for v in block["values"]:
        g = [r for r in eps if (r.get("variables") or {}).get(var) == v]
        out["values"][v] = {
            "n": len(g),
            "views_7d": _median([r.get("views_7d") for r in g]),
            "views_24h": _median([r.get("views_24h") for r in g]),
            "growth_72h": _median([r.get("growth_72h") for r in g]),
            "retention": _median([r.get("retention") for r in g]),
            "avg_view_pct": _median([r.get("avg_view_pct") for r in g]),
            "ctr": _median([r.get("ctr") for r in g]),
            "grades": "".join(r.get("grade") or "·" for r in sorted(g, key=lambda r: r["date"])),
        }
        # 조기 탈락: 최근 3편 연속 C + 계속 시청함 중앙값 < 30
        recent = sorted(g, key=lambda r: r["date"])[-3:]
        if len(recent) == 3 and all(r.get("grade") == "C" for r in recent):
            ret = out["values"][v]["retention"]
            if ret is not None and ret < EARLY_DROP_RET:
                out["early_drop"].append(v)
    scored = [(v, d[metric]) for v, d in out["values"].items() if d[metric] is not None]
    short = [v for v, d in out["values"].items() if d["n"] < MIN_PER_VALUE]
    if short:
        out["reason"] = f"표본 부족({', '.join(short)}: 값마다 {MIN_PER_VALUE}편 필요)"
        return out
    if len(scored) < 2:
        out["reason"] = f"{metric} 값이 비어 있어 판정 불가(사람 입력 필요)"
        return out
    scored.sort(key=lambda x: x[1], reverse=True)
    (v1, m1), (v2, m2) = scored[0], scored[1]
    if m2 > 0 and (m1 / m2 - 1) >= WIN_MARGIN:
        out["winner"] = v1
        out["reason"] = f"{metric} 중앙값 {m1} vs {m2} (+{round(100 * (m1 / m2 - 1))}%)"
    elif m2 == 0 and m1 > 0:
        out["winner"] = v1
        out["reason"] = f"{metric} 중앙값 {m1} vs 0"
    else:
        out["reason"] = f"무승부({metric} {m1} vs {m2}, 차이 20% 미만) → 둘 다 유지, 다음 블록에서 교차"
    return out


def log_publish(rows: list[dict], today: str, publish_log: str = "data/publish_log.json") -> dict | None:
    """발행 직후: publish_log의 오늘 행(video_id 있는 것)을 실험 행으로 올린다.

    클레이 파이프라인이 붙기 전의 편은 format=legacy로 들어가 집계에서 빠진다 — 실험 시계는
    새 포맷 첫 발행부터 돈다. 변수는 행에 `variables`가 있으면 그것, 없으면 그날 배정값.
    """
    try:
        with open(publish_log, encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, ValueError):
        return None
    todays = [r for r in log if r.get("date") == today and r.get("video_id")]
    if not todays:
        return None
    src = todays[-1]
    fmt = src.get("format") or "legacy"
    if not fmt.startswith("clay"):
        fmt = "legacy"
    variables = src.get("variables") or assign(today, rows)
    ctx = {"date": today, "variables": variables, "hot": bool(src.get("hot")),
           "price_band": src.get("price_band"), "search_volume": src.get("search_volume") or 0}
    return register(rows, video_id=src["video_id"], date=today, title=src.get("title", ""),
                    product=src.get("product", ""), fmt=fmt, variables=variables,
                    predicted=predict(ctx, rows))


def confirm_winner(rows: list[dict], var: str, value: str, date: str) -> None:
    rows[:] = [r for r in rows if not (r.get("kind") == "winner" and r.get("var") == var)]
    rows.append({"kind": "winner", "var": var, "value": value, "date": date})


def render_review(res: dict, block: dict) -> str:
    lines = [f"📊 실험 블록 {block['n']} ({block['start']}~{block['end']}) — 변수 {res['var'] or '없음'}, "
             f"1차 지표 {res['metric']}"]
    for v, d in res["values"].items():
        ret = f"{d['retention']}%" if d["retention"] is not None else "미입력"
        ctr = f"{d['ctr']}%" if d["ctr"] is not None else "미입력"
        g72 = f"{round(100 * d['growth_72h'])}%" if d["growth_72h"] is not None else "—"
        lines.append(f"· {v}: {d['n']}편 [{d['grades']}] 7d 중앙값 {d['views_7d'] or '—'} · "
                     f"72h 증가 {g72} · 계속 시청함 {ret} · 클릭률 {ctr}")
    if res["early_drop"]:
        lines.append(f"⛔ 조기 탈락 후보: {', '.join(res['early_drop'])}")
    if res["missing_manual"]:
        lines.append(f"✍️ 지속률 미입력 {res['missing_manual']}편 — Studio 숫자가 있어야 판정이 선다")
    lines.append(("✅ 승자: " + res["winner"] + " — " if res["winner"] else "⏸ 판정 보류 — ") + res["reason"])
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "review"
    rows = load()
    if cmd == "assign":
        print(json.dumps(assign(argv[1] if len(argv) > 1 else dt.date.today().isoformat(), rows),
                         ensure_ascii=False))
    elif cmd == "register":
        kv = dict(a.split("=", 1) for a in argv[1:])
        variables = json.loads(kv["variables"]) if kv.get("variables") else None
        row = register(rows, video_id=kv["video_id"], date=kv["date"], title=kv.get("title", ""),
                       product=kv.get("product", ""), fmt=kv.get("format", "clay"), variables=variables,
                       predicted=kv.get("predicted"))
        save(rows)
        print(json.dumps(row, ensure_ascii=False))
    elif cmd == "log-publish":
        from common import op_date
        row = log_publish(rows, argv[1] if len(argv) > 1 else str(op_date()))
        if row:
            save(rows)
            print(f"[experiments] 기록 {row['video_id']} format={row['format']} "
                  f"{json.dumps(row['variables'], ensure_ascii=False)} 예측 {row['predicted']}")
        else:
            print("[experiments] 오늘 발행 행이 없다")
    elif cmd == "update":
        enrich(rows, snapshots())
        save(rows)
        print(f"[experiments] {sum(1 for r in rows if r.get('kind', 'episode') == 'episode')}편 갱신")
    elif cmd == "set":
        kv = dict(a.split("=", 1) for a in argv[2:])
        row = set_manual(rows, argv[1], **{k: float(v) for k, v in kv.items()})
        save(rows)
        print(json.dumps(row, ensure_ascii=False) if row else "없는 video_id")
    elif cmd == "review":
        date = argv[1] if len(argv) > 1 else dt.date.today().isoformat()
        b = block_for(date)
        if not b:
            print("실험 기간이 아니다")
            return
        enrich(rows, snapshots())
        res = review(rows, b)
        text = render_review(res, b)
        print(text)
        os.makedirs("data", exist_ok=True)
        with open(REVIEW_MD, "a", encoding="utf-8") as f:
            f.write(f"\n## {date}\n\n{text}\n")
        save(rows)
    elif cmd == "winner":
        confirm_winner(rows, argv[1], argv[2], argv[3] if len(argv) > 3 else dt.date.today().isoformat())
        save(rows)
        print(f"[experiments] 승자 확정 {argv[1]}={argv[2]}")
    else:
        print("usage: experiments.py assign <date> | register k=v… | update | set <video_id> k=v… | "
              "review [date] | winner <var> <value> [date]")


if __name__ == "__main__":
    main(sys.argv[1:])

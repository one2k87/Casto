"""학습 루프 — **영상이 쌓일수록 다음 영상이 좋아지게** 만드는 부분.

사용자 원칙(2026-09-09): "매 영상이 나올 때마다 분석해서, 올라갈수록 더 정확하고 유용해져야 한다."

무엇을 배우는가:
  발행 이력(publish_log)에 남긴 **선택**(어떤 제품·판정·가격대·사진 유무·훅)을
  채널 성과(channel_stats)의 **결과**(조회·좋아요·댓글)와 제목으로 조인해,
  축별로 평균 대비 얼마나 잘/못 됐는지(lift)를 낸다. 그 결과를 두 곳에 되먹인다.
    ① `pick_product` — 잘 되는 가격대·카테고리를 먼저 고른다
    ② `build_script` 프롬프트 — "이 채널에서 먹힌 패턴"을 작가에게 알려준다

⚠️ 한계를 분명히 해둔다. **시청 지속률(retention)과 평균 시청 시간은 여기서 못 본다.**
Data API는 그 값을 주지 않고 YouTube Analytics API + OAuth가 필요하다. 그래서 지금은
**참여율(좋아요·댓글 ÷ 조회)을 완주의 대리 지표**로 쓴다. 대리 지표임을 잊지 말 것 —
OAuth를 붙이는 순간 이 모듈의 지표를 실제 retention으로 교체해야 한다(그때가 진짜 학습이다).

표본이 적을 때 순위를 뒤집지 않도록 **최소 표본(MIN_N)** 아래 축은 판단하지 않는다.
숫자 3개로 "고가가 잘 된다"고 결론 내리는 것이 이 단계에서 가장 흔한 사고다.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

PUBLISH_LOG = "data/publish_log.json"
STATS_DIR = "data/channel_stats"
OUT = "data/learning.json"
MIN_N = 3            # 축 하나를 판단하는 데 필요한 최소 영상 수
AXES = ("verdict", "price_band", "category", "has_photo", "format")
ENGAGE_W = 0.5       # 종합 점수에서 참여율이 갖는 비중 — 조회수와 **같은 비중**이다.
# 채널의 목표는 조회수가 아니라 "구독할 가치가 있고 끝까지 보는 영상"이다(사용자 원칙).
# 참여율이 그 목표에 더 가까운 대리 지표이므로, 조회수에 밀리지 않도록 동률로 둔다.
# 0.35로 두면 조회 3,000·참여 0인 낚시 영상이 조회 900·참여 10%인 영상을 이긴다(실측).


def _norm(t: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", (t or "").lower())


def load(path=PUBLISH_LOG, stats_dir=STATS_DIR):
    log = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []
    snaps = []
    for f in sorted(glob.glob(os.path.join(stats_dir, "*.json"))):
        try:
            snaps.append(json.load(open(f, encoding="utf-8")))
        except Exception:                                   # noqa: BLE001
            continue
    return log, snaps


def join(log: list[dict], snaps: list[dict]) -> list[dict]:
    """발행 기록 ↔ 실제 영상 성과를 **제목으로** 잇는다.

    업로드가 수동이라 영상 ID를 알 수 없다. 제목은 우리가 지은 것이고 그대로 올리므로
    정규화 제목이 가장 신뢰할 수 있는 열쇠다. 못 찾은 기록은 조용히 버리지 말고
    `matched: False`로 남겨 조인 실패율을 볼 수 있게 한다.
    """
    if not snaps:
        return [dict(e, matched=False) for e in log]
    latest = {}
    for v in snaps[-1].get("videos", []):
        latest[_norm(v["title"])] = v
    rows = []
    for e in log:
        key = _norm(e.get("title", ""))
        hit = latest.get(key) or next(
            (v for k, v in latest.items() if key and (key in k or k in key)), None)
        if not hit:
            rows.append(dict(e, matched=False))
            continue
        views = max(int(hit.get("views", 0)), 0)
        eng = ((hit.get("likes", 0) + hit.get("comments", 0)) / views) if views else 0.0
        rows.append(dict(e, matched=True, video_id=hit.get("id"), views=views,
                         likes=hit.get("likes", 0), comments=hit.get("comments", 0),
                         engagement=round(eng, 4)))
    return rows


def _score(r: dict, mean_views: float, mean_eng: float) -> float:
    """조회수와 참여율을 함께 본다 — 조회수만 보면 낚시가 이긴다."""
    v = (r["views"] / mean_views) if mean_views else 1.0
    e = (r["engagement"] / mean_eng) if mean_eng else 1.0
    return round((1 - ENGAGE_W) * v + ENGAGE_W * e, 3)


def analyze(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("matched") and r.get("views") is not None]
    out = {"videos": len(rows), "matched": len(ok), "min_n": MIN_N, "axes": {}, "notes": []}
    if len(ok) < MIN_N:
        out["notes"].append(
            f"표본 {len(ok)}편 — {MIN_N}편이 모이기 전에는 축별 판단을 하지 않는다. "
            "숫자 3개로 결론 내는 것이 이 단계에서 가장 흔한 사고다.")
        return out
    mv = sum(r["views"] for r in ok) / len(ok)
    me = sum(r["engagement"] for r in ok) / len(ok) or 1e-9
    out["mean_views"], out["mean_engagement"] = round(mv, 1), round(me, 4)
    for r in ok:
        r["score"] = _score(r, mv, me)
    for axis in AXES:
        buckets: dict[str, list[dict]] = {}
        for r in ok:
            if axis in r:
                buckets.setdefault(str(r[axis]), []).append(r)
        vals = {k: {"n": len(v), "lift": round(sum(x["score"] for x in v) / len(v), 3),
                    "avg_views": round(sum(x["views"] for x in v) / len(v), 1)}
                for k, v in buckets.items() if len(v) >= MIN_N}
        if vals:
            out["axes"][axis] = dict(sorted(vals.items(), key=lambda kv: -kv[1]["lift"]))
    best = sorted(ok, key=lambda r: -r["score"])[:3]
    out["best"] = [{"title": r.get("title"), "product": r.get("product"),
                    "views": r["views"], "score": r["score"]} for r in best]
    out["worst"] = [{"title": r.get("title"), "product": r.get("product"),
                     "views": r["views"], "score": r["score"]}
                    for r in sorted(ok, key=lambda r: r["score"])[:2]]
    return out


def hints(a: dict, limit: int = 4) -> list[str]:
    """대본 작가(LLM)에게 넘길 **이 채널에서 먹힌 패턴**. 근거 없는 축은 넣지 않는다."""
    out = []
    label = {"verdict": "판정", "price_band": "가격대", "category": "카테고리",
             "has_photo": "실제 상품사진", "format": "포맷"}
    for axis, vals in (a.get("axes") or {}).items():
        items = list(vals.items())
        if len(items) < 2:
            continue
        top, bottom = items[0], items[-1]
        if top[1]["lift"] - bottom[1]["lift"] < 0.15:      # 차이가 없으면 말하지 않는다
            continue
        out.append(f"{label.get(axis, axis)}: '{top[0]}'가 '{bottom[0]}'보다 잘 됨"
                   f"(lift {top[1]['lift']} vs {bottom[1]['lift']}, n={top[1]['n']}/{bottom[1]['n']})")
    return out[:limit]


def report(a: dict) -> str:
    lines = [f"[학습] 발행 {a['videos']}편 · 성과 조인 {a['matched']}편"]
    if a.get("notes"):
        lines += [f"[학습] {n}" for n in a["notes"]]
    if a.get("mean_views") is not None:
        lines.append(f"[학습] 평균 조회 {a['mean_views']} · 평균 참여율 {a['mean_engagement']}")
    for h in hints(a, limit=6):
        lines.append(f"[학습]   · {h}")
    for b in a.get("best", []):
        lines.append(f"[학습]   ▲ {b['title']} ({b['views']}회, score {b['score']})")
    for w in a.get("worst", []):
        lines.append(f"[학습]   ▼ {w['title']} ({w['views']}회, score {w['score']})")
    if a["matched"] < a["videos"]:
        lines.append(f"[학습] ⚠ 제목으로 못 찾은 발행 {a['videos'] - a['matched']}편 — "
                     "업로드 제목을 바꿨다면 조인이 깨진다(제목을 그대로 올릴 것)")
    return "\n".join(lines)


def load_hints(path: str = OUT) -> list[str]:
    """make_short가 프롬프트에 넣을 때 쓰는 얇은 진입점."""
    try:
        return json.load(open(path, encoding="utf-8")).get("hints", [])
    except Exception:                                       # noqa: BLE001
        return []


def main() -> int:
    rows = join(*load())
    a = analyze(rows)
    a["hints"] = hints(a)
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(a, f, ensure_ascii=False, indent=1)
    print(report(a))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

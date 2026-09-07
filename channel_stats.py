"""콕픽 채널 성과 추적 — 구독자·조회수 추이를 매일 기록하고 손절 기준을 자동 판정한다.

설계 근거: `docs/콕픽_채널_전략.md` 6-4(손절 라인) · 2-1(유튜브 쇼핑 자격)

**API 키만으로 동작한다**(OAuth 불필요). 구독자 수·총 조회수·영상별 조회수는 전부 공개 데이터라
`channels.list`(1유닛)·`playlistItems`·`videos.list`로 받을 수 있다. 업로드 자동화가 아니라
관측이 목적이므로 인증 부담 없이 오늘부터 추이를 쌓을 수 있다.

판정 기준(8주 시점, 셋 중 2개 미달이면 포맷을 의심):
  ① 편당 평균 1,000뷰   ② 쿠팡 클릭 발생   ③ 구독 100명
비용이 아니라 **시간 대비 성과**로 판단한다 — 재량 비용이 월 $5까지 내려가 접을 재무적 이유가 없다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import requests

from common import cfg

STATS_DIR = "data/channel_stats"
YT = "https://www.googleapis.com/youtube/v3"
GOALS = {"views_per_video": 1000, "subscribers": 100}
DECISION_WEEKS = 8
SHOPPING_GOAL = {"subscribers": 500, "watch_hours": 3000, "shorts_views_90d": 3_000_000}


def _get(path: str, **params):
    key = os.getenv("YT_API_KEY", "")
    if not key:
        return None
    try:
        r = requests.get(f"{YT}/{path}", params={"key": key, **params}, timeout=30)
        if r.status_code != 200:
            print(f"[stats] {path} HTTP {r.status_code}: {r.text[:160]}")
            return None
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"[stats] {path} 실패: {e}")
        return None


def fetch(channel_id: str) -> dict | None:
    """채널 통계 + 최근 업로드 영상별 조회수. 전부 공개 데이터."""
    ch = _get("channels", part="statistics,contentDetails", id=channel_id)
    if not ch or not ch.get("items"):
        print("[stats] 채널을 찾지 못했다 — channel_id와 YT_API_KEY를 확인할 것")
        return None
    item = ch["items"][0]
    st = item.get("statistics", {})
    uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, page = [], None
    while len(ids) < 50:
        pl = _get("playlistItems", part="contentDetails", playlistId=uploads,
                  maxResults=50, **({"pageToken": page} if page else {}))
        if not pl:
            break
        ids += [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        page = pl.get("nextPageToken")
        if not page:
            break
    videos = []
    if ids:
        v = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids[:50]))
        for it in (v or {}).get("items", []):
            videos.append({
                "id": it["id"],
                "title": it["snippet"]["title"],
                "published": it["snippet"]["publishedAt"][:10],
                "views": int(it.get("statistics", {}).get("viewCount", 0)),
                "likes": int(it.get("statistics", {}).get("likeCount", 0)),
                "comments": int(it.get("statistics", {}).get("commentCount", 0)),
            })
    return {
        "date": dt.date.today().isoformat(),
        "subscribers": int(st.get("subscriberCount", 0)),
        "total_views": int(st.get("viewCount", 0)),
        "video_count": int(st.get("videoCount", 0)),
        "hidden_subscriber_count": st.get("hiddenSubscriberCount", False),
        "videos": videos,
    }


def _snapshots(limit: int = 120) -> list[dict]:
    if not os.path.isdir(STATS_DIR):
        return []
    out = []
    for f in sorted(os.listdir(STATS_DIR))[-limit:]:
        if f.endswith(".json"):
            try:
                with open(os.path.join(STATS_DIR, f), encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except Exception:  # noqa: BLE001
                continue
    return out


def verdict(snaps: list[dict], start: str | None = None) -> dict:
    """손절 기준 판정. **8주가 되기 전에도 현재 상태를 보여준다** — 뒤늦게 알면 늦다."""
    if not snaps:
        return {"ready": False, "note": "스냅샷 없음"}
    cur = snaps[-1]
    first = dt.date.fromisoformat(start or snaps[0]["date"])
    weeks = (dt.date.fromisoformat(cur["date"]) - first).days / 7
    vids = [v for v in cur.get("videos", []) if v["views"] >= 0]
    per_video = (sum(v["views"] for v in vids) / len(vids)) if vids else 0
    checks = {
        "편당 평균 조회수": (per_video, GOALS["views_per_video"]),
        "구독자": (cur["subscribers"], GOALS["subscribers"]),
    }
    passed = {k: v >= g for k, (v, g) in checks.items()}
    return {
        "ready": weeks >= DECISION_WEEKS,
        "weeks": round(weeks, 1),
        "checks": {k: {"현재": round(v, 1), "목표": g, "달성": passed[k]} for k, (v, g) in checks.items()},
        "note": ("판정 시점 도달" if weeks >= DECISION_WEEKS
                 else f"{DECISION_WEEKS}주 중 {weeks:.1f}주 경과 — 아직 판정 전"),
    }


def growth(snaps: list[dict], days: int = 7) -> dict:
    """최근 며칠 증감 — 절대값보다 **기울기**가 중요하다."""
    if len(snaps) < 2:
        return {}
    cur, prev = snaps[-1], snaps[max(0, len(snaps) - 1 - days)]
    return {
        "구독자": cur["subscribers"] - prev["subscribers"],
        "총 조회수": cur["total_views"] - prev["total_views"],
        "영상 수": cur["video_count"] - prev["video_count"],
        "기간(일)": (dt.date.fromisoformat(cur["date"]) - dt.date.fromisoformat(prev["date"])).days,
    }


def report(snaps: list[dict]) -> str:
    if not snaps:
        return "[stats] 아직 스냅샷이 없다"
    cur = snaps[-1]
    lines = [f"[stats] {cur['date']} · 구독 {cur['subscribers']:,} · 총 조회 {cur['total_views']:,} "
             f"· 영상 {cur['video_count']}편"]
    g = growth(snaps)
    if g:
        lines.append(f"[stats] 최근 {g['기간(일)']}일 증감 — 구독 {g['구독자']:+,} / 조회 {g['총 조회수']:+,} "
                     f"/ 영상 {g['영상 수']:+}")
    v = verdict(snaps)
    lines.append(f"[stats] 손절 기준: {v['note']}")
    for k, c in v.get("checks", {}).items():
        lines.append(f"[stats]   {k}: {c['현재']:,} / {c['목표']:,} {'✅' if c['달성'] else '⏳'}")
    # 유튜브 쇼핑 자격 진행률 — 구독 500이 첫 관문
    sub_pct = min(100, cur["subscribers"] / SHOPPING_GOAL["subscribers"] * 100)
    lines.append(f"[stats] 유튜브 쇼핑 자격(구독 500): {sub_pct:.0f}%")
    top = sorted(cur.get("videos", []), key=lambda x: x["views"], reverse=True)[:5]
    if top:
        lines.append("[stats] 조회수 상위")
        for t in top:
            lines.append(f"[stats]   {t['views']:>7,}  {t['published']}  {t['title'][:40]}")
    return "\n".join(lines)


def main() -> None:
    c = cfg()
    cid = (c.get("channel") or {}).get("id") or os.getenv("YT_CHANNEL_ID", "")
    if not cid:
        raise SystemExit("[stats] 채널 ID가 없다 — casto.json의 channel.id를 확인할 것")
    snap = fetch(cid)
    if not snap:
        raise SystemExit("[stats] 수집 실패")
    os.makedirs(STATS_DIR, exist_ok=True)
    with open(os.path.join(STATS_DIR, f"{snap['date']}.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    print(report(_snapshots()))


if __name__ == "__main__":
    main() if len(sys.argv) < 2 or sys.argv[1] != "report" else print(report(_snapshots()))

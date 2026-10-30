"""C5 증거 자동 수집(famto 10/30 실행 설계 v1 ⑤) — 매주 월요일 `evidence/C/<날짜>/summary.json`.

YPP 확장 등급 관문(구독 500 · 90일 공개 업로드 3편 · 90일 쇼츠 300만 회)과 판매·미디어킷 원재료를
사람 손 없이 쌓는다. 숫자는 channel_latest.json(YouTube Data API 공개 통계)에서만 온다 — 추정 없음.
편당 제작비는 veo_usage(10월 Veo)와 편수로 계산하고, 제작시간은 Actions 실행 기록이 없으면 null.
"""
import datetime as dt
import json
import os
import sys


def build(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    with open("data/channel_latest.json", encoding="utf-8") as f:
        ch = json.load(f)
    since = (today - dt.timedelta(days=90)).isoformat()
    vids = ch.get("videos", [])
    recent = [v for v in vids if v.get("published", "") >= since]
    views90 = sum(int(v.get("views", 0)) for v in recent)
    try:
        with open("data/publish_log.json", encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = []
    published = [e for e in log if e.get("video_id")]
    try:
        with open("data/veo_usage.json", encoding="utf-8") as f:
            veo = json.load(f)
    except (OSError, ValueError):
        veo = {}
    veo_usd = sum(m.get("usd", 0.0) for m in veo.values())
    gate = {"subscribers": {"now": ch.get("subscribers", 0), "need": 500},
            "public_uploads_90d": {"now": len(recent), "need": 3},
            "shorts_views_90d": {"now": views90, "need": 3_000_000}}
    return {
        "date": today.isoformat(), "channel_date": ch.get("date"),
        "subscribers": ch.get("subscribers", 0), "total_views": ch.get("total_views", 0),
        "video_count": ch.get("video_count", 0),
        "uploads_90d": len(recent), "views_90d": views90,
        "avg_views_per_video_90d": round(views90 / len(recent), 1) if recent else None,
        "published_total": len(published),
        "cost": {"veo_usd_total": round(veo_usd, 2), "llm": "free tier", "tts": "ElevenLabs 구독",
                 "per_episode_usd_est": round(veo_usd / max(len(published), 1), 2)},
        "minutes_per_episode": None,
        "ypp_expanded_gate": gate,
        "top_videos_90d": sorted(recent, key=lambda v: -int(v.get("views", 0)))[:5],
    }


if __name__ == "__main__":
    today = dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today()
    out = build(today)
    d = os.path.join("evidence", "C", today.isoformat())
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    g = out["ypp_expanded_gate"]
    print(f"[evidence] {d}/summary.json — 구독 {g['subscribers']['now']}/500 · 90일 업로드 {g['public_uploads_90d']['now']}/3 · "
          f"90일 조회 {g['shorts_views_90d']['now']:,}/3,000,000")

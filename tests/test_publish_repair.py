"""publish.py 좀비 수리(2026-10-16) — Make 403 뒤 남은 'unknown' 영상을 오늘 편으로 되살린다."""
import datetime as dt

import publish


def test_토큰_없으면_수리_생략(monkeypatch):
    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert publish.repair_orphans({"title": "x", "description": ""}, dt.datetime.utcnow()) is None


def test_가장_이른_좀비를_살리고_나머지는_비공개(monkeypatch):
    monkeypatch.setattr(publish, "oauth_token", lambda: "tok")
    now = dt.datetime(2026, 10, 16, 1, 50)
    monkeypatch.setattr(publish, "my_recent_videos", lambda token, limit=10: [
        {"id": "late", "title": "unknown", "published": "2026-10-16T02:30:00Z", "privacy": "public"},
        {"id": "old", "title": "unknown", "published": "2026-10-13T19:00:00Z", "privacy": "public"},   # 기준 시각 이전 — 손대지 않음
        {"id": "early", "title": "unknown", "published": "2026-10-16T01:56:00Z", "privacy": "public"},
        {"id": "real", "title": "없으면 살림 못 한다던데", "published": "2026-10-16T02:00:00Z", "privacy": "public"},
    ])
    calls = []
    monkeypatch.setattr(publish, "set_metadata", lambda tok, vid, payload, privacy="public": calls.append((vid, payload["title"], privacy)) or True)
    vid = publish.repair_orphans({"title": "오늘 편", "description": "d", "tags": []}, now)
    assert vid == "early"
    assert ("early", "오늘 편", "public") in calls
    assert ("late", "(중복) 오늘 편", "private") in calls
    assert all(c[0] not in ("old", "real") for c in calls)


def test_수리_실패면_비공개로_내리고_None(monkeypatch):
    monkeypatch.setattr(publish, "oauth_token", lambda: "tok")
    monkeypatch.setattr(publish, "my_recent_videos", lambda token, limit=10: [
        {"id": "z", "title": "unknown", "published": "2026-10-16T01:56:00Z", "privacy": "public"}])
    calls = []

    def fake(tok, vid, payload, privacy="public"):
        calls.append((vid, privacy)); return privacy == "private"
    monkeypatch.setattr(publish, "set_metadata", fake)
    assert publish.repair_orphans({"title": "t", "description": ""}, dt.datetime(2026, 10, 16, 1, 50)) is None
    assert ("z", "private") in calls


def test_보류는_소유자_토큰이_있으면_자동_해제(monkeypatch, tmp_path):
    monkeypatch.setattr(publish, "HOLD_FILE", str(tmp_path / "hold.txt"))
    (tmp_path / "hold.txt").write_text("사유", encoding="utf-8")
    monkeypatch.delenv("YT_REFRESH_TOKEN", raising=False)
    assert publish.on_hold() == "사유"
    monkeypatch.setenv("YT_REFRESH_TOKEN", "x")
    assert publish.on_hold() is None

"""Veo Lite 클립 — 예산 가드가 먼저고, 요청 모양은 문서(2026-10) 그대로다."""
import datetime as dt
import json

import veo


def test_예산을_넘기면_생성하지_않는다(tmp_path, monkeypatch):
    p = str(tmp_path / "u.json")
    now = dt.date(2026, 10, 15)
    monkeypatch.setattr(veo, "BUDGET_USD_MONTH", 1.0)
    assert veo.within_budget(8, "720p", p, now)            # $0.40
    veo.charge(8, "720p", p, now)
    veo.charge(8, "720p", p, now)                           # $0.80
    assert veo.within_budget(4, "720p", p, now)            # $1.00 — 딱 맞음
    assert not veo.within_budget(6, "720p", p, now)        # $1.10
    u = json.load(open(p, encoding="utf-8"))["2026-10"]
    assert u["clips"] == 2 and u["seconds"] == 16 and abs(u["usd"] - 0.8) < 1e-6
    # 달이 바뀌면 다시 0
    assert veo.spent(p, dt.date(2026, 11, 1)) == 0.0


def test_요청_본문은_첫끝_프레임과_세로_9_16(tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    a.write_bytes(b"\x89PNG"), b.write_bytes(b"\x89PNG")
    body = veo.request_body("콕이가 택배를 민다", str(a), str(b), 4, "720p")
    inst = body["instances"][0]
    assert inst["prompt"] and inst["image"]["inlineData"]["mimeType"] == "image/png"
    assert "lastFrame" in inst
    assert body["parameters"] == {"aspectRatio": "9:16", "resolution": "720p",
                                  "durationSeconds": 4, "numberOfVideos": 1}
    body = veo.request_body("x", str(a), None, 8, "1080p")
    assert "lastFrame" not in body["instances"][0]


def test_키가_없으면_None_이고_길이는_4_6_8만(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert veo.clip("x", str(tmp_path / "a.png"), str(tmp_path / "o.mp4")) is None
    monkeypatch.setenv("LLM_API_KEY", "k")
    try:
        veo.clip("x", str(tmp_path / "a.png"), str(tmp_path / "o.mp4"), seconds=5)
        assert False, "5초는 막혀야 한다"
    except ValueError:
        pass


def test_영상_uri_파싱():
    s = {"done": True, "response": {"generateVideoResponse": {"generatedSamples": [
        {"video": {"uri": "https://x/y.mp4"}}]}}}
    assert veo.video_uri(s) == "https://x/y.mp4"
    assert veo.video_uri({"done": True, "response": {}}) is None

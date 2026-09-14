"""유튜브 자동 게시 — 제목·태그 규격과 기록. 네트워크는 건드리지 않는다."""
import json
import os

import publish as P


def test_제목은_꺾쇠를_지우고_100자에서_자른다():
    assert P.clean_title("<b>어쩐지</b> 자꾸 보이더라") == "b어쩐지/b 자꾸 보이더라"
    assert len(P.clean_title("가" * 150)) == 100


def test_태그는_설명란_해시태그에서_뽑고_고정태그를_붙인다():
    tags = P.tags_from("본문 #오늘의콕 #콕픽 #주방템 끝")
    assert tags[:3] == ["오늘의콕", "콕픽", "주방템"]
    assert "Shorts" in tags and "유행템" in tags
    assert len(set(tags)) == len(tags)                 # 중복 없음


def test_태그_합계는_500자를_넘지_않는다():
    long = " ".join(f"#{'가' * 60}{i}" for i in range(20))
    assert sum(len(t) + 1 for t in P.tags_from(long)) <= 500


def test_웹훅_없으면_아무것도_하지_않고_False():
    os.environ.pop("MAKE_UPLOAD_HOOK", None)
    assert P.publish(video_path="/nonexistent.mp4") is False


def test_video_id를_오늘_행과_last_caption에_기록한다(tmp_path, monkeypatch):
    log = tmp_path / "log.json"
    cap = tmp_path / "cap.json"
    log.write_text(json.dumps([{"date": "2026-09-13", "key": "a"}, {"date": "2026-09-14", "key": "b"}]))
    cap.write_text(json.dumps({"date": "2026-09-14", "title": "t"}))
    monkeypatch.setattr(P, "PUBLISH_LOG", str(log))
    monkeypatch.setattr(P, "LAST_CAPTION", str(cap))
    P.record_video("abc123", "2026-09-14")
    rows = json.loads(log.read_text())
    assert rows[1]["video_id"] == "abc123" and "video_id" not in rows[0]
    assert json.loads(cap.read_text())["video_url"].endswith("/abc123")

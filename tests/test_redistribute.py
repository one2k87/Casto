"""재배포 캡션 — 플랫폼마다 링크가 놓일 수 있는 자리가 다르다. 고지는 어디서나 첫 줄."""
import redistribute as rd

DIS = "※ 고지"
LAST = {"title": "에그크래커, 계란 한 번에", "items": ["에그크래커", "레트로 수화기", "손끼임 방지가드"],
        "winner": "에그크래커", "coupang_url": "https://link.coupang.com/a/WIN"}


def test_고지는_모든_플랫폼_첫_줄():
    caps = rd.captions(LAST, DIS)
    assert set(caps) == set(rd.PLATFORMS)
    assert all(c.splitlines()[0] == DIS for c in caps.values())


def test_릴스_틱톡은_링크_대신_프로필_안내_threads는_링크():
    caps = rd.captions(LAST, DIS)
    assert "link.coupang.com" not in caps["reels"] and "프로필" in caps["reels"]
    assert "link.coupang.com" not in caps["tiktok"] and "프로필" in caps["tiktok"]
    assert caps["threads"].splitlines()[1].startswith("🛒") and "link.coupang.com/a/WIN" in caps["threads"]


def test_링크가_없으면_안내_줄도_없다():
    caps = rd.captions(dict(LAST, coupang_url=""), DIS)
    assert "프로필" not in caps["reels"] and "🛒" not in caps["threads"]
    assert "에그크래커" in caps["reels"]                       # 상품명은 남는다(검색)


def test_파일로_쓴다(tmp_path):
    made = rd.write(LAST, DIS, video=str(tmp_path / "none.mp4"), out_dir=str(tmp_path / "r"))
    assert len(made) == 3 and all(p.endswith(".txt") for p in made)

"""2026-11-09 이미지 무료화 — CF FLUX 우선, Gemini 이미지는 IMAGE_ALLOW_PAID=1 일 때만, Pexels 크레딧."""
import base64
import io

from PIL import Image

import comic
import stock
import trend_products


class _R:
    def __init__(self, code, js=None, content=b"", text=""):
        self.status_code, self._js, self.content, self.text = code, js, content, text

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)


def _jpeg_b64():
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 100, 50)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def test_CF_FLUX가_먼저_쓰이고_PNG로_저장된다(tmp_path, monkeypatch):
    monkeypatch.setenv("CF_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    monkeypatch.delenv("IMAGE_ALLOW_PAID", raising=False)
    seen = []

    def post(url, json=None, headers=None, timeout=None):
        seen.append(url)
        assert headers["Authorization"] == "Bearer tok"
        assert json["steps"] == 4 and len(json["prompt"]) <= 2048
        return _R(200, {"result": {"image": _jpeg_b64()}, "success": True})

    monkeypatch.setattr(comic.requests, "post", post)
    out = tmp_path / "c.png"
    assert comic.generate("a cold bedroom in winter", "전기장판", str(out)) == str(out)
    assert seen == [comic.CF_RUN.format("acc")]
    assert Image.open(out).format == "PNG"          # jpeg 응답도 실제 PNG로


def test_유료_꺼져_있으면_Gemini를_부르지_않는다(tmp_path, monkeypatch):
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("LLM_API_KEY_PAID", "paid")
    monkeypatch.delenv("IMAGE_ALLOW_PAID", raising=False)
    called = []
    monkeypatch.setattr(comic.requests, "post", lambda *a, **k: called.append(1))
    assert comic.generate("a cold bedroom", "전기장판", str(tmp_path / "x.png")) is None
    assert called == []


def test_유료_켜면_Gemini_jpeg로_요청한다(tmp_path, monkeypatch):
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("LLM_API_KEY_PAID", "paid")
    monkeypatch.setenv("IMAGE_ALLOW_PAID", "1")
    bodies = []

    def post(url, json=None, headers=None, timeout=None):
        bodies.append(json)
        return _R(200, {"steps": [{"content": [{"type": "image", "data": _jpeg_b64()}]}]})

    monkeypatch.setattr(comic.requests, "post", post)
    assert comic.generate("a cold bedroom", "전기장판", str(tmp_path / "g.png"))
    assert bodies[0]["response_format"]["mime_type"] == "image/jpeg"


def test_imagegen도_유료_꺼지면_건너뛴다(tmp_path, monkeypatch):
    import imagegen
    monkeypatch.setenv("VEO_API_KEY", "v")
    monkeypatch.delenv("IMAGE_ALLOW_PAID", raising=False)
    monkeypatch.setattr(imagegen.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert imagegen.generate("x", str(tmp_path / "i.png")) is None


def test_pexels_사진과_크레딧(tmp_path, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "pk")

    def get(url, params=None, headers=None, timeout=None):
        if url == stock.SEARCH:
            assert headers == {"Authorization": "pk"} and params["orientation"] == "portrait"
            assert params["query"] == "cold winter bedroom"
            return _R(200, {"photos": [{"photographer": "Kim", "photographer_url": "https://p/kim",
                                        "url": "https://www.pexels.com/photo/1/",
                                        "src": {"portrait": "https://img/1.jpg"}}]})
        return _R(200, content=b"jpgbytes")

    monkeypatch.setattr(stock.requests, "get", get)
    got = stock.photo("cold winter bedroom!!", str(tmp_path / "s.jpg"))
    assert got and got["photographer"] == "Kim"
    lines = stock.credit_lines([got])
    assert lines[0].startswith("📷 Photos provided by Pexels")
    assert "Kim" in lines[1] and "https://www.pexels.com/photo/1/" in lines[1]


def test_pexels_키_없으면_None(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert stock.photo("kitchen", "/tmp/x.jpg") is None
    assert stock.credit_lines([]) == []


def test_트렌드_응답이_배열이어도_목록을_꺼낸다():
    one = {"key": "a", "name": "A"}
    assert trend_products._products_of({"products": [one]}) == [one]
    assert trend_products._products_of([one]) == [one]                  # 11/10 #73 유형
    assert trend_products._products_of([{"products": [one]}]) == [one]
    assert trend_products._products_of("x") == []

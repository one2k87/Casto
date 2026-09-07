"""make_briefing 테스트 — LLM·네트워크 없이 대본 구조·장면 순서·캡션을 검증한다."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import make_briefing as mb  # noqa: E402
from common import cfg  # noqa: E402


def fake_board():
    def row(key, name, rec, val, delta, price, quad="peak"):
        return {"key": key, "name": name, "recognition": rec, "value": val, "delta": delta,
                "price": price, "quadrant": quad, "videos": 8, "channels": 7,
                "exposure": rec * 1000, "mentions": 300, "price_band": "저가"}
    return {
        "updated": "2026-09-07",
        "briefing": [
            row("mat", "물결무늬 매트", 2.1, -0.4, "up", 12000, "bubble"),
            row("egg", "계란 슬라이서", 1.5, 0.2, "new", 8000),
            row("ice", "미니 제빙기", 0.9, 0.1, "down", 79000),
        ],
        "deep_dive": [row("hum", "저소음 가습기", -0.8, 1.9, "new", 89000, "blue_ocean")],
    }


def fake_llm(prompt, **kw):
    """실제 LLM 대신 스키마만 맞춘 응답. 프롬프트에 핵심 지침이 들어갔는지도 함께 검사한다."""
    fake_llm.last_prompt = prompt
    return {
        "title": "이번 주 유행템 4개 — 물결무늬 매트·계란 슬라이서·미니 제빙기 (2026년 9월)",
        "opening_voice": "이거, 보신 적 있죠?",
        "items": [
            {"key": "mat", "alias": "물결무늬 매트", "look": "물결 모양 실리콘",
             "why": "7개 채널이 동시에 다룸", "verdict": "next",
             "short_voice": "요즘 제일 많이 보이는 그거.", "long_voice": "여러 채널이 한꺼번에 다뤘습니다. 다만 리뷰는 안 늘었어요."},
            {"key": "egg", "alias": "계란 슬라이서", "look": "철사 여러 줄",
             "why": "이번 주 새로 등장", "verdict": "kok",
             "short_voice": "새로 뜬 그거.", "long_voice": "이번 주 처음 올라온 제품입니다."},
            {"key": "ice", "alias": "미니 제빙기", "look": "손바닥만 한 사각",
             "why": "여름 끝나며 하락", "verdict": "next",
             "short_voice": "이제 좀 덜 보이죠.", "long_voice": "지난주보다 노출이 줄었습니다."},
            {"key": "hum", "alias": "저소음 가습기", "look": "원통형",
             "why": "덜 보이지만 잘 팔림", "verdict": "kok",
             "short_voice": "조용히 잘 팔리는 그거.", "long_voice": "노출은 적은데 실판매가 늘고 있습니다."},
        ],
        "next_week": ["로봇청소기", "식기건조대", "전기포트"],
        "outro_voice": "자세한 판정은 수요일에.",
    }


class TestScript(unittest.TestCase):
    def setUp(self):
        self.c, self.board = cfg(), fake_board()
        self.brief = mb.build_briefing(self.board, self.c, llm=fake_llm)

    def test_prompt_carries_recognition_rules(self):
        """재인 모델의 핵심 지침이 프롬프트에 실제로 들어가야 한다(5-4-10)."""
        p = fake_llm.last_prompt
        self.assertIn("재인", p)
        self.assertIn("정식 상품명", p)      # 정식명 금지 규칙
        self.assertIn("확인 질문", p)        # 오프닝 규칙
        self.assertIn("delta", p)            # 차트 데이터

    def test_blue_ocean_item_is_included(self):
        """노출은 낮아도 구매가치가 높은 것을 뒤쪽에 섞는다(발견의 재미)."""
        self.assertIn("hum", [i["key"] for i in self.brief["items"]])

    def test_empty_board_raises(self):
        with self.assertRaises(SystemExit):
            mb.build_briefing({"briefing": []}, self.c, llm=fake_llm)


class TestScenes(unittest.TestCase):
    def setUp(self):
        self.c, self.board = cfg(), fake_board()
        self.brief = mb.build_briefing(self.board, self.c, llm=fake_llm)

    def test_short_orders_by_recognition(self):
        """첫 항목은 노출량 최상위 — 초반 이탈 방지의 핵심이 재인이다."""
        sc = mb.scenes_for("short", self.brief, self.board, self.c)
        self.assertEqual(sc[0]["kind"], "cover")
        self.assertEqual(sc[-1]["kind"], "outro")
        items = [s for s in sc if s["kind"] == "item"]
        self.assertEqual(items[0]["item"]["key"], "mat")
        self.assertEqual(items[-1]["item"]["key"], "hum")   # 재인 최하 = 발견용으로 뒤에

    def test_short_has_no_section_cards(self):
        sc = mb.scenes_for("short", self.brief, self.board, self.c)
        self.assertFalse(any(s["kind"] == "section" for s in sc))

    def test_long_groups_by_delta_new_first(self):
        """롱폼은 NEW→상승→하락 순 섹션. 신선도가 앞에 온다."""
        sc = mb.scenes_for("long", self.brief, self.board, self.c)
        secs = [s["section"] for s in sc if s["kind"] == "section"]
        self.assertEqual(secs, ["new", "up", "down"])

    def test_long_uses_long_voice(self):
        sc = mb.scenes_for("long", self.brief, self.board, self.c)
        first = next(s for s in sc if s["kind"] == "item")
        self.assertIn("이번 주 처음", first["voice"])   # long_voice가 쓰였는지

    def test_short_uses_short_voice(self):
        sc = mb.scenes_for("short", self.brief, self.board, self.c)
        first = next(s for s in sc if s["kind"] == "item")
        self.assertEqual(first["voice"], "요즘 제일 많이 보이는 그거.")


class TestCaption(unittest.TestCase):
    def test_caption_has_disclosures_and_deltas(self):
        c, board = cfg(), fake_board()
        brief = mb.build_briefing(board, c, llm=fake_llm)
        cap = mb.build_caption(brief, board, c, 62.0, "short")
        self.assertIn("쿠팡 파트너스", cap)      # 대가성 문구(정지 사유 1위)
        self.assertIn("AI로 제작", cap)          # AI 기본법 고지
        self.assertIn("pickdam.com", cap)        # CTA는 픽담 하나로
        self.assertIn("🆕", cap)                 # 델타 표기
        self.assertIn("#오늘의콕", cap)
        self.assertIn("다음 주 심사 예고", cap)   # 예고 = 구독 전환의 핵심


if __name__ == "__main__":
    unittest.main(verbosity=2)

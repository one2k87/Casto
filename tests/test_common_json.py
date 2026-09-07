"""잘린 LLM JSON 복구 테스트 — 실제 실패(2026-09-07 run #2)를 재현해 검증한다.

배경: Gemini 2.5 Flash의 사고 토큰이 maxOutputTokens에 포함돼 긴 JSON이 중간에서 끊겼고
`JSONDecodeError: Unterminated string`으로 수집이 통째로 실패했다. 사고를 끄고 한도를 올리는 게
1차 방어, 그래도 잘렸을 때 **온전히 받은 항목만 살려 진행**하는 게 2차 방어다.
"""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import repair_truncated_json  # noqa: E402


FULL = {"products": [
    {"key": "mat", "name": "물결무늬 매트", "search_keyword": "실리콘 매트", "price_band": "저가"},
    {"key": "egg", "name": "계란 슬라이서", "search_keyword": "계란 슬라이서", "price_band": "저가"},
    {"key": "ice", "name": "미니 제빙기", "search_keyword": "미니 제빙기", "price_band": "중가"},
]}


class TestRepair(unittest.TestCase):
    def test_intact_json_passes_through(self):
        s = json.dumps(FULL, ensure_ascii=False)
        self.assertEqual(repair_truncated_json(s), FULL)

    def test_truncated_mid_string(self):
        """실제 에러와 같은 형태 — 문자열 도중에 끊긴 경우."""
        s = json.dumps(FULL, ensure_ascii=False)
        cut = s.index("미니 제빙기") + 3          # 세 번째 항목의 문자열 중간
        out = repair_truncated_json(s[:cut])
        self.assertIsNotNone(out, "문자열 중간 절단은 복구 가능해야 한다")
        self.assertGreaterEqual(len(out["products"]), 2, "온전한 앞 항목들은 살아야 한다")

    def test_truncated_after_object(self):
        """객체 하나가 끝난 직후 콤마에서 끊긴 경우."""
        s = json.dumps(FULL, ensure_ascii=False)
        cut = s.index('{"key": "ice"')
        out = repair_truncated_json(s[:cut])
        self.assertIsNotNone(out)
        self.assertEqual(len(out["products"]), 2)

    def test_truncated_object_missing_fields(self):
        """마지막 객체가 필드 도중에 끊긴 경우 — 그 객체는 버리고 앞만 살린다."""
        s = json.dumps(FULL, ensure_ascii=False)
        cut = s.index('"search_keyword": "미니 제빙기"')
        out = repair_truncated_json(s[:cut])
        self.assertIsNotNone(out)
        self.assertGreaterEqual(len(out["products"]), 2)

    def test_unrecoverable_returns_none(self):
        self.assertIsNone(repair_truncated_json('{"products": [{"key'[:6]))

    def test_empty_input(self):
        self.assertIsNone(repair_truncated_json(""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

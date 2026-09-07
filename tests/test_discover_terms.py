"""제목 n-gram 보조 후보 테스트 — LLM보다 통계가 먼저여야 환각을 막는다."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import discover_terms as dt  # noqa: E402


def v(t, ch):
    return {"title": t, "channel_id": ch}


class TestTokenize(unittest.TestCase):
    def test_stopwords_and_josa_removed(self):
        toks = dt.tokenize("이 코팅팬은 진짜 꿀템 추천 쇼츠")
        self.assertIn("코팅팬", toks)
        for bad in ("꿀템", "추천", "쇼츠", "진짜"):
            self.assertNotIn(bad, toks)


class TestCandidates(unittest.TestCase):
    def setUp(self):
        self.vids = [
            v("세워지는 밥주걱 왜 이제 나왔지", "a"), v("세워지는 밥주걱 3주 사용기", "b"),
            v("세워지는 밥주걱 단점도 있어요", "c"), v("한 채널만 미는 제품 후기", "d"),
            v("한 채널만 미는 제품 재탕", "d"), v("한 채널만 미는 제품 또", "d"),
        ]

    def test_multi_channel_term_survives(self):
        terms = [r["term"] for r in dt.candidates(self.vids, min_videos=3, min_channels=2)]
        self.assertTrue(any("밥주걱" in t for t in terms))

    def test_single_channel_term_filtered(self):
        terms = [r["term"] for r in dt.candidates(self.vids, min_videos=3, min_channels=2)]
        self.assertFalse(any("재탕" in t for t in terms))

    def test_longer_phrase_preferred(self):
        """'코팅팬'보다 '눌어붙지 않는 코팅팬'이 제품 특정에 가깝다."""
        rows = dt.candidates(self.vids, min_videos=3, min_channels=2)
        self.assertGreaterEqual(rows[0]["words"], 2)

    def test_evidence_block_has_counts(self):
        out = dt.evidence_block(dt.candidates(self.vids, min_videos=3, min_channels=2))
        self.assertIn("채널", out)
        self.assertIn("영상", out)

    def test_empty_input(self):
        self.assertEqual(dt.candidates([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

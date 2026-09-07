"""trend_products 통합 테스트 — API 키 없이 목 스냅샷으로 집계·중복차단을 검증한다."""
import datetime as dt, json, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trend_products as tp  # noqa: E402


def video(views, age, ch):
    return {"views": views, "age_days": age, "channel_id": ch}


def make_snapshot(date, review_viral, review_quiet, price_viral=30000):
    """바이럴(노출 大·리뷰 정체) vs 조용(노출 小·리뷰 급증) 두 제품."""
    return {
        "date": date,
        "sources": {"youtube": True, "naver": True, "coupang": True},
        "products": [
            {"key": "viral", "name": "물결무늬 매트", "keyword": "실리콘 매트",
             "price_band": "저가",
             "videos": [video(250_000, 2, f"c{i}") for i in range(12)],
             "mentions": 4200, "demand": [100 + i for i in range(30)],
             "demand_last_year": None,
             "price": price_viral, "review_count": review_viral,
             "coupang_url": "https://coupang/viral"},
            {"key": "quiet", "name": "저소음 가습기", "keyword": "저소음 가습기",
             "price_band": "중가",
             "videos": [video(1_500, 3, "z1")],
             "mentions": 60, "demand": [100 + 0.5 * i * i for i in range(30)],
             "demand_last_year": None,
             "price": 89000, "review_count": review_quiet,
             "coupang_url": "https://coupang/quiet"},
        ],
    }


class TestBoard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (tp.DAILY_DIR, tp.BOARD, tp.COVERED)
        tp.DAILY_DIR = os.path.join(self.tmp, "trends_daily")
        tp.BOARD = os.path.join(self.tmp, "trend_board.json")
        tp.COVERED = os.path.join(self.tmp, "covered.json")
        os.makedirs(tp.DAILY_DIR)
        today = dt.date.today()
        # 어제: 기준점 / 오늘: 조용한 제품만 리뷰 급증
        for i, (d, rv, rq) in enumerate([
            (today - dt.timedelta(days=2), 1000, 400),
            (today - dt.timedelta(days=1), 1000, 600),
            (today, 1000, 1100),
        ]):
            snap = make_snapshot(d.isoformat(), rv, rq)
            with open(os.path.join(tp.DAILY_DIR, f"{d.isoformat()}.json"), "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)

    def tearDown(self):
        tp.DAILY_DIR, tp.BOARD, tp.COVERED = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_rankings_differ(self):
        out = tp.board()
        self.assertEqual(out["briefing"][0]["key"], "viral",
                         "브리핑은 노출량 1위(재인)를 앞세워야 한다")
        self.assertEqual(out["deep_dive"][0]["key"], "quiet",
                         "심층은 거래 신호 1위(구매가치)를 앞세워야 한다")

    def test_board_written_to_disk(self):
        tp.board()
        self.assertTrue(os.path.exists(tp.BOARD))
        with open(tp.BOARD, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("briefing", data)
        self.assertEqual(data["snapshot_days"], 3)

    def test_covered_blocks_for_8_weeks(self):
        tp.mark_covered("viral", price=30000)
        out = tp.board()
        self.assertIn("viral", out["blocked"])
        self.assertNotIn("viral", [r["key"] for r in out["briefing"]])

    def test_price_drop_exempts_block(self):
        """가격이 15% 이상 내리면 8주 차단을 무시한다(재심콕)."""
        tp.mark_covered("viral", price=30000)
        today = dt.date.today()
        snap = make_snapshot(today.isoformat(), 1000, 1100, price_viral=24000)  # -20%
        with open(os.path.join(tp.DAILY_DIR, f"{today.isoformat()}.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        out = tp.board()
        self.assertNotIn("viral", out["blocked"])

    def test_no_snapshots_returns_empty(self):
        for f in os.listdir(tp.DAILY_DIR):
            os.remove(os.path.join(tp.DAILY_DIR, f))
        self.assertEqual(tp.board(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)

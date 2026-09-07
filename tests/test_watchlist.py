"""추적 목록(watchlist) 테스트 — 델타 계산이 성립하려면 같은 제품이 연속으로 수집돼야 한다.

배경(2026-09-07 실측): discover는 매 실행 LLM 샘플링으로 서로 다른 제품을 뽑는다
(run #4 프라이팬·철수세미 → run #5 코팅팬·종이호일). 그대로 두면 매일 전부 'new'가 되어
NEW/↑/↓ 차트도, 리뷰 증가도 영원히 계산되지 않는다.
"""
import datetime as dt, os, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trend_products as tp  # noqa: E402


def found(*keys):
    return [{"key": k, "name": k, "search_keyword": k, "category": "50000008",
             "price_band": "저가"} for k in keys]


class TestWatchlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = tp.WATCHLIST
        tp.WATCHLIST = os.path.join(self.tmp, "watchlist.json")
        self.today = dt.date(2026, 9, 7)

    def tearDown(self):
        tp.WATCHLIST = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_first_run_returns_found(self):
        out = tp.merge_watchlist(found("pan", "foil"), self.today)
        self.assertEqual({p["key"] for p in out}, {"pan", "foil"})

    def test_previous_products_survive_when_not_refound(self):
        """핵심 — 오늘 발굴에 없어도 어제 제품이 계속 수집돼야 시계열이 생긴다."""
        tp.merge_watchlist(found("pan", "foil"), self.today)
        out = tp.merge_watchlist(found("kimchi"), self.today + dt.timedelta(days=1))
        self.assertEqual({p["key"] for p in out}, {"pan", "foil", "kimchi"},
                         "어제 제품이 사라지면 델타를 계산할 수 없다")

    def test_stale_products_dropped(self):
        tp.merge_watchlist(found("pan"), self.today)
        out = tp.merge_watchlist(found("kimchi"), self.today + dt.timedelta(days=tp.WATCH_DAYS + 1))
        self.assertEqual({p["key"] for p in out}, {"kimchi"}, "오래 재발굴 안 된 제품은 정리된다")

    def test_refound_product_stays_alive(self):
        tp.merge_watchlist(found("pan"), self.today)
        later = self.today + dt.timedelta(days=tp.WATCH_DAYS - 1)
        tp.merge_watchlist(found("pan"), later)                      # 재발굴로 갱신
        out = tp.merge_watchlist(found("x"), later + dt.timedelta(days=2))
        self.assertIn("pan", {p["key"] for p in out})

    def test_cap_respects_quota(self):
        """유튜브 search는 제품당 100유닛 — 추적 목록이 무한히 늘면 하루 할당량을 넘긴다."""
        out = tp.merge_watchlist(found(*[f"p{i}" for i in range(40)]), self.today)
        self.assertLessEqual(len(out), tp.WATCH_MAX)

    def test_metadata_preserved_and_updated(self):
        tp.merge_watchlist([{"key": "pan", "name": "코팅팬", "search_keyword": "코팅팬",
                             "category": "50000008", "price_band": "중가"}], self.today)
        out = tp.merge_watchlist([{"key": "pan", "name": "코팅팬", "search_keyword": "눌어붙지 않는 팬",
                                   "category": "50000003", "price_band": "중가"}],
                                 self.today + dt.timedelta(days=1))
        rec = next(p for p in out if p["key"] == "pan")
        self.assertEqual(rec["search_keyword"], "눌어붙지 않는 팬")   # 갱신
        self.assertEqual(rec["category"], "50000003")                # 카테고리도 갱신
        self.assertEqual(rec["first_seen"], self.today.isoformat())  # 최초 발견일은 유지


class TestCategoryNormalization(unittest.TestCase):
    """실측(run #6): LLM이 프롬프트 설명을 그대로 복사해 '50000003 디지털가전'으로 저장됐다.
    그 값을 데이터랩에 넘기면 400이 난다."""

    def test_strips_description_text(self):
        self.assertEqual(tp.normalize_category("50000003 디지털가전"), "50000003")

    def test_plain_code(self):
        self.assertEqual(tp.normalize_category("50000008"), "50000008")

    def test_no_code_returns_none(self):
        for v in ("디지털가전", "", None, "코드없음", "123"):
            self.assertIsNone(tp.normalize_category(v), repr(v))

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = tp.WATCHLIST
        tp.WATCHLIST = os.path.join(self.tmp, "watchlist.json")
        self.today = dt.date(2026, 9, 7)

    def tearDown(self):
        tp.WATCHLIST = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_watchlist_stores_normalized_code(self):
        out = tp.merge_watchlist([{"key": "k", "name": "n", "search_keyword": "kw",
                                   "category": "50000003 디지털가전", "price_band": "중가",
                                   "brand": "브랜드", "product_id": "coupang:123",
                                   "evidence": "채널 5개"}], self.today)
        rec = out[0]
        self.assertEqual(rec["category"], "50000003")
        self.assertEqual(rec["brand"], "브랜드")
        self.assertEqual(rec["product_id"], "coupang:123")   # 상품 특정 근거가 보존돼야 한다
        self.assertEqual(rec["evidence"], "채널 5개")


if __name__ == "__main__":
    unittest.main(verbosity=2)

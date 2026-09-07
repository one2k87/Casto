"""요일 편성 엔진 테스트 — 케이던스가 흔들리지 않는 것이 구독의 전제다(5-1E)."""
import datetime as dt, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schedule as sch  # noqa: E402


def row(key, name, band, rec=0.0, val=0.0, delta="flat", quad="peak", blocked=False):
    return {"key": key, "name": name, "price_band": band, "recognition": rec,
            "value": val, "delta": delta, "quadrant": quad, "blocked": blocked}


BOARD = {
    "briefing": [row("foil", "종이호일", "저가", rec=1.3), row("pan", "코팅팬", "중가", rec=1.4)],
    "deep_dive": [row("pan", "코팅팬", "중가", val=1.0), row("dish", "식기세척기", "고가", val=0.5)],
    "all": [row("pan", "코팅팬", "중가", delta="up", quad="blue_ocean")],
}
MON, TUE, WED, THU, SAT, SUN = (dt.date(2026, 9, d) for d in (7, 8, 9, 10, 12, 13))


class TestCadence(unittest.TestCase):
    def test_publish_days_are_mon_tue_thu_sat(self):
        self.assertEqual(sch.slot_for(MON), "trend")
        self.assertEqual(sch.slot_for(TUE), "deep1")
        self.assertEqual(sch.slot_for(THU), "deep2")
        self.assertEqual(sch.slot_for(SAT), "season")

    def test_non_publish_days(self):
        for d in (WED, SUN, dt.date(2026, 9, 11)):   # 수·금·일
            self.assertIsNone(sch.slot_for(d))
            self.assertFalse(sch.plan(d, BOARD)["publish"])

    def test_weekly_count_matches_cap(self):
        """주 4편 — 양산형 콘텐츠 정책 대응 상한을 요일로 강제한다."""
        week = [dt.date(2026, 9, 7) + dt.timedelta(days=i) for i in range(7)]
        self.assertEqual(sum(1 for d in week if sch.slot_for(d)), sch.MAX_PER_WEEK)


class TestSlotRouting(unittest.TestCase):
    def test_monday_uses_recognition_ranking(self):
        """브리핑은 재인 랭킹에서 고른다(이미 봤을 확률)."""
        p = sch.plan(MON, BOARD)
        self.assertEqual(p["format"], "briefing")
        self.assertEqual(p["product"]["key"], "foil")   # 저가 밴드 우선

    def test_deep_slots_use_value_ranking(self):
        """심층은 구매가치 랭킹에서 고른다(사도 되는가) — 브리핑과 다른 질문."""
        self.assertEqual(sch.plan(TUE, BOARD)["product"]["key"], "pan")    # 중가
        self.assertEqual(sch.plan(THU, BOARD)["product"]["key"], "dish")   # 고가

    def test_season_slot_uses_calendar_not_board(self):
        p = sch.plan(SAT, BOARD)
        self.assertIn(p["product"]["name"], sch.SEASON_CALENDAR[9])
        self.assertTrue(p["product"]["season"])

    def test_blocked_products_excluded(self):
        b = {"deep_dive": [row("pan", "코팅팬", "중가", blocked=True)], "briefing": [], "all": []}
        self.assertFalse(sch.plan(TUE, b)["publish"])

    def test_recently_used_deprioritized(self):
        log = [{"date": "2026-09-01", "slot": "deep1", "key": "pan", "verdict": "buy"}]
        self.assertEqual(sch.plan(TUE, BOARD, log)["product"]["key"], "dish")

    def test_month_category_rotates(self):
        self.assertEqual(sch.plan(MON, BOARD)["category"], "주방")
        self.assertEqual(sch.plan(dt.date(2026, 10, 5), BOARD)["category"], "청소")


class TestVerdictQuota(unittest.TestCase):
    def test_small_sample_does_not_force(self):
        self.assertFalse(sch.next_kok_due([{"verdict": "buy"}] * 3))

    def test_forces_when_next_ratio_too_low(self):
        """매번 열리면 '열릴까?'가 성립하지 않아 완주 장치가 죽는다."""
        self.assertTrue(sch.next_kok_due([{"verdict": "buy"}] * 12))

    def test_does_not_force_when_ratio_ok(self):
        log = [{"verdict": "later"}] * 4 + [{"verdict": "buy"}] * 8
        self.assertFalse(sch.next_kok_due(log))

    def test_plan_surfaces_quota_flag(self):
        self.assertTrue(sch.plan(TUE, BOARD, [{"verdict": "buy", "key": "x"}] * 12)["prefer_next_kok"])


class TestRevisit(unittest.TestCase):
    def test_revisit_candidate_offered_on_deep_slots(self):
        self.assertEqual(sch.plan(TUE, BOARD)["revisit_available"], "코팅팬")

    def test_no_revisit_on_briefing_slot(self):
        self.assertNotIn("revisit_available", sch.plan(MON, BOARD))

    def test_flat_delta_is_not_revisit(self):
        b = dict(BOARD, all=[row("pan", "코팅팬", "중가", delta="flat")])
        self.assertIsNone(sch.revisit_candidate(b))


class TestDescribe(unittest.TestCase):
    def test_describe_non_publish(self):
        self.assertIn("발행 없음", sch.describe(sch.plan(WED, BOARD)))

    def test_describe_includes_reason_and_product(self):
        out = sch.describe(sch.plan(TUE, BOARD))
        self.assertIn("코팅팬", out)
        self.assertIn("이유:", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

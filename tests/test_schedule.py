"""요일 편성 엔진 테스트 — 케이던스가 흔들리지 않는 것이 구독의 전제다(5-1E)."""
import datetime as dt, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schedule as sch  # noqa: E402

# 이 파일의 기존 테스트는 **램프업 해제 후**(스냅샷 7일 이상)의 주 4편 계약을 검증한다.
# 램프업 구간(2026-09-09 도입)의 계약은 파일 하단에 따로 있다.
sch.snapshot_days = lambda *a, **k: 30


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


# ── 램프업(2026-09-09) ────────────────────────────────────────────────────────
def test_램프업이면_화토_2편만_편성된다():
    """스냅샷이 7일 미만이면 델타를 신뢰할 수 없다 → 확정 소재로 주 2편만."""
    import datetime as dt
    mon, tue, thu, sat = (dt.date(2026, 9, 14), dt.date(2026, 9, 15),
                          dt.date(2026, 9, 17), dt.date(2026, 9, 19))
    assert sch.slot_for(mon, ramp=True) is None      # 브리핑은 데이터가 모인 뒤에
    assert sch.slot_for(thu, ramp=True) is None
    assert sch.slot_for(tue, ramp=True) == "deep1"
    assert sch.slot_for(sat, ramp=True) == "season"
    # 램프업 해제 후에는 기존 주 4편 편성으로 돌아온다
    assert sch.slot_for(mon, ramp=False) == "trend"
    assert sch.slot_for(thu, ramp=False) == "deep2"


def test_ramping_기준은_7일():
    assert sch.ramping(0) and sch.ramping(6)
    assert not sch.ramping(7)


def test_실사진_소재가_없으면_램프업중에는_발행하지_않는다(monkeypatch):
    """제품 사진 없는 영상은 재인을 못 만든다 — 재인이 구독의 동력이다."""
    import datetime as dt
    monkeypatch.setattr(sch, "snapshot_days", lambda *a, **k: 2)
    board = {"deep_dive": [{"key": "k1", "name": "테스트", "price_band": "중가"}]}
    p = sch.plan(dt.date(2026, 9, 15), board, [], ready=[])
    assert p["publish"] is False and "실사진" in p["reason"]
    p2 = sch.plan(dt.date(2026, 9, 15), board, [], ready=["씨밀렉스 쌀통"])
    assert p2["publish"] is True and p2["ramp"] is True


def test_램프업편은_반드시_실사진_있는_상품을_고른다(monkeypatch):
    """게이트가 '실사진 하나라도 있으면 발행'까지만 봐서, 정작 **고른 상품**은
    사진 없는 시즌 키워드로 나갈 수 있었다. 첫 편이 그럴 뻔했다."""
    import datetime as dt
    monkeypatch.setattr(sch, "snapshot_days", lambda *a, **k: 2)
    # 실사진이 있는 건 '밀폐용기'뿐이라고 가정한다
    monkeypatch.setattr(sch, "_has_photo",
                        lambda name, ready: ready is None or name == "밀폐용기")
    board = {"deep_dive": [{"key": "코팅팬", "name": "코팅팬", "price_band": "중가"}]}
    p = sch.plan(dt.date(2026, 9, 15), board, [], ready=["밀폐용기"])
    assert p["publish"] is True
    assert p["product"]["name"] == "밀폐용기"   # 사진 없는 코팅팬으로 가면 안 된다

    # 시즌 슬롯도 마찬가지 — 시즌 키워드에 사진이 없으면 손에 든 걸 쓴다
    ps = sch.plan(dt.date(2026, 9, 12), board, [], ready=["밀폐용기"])
    assert ps["slot"] == "season" and ps["product"]["name"] == "밀폐용기"


def test_램프업_폴백은_같은_상품을_반복하지_않는다():
    """폴백이 늘 ready[0]이면 첫 네 편이 전부 같은 상품이 된다."""
    assert sch._unused(["a", "b", "c"], [{"product": "a"}]) == "b"
    assert sch._unused(["a", "b"], [{"key": "a"}, {"key": "b"}]) == "a"   # 다 썼으면 처음으로

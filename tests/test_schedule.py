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
    def test_publish_days_are_tue_thu_sat_sun(self):
        """2026-09-15부터 월요일 브리핑 → **일요일 차트**. 주 결산은 주가 끝난 뒤다."""
        self.assertIsNone(sch.slot_for(MON))
        self.assertEqual(sch.slot_for(TUE), "deep1")
        self.assertEqual(sch.slot_for(THU), "deep2")
        self.assertEqual(sch.slot_for(SAT), "season")
        self.assertEqual(sch.slot_for(SUN), "chart")

    def test_non_publish_days(self):
        for d in (MON, WED, dt.date(2026, 9, 11)):   # 월·수·금
            self.assertIsNone(sch.slot_for(d))
            self.assertFalse(sch.plan(d, BOARD)["publish"])

    def test_weekly_count_matches_cap(self):
        """주 4편 — 양산형 콘텐츠 정책 대응 상한을 요일로 강제한다."""
        week = [dt.date(2026, 9, 7) + dt.timedelta(days=i) for i in range(7)]
        self.assertEqual(sum(1 for d in week if sch.slot_for(d)), sch.MAX_PER_WEEK)


class TestSlotRouting(unittest.TestCase):
    def test_sunday_is_the_weekly_chart(self):
        """일요일은 한 상품이 아니라 5개짜리 순위표다."""
        self.assertEqual(sch.SLOT_SPEC["chart"]["format"], "chart")
        self.assertEqual(sch.SLOT_SPEC["chart"]["ranking"], "chart")

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
        self.assertEqual(sch.plan(TUE, BOARD)["category"], "주방")
        self.assertEqual(sch.plan(dt.date(2026, 10, 6), BOARD)["category"], "청소")


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
def test_램프업이면_화일_2편만_편성된다():
    """스냅샷이 7일 미만이면 델타를 신뢰할 수 없다 → 확정 소재로 주 2편만(화·일)."""
    import datetime as dt
    mon, tue, thu, sat, sun = (dt.date(2026, 9, 14), dt.date(2026, 9, 15),
                               dt.date(2026, 9, 17), dt.date(2026, 9, 19),
                               dt.date(2026, 9, 20))
    assert sch.slot_for(mon, ramp=True) is None
    assert sch.slot_for(thu, ramp=True) is None
    assert sch.slot_for(sat, ramp=True) is None      # 토 → 일로 옮겼다
    assert sch.slot_for(tue, ramp=True) == "deep1"
    assert sch.slot_for(sun, ramp=True) == "chart"   # 첫 「콕픽 차트」 2026-09-20
    # 램프업 해제 후에는 주 4편으로 돌아오지만 일요일 차트는 그대로다
    assert sch.slot_for(thu, ramp=False) == "deep2"
    assert sch.slot_for(sun, ramp=False) == "chart"


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

    # 시즌 슬롯도 마찬가지 — 시즌 키워드에 사진이 없으면 손에 든 걸 쓴다.
    # (토요일은 이제 램프업 편성에 없어서 슬롯 선택을 거치지 않고 직접 본다)
    ps = sch.pick_product("season", board, [], 9, ready=["밀폐용기"])
    assert ps["name"] == "밀폐용기" and ps["photo_fallback"]


def test_램프업_폴백은_같은_상품을_반복하지_않는다():
    """폴백이 늘 ready[0]이면 첫 네 편이 전부 같은 상품이 된다."""
    assert sch._unused(["a", "b", "c"], [{"product": "a"}]) == "b"
    assert sch._unused(["a", "b"], [{"key": "a"}, {"key": "b"}]) == "a"   # 다 썼으면 처음으로


# ── 상품 선택 (2026-10-01) ─────────────────────────────────────────────────
def test_쿨다운은_풀_크기에_맞춰_줄어든다():
    """ready 17종에 '최근 6편 제외'를 고정으로 걸어 화요일 데일리가 2주 결번이었다."""
    import schedule as s
    ready = [f"p{i}" for i in range(17)]
    log = [{"products": [f"p{i}", f"p{i+1}", f"p{i+2}"]} for i in range(0, 15, 3)]  # 5편
    got = s.choose_items(ready, log, set(), 3)
    assert len(got) == 3                                       # 결번이 아니다
    assert "p15" in got and "p16" in got                       # 한 번도 안 나온 것이 먼저


def test_풀이_작아도_결번은_없다():
    import schedule as s
    ready = ["a", "b", "c", "d"]
    log = [{"products": ["a", "b", "c"]}, {"products": ["d", "a", "b"]}]
    got = s.choose_items(ready, log, set(), 3)
    assert len(got) == 3 and got[0] == "c"                     # 가장 오래전 것부터 채운다


def test_링크_있는_상품이_먼저_선다():
    """링크 없는 영상은 조회가 나와도 수수료 0 — 같은 조건이면 링크 있는 쪽이 나간다."""
    import schedule as s
    ready = [f"p{i}" for i in range(10)]
    got = s.choose_items(ready, [], {"p7", "p9"}, 3)
    assert got[:2] == ["p7", "p9"]
    assert len(got) == 3


# ── 편성 기준일 (2026-10-06) ───────────────────────────────────────────────
def test_자정을_넘겨_돌아도_전날_작업이다(monkeypatch):
    """크론이 4~9시간 늦어 19:40 KST 작업이 월요일 00:29에 돌았고 일요일 차트가 결번됐다(10/4)."""
    import datetime as dt
    import common
    monkeypatch.delenv("CASTO_DATE", raising=False)
    kst = dt.timezone(dt.timedelta(hours=9))
    assert common.op_date(dt.datetime(2026, 10, 5, 0, 29, tzinfo=kst)) == dt.date(2026, 10, 4)
    assert common.op_date(dt.datetime(2026, 10, 5, 4, 22, tzinfo=kst)) == dt.date(2026, 10, 4)
    assert common.op_date(dt.datetime(2026, 10, 4, 19, 40, tzinfo=kst)) == dt.date(2026, 10, 4)
    assert common.op_date(dt.datetime(2026, 10, 4, 10, 0, tzinfo=kst)) == dt.date(2026, 10, 4)
    monkeypatch.setenv("CASTO_DATE", "2026-10-11")
    assert common.op_date(dt.datetime(2026, 10, 12, 3, 0, tzinfo=kst)) == dt.date(2026, 10, 11)


def test_가격대는_60_30_10으로_수렴한다():
    """famto 10/1: 저가 60 · 중가 30 · 고가 10. 고가만 있는 풀이 아니면 고가가 세 편에 한 번을 넘지 않는다."""
    import schedule as s
    ready = [f"L{i}" for i in range(8)] + [f"M{i}" for i in range(5)] + [f"H{i}" for i in range(4)]
    bands = {x: {"L": "low", "M": "mid", "H": "high"}[x[0]] for x in ready}
    log, hist = [], []
    for _ in range(10):
        pick = s.choose_items(ready, log, set(), 3, bands=bands)
        log.append({"products": pick}); hist += pick
    share = {b: sum(1 for x in hist if bands[x] == b) / len(hist) for b in ("low", "mid", "high")}
    assert 0.5 <= share["low"] <= 0.7 and 0.2 <= share["mid"] <= 0.4 and share["high"] <= 0.2


def test_핫이슈는_편당_둘까지():
    """6:4 — 핫이슈가 넷이어도 한 편에 둘만, 나머지는 에버그린."""
    import schedule as s
    ready = [f"p{i}" for i in range(9)]
    hot = {"p0", "p1", "p2", "p3"}
    pick = s.choose_items(ready, [], set(), 3, hot=hot)
    assert sum(1 for x in pick if x in hot) == 2


def test_보드가_묵으면_핫이슈가_없다():
    import datetime as dt
    import schedule as s
    board = {"updated": "2026-10-04", "deep_dive": [{"name": "스크럽대디", "delta": "new"}]}
    assert s.hot_names(board, ["스크럽대디 수세미"], dt.date(2026, 10, 6)) == {"스크럽대디 수세미"}
    assert s.hot_names(board, ["스크럽대디 수세미"], dt.date(2026, 10, 7)) == set()
    assert s.hot_names({"updated": "2026-10-06", "deep_dive": [{"name": "양념통", "delta": "flat"}]},
                       ["양념통"], dt.date(2026, 10, 6)) == set()

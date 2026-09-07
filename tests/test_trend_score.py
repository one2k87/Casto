"""trend_score 단위 테스트 — API 키 없이 점수 모델이 의도대로 동작하는지 검증한다.

핵심 검증: **재인 랭킹과 구매가치 랭킹이 서로 다른 것을 측정한다**(5-4-10).
같은 제품이 한쪽에서 1위, 다른 쪽에서 꼴찌일 수 있어야 설계가 성립한다.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trend_score import (  # noqa: E402
    ProductSignals, VideoStat, acceleration, channel_diversity, exposure, growth_rate,
    median, persistence_ok, quadrant, rank, recognition_scores, seasonal_excess, value_scores,
)


def rising(base=100.0, n=30, step=3.0):
    """꾸준히 상승하는 시계열."""
    return [base + step * i for i in range(n)]


def accelerating(base=100.0, n=30):
    """가속 상승(2차) — 진입 초기 패턴."""
    return [base + 0.4 * i * i for i in range(n)]


def decelerating(base=100.0, n=30):
    """감속 상승 — 정점 통과 패턴."""
    return [base + 40 * (i ** 0.5) for i in range(n)]


def flat(base=100.0, n=30):
    return [base] * n


class TestPrimitives(unittest.TestCase):
    def test_median_and_growth(self):
        self.assertEqual(median([1, 3, 2]), 2)
        self.assertEqual(median([]), 0.0)
        self.assertAlmostEqual(growth_rate(120, 100), 0.2)
        self.assertIsNone(growth_rate(120, None))          # 결측은 None으로 전파
        self.assertEqual(growth_rate(5, 0), 1.0)           # 0에서 시작 = 신규 진입

    def test_exposure_decays_with_age(self):
        fresh = exposure([VideoStat(1000, 0, "c1")])
        old = exposure([VideoStat(1000, 14, "c1")])
        self.assertGreater(fresh, old)
        self.assertAlmostEqual(old, 1000 * 0.25, places=3)  # 반감기 7일 → 14일이면 1/4

    def test_channel_diversity_prefers_spread(self):
        """총 조회수가 같아도 여러 채널에 흩어진 쪽이 피드 도달이 넓다(5-4-10)."""
        one_channel = [VideoStat(100, 1, "c1") for _ in range(10)]
        ten_channels = [VideoStat(100, 1, f"c{i}") for i in range(10)]
        self.assertLess(channel_diversity(one_channel), channel_diversity(ten_channels))

    def test_acceleration_sign(self):
        self.assertGreater(acceleration(accelerating()), 0)   # 가속 = 진입 초기
        self.assertLess(acceleration(decelerating()), 0)      # 감속 = 정점 통과
        self.assertIsNone(acceleration(flat(n=5)))            # 표본 부족은 None

    def test_persistence_gate(self):
        self.assertTrue(persistence_ok(rising()))
        self.assertFalse(persistence_ok(flat()))              # 횡보는 미충족
        self.assertFalse(persistence_ok([1, 2]))              # 표본 부족

    def test_seasonal_excess_needs_last_year(self):
        self.assertEqual(seasonal_excess(rising(), None), 0.0)   # 작년 없으면 감점 없음


class TestRecognitionVsValue(unittest.TestCase):
    """설계의 핵심 — 두 랭킹이 갈리는가."""

    def setUp(self):
        # A: 온 피드에 도배됐지만 살 이유는 약함 → 재인 1위, 구매가치 하위 (bubble)
        self.viral_but_weak = ProductSignals(
            key="viral", name="물결무늬 매트",
            videos=[VideoStat(300_000, 2, f"ch{i}") for i in range(12)],
            demand_series=flat(), mentions_recent=5000,
            review_count=1000, review_count_prev=1000,      # 리뷰 정체 = 실판매 없음
        )
        # B: 거의 안 보이지만 실제로 잘 팔리고 수요 가속 → 구매가치 1위, 재인 하위 (blue_ocean)
        self.quiet_but_selling = ProductSignals(
            key="quiet", name="저소음 가습기",
            videos=[VideoStat(1_200, 3, "chA")],
            demand_series=accelerating(), mentions_recent=40,
            review_count=1800, review_count_prev=1000,      # 리뷰 80% 증가 = 강한 실판매
        )
        # C: 중간
        self.middle = ProductSignals(
            key="mid", name="전기 포트",
            videos=[VideoStat(30_000, 4, f"m{i}") for i in range(4)],
            demand_series=rising(), mentions_recent=800,
            review_count=1200, review_count_prev=1100,
        )
        self.products = [self.viral_but_weak, self.quiet_but_selling, self.middle]

    def test_recognition_ranks_exposure_first(self):
        rec = recognition_scores(self.products)
        self.assertGreater(rec["viral"], rec["mid"])
        self.assertGreater(rec["mid"], rec["quiet"])

    def test_value_ranks_transaction_first(self):
        val = value_scores(self.products)
        self.assertGreater(val["quiet"], val["viral"],
                           "리뷰가 정체된 바이럴 제품이 구매가치에서 앞서면 안 된다")

    def test_two_rankings_disagree(self):
        """같은 데이터로 만든 두 랭킹의 1위가 서로 달라야 설계가 성립한다."""
        rec, val = recognition_scores(self.products), value_scores(self.products)
        top_rec = max(rec, key=rec.get)
        top_val = max(val, key=val.get)
        self.assertEqual(top_rec, "viral")
        self.assertEqual(top_val, "quiet")
        self.assertNotEqual(top_rec, top_val)

    def test_quadrants(self):
        rows = {r["key"]: r for r in rank(self.products)}
        self.assertEqual(rows["viral"]["quadrant"], "bubble")       # 많이 보이나 살 이유 약함
        self.assertEqual(rows["quiet"]["quadrant"], "blue_ocean")   # 안 보이나 살 만함


class TestMissingSources(unittest.TestCase):
    """키가 없어도(쿠팡 미승인 등) 파이프라인이 멈추지 않아야 한다."""

    def test_no_transaction_axis_still_ranks(self):
        ps = [
            ProductSignals(key="a", name="A", videos=[VideoStat(9000, 1, "c1")],
                           demand_series=accelerating()),
            ProductSignals(key="b", name="B", videos=[VideoStat(100, 1, "c2")],
                           demand_series=decelerating()),
        ]
        val = value_scores(ps)
        self.assertEqual(len(val), 2)
        self.assertGreater(val["a"], val["b"], "거래 축이 없어도 남은 축으로 순위가 나야 한다")

    def test_no_mentions_falls_back_to_exposure(self):
        ps = [
            ProductSignals(key="a", name="A", videos=[VideoStat(50_000, 1, "c1")]),
            ProductSignals(key="b", name="B", videos=[VideoStat(500, 1, "c2")]),
        ]
        rec = recognition_scores(ps)
        self.assertGreater(rec["a"], rec["b"])

    def test_empty_input(self):
        self.assertEqual(recognition_scores([]), {})
        self.assertEqual(value_scores([]), {})
        self.assertEqual(rank([]), [])


class TestGates(unittest.TestCase):
    def test_persistence_penalty_applied(self):
        """단발 급등(횡보 시계열)은 지속성 게이트에서 절반으로 깎인다."""
        strong = ProductSignals(key="s", name="S", videos=[VideoStat(10_000, 1, "c1")],
                                demand_series=rising(), review_count=200, review_count_prev=100)
        spike = ProductSignals(key="p", name="P", videos=[VideoStat(10_000, 1, "c2")],
                               demand_series=flat(), review_count=200, review_count_prev=100)
        val = value_scores([strong, spike])
        self.assertGreater(val["s"], val["p"])

    def test_seasonal_penalty_reduces_score(self):
        """작년 같은 시기에도 올랐다면 트렌드가 아니라 계절이므로 감점된다."""
        no_ly = ProductSignals(key="n", name="N", videos=[VideoStat(5000, 1, "c1")],
                               demand_series=rising(), review_count=200, review_count_prev=100)
        with_ly = ProductSignals(key="w", name="W", videos=[VideoStat(5000, 1, "c2")],
                                 demand_series=rising(),
                                 demand_series_last_year=[300.0] * 30,  # 작년 동기가 평시보다 훨씬 높음
                                 review_count=200, review_count_prev=100)
        val = value_scores([no_ly, with_ly])
        self.assertGreater(val["n"], val["w"])

    def test_bubble_clipping(self):
        """거래가 반증하면 노출계 축(공급·효율)의 양(+) 기여를 잘라낸다.
        이게 없으면 공급(1)+효율(2)이 거래(3)를 상쇄해 바이럴 제품이 심층 편으로 올라간다."""
        bubble = ProductSignals(
            key="bub", name="거품", videos=[VideoStat(400_000, 1, f"c{i}") for i in range(15)],
            demand_series=rising(), review_count=500, review_count_prev=500)      # 리뷰 정체
        real = ProductSignals(
            key="real", name="진짜", videos=[VideoStat(2_000, 1, "z1")],
            demand_series=rising(), review_count=900, review_count_prev=500)      # 리뷰 급증
        val = value_scores([bubble, real])
        self.assertGreater(val["real"], val["bub"])
        self.assertLess(val["bub"], 0.0, "거래가 반증한 제품은 구매가치가 음수여야 한다")

    def test_persistence_penalty_does_not_invert_negative_scores(self):
        """감점을 배수(×0.5)로 주면 음수 점수가 오히려 올라가 순위가 뒤집힌다 — 뺄셈이어야 한다."""
        weak_persistent = ProductSignals(
            key="wp", name="약하지만 지속", videos=[VideoStat(1_000, 1, "c1")],
            demand_series=rising(), review_count=100, review_count_prev=100)
        weak_spike = ProductSignals(
            key="ws", name="약하고 단발", videos=[VideoStat(1_000, 1, "c2")],
            demand_series=flat(), review_count=100, review_count_prev=100)
        val = value_scores([weak_persistent, weak_spike])
        self.assertGreater(val["wp"], val["ws"])

    def test_quadrant_boundaries(self):
        self.assertEqual(quadrant(1.0, 1.0), "peak")
        self.assertEqual(quadrant(1.0, -1.0), "bubble")
        self.assertEqual(quadrant(-1.0, 1.0), "blue_ocean")
        self.assertEqual(quadrant(-1.0, -1.0), "ignore")


if __name__ == "__main__":
    unittest.main(verbosity=2)

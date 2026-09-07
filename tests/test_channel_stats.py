"""채널 성과 판정 테스트 — 손절 기준을 코드로 못박아 감으로 판단하지 않게 한다."""
import datetime as dt, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import channel_stats as cs  # noqa: E402


def snap(date, subs, views, vcount, per_video=0, n=0):
    return {"date": date, "subscribers": subs, "total_views": views, "video_count": vcount,
            "videos": [{"id": f"v{i}", "title": f"t{i}", "published": date,
                        "views": per_video, "likes": 0, "comments": 0} for i in range(n)]}


class TestVerdict(unittest.TestCase):
    def test_before_8_weeks_not_ready(self):
        v = cs.verdict([snap("2026-09-01", 10, 100, 1), snap("2026-09-08", 20, 300, 2)])
        self.assertFalse(v["ready"])
        self.assertIn("아직 판정 전", v["note"])

    def test_at_8_weeks_ready(self):
        start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 1) + dt.timedelta(weeks=8)
        v = cs.verdict([snap(start.isoformat(), 10, 100, 1), snap(end.isoformat(), 120, 9000, 9, 1200, 9)])
        self.assertTrue(v["ready"])
        self.assertTrue(all(c["달성"] for c in v["checks"].values()))

    def test_failing_checks_are_marked(self):
        start, end = dt.date(2026, 9, 1), dt.date(2026, 9, 1) + dt.timedelta(weeks=8)
        v = cs.verdict([snap(start.isoformat(), 0, 0, 0), snap(end.isoformat(), 30, 900, 9, 100, 9)])
        self.assertFalse(v["checks"]["구독자"]["달성"])
        self.assertFalse(v["checks"]["편당 평균 조회수"]["달성"])

    def test_empty(self):
        self.assertFalse(cs.verdict([])["ready"])


class TestGrowth(unittest.TestCase):
    def test_growth_delta(self):
        g = cs.growth([snap("2026-09-01", 10, 100, 1), snap("2026-09-08", 25, 400, 3)])
        self.assertEqual(g["구독자"], 15)
        self.assertEqual(g["총 조회수"], 300)
        self.assertEqual(g["기간(일)"], 7)

    def test_single_snapshot(self):
        self.assertEqual(cs.growth([snap("2026-09-01", 10, 100, 1)]), {})


class TestReport(unittest.TestCase):
    def test_report_mentions_shopping_goal(self):
        out = cs.report([snap("2026-09-01", 250, 5000, 5, 900, 5)])
        self.assertIn("유튜브 쇼핑 자격", out)
        self.assertIn("50%", out)          # 250/500

    def test_report_no_snapshots(self):
        self.assertIn("스냅샷이 없다", cs.report([]))


if __name__ == "__main__":
    unittest.main(verbosity=2)

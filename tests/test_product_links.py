"""제휴 링크 → 상품 특정 테스트.

사용자 지적(2026-09-07): "코팅팬"이 아니라 정확히 어느 브랜드의 어떤 제품인지가 중요하고,
그게 선행되지 않으면 나머지가 의미 없다. 제목 파싱으로는 도달할 수 없고,
**설명란 제휴 링크가 상품을 고유 ID로 특정**한다.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import product_links as pl  # noqa: E402


def vid(i, ch, views, title, desc):
    return {"id": i, "channel_id": ch, "views": views, "title": title, "description": desc}


class TestIdentify(unittest.TestCase):
    def test_coupang_product_url(self):
        r = pl.identify("https://www.coupang.com/vp/products/7788990?itemId=1&vendorItemId=2")
        self.assertEqual((r["platform"], r["id"]), ("coupang", "7788990"))

    def test_coupang_short_url_is_its_own_fingerprint(self):
        """단축 링크는 리다이렉트를 풀지 않아도 코드 자체가 고유해 지문으로 쓸 수 있다."""
        r = pl.identify("https://link.coupang.com/a/bXYZ12")
        self.assertEqual(r["id"], "short:bXYZ12")

    def test_smartstore(self):
        r = pl.identify("https://smartstore.naver.com/myshop/products/123456")
        self.assertEqual((r["platform"], r["id"]), ("smartstore", "myshop/123456"))

    def test_noise_hosts_ignored(self):
        for u in ("https://youtube.com/@kokpick", "https://instagram.com/x",
                  "https://linktr.ee/abc", "https://blog.naver.com/y"):
            self.assertIsNone(pl.identify(u), u)


class TestLabel(unittest.TestCase):
    def test_same_line_before_arrow(self):
        d = "실리콘 물결 도마매트 ▶ https://link.coupang.com/a/b1"
        self.assertEqual(pl.label_for(d, "https://link.coupang.com/a/b1"), "실리콘 물결 도마매트")

    def test_previous_line(self):
        d = "오늘의 제품\nhttps://link.coupang.com/a/b1"
        self.assertEqual(pl.label_for(d, "https://link.coupang.com/a/b1"), "오늘의 제품")

    def test_numbered_prefix_stripped(self):
        d = "1) 세워지는 밥주걱 https://link.coupang.com/a/b1"
        self.assertEqual(pl.label_for(d, "https://link.coupang.com/a/b1"), "세워지는 밥주걱")


class TestCluster(unittest.TestCase):
    def setUp(self):
        self.vids = [
            vid("v1", "a", 120000, "이 매트 편해요", "물결 도마매트 ▶ https://link.coupang.com/a/bX\n구독 https://youtube.com/@z"),
            vid("v2", "b", 88000, "요즘 난리난 매트", "오늘의 제품\nhttps://link.coupang.com/a/bX"),
            vid("v3", "a", 3000, "같은 채널 반복", "혼자만 민 상품 https://www.coupang.com/vp/products/111"),
            vid("v4", "a", 2000, "또 같은 채널", "혼자만 민 상품 https://www.coupang.com/vp/products/111"),
        ]

    def test_multi_channel_product_survives(self):
        rows = pl.cluster(self.vids, min_channels=2)
        self.assertEqual([r["product_id"] for r in rows], ["short:bX"])

    def test_single_channel_product_filtered(self):
        """한 채널이 반복해서 민 상품은 유행이 아니라 그 채널의 소재다."""
        rows = pl.cluster(self.vids, min_channels=2)
        self.assertNotIn("111", [r["product_id"] for r in rows])

    def test_views_summed_and_name_picked(self):
        r = pl.cluster(self.vids, min_channels=2)[0]
        self.assertEqual(r["views"], 208000)
        self.assertEqual(r["channels"], 2)
        self.assertIn("매트", r["name"])

    def test_no_links_returns_empty(self):
        self.assertEqual(pl.cluster([vid("x", "a", 1, "t", "설명에 링크 없음")]), [])

    def test_summary_includes_ids_and_channels(self):
        out = pl.summary(pl.cluster(self.vids, min_channels=2))
        self.assertIn("coupang:short:bX", out)
        self.assertIn("채널 2개", out)


class TestBestLabel(unittest.TestCase):
    def test_most_common_wins(self):
        """사람들이 실제로 부르는 이름이어야 재인이 일어난다 — 최빈값이 정답에 가깝다."""
        self.assertEqual(pl.best_label(["물결 매트", "물결 매트", "실리콘패드"]), "물결 매트")

    def test_empty(self):
        self.assertEqual(pl.best_label([]), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""네이버 엔드포인트 경로 테스트 — HUB 이관 시 경로 구조가 바뀌는 것을 고정한다.

배경(2026-09-07 실측): HUB는 도메인·헤더만 바뀐 게 아니라 **경로 구조가 뒤집혔다**.
"레거시와 같은 경로"로 가정했다가 수집 run에서 네이버 두 축이 12/12 전멸했다.
공식 문서의 curl 예제를 그대로 못박아, 다음에 누가 경로를 만질 때 회귀를 잡는다.
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trend_sources as src  # noqa: E402


class TestEndpoints(unittest.TestCase):
    def test_hub_paths_match_official_curl(self):
        # 공식 문서: GET https://naverapihub.apigw.ntruss.com/search/v1/blog?query=...
        self.assertEqual(src.naver_url("hub", "search", "blog"),
                         "https://naverapihub.apigw.ntruss.com/search/v1/blog")
        # 공식 문서: POST https://naverapihub.apigw.ntruss.com/shopping/v1/category/keywords
        self.assertEqual(src.naver_url("hub", "datalab"),
                         "https://naverapihub.apigw.ntruss.com/shopping/v1/category/keywords")

    def test_hub_search_has_no_json_extension(self):
        """HUB 검색 경로에 .json을 붙이면 300(API 없음)이 난다."""
        self.assertNotIn(".json", src.naver_url("hub", "search", "blog"))

    def test_legacy_paths_unchanged(self):
        self.assertEqual(src.naver_url("legacy", "search", "blog"),
                         "https://openapi.naver.com/v1/search/blog.json")
        self.assertEqual(src.naver_url("legacy", "datalab"),
                         "https://openapi.naver.com/v1/datalab/shopping/keywords")

    def test_other_search_kinds(self):
        self.assertTrue(src.naver_url("hub", "search", "cafearticle").endswith("/search/v1/cafearticle"))
        self.assertTrue(src.naver_url("legacy", "search", "news").endswith("/v1/search/news.json"))

    def test_paths_differ_between_modes(self):
        """두 모드의 경로가 같아지면 이관 대응이 무너진 것이다."""
        for api, kind in (("search", "blog"), ("datalab", "")):
            self.assertNotEqual(src.naver_url("hub", api, kind), src.naver_url("legacy", api, kind))


class TestAuthSelection(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in
                     ("NAVER_HUB_KEY_ID", "NAVER_HUB_KEY", "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")}

    def tearDown(self):
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_no_keys(self):
        self.assertIsNone(src._naver_auth())
        self.assertEqual(src.naver_mode(), "none")

    def test_hub_wins_over_legacy(self):
        """이관 중에는 둘 다 있을 수 있다 — HUB를 우선해야 무중단 교체가 된다."""
        os.environ.update({"NAVER_HUB_KEY_ID": "a", "NAVER_HUB_KEY": "b",
                           "NAVER_CLIENT_ID": "c", "NAVER_CLIENT_SECRET": "d"})
        base, headers, mode = src._naver_auth()
        self.assertEqual(mode, "hub")
        self.assertIn("X-NCP-APIGW-API-KEY-ID", headers)
        self.assertNotIn("X-Naver-Client-Id", headers)

    def test_legacy_fallback(self):
        os.environ.update({"NAVER_CLIENT_ID": "c", "NAVER_CLIENT_SECRET": "d"})
        base, headers, mode = src._naver_auth()
        self.assertEqual(mode, "legacy")
        self.assertIn("X-Naver-Client-Id", headers)


if __name__ == "__main__":
    unittest.main(verbosity=2)

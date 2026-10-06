"""쇼츠 제목 = 실제 검색어. 상품과 무관한 검색어가 제목이 되면 클릭은 늘고 시청률은 죽는다."""
import search_terms as st

Q = [{"query": "비데 설치비용", "clicks": 0, "impressions": 4},
     {"query": "비데설치비용", "clicks": 0, "impressions": 2},
     {"query": "200만원 12개월 할부", "clicks": 0, "impressions": 3},
     {"query": "네", "clicks": 0, "impressions": 1},
     {"query": "에그크래커 사용법", "clicks": 1, "impressions": 2}]


def test_상품이_들어간_검색어만_고른다():
    assert st.match(["에그크래커", "레트로 수화기"], Q) == "에그크래커 사용법"
    assert st.match(["늘어나는 밀폐용기"], Q) is None          # 할부·비데는 이 편 상품이 아니다


def test_노출이_큰_표기를_고른다():
    assert st.match(["비데 본체"], Q) == "비데 설치비용"


def test_브랜드_모델번호는_토큰이_아니다():
    assert st._tokens("신일전자 삶는 미니세탁기 3kg SWM-1500WSJ") == ["신일전자", "삶는", "미니세탁기"]


def test_제목은_검색어가_앞에_선다():
    assert st.title_with("에그크래커 사용법", "계란 한 번에 깨기") == "에그크래커 사용법, 계란 한 번에 깨기"
    assert st.title_with("에그크래커 사용법", "에그크래커 사용법 총정리") == "에그크래커 사용법"
    assert len(st.title_with("가" * 50, "나" * 50)) <= 80


def test_네트워크가_막히면_조용히_None(monkeypatch):
    monkeypatch.setattr(st, "fetch", lambda *a, **k: [])
    assert st.best_for(["에그크래커"]) is None

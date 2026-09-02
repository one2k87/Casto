"""주간 트렌드 스캔 — 다른 쇼츠/릴스를 분석해 '지금 먹히는 형식'을 data/trends.json으로 갱신.

방식(2026-09-02 설계):
1) YT_API_KEY가 있으면: YouTube Data API로 니치 검색어별 인기 쇼츠 상위 영상의
   제목·조회수를 실측 수집 → LLM이 훅 패턴·형식·소재를 추출.
2) 키가 없으면: LLM 지식 기반 폴백(그 주의 일반적 쇼츠 문법). 실측이 아니므로
   trends.json에 source:"llm-fallback"으로 표시해 대시보드에서 구분한다.
매주 월요일 크론(weekly-trends.yml)이 실행하고, 결과는 make_short.py가 대본에 주입한다.
"""
import json, os, datetime
import requests
from common import cfg, llm_json

def yt_titles(queries, region="KR", per=12):
    key = os.getenv("YT_API_KEY", "")
    if not key:
        return None
    items = []
    for q in queries:
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search",
                             params={"key": key, "q": q, "part": "snippet", "type": "video",
                                     "videoDuration": "short", "order": "viewCount",
                                     "regionCode": region, "relevanceLanguage": "ko",
                                     "publishedAfter": (datetime.datetime.utcnow() - datetime.timedelta(days=30)).isoformat("T") + "Z",
                                     "maxResults": per}, timeout=30)
            for it in r.json().get("items", []):
                items.append(it["snippet"]["title"])
        except Exception as e:
            print("[yt]", q, "실패:", e)
    return items or None

def main():
    c = cfg()
    titles = yt_titles(c["trends"]["queries"], c["trends"].get("region", "KR"))
    src = "youtube-api" if titles else "llm-fallback"
    sample = ("\n".join(f"- {t}" for t in titles[:36])) if titles else "(실측 없음 — 최근 한국 쇼츠/릴스의 일반 문법으로)"
    prompt = f"""당신은 한국 쇼츠/릴스 트렌드 분석가입니다. 니치: {c['niche']}.
최근 30일 인기 쇼츠 제목 샘플:
{sample}

위를 분석해 '이번 주 쇼츠 제작 지침'을 JSON으로 정리하세요:
{{"hooks": [강력한 첫 3초 훅 문장 패턴 6개 — 한국어, 이 니치에 맞게],
 "formats": [지금 먹히는 영상 형식 4개 — 예: 비교 리스트, 실수 지적, 비포애프터, 가격 폭로],
 "topics": [이 니치에서 이번 주 다룰만한 소재 8개],
 "caption_style": "자막 스타일 지침 1문장 (길이·톤·이모지 사용)",
 "hashtags": [해시태그 10개],
 "avoid": [피해야 할 낡은 패턴 3개]}}"""
    data = llm_json(prompt)
    data["updated"] = datetime.date.today().isoformat()
    data["source"] = src
    os.makedirs("data", exist_ok=True)
    json.dump(data, open("data/trends.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[trends] 갱신 완료 ({src}) — 훅 {len(data.get('hooks', []))}개, 소재 {len(data.get('topics', []))}개")

if __name__ == "__main__":
    main()

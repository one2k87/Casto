# 🎬 Casto — 픽담 쇼츠/릴스 완전 자동 배포 엔진

스크립토 패밀리의 배포(Fanout) 라인. **픽담(pickdam.com) 글을 매일 쇼츠/릴스 영상(mp4)으로
완전 자동 변환**해 텔레그램으로 보낸다 — 폰에서 1분 내 유튜브 쇼츠·인스타 릴스 업로드.

## 동작 원리

```
[주 1회] trend_scan.py   다른 쇼츠/릴스 분석(유튜브 인기 영상 실측) → data/trends.json
                          "지금 먹히는 훅·형식·소재"를 매주 자동 갱신
[매일]   make_short.py   픽담 최신 글 → 트렌드 반영 대본(LLM)
                          → 씬 카드(캐릭터/실사 스타일) → 무료 TTS 내레이션
                          → ffmpeg 1080×1920 합성 → 텔레그램 전송
```

## 시크릿 (Settings → Secrets → Actions)

| 이름 | 값 | 비고 |
|---|---|---|
| LLM_API_KEY | Gemini 키 | Scripto/Picto와 동일 |
| TELEGRAM_TOKEN / TELEGRAM_CHAT_ID | 봇 토큰/챗 | 동일 |
| YT_API_KEY | YouTube Data API v3 키 | 선택 — 있으면 트렌드가 '실측' 기반 |

## 설정: `casto.json`
- `style`: `character`(이모지 캐릭터 카드) / `card`(텍스트만) / `realistic`(실사, v1)
- `video.voice`: edge-tts 한국어 보이스
- `trends.queries`: 트렌드 스캔 검색어(니치 확장 시 수정)

## 로드맵
- v0 (지금): 카드+TTS 완전 자동 mp4, 텔레그램 수동 업로드
- v1: 실사/생성 이미지 씬, BGM, 자막 애니메이션
- v2: YouTube API 자동 업로드(OAuth), 인스타 그래프 API, 픽토 상품 데이터 연동

# Tailored 스튜디오 (2026-11-19~)

대사 없는 동물 연재 만화 쇼츠 「Tailored · Tiny Tail World」의 세계관·콘티·렌더 데이터.

| 방 | 파일 | 하는 일 |
|---|---|---|
| 바이블 | `world.json` `characters.json` `inventions.json` `seasons/*.json` `story_so_far.md` | 세계관·캐릭터(고유색·애착템·기준 이미지)·발명품 도감·시즌 아크·줄거리 |
| 작가실 | `episodes/<화>/conti.json` | 컷별 장소·행동·개그·발명품·카메라·효과·효과음 |
| 미술실 | `episodes/<화>/cNN.jpg` `cNN.mp4` | 컷 이미지(힉스필드 GPT Image, 캐릭터 시트 참조)와 마지막 영상 컷 |
| 음악실 | `sfx/*.mp3` `assets/bgm/*.mp3` | 효과음·편별 로파이(ElevenLabs, Actions에서 1회 생성 후 캐시) |
| 편집실 | `../tailored_render.py` `.github/workflows/tailored-render.yml` | 움직이는 만화 렌더 → 텔레그램 |
| 굿즈 창고 | `emoji_pool/` | 표정·동작 컷(투명 배경) 모음 |

## 렌더
`tailored/request.txt`에 `tailored/episodes/s1e01 설명` 한 줄을 적어 푸시하면 Actions가 렌더해 텔레그램으로 보낸다.

## 콘티 컷 형식
`{id, sec, place, who[], beat, action, gag, invention?, scene(영문 장면 묘사), img, alt?, hold?, cam{from[cx,cy,zoom], to[...]}, fx[pop|shake|sway|bob], emotes[{t, kind(! ? heart star zzz sweat), at[x,y]}], sfx[{t, name, prompt, sec}], video?, flash?}`

## 규칙(요약)
- 화면에 글자 없음. 대사 없음. 매 화 마지막 컷은 실제 영상(3~5초).
- 캐릭터 고유색·애착템은 모든 컷에 유지. 지네류 금지, 벌레는 귀엽게 캐릭터화.
- 매 화 발명품 1~2개, 쓴 것은 `inventions.json`의 used에 기록.

## 캐릭터 도구 (2026-11-23)

세계관 안에서 어긋나는 곳을 그림 생성 전에 잡는다. 도감 페이지: https://claude.ai/artifact/5BxL9bSAtYsRhPq4QqNfF1

| 명령 | 하는 일 |
|---|---|
| `python tailored_cast.py lint` | 설정 빠짐·고유색 충돌·키 범위·소지품 장부 점검(충돌이 있으면 종료 코드 1) |
| `python tailored_cast.py check s1e03` | 그 화에 나오는 캐릭터가 확정이고 기준 그림이 있는지 |
| `python tailored_cast.py prompt mochi kong [--back]` | 그림 지시문에 넣을 표준 문장(생김새·애착템·키·계절) |
| `python tailored_cast.py page` | 도감 페이지 `tailored/cast_page.html` 생성(생성 뒤 다시 게시) |

- `characters.json`: 키(모찌 = 1.0)·체형·애착템 그리는 법·금지 사항·첫 등장 화. 처음 등장하기 전에 `_required` 항목을 채우고 status를 확정으로.
- `world.json`: `scale`(크기 분류), `laws`(세계 법칙), `residents`(주민·일터 거인).
- `continuity.json`: 누가 무엇을 갖고 있나, 화가 끝났을 때 어디에 있나, 풀리지 않은 것. 콘티 전에 읽고 게시 뒤 갱신.

제작 순서: 줄거리 승인 → `check <화>` 통과 → `prompt`로 지시문 작성 → 견적·장부 예약 → 그림 생성 → 게시 뒤 `continuity.json` 갱신 → `page` 다시 게시.

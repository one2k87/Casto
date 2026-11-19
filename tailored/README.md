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

# Tailored 롱폼 매일 작업 (Flow 매일 50크레딧 = 5클립)

사용자 결정(2026-11-25): B안 — 시즌 2가 시작되면 매일분은 쇼츠, 롱폼은 월 크레딧으로 몰아서.
시즌 1 쇼츠가 끝나 있는 지금(12월까지)은 **매일분을 시즌 1 롱폼에 쓴다.**

## 매일 순서 (하루 5클립, 50크레딧)

0. **하루치 지급 시각: 매일 13:35 전후**(11/27 확인 — 13:26 0 → 13:40 50, 이월 없음). 매일 예약 작업은 13:50에 돈다. 시작 전 https://one.google.com/ai/activity 에서 「Google Flow 크레딧」 숫자를 읽고, 0이면 건너뜀. (11/27 13:52엔 그 페이지에 「AI 크레딧 0」(구매분)만 보였음 → Flow 화면 오른쪽 위 프로필 메뉴의 「Google Flow 크레딧 ○개」로 확인. 영상 버튼이 빨간 ⓘ로 바뀌면 잔액 0)
1. `tailored/longform/queue.json`에서 status가 `todo` 또는 `redo`인 앞쪽 5개를 고른다(`replaced`는 건너뜀).
2. 크롬 Flow 프로젝트 https://flow.google.com/project/1d459ece-b64b-4613-bc04-8fe6acfe093a 를 연다. **Flow 탭을 화면 앞에 둔다**(뒤에 있으면 크롬이 자동 작업을 1분에 1컷으로 늦춘다).
3. 그림 만들기(0크레딧): 프롬프트 칸 설정 = 이미지 · 16:9 · Nano Banana 2.1 · x1. 「+」로 원본 세로 그림(`<ep>_<img>`, 없으면 raw.githubusercontent.com/one2k87/Casto/main/tailored/episodes/<ep>/<img> 를 받아 「미디어 업로드」)을 넣고 프롬프트:
   `Outpaint this exact illustration into a wide 16:9 landscape frame. Keep the characters, their poses, the art style, colors and lighting exactly the same and centered. Extend the scene naturally to the left and right. No text.` + modules/review/prompt_guards.json 의 flow_image_suffix
4. 영상 만들기(10크레딧): 설정 = 동영상 · 프레임 · 16:9 · Veo 3.1 - Lite · x1. 시작 프레임 = 3의 가로 그림. 프롬프트 = 컷 action을 영어 한두 문장으로 + `Keep the exact art style, colors and character designs of the image. Gentle expressive cartoon animation, smooth natural motion, slow subtle camera movement. No text.` + prompt_guards.json 의 flow_video_suffix. 영상 전에 by_case를 보고 still로 둘 컷은 영상 생성을 건너뛴다(크레딧 아낌)
5. 완성되면 편집 화면 「미디어 다운로드 → 720p」로 받는다(파일 이름 `<ep>_<cut>_wide.mp4`). 받은 파일을 기기 `~/Downloads` → `Casto/tailored/longform/<ep>/<cut>.mp4` 로 복사하고 queue.json status를 `done`으로.
5-1. **검수(QA_CHECKLIST.md 2단계)**: 받은 클립마다 시작·가운데·끝 3장을 뽑아 본다. ❌면 queue status를 `redo`로 두고 이유를 note에 적는다(그림부터 다시).
6. 생성이 「실패」면 크레딧이 환불되므로 그 컷은 `todo`로 두고 다음 날 다시.
7. 끝나면 famto 인박스에 한 줄: `캐스토 | 롱폼 매일 ○/201 (오늘 c..~c..)`.

## 지키는 것
- 워터마크(오른쪽 아래 「Veo」)는 자르거나 가리지 않는다. 가로 영상을 잘라 쇼츠로 쓰지 않는다.
- 요금제 상향·추가 크레딧 구매 없음. 하루 50을 넘겨 쓰지 않는다(월 1,000은 쇼츠·월간 롱폼 몰아서용).
- 크롬이 꺼져 있거나 Flow에 접근이 안 되면 아무것도 하지 말고 famto에 「오늘 건너뜀」 한 줄.

## 렌더(가로 16:9, 1280×720)
- 한 화: `python3 tailored/longform_build.py <ep>` → 그 화 컷 순서대로(c00 제외) 가로 클립을 1배속 앞 6초씩 쓰고, 아직 없는 컷은 세로 그림을 가운데·양옆 흐림으로 임시 표시. 음악은 쇼츠 완성본을 반복(끝 무음 잘라 이음매 매끄럽게)·0.45배, 자막 ko·en·ja·es SRT를 새 시간에 맞춰 함께 만든다.
- 시즌 묶음: `python3 tailored/longform_build.py --season s1e01,s1e02,...,s1e08 --out season1_longform.mp4`
- 워터마크가 있는 가로 클립은 크기만 맞추고 자르지 않는다.

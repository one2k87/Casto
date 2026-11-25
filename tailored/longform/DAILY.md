# Tailored 롱폼 매일 작업 (Flow 매일 50크레딧 = 5클립)

사용자 결정(2026-11-25): B안 — 시즌 2가 시작되면 매일분은 쇼츠, 롱폼은 월 크레딧으로 몰아서.
시즌 1 쇼츠가 끝나 있는 지금(12월까지)은 **매일분을 시즌 1 롱폼에 쓴다.**

## 매일 순서 (하루 5클립, 50크레딧)

1. `tailored/longform/queue.json`에서 status가 `todo`인 앞쪽 5개를 고른다.
2. 크롬 Flow 프로젝트 https://flow.google.com/project/1d459ece-b64b-4613-bc04-8fe6acfe093a 를 연다. **Flow 탭을 화면 앞에 둔다**(뒤에 있으면 크롬이 자동 작업을 1분에 1컷으로 늦춘다).
3. 그림 만들기(0크레딧): 프롬프트 칸 설정 = 이미지 · 16:9 · Nano Banana 2.1 · x1. 「+」로 원본 세로 그림(`<ep>_<img>`, 없으면 raw.githubusercontent.com/one2k87/Casto/main/tailored/episodes/<ep>/<img> 를 받아 「미디어 업로드」)을 넣고 프롬프트:
   `Outpaint this exact illustration into a wide 16:9 landscape frame. Keep the characters, their poses, the art style, colors and lighting exactly the same and centered. Extend the scene naturally to the left and right. No text.`
4. 영상 만들기(10크레딧): 설정 = 동영상 · 프레임 · 16:9 · Veo 3.1 - Lite · x1. 시작 프레임 = 3의 가로 그림. 프롬프트 = 컷 action을 영어 한두 문장으로 + `Keep the exact art style, colors and character designs of the image. Gentle expressive cartoon animation, smooth natural motion, slow subtle camera movement. No text.`
5. 완성되면 편집 화면 「미디어 다운로드 → 720p」로 받는다(파일 이름 `<ep>_<cut>_wide.mp4`). 받은 파일을 기기 `~/Downloads` → `Casto/tailored/longform/<ep>/<cut>.mp4` 로 복사하고 queue.json status를 `done`으로.
6. 생성이 「실패」면 크레딧이 환불되므로 그 컷은 `todo`로 두고 다음 날 다시.
7. 끝나면 famto 인박스에 한 줄: `캐스토 | 롱폼 매일 ○/201 (오늘 c..~c..)`.

## 지키는 것
- 워터마크(오른쪽 아래 「Veo」)는 자르거나 가리지 않는다. 가로 영상을 잘라 쇼츠로 쓰지 않는다.
- 요금제 상향·추가 크레딧 구매 없음. 하루 50을 넘겨 쓰지 않는다(월 1,000은 쇼츠·월간 롱폼 몰아서용).
- 크롬이 꺼져 있거나 Flow에 접근이 안 되면 아무것도 하지 말고 famto에 「오늘 건너뜀」 한 줄.

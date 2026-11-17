"""원템포 대본 작가 v2 (2026-11-17 사용자 피드백: "대사가 짧고 현실 부부 대화가 아니다, 재미없다, 정말 대화하듯이,
더 많은 동작, 힐링 + 잔잔한 웃음, 퇴근길 지친 마음을 치유").

흐름: 플롯 랜덤(story_plots.pick, 최근 3편 제외) + 소재 랜덤(TOPICS, 최근 소재 제외)
   → ① 초안 3편(같은 플롯·소재, 서로 다른 각도) → ② 비평가(별도 프롬프트)가 6항목 채점·최고안 선택·약점 고쳐 최종본(JSON)
   → pilot/story/<ep>/script.json·script.md 저장 → (선택) 낭독 음성(dialogue.py)으로 텔레그램 전송.
키: ANTHROPIC_API_KEY(Actions Secrets, 금고 배포). 모델 STORY_MODEL(기본 claude-opus-5-5).
사용: python story_writer.py <ep 이름> [--plot id] [--topic "소재"] [--readthrough]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
import sys

MODEL = os.getenv("STORY_MODEL", "claude-opus-5-5")

BIBLE = """너는 한국 쇼츠 애니메이션 「원템포 | 토끼와 늘보 부부」의 수석 작가다(클레이 스톱모션, 세로 9:16, 40~50초).

[방향 — 사용자 확정] 힐링 + 잔잔한 웃음. 매일 일하고 퇴근하는 사람이 보고 지친 마음이 풀리는 영상.
귀엽고, 포근하고, 희망적이고, 따뜻하고, 사랑스럽게. 웃음 목표는 박장대소가 아니라 '피식'과 '아 귀여워'. 끝은 마음이 따뜻해져야 한다.

[캐릭터]
- 토끼 아내: 하얀 롭이어 토끼, 분홍 목걸이 방울. 말이 빠르고 하이톤, 감정이 얼굴에 다 드러남, 실황 중계하듯 말함, 질문 폭탄. 사실 겁도 많고 정도 많음.
- 늘보 남편: 크고 듬직한 나무늘보, 남색 반다나. 느리고 낮은 톤. 말수 적지만 한마디가 정곡이거나 엉뚱하게 귀여움. 다 듣고 있고 다 기억함.
- 이웃 미어캣(안경·나비넥타이): 가끔 등장하는 장난꾸러기 조연.

[진짜 대화처럼 — 가장 중요]
1. 실제 한국 부부가 집에서 하는 말투: 반말, 구어체, 말끝 흐리기, 추임새(음, 어?, 아니 근데, 잠깐만, 그니까), 되묻기, 말 끊기.
2. 말 끊기: 끊기는 대사 끝에 "—", 끊는 대사 앞에 [interrupting]. 겹쳐 말하기 [overlapping]. 머뭇거림 [hesitates], 멈춤 [pause].
   감정 태그는 대사당 0~1개: [laughs] [giggles] [sighs] [whispers] [excited] [warm] [sleepy] [surprised]. 남발 금지.
3. 대사 길이를 섞어라(한 단어 ~ 두 문장). 말하는 시간이 전체의 70% 이상(45초면 대사 약 200~260자). 빈 박자 금지.
4. 늘보의 느림은 '대사 전 짧은 뜸'과 '느린 말투'로만 표현하고 대사 자체는 충분히 재밌게.
5. 오글거리는 직설 애정 표현(사랑해, 귀여워, 애칭 남발) 대신 행동과 구체적인 기억으로 애정을 보여라. 단 엔딩의 진심 한마디는 허용.
6. 투닥거림 OK. 인신공격·진짜 상처 주는 말·한쪽만 일방적으로 혼나는 구성 금지. 다툼은 끝에서 웃음이나 다정함으로 뒤집힌다.

[웃음 설계]
- 웃음 아이디어(게임) 하나를 정하고 3단으로 키운 뒤 마지막에 뒤집기(버튼). '피식' 포인트 최소 3개.
- 반전은 매 편 다른 유형(기억 엇갈림, 말 오해, 역할 뒤집기, 숨은 준비, 사물 시점, 관찰자 폭로).
- 공감: 시청자가 댓글에 "우리 집 얘기"라고 쓸 만한 구체적 디테일(실제 습관·물건·시간)을 넣어라. 제품명·브랜드·가격 금지.

[화면·동작 — 클레이 스톱모션]
- 같은 집 안에서 장소·구도를 5~8초마다 바꾼다. 세트: 거실 와이드 / 소파(나란히 앉기) / 창가 벤치 / 부엌(식탁) / 현관 / 거실-창가-부엌 파노라마(걸어서 이동). 새 세트는 편당 1곳까지.
- 동작은 '중간 한 장면'이 아니라 시작→중간→끝 단계로 보여 줘라(예: 패딩 입기 = 패딩 집기 → 한 팔 → 두 팔 → 지퍼 → 완성 포즈). 각 동작을 2~6단계 포즈로 적는다.
- 걷기·앉기·일어서기·손 흔들기·고개 끄덕임·웃음은 재사용 동작이라 비용이 없다. 새 포즈 그림은 편당 25장 이내.
- 엔딩 시그니처 '느린 하이파이브'(토끼가 손 들고 기다리면 늘보 손이 천천히 와서 '짝')를 그 장면 안에서 매번 다른 구도로. 마지막 2초는 따뜻한 버튼(시청자에게 건네는 한마디 가능).
- 첫 소리는 토끼 방울 '딸랑'. 늘보 느린 깜빡임 + '째깍'은 편당 1~2회."""

TOPICS = [
    "저녁 메뉴 '아무거나'", "냉장고 앞 '어딨어?'", "보일러 온도 1도", "택배 몰래 산 거 들킴", "아침 알람 '5분만'",
    "리모컨 넘기기", "같이 사진 찍기(남편 사진 실력)", "주말 계획 짜기", "이불 각자 말고 자기", "귤 까 주기",
    "장보기 목록 빠뜨림", "설거지 순서 차이", "퇴근 후 '오늘 어땠어?'", "잠들기 전 수다", "붕어빵 사러 가기",
    "첫눈 오는 날", "김장 도우러 가기", "크리스마스 트리 꾸미기", "연말 대청소", "새해 계획 세우기",
    "감기 걸린 날 간호", "운동 같이 하자고 했다가", "산책 코스 고르기", "빨래 개는 방식", "치약 짜는 위치",
    "카페에서 메뉴 고르기", "드라마 결말 스포", "양말 짝 맞추기", "화분 물 주기 당번", "마트 계산대 줄 고르기",
]


def ask(prompt: str, system: str = BIBLE, max_tokens: int = 8000, model: str = MODEL) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("[writer] ANTHROPIC_API_KEY 없음")
        return None
    import requests
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": model, "max_tokens": max_tokens, "system": system,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=600)
    if r.status_code != 200:
        print(f"[writer] API {r.status_code}: {r.text[:300]}")
        return None
    j = r.json()
    u = j.get("usage", {})
    print(f"[writer] {model} 입력 {u.get('input_tokens')} · 출력 {u.get('output_tokens')} 토큰")
    return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")


SCHEMA = """{"title": "쇼츠 제목(검색어 포함 20자 이내)", "logline": "한 줄", "plot": "플롯 id", "topic": "소재",
 "cuts": [{"n": 1, "place": "세트 이름", "shot": "와이드|미디엄|클로즈", "card": "인터뷰 질문 카드 등 화면 글자(없으면 빈칸)",
           "action": [{"who": "wife|husband|meerkat|object", "steps": ["포즈1", "포즈2", "..."]}],
           "lines": [{"who": "wife|husband|meerkat|narrator", "text": "태그 포함 대사"}],
           "sfx": ["bell|tick|clap|기타"]}],
 "new_poses": ["새로 그릴 포즈(캐릭터: 설명)"], "pinned_comment": "고정 댓글(캐릭터 속마음 한 줄)",
 "laugh_points": ["피식 포인트"], "heal_point": "힐링 포인트"}"""


def write(ep: str, plot: dict, topic: str) -> dict | None:
    draft = ask(f"""플롯 형식: {plot['name']} — {plot['how']}
웃음 장치: {plot['laugh']} / 힐링 포인트: {plot['heal']} / 참고 유형: {plot['ref']}
소재: {topic}  ·  공개 시기: {dt.date.today().isoformat()} 무렵(계절감 반영)

이 플롯과 소재로 서로 다른 각도의 대본 초안 3편(A·B·C)을 써라. 각 편: 제목, 로그라인, 컷별(장소·구도·동작 단계·대사·소리) 표.
대사는 실제 부부 대화처럼(규칙 '진짜 대화처럼' 전부 적용), 말하는 시간 70% 이상, 피식 포인트 3개 이상.""")
    if not draft:
        return None
    final = ask(f"""아래는 원템포 대본 초안 3편이다. 너는 냉정한 비평가 겸 최종 편집자다.

1) 각 편을 6항목 1~5점으로 채점: 공감(우리 집 얘기 같은가) / 피식 웃음(포인트 수와 질) / 힐링(끝나고 마음이 따뜻한가) /
   대화 자연스러움(실제 부부 말투·말 끊기·추임새) / 반전·버튼 / 제작 가능성(세트·포즈 예산).
2) 최고점 1편을 고르고, 4점 미만 항목을 고쳐 최종본을 완성하라. 대사는 소리 내어 읽었을 때 진짜 대화처럼 들려야 한다.
3) 출력: 먼저 채점 표(마크다운), 그다음 ```json 코드블록 하나에 최종본(아래 형식).
형식: {SCHEMA}

초안:
{draft}""", max_tokens=10000)
    if not final:
        return None
    m = re.search(r"```json\s*(\{.*\})\s*```", final, re.S)
    if not m:
        print("[writer] JSON 못 찾음")
        return None
    script = json.loads(m.group(1))
    out = os.path.join("pilot", "story", ep)
    os.makedirs(out, exist_ok=True)
    json.dump(script, open(os.path.join(out, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(out, "script.md"), "w", encoding="utf-8") as f:
        f.write(f"# {ep} — {script.get('title')}\n\n플롯: {plot['name']} · 소재: {topic}\n\n## 초안 3편\n\n{draft}\n\n## 비평·최종\n\n{final}\n")
    return script


def readthrough(ep: str, script: dict) -> str | None:
    """대본 낭독본(그림 없이 음성만) — 그림 비용 쓰기 전에 재미를 귀로 먼저 확인."""
    import dialogue
    lines = [l for c in script["cuts"] for l in c.get("lines", []) if l["who"] in dialogue.VOICES]
    if not lines:
        return None
    voiced = dialogue.build(lines, os.path.join("pilot", "story", ep, "voice"))
    full = os.path.join("pilot", "story", ep, "voice", "dialogue_full.mp3")
    return full if os.path.exists(full) and voiced else None


if __name__ == "__main__":
    import story_plots
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    ep = a[0]
    opt, i = {}, 1
    while i < len(a):
        if a[i] in ("--plot", "--topic") and i + 1 < len(a):
            opt[a[i]] = a[i + 1]
            i += 2
        else:
            i += 1
    bank = story_plots.load()
    plot = next((p for p in bank["plots"] if p["id"] == opt.get("--plot")), None) or story_plots.pick(bank)
    recent_topics = [h.get("topic") for h in bank["history"][-8:]]
    topic = opt.get("--topic") or random.choice([t for t in TOPICS if t not in recent_topics])
    s = write(ep, plot, topic)
    if not s:
        raise SystemExit("대본 생성 실패")
    bank["history"].append({"date": dt.date.today().isoformat(), "plot": plot["id"], "topic": topic, "episode": ep})
    story_plots.save(bank)
    print(f"✅ {ep}: {s.get('title')} — {plot['name']} / {topic}")
    if "--readthrough" in sys.argv:
        p = readthrough(ep, s)
        if p:
            import requests
            tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
            if tok and chat:
                with open(p, "rb") as f:
                    requests.post(f"https://api.telegram.org/bot{tok}/sendAudio",
                                  data={"chat_id": chat, "caption": f"[원템포 낭독본] {s.get('title')} — {s.get('logline')}"[:1000]},
                                  files={"audio": f}, timeout=120)

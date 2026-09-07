"""캐스토 공용 유틸 — LLM(Gemini REST)·텔레그램·설정 로드.
Scripto/Picto와 독립 실행되도록 의존성을 최소화했다(requests만)."""
import json, os, time
import requests

def cfg():
    c = json.load(open("casto.json", encoding="utf-8"))
    return c

def llm(prompt, max_tokens=8000, temperature=0.8, retries=3, json_mode=False):
    """Gemini generateContent 단순 REST 호출. 실패 시 재시도.

    **thinking 함정(2026-09-07 실측)**: Gemini 2.5 Flash는 사고 토큰이 maxOutputTokens에
    포함되므로, 긴 JSON을 요구하면 본문이 중간에서 잘려 `JSONDecodeError: Unterminated string`이
    난다. 그래서 `thinkingConfig.thinkingBudget=0`으로 사고를 끄고, JSON을 받을 때는
    `responseMimeType`으로 스키마를 강제한다. 잘림은 finishReason=MAX_TOKENS로 판별해
    한도를 올려 재시도한다(조용히 깨진 JSON을 넘기지 않는다).
    """
    key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL") or "gemini-2.5-flash"   # 시크릿 미등록 시 env가 빈 문자열이라 or 필수(404 실측)
    if not key:
        raise SystemExit("LLM_API_KEY 시크릿이 없습니다")
    # 키는 x-goog-api-key 헤더로 전달 — 신형 키(AQ.…)는 ?key= 쿼리 방식에서 404가 난다(2026-09-02 실측)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    gen = {"maxOutputTokens": max_tokens, "temperature": temperature,
           "thinkingConfig": {"thinkingBudget": 0}}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen}
    last = ""
    for i in range(retries):
        r = requests.post(url, json=body, timeout=180,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code == 400 and "thinking" in r.text.lower():
            # 사고 비활성화를 지원하지 않는 모델 → 옵션을 빼고 즉시 재시도
            print("[llm] thinkingConfig 미지원 모델 — 옵션 제거 후 재시도")
            gen.pop("thinkingConfig", None)
            continue
        if r.status_code == 200:
            try:
                cand = r.json()["candidates"][0]
                text = cand["content"]["parts"][0]["text"]
                if cand.get("finishReason") == "MAX_TOKENS":
                    # 잘린 응답을 그대로 파싱하면 원인 불명의 JSONDecodeError로 터진다.
                    print(f"[llm] 출력이 한도({gen['maxOutputTokens']})에서 잘림 — 한도를 올려 재시도")
                    gen["maxOutputTokens"] = min(gen["maxOutputTokens"] * 2, 32000)
                    last = text
                    continue
                return text
            except (KeyError, IndexError, TypeError):
                pass
        time.sleep(8 * (i + 1))
    if last:
        print("[llm] 재시도 후에도 잘림 — 마지막 응답으로 복구를 시도한다")
        return last
    raise RuntimeError(f"LLM 호출 실패: {r.status_code} {r.text[:200]}")

def repair_truncated_json(text):
    """잘린 JSON에서 **마지막까지 온전한 부분만** 살려낸다.

    LLM 응답이 한도에서 끊기면 배열 중간의 객체가 미완성으로 남는다. 한 번의 수집 실패로
    파이프라인 전체를 세우는 것보다, 온전히 받은 항목들만 쓰고 진행하는 편이 낫다
    (수집기는 항목 수가 줄어도 랭킹이 나온다). 복구가 불가능하면 None을 반환한다.
    """
    t = text.strip()
    if not t:
        return None
    # 미완성 문자열/토큰을 잘라내며 뒤에서부터 닫아본다.
    # 하한을 두는 이유: 끝까지 잘라내면 `{` + `}` = 빈 객체가 "파싱 성공"으로 나오는데,
    # 그건 실패보다 나쁘다(0건을 조용히 정상으로 취급해 원인을 숨긴다). 실측으로 잡힌 결함.
    floor = max(len(t) // 2, len(t) - 4000)
    for cut in range(len(t), floor, -1):
        head = t[:cut].rstrip().rstrip(",")
        for tail in ("", "}", "]", "]}", "}]}", "\"}]}", "\"}]}}"):
            try:
                out = json.loads(head + tail)
            except (json.JSONDecodeError, ValueError):
                continue
            if _has_content(out):
                return out
    return None


def _has_content(obj):
    """복구 결과가 쓸모 있는지 — 빈 껍데기는 복구 성공으로 치지 않는다."""
    if isinstance(obj, dict):
        return bool(obj) and any(_has_content(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_content(v) for v in obj)
    return obj not in (None, "", [], {})


def llm_json(prompt, **kw):
    """JSON 응답 강제 + 코드펜스 제거 후 파싱. 잘렸으면 복구를 시도한다."""
    kw.setdefault("json_mode", True)
    t = llm(prompt + "\n\n[출력] 순수 JSON만. 코드블록·설명 금지.", **kw)
    t = t.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        print(f"[llm] JSON 파싱 실패({e}) — 잘린 응답 복구 시도")
        fixed = repair_truncated_json(t)
        if fixed is None:
            raise
        print("[llm] 복구 성공 — 온전히 받은 부분만 사용한다")
        return fixed

def telegram_video(path, caption=""):
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        print("[tg] 토큰 없음 — 전송 생략"); return False
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendVideo",
                          data={"chat_id": chat, "caption": caption[:1000]},
                          files={"video": f}, timeout=300)
    print("[tg] sendVideo", r.status_code)
    return r.status_code == 200

def telegram_msg(text):
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tok and chat):
        return False
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  data={"chat_id": chat, "text": text[:4000]}, timeout=30)
    return True

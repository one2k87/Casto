"""캐스토 공용 유틸 — LLM(Gemini REST)·텔레그램·설정 로드.
Scripto/Picto와 독립 실행되도록 의존성을 최소화했다(requests만)."""
import json, os, time
import requests

def cfg():
    c = json.load(open("casto.json", encoding="utf-8"))
    return c

def llm(prompt, max_tokens=8000, temperature=0.8, retries=3):
    """Gemini generateContent 단순 REST 호출. 실패 시 재시도."""
    key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL") or "gemini-2.5-flash"   # 시크릿 미등록 시 env가 빈 문자열이라 or 필수(404 실측)
    if not key:
        raise SystemExit("LLM_API_KEY 시크릿이 없습니다")
    # 키는 x-goog-api-key 헤더로 전달 — 신형 키(AQ.…)는 ?key= 쿼리 방식에서 404가 난다(2026-09-02 실측)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature}}
    for i in range(retries):
        r = requests.post(url, json=body, timeout=120,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                pass
        time.sleep(8 * (i + 1))
    raise RuntimeError(f"LLM 호출 실패: {r.status_code} {r.text[:200]}")

def llm_json(prompt, **kw):
    """JSON 응답 강제 + 코드펜스 제거 후 파싱."""
    t = llm(prompt + "\n\n[출력] 순수 JSON만. 코드블록·설명 금지.", **kw)
    t = t.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t.strip())

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

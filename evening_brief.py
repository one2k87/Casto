"""저녁 20:00 브리핑 — 작업 시작 시각에 **할 일 한 줄**을 폰으로 보낸다.

사용자의 실제 작업 시간대는 20:00~24:00 KST다(2026-09-09 확정). 그 앞 시간에 모든 자동
작업이 끝나도록 크론을 옮겼고, 이 스크립트가 "지금 앉으면 무엇부터"를 알려준다.

대시보드와 같은 판단 순서를 쓴다: 업로드 → 캡처 → 대기 → 없음.
두 화면이 다른 말을 하면 사람이 헷갈리므로 순서를 반드시 일치시킨다.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request

APP = "https://one2k87.github.io/Casto/dashboard/"


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) if path.endswith(".json") else f.read().strip()
    except Exception:                                     # noqa: BLE001
        return default


def build() -> str:
    today = dt.date.today().isoformat()
    last = _load("data/last_short.txt", "")
    q = _load("data/shot_queue.json", {"items": {}})
    st = _load("data/channel_latest.json", {})
    todo = [i for i in q.get("items", {}).values() if not i.get("done") and not i.get("hold")]
    short_done = (last == today)

    cap = _load("data/last_caption.json", {})
    lines = [f"🌙 {today} 저녁 작업 브리핑", ""]
    if short_done:
        lines.append("1️⃣ 오늘 영상 업로드 (약 3분)")
        if cap.get("date") == today:
            lines.append(f"   「{cap.get('title')}」")
            lines.append("   앱에서 제목·설명 복사 버튼 한 번이면 됩니다")
            if not cap.get("coupang_url"):
                lines.append("   ⚠ 이 제품은 쿠팡 링크가 없습니다 — 앱 🔗 카드에서 먼저 넣어주세요")
    else:
        lines.append("1️⃣ 오늘 쇼츠가 아직 없습니다 — 19:40 자동 제작 확인 필요")
    if todo:
        lines.append("")
        head = ", ".join(f"{n}번 {it.get('display') or it.get('name')}"
                         for n, it in sorted(
                             ((int(n), i) for n, i in q["items"].items()
                              if not i.get("done") and not i.get("hold")))[:3])
        lines.append(f"2️⃣ 상품 캡처 {len(todo)}건 (건당 1분) — {head} …")
    else:
        lines.append("")
        lines.append("2️⃣ 캡처 대기 없음 👍")
    cat = _load("data/catalog.json", {})
    nolink = [e for e in (cat.get("products") or {}).values()
              if e.get("image") and not e.get("coupang_url")]
    if nolink:
        lines.append(f"3️⃣ 쿠팡 링크 {len(nolink)}건 미등록 — 오늘 쓸 것 1개만 넣어도 충분합니다")
    lines += ["",
              f"📊 구독 {st.get('subscribers', '—')} · 영상 {st.get('video_count', '—')}편",
              "", f"👉 앱에서 바로: {APP}"]
    return "\n".join(lines)


def main() -> int:
    tok, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    msg = build()
    print(msg)
    if not (tok and chat):
        print("[brief] 텔레그램 시크릿 없음 — 출력만 하고 종료")
        return 0
    urllib.request.urlopen(
        f"https://api.telegram.org/bot{tok}/sendMessage",
        urllib.parse.urlencode({"chat_id": chat, "text": msg,
                                "disable_web_page_preview": "true"}).encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Veo 3.1 Lite 클립 — 키프레임 두 장(컷 시작·끝) 사이를 잇는다. 정체성 실험(3개월)의 "움직임" 재료.

왜 Lite인가(2026-10-12 결정): 초당 $0.05~0.08로 4초 컷 8개면 편당 $1.6~2.6. 3개월 상한 월 ₩10만 안.
왜 첫·끝 프레임인가: 시작 프레임을 고정하면 캐릭터가 컷마다 달라지는 문제가 줄어든다.
Lite 제약(문서 2026-10 확인): 길이 4·6·8초, 720p 기본(1080p는 8초만), 참고 이미지(referenceImages)·
연장 불가, lastFrame은 지원. 오디오는 항상 생성된다(끌 수 없음) → 우리는 **음성 트랙을 버리고**
TTS·효과음을 따로 얹는다(대사 일관성). 차단된 영상은 과금되지 않는다.

예산 가드: `BUDGET_USD_MONTH` 안에서만 생성한다. 사용량은 `data/veo_usage.json`에 월별로 누적.
키가 없거나 예산을 넘기면 None — 호출부는 클레이 모션(패키지 1)으로 폴백한다. 결번보다 등급 하락이 낫다.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import time

import requests

MODEL = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")
BASE = "https://generativelanguage.googleapis.com/v1beta"
PRICE_PER_SEC = {"720p": 0.05, "1080p": 0.08}         # benchlm 2026-09-11 기준 ❓ 청구서로 재확인
BUDGET_USD_MONTH = float(os.getenv("VEO_BUDGET_USD", "70"))   # ≈ ₩10만
USAGE = "data/veo_usage.json"


def _b64(path: str) -> dict:
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    mime = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    return {"inlineData": {"mimeType": mime, "data": data}}


# ---------------------------------------------------------------- 예산
def usage(path: str = USAGE) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def month_key(now: dt.date | None = None) -> str:
    return (now or dt.date.today()).strftime("%Y-%m")


def spent(path: str = USAGE, now: dt.date | None = None) -> float:
    return float(usage(path).get(month_key(now), {}).get("usd", 0.0))


def charge(seconds: int, resolution: str, path: str = USAGE, now: dt.date | None = None) -> float:
    u = usage(path)
    m = u.setdefault(month_key(now), {"usd": 0.0, "seconds": 0, "clips": 0})
    cost = seconds * PRICE_PER_SEC.get(resolution, 0.08)
    m["usd"] = round(m["usd"] + cost, 4)
    m["seconds"] += seconds
    m["clips"] += 1
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False, indent=1)
    return cost


def within_budget(seconds: int, resolution: str, path: str = USAGE, now: dt.date | None = None) -> bool:
    return spent(path, now) + seconds * PRICE_PER_SEC.get(resolution, 0.08) <= BUDGET_USD_MONTH


# ---------------------------------------------------------------- 요청
def request_body(prompt: str, first: str, last: str | None, seconds: int, resolution: str) -> dict:
    inst = {"prompt": prompt, "image": _b64(first)}
    if last:
        inst["lastFrame"] = _b64(last)
    return {"instances": [inst],
            "parameters": {"aspectRatio": "9:16", "resolution": resolution,
                           "durationSeconds": seconds, "numberOfVideos": 1}}


def clip(prompt: str, first: str, out_path: str, last: str | None = None, seconds: int = 4,
         resolution: str = "720p", timeout: int = 600, poll: int = 10) -> str | None:
    """첫(·끝) 프레임 → mp4. 실패·예산 초과·키 없음이면 None."""
    key = os.getenv("LLM_API_KEY", "")
    if not key:
        print("[veo] LLM_API_KEY 없음 — 생성 건너뜀")
        return None
    if seconds not in (4, 6, 8):
        raise ValueError("Veo 길이는 4·6·8초")
    if resolution == "1080p" and seconds != 8:
        resolution = "720p"
    if not within_budget(seconds, resolution):
        print(f"[veo] ⛔ 월 예산 ${BUDGET_USD_MONTH} 초과 — 클레이 모션으로 폴백")
        return None
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    try:
        r = requests.post(f"{BASE}/models/{MODEL}:predictLongRunning",
                          json=request_body(prompt, first, last, seconds, resolution),
                          headers=headers, timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"[veo] 요청 예외: {e}")
        return None
    if r.status_code != 200:
        print(f"[veo] 요청 실패 {r.status_code}: {r.text[:200]}")
        return None
    op = r.json().get("name")
    if not op:
        print("[veo] operation 이름 없음")
        return None
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(poll)
        try:
            s = requests.get(f"{BASE}/{op}", headers=headers, timeout=30).json()
        except Exception as e:  # noqa: BLE001
            print(f"[veo] 폴링 예외: {e}")
            continue
        if s.get("done"):
            if s.get("error"):
                print(f"[veo] 실패: {s['error']}")
                return None
            uri = video_uri(s)
            if not uri:
                print("[veo] 응답에 영상 없음(차단?) — 과금 없음")
                return None
            v = requests.get(uri, headers=headers, timeout=120, allow_redirects=True)
            if v.status_code != 200:
                print(f"[veo] 다운로드 실패 {v.status_code}")
                return None
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(v.content)
            cost = charge(seconds, resolution)
            print(f"[veo] ✅ {out_path} {seconds}s {resolution} ${cost:.2f} (이달 ${spent():.2f})")
            return out_path
    print("[veo] 시간 초과")
    return None


def video_uri(status: dict) -> str | None:
    try:
        return status["response"]["generateVideoResponse"]["generatedSamples"][0]["video"]["uri"]
    except (KeyError, IndexError, TypeError):
        return None

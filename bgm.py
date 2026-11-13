"""원템포 배경음(BGM) — ElevenLabs Music API로 한 번 만들어 assets/bgm/ 에 저장하고 매 편 재사용.

라이선스(2026-11-13 공식 https://elevenlabs.io/music-terms 확인):
  모든 요금제에서 "All online and offline commercial use permitted, except film, TV, radio, and Studio Games".
  무료 요금제만 'Eleven Music' 표기 필요, 유료(Starter 이상)는 표기 불필요 → 수익 창출 유튜브·인스타 사용 가능.
  단 '베타 서비스'로 만든 결과물은 상업 이용 불가 — music_v2_5 는 API 문서에 베타 표시 없음(11/13 확인).
  주의: AI 음악도 Content ID 오탐 가능성은 있음 → 소유권 주장이 오면 이 파일의 song-id(meta)로 이의 제기.

API: POST https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128
     body {prompt, music_length_ms(3000~600000), model_id, force_instrumental} → mp3 바이트, 헤더 song-id.
키는 Actions Secrets 의 ELEVEN_API_KEY(세션은 키를 읽지 않는다). 파일이 이미 있으면 절대 다시 만들지 않는다.
"""
from __future__ import annotations

import json
import os

DIR = "assets/bgm"
MODEL = os.getenv("ELEVEN_MUSIC_MODEL", "music_v2_5")

# 원템포 기본 트랙(사운드 로고와 어울리게: 오르골·우쿨렐레, 잔잔, 가사 없음)
TRACKS = {
    "cozy_home": ("Gentle cozy instrumental for a cute claymation animation about a married rabbit and sloth couple "
                  "at home. Soft music box and warm ukulele, light brushed percussion, slow relaxed tempo around 80 BPM, "
                  "warm and heartwarming, a little playful, calm background bed under dialogue, no vocals, "
                  "no sudden loud parts, seamless loop-friendly ending."),
    "first_snow": ("Quiet wintery instrumental for a cute claymation animation: celesta and soft glockenspiel with "
                   "gentle felt piano, sleigh-bell sparkle very subtle, slow tempo around 72 BPM, cozy and tender, "
                   "background bed under dialogue, no vocals, no drums, soft fade at the end."),
}


def ensure(name: str, prompt: str | None = None, seconds: int = 60) -> str | None:
    """assets/bgm/<name>.mp3 경로. 없으면 ElevenLabs로 1회 생성(키 없으면 None — 렌더는 배경음 없이 진행)."""
    path = os.path.join(DIR, f"{name}.mp3")
    if os.path.exists(path):
        return path
    key = os.getenv("ELEVEN_API_KEY", "").strip()
    if not key:
        print(f"[bgm] {name}: 파일도 키도 없음 — 배경음 없이 진행")
        return None
    import requests
    body = {"prompt": prompt or TRACKS[name], "music_length_ms": int(seconds * 1000),
            "model_id": MODEL, "force_instrumental": True}
    r = requests.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_44100_128"},
                      headers={"xi-api-key": key, "Content-Type": "application/json"}, json=body, timeout=300)
    if r.status_code != 200 or len(r.content) < 10000:
        print(f"[bgm] 생성 실패 {r.status_code}: {r.text[:200]}")
        return None
    os.makedirs(DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(r.content)
    meta = {"name": name, "song_id": r.headers.get("song-id", ""), "model": MODEL, "seconds": seconds,
            "prompt": body["prompt"], "license": "ElevenLabs paid plan — online commercial use, no attribution (music-terms 2026-11-13)"}
    with open(os.path.join(DIR, f"{name}.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"[bgm] ✅ {path} (song-id {meta['song_id']})")
    return path


if __name__ == "__main__":
    import sys
    for n in (sys.argv[1:] or list(TRACKS)):
        ensure(n)

"""원템포 대사 음성 — ElevenLabs v4 대화(text-to-dialogue) 한 번에 만들고 대사별로 잘라 쓴다 (2026-11-17).

왜 한 번에: 대사를 따로따로 만들면 톤·호흡이 끊긴다. 대화 API는 두 목소리를 한 장면처럼 이어 만들고,
응답의 voice_segments(대사별 시작·끝 초)로 정확히 자를 수 있다.

API(11/17 공식 문서 확인):
  POST https://api.elevenlabs.io/v1/text-to-dialogue/with-timestamps?output_format=mp3_44100_128
  body {inputs:[{text, voice_id}], model_id:"eleven_v4", language_code:"ko"}
  → {audio_base64, voice_segments:[{dialogue_input_index, start_time_seconds, end_time_seconds}], alignment}
  모델 표(models 문서): eleven_v4 = Text to Dialogue API 지원, 한국어 포함. 한 요청 2,000자 이하 권장.
보이스(사용자 확정 11/11): 토끼 Annie = Variables ELEVEN_VOICE_WIFE, 늘보 Bin = ELEVEN_VOICE_HUSBAND.
키 ELEVEN_API_KEY 는 Actions Secrets(세션은 키를 읽지 않는다). 결과는 voice/ 폴더에 캐시 — 대사가 같으면 다시 만들지 않는다.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess

MODEL = os.getenv("ELEVEN_DIALOGUE_MODEL", "eleven_v4")
VOICES = {"wife": os.getenv("ELEVEN_VOICE_WIFE", "Lb7qkOn5hF8p7qfCDH8q"),
          "husband": os.getenv("ELEVEN_VOICE_HUSBAND", "jB1Cifc2UQbq1gR3wnb0")}


def speakable(text: str, who: str) -> str:
    """음성용 글: [laughs]·[interrupting] 같은 v4 감정·대화 태그와 끊김 '—'는 그대로 둔다(모델이 연기에 씀).
    앞 줄임표만 지운다(뜸은 태그 [pause]나 타이밍으로)."""
    t = (text or "").strip()
    t = re.sub(r"^[…\.\s]+", "", t)
    return t


def caption(text: str) -> str:
    """자막용 글: 대괄호 태그 제거, 앞뒤 공백 정리."""
    t = re.sub(r"\[[^\]]*\]\s*", "", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _dur(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def build(lines: list[dict], out_dir: str) -> list[dict]:
    """lines=[{who, text}] → [{who, text, file, dur}]. 키가 없고 캐시도 없으면 file=None, dur=추정치(자막 타이밍용)."""
    os.makedirs(out_dir, exist_ok=True)
    sig = hashlib.sha1(json.dumps([[l["who"], l["text"]] for l in lines], ensure_ascii=False).encode()).hexdigest()[:12]
    meta_p = os.path.join(out_dir, "dialogue.json")
    if os.path.exists(meta_p):
        meta = json.load(open(meta_p, encoding="utf-8"))
        if meta.get("sig") == sig and all(os.path.exists(os.path.join(out_dir, x["file"])) for x in meta["lines"]):
            return [dict(x, file=os.path.join(out_dir, x["file"]), full=os.path.join(out_dir, "dialogue_full.mp3"))
                    for x in meta["lines"]]
    key = os.getenv("ELEVEN_API_KEY", "").strip()
    if not key:
        print("[dialogue] 키도 캐시도 없음 — 음성 없이 자막 타이밍만 추정")
        return [dict(l, file=None, dur=max(0.8, len(l["text"]) * 0.13)) for l in lines]
    import requests
    inputs = [{"text": speakable(l["text"], l["who"]), "voice_id": VOICES[l["who"]]} for l in lines]
    r = requests.post("https://api.elevenlabs.io/v1/text-to-dialogue/with-timestamps",
                      params={"output_format": "mp3_44100_128"},
                      headers={"xi-api-key": key, "Content-Type": "application/json"},
                      json={"inputs": inputs, "model_id": MODEL, "language_code": "ko"}, timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"[dialogue] 실패 {r.status_code}: {r.text[:300]}")
    j = r.json()
    full = os.path.join(out_dir, "dialogue_full.mp3")
    with open(full, "wb") as f:
        f.write(base64.b64decode(j["audio_base64"]))
    segs: dict[int, list[float]] = {}
    for s in j.get("voice_segments", []):                    # 한 대사가 여러 조각이면 처음~끝으로 합친다
        i = s["dialogue_input_index"]
        a, b = s["start_time_seconds"], s["end_time_seconds"]
        segs[i] = [min(segs[i][0], a), max(segs[i][1], b)] if i in segs else [a, b]
    out = []
    for i, l in enumerate(lines):
        a, b = segs.get(i, [0, 0])
        fn = f"line{i:02d}.wav"
        p = os.path.join(out_dir, fn)
        subprocess.run(["ffmpeg", "-y", "-ss", f"{max(a - 0.03, 0):.3f}", "-to", f"{b + 0.08:.3f}", "-i", full,
                        "-af", "afade=t=in:d=0.02,areverse,afade=t=in:d=0.04,areverse", "-ar", "44100", "-ac", "1", p],
                       check=True, capture_output=True)
        out.append({"who": l["who"], "text": l["text"], "file": fn, "dur": round(_dur(p), 3),
                    "start": round(a, 3), "end": round(b, 3)})
    json.dump({"sig": sig, "model": MODEL, "lines": out}, open(meta_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[dialogue] ✅ {len(out)}줄, 전체 {_dur(full):.1f}초 ({MODEL})")
    return [dict(x, file=os.path.join(out_dir, x["file"]), full=full) for x in out]

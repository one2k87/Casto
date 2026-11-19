"""Tailored 자막실 — 콘티의 컷별 내레이션(narr)을 언어별 자막 파일(SRT)로 만든다 (2026-11-19).

영상 화면에는 글자를 넣지 않는다. 내레이션은 유튜브 자막 트랙(언어별)으로만 제공해 시청자가 자기 언어로 본다.
conti.json 의 cut.narr = {"ko": "...", "en": "...", ...}. 컷 시작 시각은 렌더러와 같은 방식(프레임 반올림)으로 계산한다.
출력: <에피소드 폴더>/captions/<화>.<언어>.srt
사용: python tailored_captions.py tailored/episodes/s1e01
"""
from __future__ import annotations

import json
import os
import sys

FPS = 30


def stamp(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def build(ep_dir: str) -> list[str]:
    conti = json.load(open(os.path.join(ep_dir, "conti.json"), encoding="utf-8"))
    spans, t = [], 0.0
    for cut in conti["cuts"]:
        d = max(1, round(cut["sec"] * FPS)) / FPS
        spans.append((t + 0.15, t + d - 0.1, cut.get("narr") or {}))
        t += d
    langs = sorted({k for _, _, n in spans for k in n})
    os.makedirs(os.path.join(ep_dir, "captions"), exist_ok=True)
    out = []
    for lang in langs:
        rows = [(a, b, n[lang]) for a, b, n in spans if n.get(lang)]
        path = os.path.join(ep_dir, "captions", f"{conti['episode']}.{lang}.srt")
        with open(path, "w", encoding="utf-8") as f:
            for i, (a, b, text) in enumerate(rows, 1):
                f.write(f"{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n\n")
        out.append(path)
        print(f"[captions] {path} ({len(rows)}줄)")
    return out


if __name__ == "__main__":
    build(sys.argv[1])

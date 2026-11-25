"""Tailored 연출 시안 렌더러 (2026-11-25, famto 11/25 지시 ②) — tailored_render.py를 고치지 않고 덧씌운다.

추가 연출(크레딧 0, 그림 재생성 없음):
  (a) 카메라: 가감속(easeInOutCubic) 확대·이동을 기본보다 크게 + 손으로 든 듯한 가벼운 흔들림
  (b) 깊이감: rembg(isnet-anime)로 캐릭터만 떼어 내고, 배경은 빈자리를 메운 뒤(cv2.inpaint) 덜 움직여 겹이 생기게
  (c) 컷 전환 효과음: 휙 소리를 숫자로 만들어(외부 API 없음) 컷 경계마다 작게
사용: python tailored_render_fx.py <ep_dir> <out.mp4> [--audio-from 원본.mp4] [--no-depth]
  --audio-from 이 있으면 원본 영상의 소리(배경음·효과음)를 그대로 깔고 전환음만 더한다(키 불필요).
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

import tailored_render as T

W, H, FPS = T.W, T.H, T.FPS
_SESS = None
_CACHE: dict = {}


def ease3(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


def _up(im: Image.Image) -> Image.Image:
    s = max(W / im.width, H / im.height) * 1.5
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def layers(path: str, depth: bool):
    """(배경 RGB, 캐릭터 RGBA 또는 None) — 한 번만 계산해 캐시."""
    key = (path, depth)
    if key in _CACHE:
        return _CACHE[key]
    im = Image.open(path).convert("RGB")
    if not depth:
        _CACHE[key] = (T.load(path), None)
        return _CACHE[key]
    global _SESS
    import cv2
    from rembg import new_session, remove
    _SESS = _SESS or new_session("isnet-anime")
    mask = np.array(remove(im, session=_SESS, only_mask=True))
    hard = (mask > 110).astype(np.uint8) * 255
    hole = cv2.dilate(hard, np.ones((31, 31), np.uint8))
    filled = cv2.inpaint(np.array(im), hole, 11, cv2.INPAINT_TELEA)
    near = cv2.dilate(hard, np.ones((9, 9), np.uint8)) > 0      # 캐릭터 바로 밑만 메운 그림, 나머지는 원본 그대로
    bg = np.where(near[..., None], filled, np.array(im))
    bg = Image.fromarray(bg.astype(np.uint8))
    alpha = Image.fromarray(hard).filter(ImageFilter.GaussianBlur(1.5))
    fg = im.copy()
    fg.putalpha(alpha)
    cov = hard.mean() / 255
    if cov < 0.03 or cov > 0.75:            # 캐릭터를 못 찾았거나 화면 대부분이면 분리하지 않는다
        _CACHE[key] = (T.load(path), None)
    else:
        _CACHE[key] = (_up(bg), _up(fg))
    return _CACHE[key]


def cut_frames(cut: dict, base: str, rng: random.Random, depth: bool):
    if cut.get("video") and os.path.exists(os.path.join(base, cut["video"])):
        yield from T.cut_frames(cut, base, rng)
        return
    n = max(1, round(cut["sec"] * FPS))
    bg, fg = layers(os.path.join(base, cut["img"]), depth)
    cam = cut.get("cam", {})
    a = list(cam.get("from", [0.5, 0.5, 1.0]))
    b = list(cam.get("to", cam.get("from", [0.5, 0.5, 1.06])))
    if abs(b[2] - a[2]) < 0.08:             # 움직임이 작은 컷은 밀어 들어가기를 조금 더
        b[2] = a[2] + 0.10
    fx = set(cut.get("fx", []))
    seed = rng.random() * 10
    side = 1 if rng.random() < 0.5 else -1
    for i in range(n):
        t, u = i / FPS, ease3(i / max(n - 1, 1))
        cx, cy, zoom = (a[j] + (b[j] - a[j]) * u for j in range(3))
        # 손으로 든 카메라: 느린 사인 3개를 겹쳐 2~5px
        hx = 3.2 * math.sin(t * 1.3 + seed) + 1.8 * math.sin(t * 2.7 + seed * 2)
        hy = 2.6 * math.sin(t * 1.1 + seed * 3) + 1.4 * math.sin(t * 2.3 + seed)
        rot, dx, dy = 0.25 * math.sin(t * 0.9 + seed), hx, hy
        if "pop" in fx and t < 0.3:
            zoom *= 1 + 0.07 * math.sin(math.pi * t / 0.3) * (1 - t / 0.3)
        if "bob" in fx:
            dy += 12 * math.sin(t * 5.0)
        if "sway" in fx:
            rot += 0.9 * math.sin(t * 3.0)
        if "shake" in fx:
            k = max(0.0, 1 - t / cut["sec"] * 0.5)
            dx += rng.uniform(-1, 1) * 16 * k
            dy += rng.uniform(-1, 1) * 16 * k
        zoom *= 1 + 0.006 * math.sin(t * 2.4)
        if fg is None:
            fr = T.view(bg, cx, cy, max(zoom, 1.0), rot, dx, dy)
        else:
            par = (u - 0.5) * 2 * side    # -1→1
            fr = T.view(bg, cx, cy, max(1 + (zoom - 1) * 0.75, 1.0) * 1.02, rot * 0.5, dx * 0.5 - 8 * par, dy * 0.5)
            layer = T.view(fg, cx, cy, max(zoom, 1.0) * (1.02 + 0.015 * u), rot, dx + 10 * par, dy)
            fr = fr.convert("RGBA")
            fr.alpha_composite(layer)
            fr = fr.convert("RGB")
        for em in cut.get("emotes", []):
            T.emote(fr, em, t)
        yield fr


def whoosh(path: str, sec: float = 0.42, sr: int = 44100) -> str:
    """대역이 위로 쓸려 올라가는 바람 소리 — 무작위 잡음 + 이동 대역 필터(결정적 시드)."""
    if os.path.exists(path):
        return path
    rs = np.random.RandomState(3)
    n = int(sec * sr)
    x = rs.randn(n)
    tt = np.arange(n) / sr
    f = 300 + 2600 * (tt / sec) ** 1.4
    y = np.zeros(n)
    s1 = s2 = 0.0
    for i in range(n):                       # 상태변수 필터(간단)
        g = 2 * math.sin(math.pi * f[i] / sr)
        hp = x[i] - s1 * 0.6 - s2
        s1 += g * hp
        s2 += g * s1
        y[i] = s1
    env = np.sin(np.pi * np.clip(tt / sec, 0, 1)) ** 1.6
    y = y * env
    y = y / (np.abs(y).max() + 1e-9) * 0.55
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype(np.int16).tobytes())
    return path


def render(ep_dir: str, out: str, audio_from: str | None, depth: bool = True, sfx: bool = True) -> str:
    conti = json.load(open(os.path.join(ep_dir, "conti.json"), encoding="utf-8"))
    rng = random.Random(conti.get("seed", 7))
    tmp = out + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", tmp],
                           stdin=subprocess.PIPE)
    starts, t = [], 0.0
    for cut in conti["cuts"]:
        starts.append(t)
        for fr in cut_frames(cut, ep_dir, rng, depth):
            enc.stdin.write(fr.tobytes())
        t += max(1, round(cut["sec"] * FPS)) / FPS
        print(f"[fx] {cut['id']}", flush=True)
    enc.stdin.close(); enc.wait()
    ins, filt = [], []
    if audio_from:
        ins += ["-i", audio_from]; filt.append("[1:a]anull[a0]")
    k = len(filt)
    if sfx:
        w = whoosh(os.path.join(os.path.dirname(out) or ".", "_whoosh.wav"))
        for st in starts[1:]:
            ms = max(0, int((st - 0.18) * 1000))
            ins += ["-i", w]
            filt.append(f"[{k + 1}:a]adelay={ms}|{ms},volume=0.35[a{k}]"); k += 1
    if filt:
        mix = "".join(f"[a{i}]" for i in range(k)) + f"amix=inputs={k}:normalize=0:duration=first,alimiter=limit=0.95[m]"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, *ins, "-filter_complex", ";".join(filt) + ";" + mix,
                        "-map", "0:v", "-map", "[m]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{t:.2f}", out], check=True)
        os.remove(tmp)
    else:
        os.replace(tmp, out)
    print(f"[fx] ✅ {out} ({t:.1f}s)")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    af = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--audio-from"), None)
    args = [a for a in args if a != af]
    render(args[0], args[1], af, depth="--no-depth" not in sys.argv, sfx="--no-sfx" not in sys.argv)

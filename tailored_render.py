"""Tailored 편집실 — 만화 컷(정지 이미지)을 '움직이는 만화' 쇼츠로 렌더한다 (2026-11-19).

입력: tailored/episodes/<ep>/conti.json  (형식은 tailored/README.md)
  cut = {id, sec, img, alt?, hold?, cam{from[cx,cy,zoom], to[...]}, fx[], emotes[], sfx[], video?, flash?}
  - img/alt : 컷 이미지. alt가 있으면 hold초마다 두 포즈를 번갈아 보여 준다(2장 애니메이션).
  - cam     : 화면 중심(0~1)과 확대. from→to로 부드럽게 이동.
  - fx      : pop(컷 시작 튕김) · shake(흔들림) · sway(좌우 기울임) · bob(위아래 둥실) · breathe(숨쉬기, 기본 켜짐)
  - emotes  : {t, kind(! ? heart star zzz sweat), at[x,y], size?}  — 글자가 아닌 기호만.
  - video   : 마지막 컷 등 실제 영상 파일(mp4). 있으면 이미지 대신 영상을 쓴다.
출력: 1080x1920 30fps mp4. 효과음·배경음은 ElevenLabs(키는 Actions Secrets — 세션은 키를 읽지 않는다)로 만들어 캐시.
사용: python tailored_render.py tailored/episodes/s1e01 [out.mp4] [--cuts c01,c02]
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
FONT = next((p for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                         "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if os.path.exists(p)), None)
GLYPH = {"!": "!", "?": "?", "heart": "♥", "star": "★", "zzz": "z"}
COLOR = {"!": "#FF6B5E", "?": "#6B8CFF", "heart": "#FF7FA0", "star": "#FFD24A", "zzz": "#8FA8E8", "sweat": "#7EC8F2"}


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def load(path: str) -> Image.Image:
    """컷 이미지를 화면을 덮는 크기의 1.5배로 한 번만 키워 둔다(확대해도 흐려지지 않게)."""
    im = Image.open(path).convert("RGB")
    s = max(W / im.width, H / im.height) * 1.5
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return im.filter(ImageFilter.UnsharpMask(radius=1.5, percent=50, threshold=2))


def view(src: Image.Image, cx: float, cy: float, zoom: float, rot: float = 0.0, dx: float = 0.0, dy: float = 0.0) -> Image.Image:
    """src에서 (cx,cy) 중심·zoom 배율·rot(도) 기울임으로 화면 한 장을 뽑는다(소수점 좌표라 움직임이 매끄럽다)."""
    base = max(W / src.width, H / src.height)
    k = 1.0 / (base * zoom)                                    # 화면 1픽셀 = 원본 k픽셀
    vw, vh = W * k, H * k
    px = min(max(cx * src.width, vw / 2), src.width - vw / 2) + dx * k
    py = min(max(cy * src.height, vh / 2), src.height - vh / 2) + dy * k
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    a, b, d, e = k * c, k * s, -k * s, k * c
    cc = px - a * W / 2 - b * H / 2
    ff = py - d * W / 2 - e * H / 2
    return src.transform((W, H), Image.AFFINE, (a, b, cc, d, e, ff), resample=Image.BICUBIC)


def emote(frame: Image.Image, em: dict, t: float) -> None:
    """기호 하나를 통통 튀며 띄운다. 0.25초 동안 커졌다가 자리 잡고, dur 뒤 사라진다."""
    age = t - em["t"]
    dur = em.get("dur", 1.2)
    if age < 0 or age > dur:
        return
    grow = 1.25 - 0.25 * ease((age - 0.12) / 0.15) if age > 0.12 else ease(age / 0.12) * 1.25
    size = max(8, int(em.get("size", 150) * grow))
    x, y = int(em["at"][0] * W), int(em["at"][1] * H - 14 * math.sin(age * 6))
    kind = em["kind"]
    d = ImageDraw.Draw(frame)
    if kind == "sweat":
        r = size // 3
        if r >= 8:                                             # 물방울: 흰 테두리 → 색
            for grow_px, col in ((7, "#FFFFFF"), (0, COLOR[kind])):
                g = r + grow_px
                d.polygon([(x, y - g * 2.1), (x - g * 0.92, y - g * 0.3), (x + g * 0.92, y - g * 0.3)], fill=col)
                d.ellipse([x - g, y - g, x + g, y + g], fill=col)
            d.ellipse([x - r * 0.5, y - r * 0.5, x - r * 0.1, y - r * 0.1], fill="#FFFFFF")
        return
    f = ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default()
    for i in range(3 if kind == "zzz" else 1):
        sz = ImageFont.truetype(FONT, int(size * (0.6 + 0.25 * i))) if (FONT and kind == "zzz") else f
        ox, oy = (i * size * 0.45, -i * size * 0.5) if kind == "zzz" else (0, 0)
        d.text((x + ox, y + oy), GLYPH[kind], font=sz, fill=COLOR[kind], anchor="mm", stroke_width=max(6, size // 14), stroke_fill="#FFFFFF")


def video_frames(path: str, n: int):
    """영상 컷을 화면 크기에 맞춰 n프레임 읽는다(모자라면 마지막 프레임 유지)."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    last = None
    for _ in range(n):
        buf = p.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            last = Image.frombytes("RGB", (W, H), buf)
        yield last or Image.new("RGB", (W, H), "#FFF7EC")
    p.kill()


def cut_frames(cut: dict, base: str, rng: random.Random):
    n = max(1, round(cut["sec"] * FPS))
    vid = cut.get("video")
    if isinstance(vid, str) and os.path.exists(os.path.join(base, vid)):
        for i, fr in enumerate(video_frames(os.path.join(base, vid), n)):
            fr = fr.copy()
            for em in cut.get("emotes", []):
                emote(fr, em, i / FPS)
            yield fr
        return
    imgs = [load(os.path.join(base, cut["img"]))]
    if cut.get("alt") and os.path.exists(os.path.join(base, cut["alt"])):
        imgs.append(load(os.path.join(base, cut["alt"])))
    cam = cut.get("cam", {})
    a, b = cam.get("from", [0.5, 0.5, 1.0]), cam.get("to", cam.get("from", [0.5, 0.5, 1.06]))
    fx = set(cut.get("fx", [])) | {"breathe"}
    hold = cut.get("hold", 0.35)
    for i in range(n):
        t, u = i / FPS, ease(i / max(n - 1, 1))
        cx, cy, zoom = (a[j] + (b[j] - a[j]) * u for j in range(3))
        rot = dx = dy = 0.0
        if "breathe" in fx:
            zoom *= 1 + 0.006 * math.sin(t * 2.4)
        if "pop" in fx and t < 0.3:
            zoom *= 1 + 0.07 * math.sin(math.pi * t / 0.3) * (1 - t / 0.3)
        if "sway" in fx:
            rot = 0.9 * math.sin(t * 3.0)
        if "bob" in fx:
            dy = 12 * math.sin(t * 5.0)
        if "shake" in fx:
            sh = cut.get("shake", {"t": 0, "dur": cut["sec"], "amp": 16})
            if sh["t"] <= t <= sh["t"] + sh["dur"]:
                k = 1 - (t - sh["t"]) / sh["dur"] * 0.5
                dx, dy = rng.uniform(-1, 1) * sh["amp"] * k, dy + rng.uniform(-1, 1) * sh["amp"] * k
                zoom *= 1.03
        src = imgs[int(t / hold) % len(imgs)] if len(imgs) > 1 else imgs[0]
        fr = view(src, cx, cy, max(zoom, 1.0), rot, dx, dy)
        if cut.get("flash") and i < 3:
            fr = Image.blend(fr, Image.new("RGB", (W, H), "white"), [0.7, 0.4, 0.15][i])
        for em in cut.get("emotes", []):
            emote(fr, em, t)
        yield fr


def sfx_file(name: str, prompt: str | None, sec: float = 1.5) -> str | None:
    """tailored/sfx/<name>.mp3 — 없으면 ElevenLabs 효과음 API로 1회 생성(키 없으면 건너뜀)."""
    path = os.path.join(os.getenv("TAILORED_SFX_DIR", "tailored/sfx"), f"{name}.mp3")
    if os.path.exists(path):
        return path
    key = os.getenv("ELEVEN_API_KEY", "").strip()
    if not key or not prompt:
        return None
    import requests
    r = requests.post("https://api.elevenlabs.io/v1/sound-generation", headers={"xi-api-key": key},
                      json={"text": prompt, "duration_seconds": max(0.5, min(sec, 5)), "prompt_influence": 0.5}, timeout=120)
    if r.status_code != 200 or len(r.content) < 2000:
        print(f"[sfx] {name} 실패 {r.status_code}: {r.text[:120]}")
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(r.content)
    print(f"[sfx] ✅ {name}")
    return path


def audio(conti: dict, starts: dict, total: float, out: str) -> str | None:
    ins, filt, idx = [], [], 0
    b = conti.get("bgm")
    if b:
        import bgm
        p = bgm.ensure(b["name"], b.get("prompt"), int(b.get("sec", 60)))
        if p:
            ins += ["-stream_loop", "-1", "-i", p]
            filt.append(f"[{idx}:a]volume={b.get('vol', 0.5)},afade=t=in:d=0.6,afade=t=out:st={total - 1.5:.2f}:d=1.5[a{idx}]")
            idx += 1
    for cut in conti["cuts"]:
        for s in cut.get("sfx", []):
            p = sfx_file(s["name"], s.get("prompt"), s.get("sec", 1.5))
            if p:
                ms = int((starts[cut["id"]] + s.get("t", 0)) * 1000)
                ins += ["-i", p]
                filt.append(f"[{idx}:a]adelay={ms}|{ms},volume={s.get('vol', 0.9)}[a{idx}]")
                idx += 1
    if not idx:
        return None
    mix = "".join(f"[a{i}]" for i in range(idx)) + f"amix=inputs={idx}:normalize=0:duration=longest,alimiter=limit=0.95[m]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", ";".join(filt) + ";" + mix, "-map", "[m]",
                    "-t", f"{total:.2f}", "-ar", "44100", "-ac", "2", out], check=True)
    return out


def render(ep_dir: str, out: str | None = None, only: list[str] | None = None) -> str:
    conti = json.load(open(os.path.join(ep_dir, "conti.json"), encoding="utf-8"))
    cuts = [c for c in conti["cuts"] if not only or c["id"] in only]
    out = out or os.path.join(ep_dir, f"{conti['episode']}.mp4")
    rng = random.Random(conti.get("seed", 7))
    tmp = out + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", tmp],
                           stdin=subprocess.PIPE)
    starts, t = {}, 0.0
    for cut in cuts:
        starts[cut["id"]] = t
        for fr in cut_frames(cut, ep_dir, rng):
            enc.stdin.write(fr.tobytes())
        t += max(1, round(cut["sec"] * FPS)) / FPS
        print(f"[render] {cut['id']} {cut['sec']}s")
    enc.stdin.close()
    enc.wait()
    a = audio({**conti, "cuts": cuts}, starts, t, out + ".audio.m4a")
    if a:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-i", a, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out], check=True)
        os.remove(a)
    else:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", tmp, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:v", "copy",
                        "-c:a", "aac", "-shortest", out], check=True)
    os.remove(tmp)
    print(f"[render] ✅ {out} ({t:.1f}s)")
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    only = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--cuts=")), None)
    render(args[0], args[1] if len(args) > 1 else None, only)

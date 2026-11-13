"""원템포 스톱모션 렌더러 1단계 (2026-11-13, famto 9차 지시 + 실행계획 11/13).

월레스와 그로밋 방식(아드만: 24fps 촬영, 캐릭터는 2프레임마다 한 포즈 = 'on twos', 카메라만 매 프레임):
  ①세트 고정   장면당 배경판 1장(set). 다시 생성하지 않는다. 캐릭터는 투명 PNG(스프라이트)로 따로 만들어 합성.
  ②홀드       포즈 사이를 보간하지 않는다. 포즈 n장을 정해진 '박자'만큼 2프레임 단위로 유지(12fps).
  ③절차 움직임 숨쉬기(세로 1~2%), 접지 그림자 — 12fps 계단식으로만 바뀐다.
  ④보일       2프레임마다 1px 흔들림 + 약한 조명 깜빡임(스톱모션 질감).
  ⑤카메라     배경판에서 느린 밀기(push-in)만 매 프레임(24fps). 전환은 컷만(디졸브·모핑 금지).

사용:  python clay_stop.py <shot.json> <out.mp4>
shot.json 예시는 pilot/stop/test1/shot.json. 좌표는 1080x1920 기준 픽셀, 'feet'는 발바닥 중앙 위치.
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

W, H = 1080, 1920
FPS = 24          # 출력(카메라)
STEP = 2          # 캐릭터는 2프레임마다만 바뀜(on twos → 12fps)


# ------------------------------------------------------------ 스프라이트
_session = None

def cutout(src: str, out: str) -> str:
    """단색 배경 캐릭터 그림 → 투명 PNG(rembg). 이미 있으면 그대로 쓴다(재생성 금지 원칙)."""
    if os.path.exists(out):
        return out
    from rembg import new_session, remove                      # 무거운 의존성은 필요할 때만
    global _session
    if _session is None:                                       # 기본 bria(1GB)는 Actions에 무거움 → isnet(약 170MB)
        _session = new_session(os.getenv("CLAY_MATTE_MODEL", "isnet-general-use"))
    img = Image.open(src).convert("RGBA")
    cut = remove(img, session=_session)          # 캔버스는 자르지 않는다 — 편집 포즈끼리 크기·위치 기준이 같아야 함
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    cut.save(out)
    return out


_cache: dict[tuple, tuple[Image.Image, int]] = {}


def sprite(path: str, body_h: int, tint=None) -> tuple[Image.Image, int]:
    """몸 높이(알파 bbox)를 body_h로 맞춘 스프라이트와 발바닥 y. 편집 포즈마다 캔버스 안 크기·위치가 조금씩 달라서
    (11/13 시험: 토끼가 포즈마다 커졌다 작아짐) 캔버스가 아니라 '몸' 기준으로 맞추고, 가로는 몸 중심에 맞춘다.
    tint=[r,g,b] 배율 — 회색 배경에서 만든 캐릭터를 세트 조명색(따뜻함)에 맞춘다."""
    key = (path, body_h, tuple(tint or ()))
    if key not in _cache:
        im = Image.open(path).convert("RGBA")
        bbox = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() or (0, 0, im.width, im.height)
        im = im.crop(bbox)
        k = body_h / im.height
        im = im.resize((max(1, round(im.width * k)), body_h), Image.LANCZOS)
        if tint:
            r, g, b, a = im.split()
            r, g, b = (ch.point(lambda v, m=m: min(255, round(v * m))) for ch, m in zip((r, g, b), tint))
            im = Image.merge("RGBA", (r, g, b, a))
        _cache[key] = (im, im.height)
    return _cache[key]


def shadow(w: int, strength: float = 0.35) -> Image.Image:
    """발밑 접지 그림자(타원 블러)."""
    sh = Image.new("RGBA", (w * 2, w), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    d.ellipse((w * 0.35, w * 0.38, w * 1.65, w * 0.62), fill=(60, 40, 30, int(255 * strength)))
    return sh.filter(ImageFilter.GaussianBlur(w * 0.06))


# ------------------------------------------------------------ 타임라인
def pose_at(actor: dict, beat: int) -> tuple[str, int]:
    """beat(12fps 박자) → (포즈 파일, 위로 띄울 px). timeline = [[포즈번호, 박자수, (띄움px)], ...]
    loop=true면 반복, 아니면 마지막 포즈 유지. 띄움은 깡충 뛰기처럼 '포즈는 그대로, 몸만 공중'일 때."""
    seq = actor["timeline"]
    total = sum(e[1] for e in seq)
    b = beat % total if actor.get("loop", False) else min(beat, total - 1)
    for e in seq:
        if b < e[1]:
            return actor["poses"][e[0]], (e[2] if len(e) > 2 else 0)
        b -= e[1]
    return actor["poses"][seq[-1][0]], 0


def compose(set_img: Image.Image, actors: list[dict], beat: int, rng: random.Random, R: int = 1) -> Image.Image:
    """한 박자(12fps)의 합성 화면. R=내부 배율(클로즈업은 2 — 확대해도 캐릭터가 뭉개지지 않게). 카메라는 나중에."""
    frame = set_img.copy()
    for a in sorted(actors, key=lambda a: a["feet"][1]):          # 뒤(위쪽)에 선 캐릭터부터
        path, lift = pose_at(a, beat)
        ph = (a.get("pose_h") or {}).get(path, 1.0)           # 웅크림 같은 포즈만 키를 줄인다(예: 0.9)
        sp, foot = sprite(path, round(a["height"] * ph * R), a.get("tint"))
        lift *= R
        breath = 1.0 + a.get("breath", 0.012) * math.sin(2 * math.pi * beat / a.get("breath_beats", 30))
        if breath != 1.0:                                         # 발바닥 기준으로 세로만 살짝(숨쉬기)
            sp = sp.resize((sp.width, max(1, round(sp.height * breath))), Image.LANCZOS)
            foot = round(foot * breath)
        if a.get("flip"):
            sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
        fx, fy = a["feet"][0] * R, a["feet"][1] * R
        jx, jy = rng.choice((-1, 0, 1)) * R, rng.choice((-1, 0, 1)) * R  # 보일: 손으로 만진 듯 1px
        if a.get("shadow", True):                                 # 앉은 캐릭터(소파 위)는 그림자 대신 세트 그늘
            sh = shadow(round(sp.width * a.get("shadow_w", 0.55)), 0.35 * (1 - min(lift, 120) / 200))
            frame.alpha_composite(sh, (round(fx - sh.width / 2), round(fy - sh.height / 2)))
        frame.alpha_composite(sp, (round(fx - sp.width / 2 + jx), round(fy - foot - lift + jy)))
    return frame


def camera(img: Image.Image, t: float, cam: dict) -> Image.Image:
    """t(0~1) 진행도에 따라 zoom0→zoom1, 중심 c0→c1 로 매 프레임 이동(24fps) 후 1080x1920."""
    z = cam.get("zoom0", 1.0) + (cam.get("zoom1", 1.0) - cam.get("zoom0", 1.0)) * t
    c0, c1 = cam.get("c0", [0.5, 0.5]), cam.get("c1", cam.get("c0", [0.5, 0.5]))
    cx = (c0[0] + (c1[0] - c0[0]) * t) * img.width
    cy = (c0[1] + (c1[1] - c0[1]) * t) * img.height
    vw = img.width / z
    vh = vw * H / W
    if vh > img.height:                                   # 세로가 모자라면 세로 기준
        vh = img.height
        vw = vh * W / H
    x0 = min(max(cx - vw / 2, 0), img.width - vw)
    y0 = min(max(cy - vh / 2, 0), img.height - vh)
    return img.crop((round(x0), round(y0), round(x0 + vw), round(y0 + vh))).resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------ 컷 → 영상
def render_cut(cut: dict, set_path: str, tmp: str, seed: int) -> list[str]:
    cam = cut.get("camera", {})
    R = cut.get("res") or (2 if max(cam.get("zoom0", 1), cam.get("zoom1", 1)) > 1.3 else 1)
    set_img = Image.open(set_path).convert("RGBA")
    scale = max(W * R / set_img.width, H * R / set_img.height) * cut.get("set_scale", 1.0)
    if scale != 1.0:
        set_img = set_img.resize((round(set_img.width * scale), round(set_img.height * scale)), Image.LANCZOS)
    n = max(STEP, round(cut["seconds"] * FPS))
    rng = random.Random(seed)
    files, held = [], None
    for f in range(n):
        beat = f // STEP
        if f % STEP == 0:                                           # 캐릭터·보일은 2프레임마다만
            held = compose(set_img, cut.get("actors", []), beat, rng, R)
            fl = rng.uniform(-1, 1)
        img = camera(held, f / max(n - 1, 1), cut.get("camera", {}))
        img = ImageEnhance.Brightness(img).enhance(1.0 + fl * cut.get("flicker", 0.006))
        p = os.path.join(tmp, f"f{len(os.listdir(tmp)):05d}.png")
        img.convert("RGB").save(p, compress_level=1)
        files.append(p)
    return files


def mix_audio(shot: dict, total: float, out: str) -> str | None:
    """효과음(방울·째깍 등)을 지정 시각에 얹고, 배경음(bgm)은 낮게 깔아 앞뒤 페이드. 없으면 None.
    shot["bgm"] = {"name": "first_snow", "volume": 0.16, "offset": 0} — assets/bgm/<name>.mp3(없으면 bgm.ensure로 1회 생성)."""
    events = shot.get("sfx", [])
    bg = None
    if shot.get("bgm"):
        import bgm
        bg = bgm.ensure(shot["bgm"]["name"], shot["bgm"].get("prompt"))
    if not events and not bg:
        return None
    base = os.path.dirname(out)
    cmd, fc, labels = ["ffmpeg", "-y"], [], []
    for i, e in enumerate(events):
        src = e.get("file") or synth(e["kind"], os.path.join(base, f"sfx_{e['kind']}.wav"))
        cmd += ["-i", src]
        ms = int(e["at"] * 1000)
        fc.append(f"[{i}:a]volume={e.get('vol', 1.0)},adelay={ms}|{ms},apad[a{i}]")
        labels.append(f"[a{i}]")
    if bg:
        k = len(events)
        cmd += ["-stream_loop", "-1", "-ss", str(shot["bgm"].get("offset", 0)), "-i", bg]
        fade_out = max(total - 0.8, 0)
        fc.append(f"[{k}:a]atrim=duration={total:.3f},volume={shot['bgm'].get('volume', 0.16)},"
                  f"afade=t=in:st=0:d=0.4,afade=t=out:st={fade_out:.2f}:d=0.8,aresample=44100,apad[a{k}]")
        labels.append(f"[a{k}]")
    fc.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,atrim=duration={total:.3f}[aout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[aout]", "-ar", "44100", "-ac", "2", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def synth(kind: str, out: str) -> str:
    """사운드 로고 초안: 방울 '딸랑'(고음 두 겹 감쇠) · 초침 '째깍'(짧은 클릭) · 하이파이브 '짝'(노이즈 버스트)."""
    if os.path.exists(out):
        return out
    spec = {
        "bell": ("aevalsrc='0.5*sin(2*PI*2093*t)*exp(-5*t)+0.35*sin(2*PI*3136*t)*exp(-7*t)"
                 "+0.25*sin(2*PI*2637*(t-0.09))*exp(-6*(t-0.09))*gt(t,0.09)':s=44100:d=0.9", "volume=0.9"),
        "tick": ("aevalsrc='0.9*sin(2*PI*2400*t)*exp(-180*t)':s=44100:d=0.06", "volume=0.8"),
        "clap": ("anoisesrc=d=0.12:c=pink:a=0.9", "afade=t=out:st=0.01:d=0.11,highpass=f=700"),
    }[kind]
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", spec[0], "-af", spec[1], out], check=True, capture_output=True)
    return out


def render(shot_path: str, out: str) -> str:
    shot = json.load(open(shot_path, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(shot_path))
    j = lambda p: p if os.path.isabs(p) else os.path.join(base, p)      # noqa: E731
    tmp = out + ".frames"
    os.makedirs(tmp, exist_ok=True)
    for f in os.listdir(tmp):
        os.remove(os.path.join(tmp, f))
    for c in shot["cuts"]:                                           # 경로 정리 + 스프라이트 투명화(1회)
        for a in c.get("actors", []):
            a["poses"] = [cutout(j(p), j(p).rsplit(".", 1)[0] + "_cut.png") if not p.endswith("_cut.png") else j(p)
                          for p in a["poses"]]
            if isinstance(a.get("pose_h"), list):                    # 포즈 순서대로 준 키 배율 → 파일 기준
                a["pose_h"] = dict(zip(a["poses"], a["pose_h"]))
    total = 0.0
    for i, c in enumerate(shot["cuts"]):
        render_cut(c, j(c.get("set", shot["set"])), tmp, seed=shot.get("seed", 13) + i)
        total += c["seconds"]
    audio = mix_audio(shot, total, out + ".sfx.wav")
    cmd = ["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(tmp, "f%05d.png")]
    if audio:
        cmd += ["-i", audio, "-c:a", "aac", "-shortest"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", "-r", str(FPS), out]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[stop] ✅ {out} ({total:.1f}초, {len(os.listdir(tmp))}프레임)")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("사용: python clay_stop.py <shot.json> <out.mp4>")
    render(sys.argv[1], sys.argv[2])

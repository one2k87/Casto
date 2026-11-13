"""원템포 스톱모션 렌더러 1단계 (2026-11-13, famto 9차 지시 + 실행계획 11/13).

월레스와 그로밋 방식(아드만: 24fps 촬영, 캐릭터는 2프레임마다 한 포즈 = 'on twos', 카메라만 매 프레임):
  ①세트 고정   장면당 배경판 1장(set). 다시 생성하지 않는다. 캐릭터는 투명 PNG(스프라이트)로 따로 만들어 합성.
  ②홀드       포즈 사이를 보간하지 않는다. 포즈 n장을 정해진 '박자'만큼 2프레임 단위로 유지(12fps).
  ③절차 움직임 위치 이동(path)·깡충 높이·숨쉬기·살랑임은 매 프레임(24fps) ease 보간 — 2단계(11/13 사용자: "뚝뚝 끊긴다").
  ④보일       1px 손떨림은 기본 끔(boil 옵션), 조명 깜빡임 0.4%만. 포즈 전환 반반 섞기(blend)는 잔상이 보여 기본 끔.
  ⑤카메라     path 키프레임으로 매 프레임 이동 — 가로로 긴 파노라마 세트를 훑으며 방→방으로 옮겨 간다
              (11/13 사용자: "배경 고정 말고 다른 배경으로 옮겨가도록"). 컷 사이 전환은 컷만(디졸브·모핑 금지).

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
def ease(t: float) -> float:
    """천천히 출발·천천히 멈춤(smoothstep). 손으로 옮긴 인형처럼 끝에서 감속."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def keyed(keys: list, t: float) -> list[float]:
    """[[시각, v1, v2, ...], ...] 키프레임을 t(초)에서 ease 보간."""
    if t <= keys[0][0]:
        return list(keys[0][1:])
    for k0, k1 in zip(keys, keys[1:]):
        if t <= k1[0]:
            u = ease((t - k0[0]) / max(k1[0] - k0[0], 1e-6))
            return [x0 + (x1 - x0) * u for x0, x1 in zip(k0[1:], k1[1:])]
    return list(keys[-1][1:])


def pose_at(actor: dict, beat: float) -> tuple[str, float]:
    """beat(12fps 박자, 소수 가능) → (포즈 파일, 위로 띄울 px).
    timeline = [[포즈번호, 박자수, (띄움px)], ...] — loop=true면 반복, 아니면 마지막 포즈 유지.
    포즈 그림은 박자 단위로만 바뀌지만(on twos) 띄움(깡충 높이)은 박자 사이를 매 프레임 이어서 포물선처럼 움직인다."""
    seq = actor["timeline"]
    total = sum(e[1] for e in seq)

    def at(bi: int):
        b = bi % total if actor.get("loop", False) else min(bi, total - 1)
        for e in seq:
            if b < e[1]:
                return actor["poses"][e[0]], (e[2] if len(e) > 2 else 0)
            b -= e[1]
        return actor["poses"][seq[-1][0]], 0

    bi = int(beat)
    path, l0 = at(bi)
    _, l1 = at(bi + 1)
    frac = beat - bi
    return path, l0 + (l1 - l0) * frac


def place(a: dict, t: float) -> tuple[float, float]:
    """발 위치: path=[[초, x, y], ...]가 있으면 ease 보간(걸어서 이동), 없으면 feet 고정."""
    return tuple(keyed(a["path"], t)) if a.get("path") else tuple(a["feet"])


def draw_actor(frame: Image.Image, a: dict, path: str, lift: float, t: float, fpos, R: int, rng) -> None:
    ph = (a.get("pose_h") or {}).get(path, 1.0)               # 웅크림 같은 포즈만 키를 줄인다(예: 0.9)
    sp, foot = sprite(path, round(a["height"] * ph * R), a.get("tint"))
    lift *= R
    cb = a.get("crop_bottom", 0.0)                            # 식탁·아일랜드 뒤: 몸 아래쪽(다리)을 잘라 '밑에 들어간' 것처럼
    if cb:
        sp = sp.crop((0, 0, sp.width, round(sp.height * (1 - cb))))
        foot = sp.height
    br = 1.0 + a.get("breath", 0.012) * math.sin(2 * math.pi * t / a.get("breath_sec", 2.6))
    if br != 1.0:                                             # 숨쉬기: 발바닥 기준 세로만 살짝, 매 프레임 부드럽게
        sp = sp.resize((sp.width, max(1, round(sp.height * br))), Image.LANCZOS)
        foot = round(foot * br)
    if a.get("flip"):
        sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
    sway = a.get("sway", 0.0)                                 # 좌우 살랑(도) — 발 기준 회전
    if sway:
        ang = sway * math.sin(2 * math.pi * t / a.get("sway_sec", 1.8))
        big = Image.new("RGBA", (sp.width * 2, sp.height * 2), (0, 0, 0, 0))
        big.alpha_composite(sp, (sp.width // 2, sp.height - foot + sp.height // 2 + foot - sp.height))
        big = big.rotate(ang, resample=Image.BICUBIC, center=(sp.width, sp.height // 2 + foot))
        sp, foot = big, sp.height // 2 + foot
    fx, fy = fpos[0] * R, fpos[1] * R
    j = a.get("boil", 0)                                      # 손떨림(px) — 기본 0(11/13 사용자: 뚝뚝 끊김)
    jx, jy = (rng.uniform(-j, j) * R, rng.uniform(-j, j) * R) if j else (0, 0)
    if a.get("shadow", True):                                 # 앉은 캐릭터(소파 위)는 그림자 끔
        base_w = sp.width if not sway else sp.width // 2
        sh = shadow(round(base_w * a.get("shadow_w", 0.55)), 0.35 * (1 - min(lift, 120 * R) / (200 * R)))
        frame.alpha_composite(sh, (round(fx - sh.width / 2), round(fy - sh.height / 2)))
    frame.alpha_composite(sp, (round(fx - sp.width / 2 + jx), round(fy - foot - lift + jy)))


def compose(set_img: Image.Image, actors: list[dict], t: float, beat: float, rng: random.Random, R: int = 1,
            override: dict | None = None, props: list[dict] | None = None) -> Image.Image:
    """한 프레임 합성. 포즈 그림은 박자(12fps)마다 바뀌고, 위치·높이·숨쉬기·살랑임은 매 프레임(24fps) 이어진다.
    override = {배우이름: 포즈파일} — 포즈가 바뀌는 순간 직전 포즈와 반반 섞는 프레임용.
    props = [{"prop": true, "img": 투명PNG, "pos": [x, 바닥y], "height": px}] — 세트를 '빈 배경판 + 가구 조각'으로 나눠
    가구를 캐릭터와 함께 바닥 y로 정렬해 그린다. 식탁 뒤에 앉은 늘보는 식탁에 아랫몸이 가려진다(11/13 사용자 질문)."""
    frame = set_img.copy()
    placed = [(a, place(a, t)) for a in actors]
    for pr in props or []:                                         # 가구 소품(식탁·아일랜드 등) — 같은 깊이 정렬에 넣는다
        placed.append((pr, tuple(pr["pos"])))
    for a, pos in sorted(placed, key=lambda x: x[1][1]):          # 바닥 y가 작은(뒤쪽) 것부터 → 앞 가구가 뒤 캐릭터를 가린다
        if a.get("prop"):
            sp, foot = sprite(a["img"], round(a["height"] * R), a.get("tint"))
            frame.alpha_composite(sp, (round(pos[0] * R - sp.width / 2), round(pos[1] * R - foot)))
            continue
        path, lift = pose_at(a, beat)
        if override and a.get("name") in override:
            path = override[a["name"]]
        draw_actor(frame, a, path, lift, t, pos, R, rng)
    return frame


def camera(img: Image.Image, t: float, cam: dict, sec: float = 0.0) -> Image.Image:
    """카메라: path=[[초, cx, cy, zoom], ...] 키프레임(ease) 또는 zoom0→zoom1·c0→c1(ease). 매 프레임 이동 후 1080x1920."""
    if cam.get("path"):
        cxf, cyf, z = keyed(cam["path"], sec)
    else:
        u = ease(t)
        z = cam.get("zoom0", 1.0) + (cam.get("zoom1", 1.0) - cam.get("zoom0", 1.0)) * u
        c0, c1 = cam.get("c0", [0.5, 0.5]), cam.get("c1", cam.get("c0", [0.5, 0.5]))
        cxf, cyf = c0[0] + (c1[0] - c0[0]) * u, c0[1] + (c1[1] - c0[1]) * u
    vh = img.height / z                                    # 세로 기준(가로로 긴 파노라마 세트도 같은 규칙)
    vw = vh * W / H
    if vw > img.width:
        vw = img.width
        vh = vw * H / W
    cx, cy = cxf * img.width, cyf * img.height
    x0 = min(max(cx - vw / 2, 0), img.width - vw)
    y0 = min(max(cy - vh / 2, 0), img.height - vh)
    return img.crop((round(x0), round(y0), round(x0 + vw), round(y0 + vh))).resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------ 컷 → 영상
def render_cut(cut: dict, set_path: str, tmp: str, seed: int) -> list[str]:
    cam = cut.get("camera", {})
    zmax = max([cam.get("zoom0", 1), cam.get("zoom1", 1)] + [k[3] for k in cam.get("path", [])])
    R = cut.get("res") or (2 if zmax > 1.3 else 1)
    set_img = Image.open(set_path).convert("RGBA")
    scale = (H * R / set_img.height) * cut.get("set_scale", 1.0)   # 세로를 화면 높이에 맞춘다(파노라마는 가로가 남음)
    if set_img.width * scale < W * R:
        scale = W * R / set_img.width
    if scale != 1.0:
        set_img = set_img.resize((round(set_img.width * scale), round(set_img.height * scale)), Image.LANCZOS)
    n = max(STEP, round(cut["seconds"] * FPS))
    rng = random.Random(seed)
    actors = cut.get("actors", [])
    files, prev = [], {}
    fl = 0.0
    for f in range(n):
        t = f / FPS
        beat = f / STEP
        cur = {a.get("name", str(i)): pose_at(a, beat)[0] for i, a in enumerate(actors)}
        props = cut.get("props", [])
        img = compose(set_img, actors, t, beat, rng, R, props=props)
        changed = {k: prev[k] for k in cur if k in prev and prev[k] != cur[k]}
        if changed and cut.get("blend", False):            # 포즈 전환 반반 섞기 — 빠른 동작에서 잔상이 보여(11/13 시험3) 기본 끔
            img = Image.blend(img, compose(set_img, actors, t, beat, rng, R, override=changed, props=props), 0.45)
        prev = cur
        if f % STEP == 0:
            fl = rng.uniform(-1, 1)
        out = camera(img, f / max(n - 1, 1), cam, t)
        out = ImageEnhance.Brightness(out).enhance(1.0 + fl * cut.get("flicker", 0.004))
        p = os.path.join(tmp, f"f{len(os.listdir(tmp)):05d}.png")
        out.convert("RGB").save(p, compress_level=1)
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
        for pr in c.get("props", []):
            pr["prop"] = True
            src = j(pr["img"])
            pr["img"] = src if src.endswith("_cut.png") else cutout(src, src.rsplit(".", 1)[0] + "_cut.png")
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

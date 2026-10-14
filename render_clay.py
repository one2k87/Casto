"""「콕이네 집」 렌더러 — 대본 + 키프레임 8장 → 22~25초 쇼츠(mp4) + 설명란.

컷마다: 키프레임 → 움직임(Veo Lite 4초 클립, 안 되면 Ken Burns 폴백) → 자막 오버레이(말풍선 대신 하단 자막 + 배역 색 태그)
→ 대사 TTS(배역별 목소리) → 세그먼트. 컷 6은 실물 사진 카드 + 판정 도장(1.5초 뒤 '쾅'), 컷 8은 컷 1 그림으로 루프.
총길이 25초 하드캡(포맷 3판 §2): 넘치면 컷 2를 줄이고 그래도 넘치면 컷 5를 뺀다. 컷 6·7·8은 안 뺀다.

소리: 음악 팩이 아직 없다 — 효과음은 ffmpeg 합성 톤(콕 도장·서랍)만. 음악은 라이선스 확인 뒤 붙인다(❓).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

import veo
import visuals

W, H = 1080, 1920
HARD_CAP = 25.0
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
VOICE = {"wife": ("ko-KR-SunHiNeural", "+10%", "+0Hz"),
         "husband": ("ko-KR-InJoonNeural", "-4%", "-10Hz"),
         "guide": ("ko-KR-SunHiNeural", "-4%", "+25Hz")}
COLOR = {"wife": (236, 128, 104), "husband": (176, 150, 214), "guide": (214, 178, 100)}
STAMP_COLOR = {"콕": (47, 93, 78), "글쎄": (214, 150, 40), "패스": (190, 60, 60)}
MIN_CUT = {1: 2.2, 2: 2.0, 3: 2.4, 4: 3.0, 5: 2.0, 6: 5.0, 7: 2.4, 8: 1.8}


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for p in (FONTS if bold else FONTS[::-1]):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def dur(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- 목소리
async def _tts(text: str, path: str, voice: str, rate: str, pitch: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(path)


def tts_line(text: str, role: str, path: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    voice, rate, pitch = VOICE.get(role, VOICE["wife"])
    try:
        asyncio.run(_tts(text, path, voice, rate, pitch))
        return path if os.path.exists(path) and dur(path) > 0 else None
    except Exception as e:  # noqa: BLE001
        print(f"[render] TTS 실패({role}): {e}")
        return None


# ---------------------------------------------------------------- 오버레이
def _rounded(d: ImageDraw.ImageDraw, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def subtitle_png(line: str, role: str, out: str, hook: str | None = None) -> str:
    """하단 자막(배역 색 태그) + (컷 1) 상단 훅. 투명 PNG."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if hook:
        f = font(96)
        y = int(H * 0.11)
        tw = d.textlength(hook, font=f)
        _rounded(d, (W / 2 - tw / 2 - 36, y - 20, W / 2 + tw / 2 + 36, y + 120), 28, (0, 0, 0, 150))
        d.text((W / 2, y + 50), hook, font=f, fill=(255, 255, 255), anchor="mm",
               stroke_width=4, stroke_fill=(0, 0, 0))
    if line:
        f = font(66)
        y = int(H * 0.78)
        tw = d.textlength(line, font=f)
        _rounded(d, (W / 2 - tw / 2 - 40, y - 56, W / 2 + tw / 2 + 40, y + 56), 30, (0, 0, 0, 170))
        d.text((W / 2, y), line, font=f, fill=(255, 255, 255), anchor="mm")
        # 배역 태그 — 색으로 누가 말하는지
        tag = {"wife": "아내", "husband": "남편", "guide": "콕픽"}.get(role, "")
        if tag:
            ft = font(34)
            tx = W / 2 - tw / 2 - 40
            _rounded(d, (tx, y - 96, tx + 110, y - 58), 14, COLOR.get(role, (120, 120, 120)) + (255,))
            d.text((tx + 55, y - 77), tag, font=ft, fill=(255, 255, 255), anchor="mm")
    im.save(out)
    return out


def card_png(product: dict, out: str) -> str:
    """컷 6 실물 카드 — 상품 사진(실사진만)·이름·가격(있을 때만). 화면 위쪽 62%를 쓴다."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 120, 120, W - 120, int(H * 0.50)      # 안내 캐릭터 얼굴이 아래에 보이게(파일럿 1호 피드백)
    _rounded(d, (x0 + 10, y0 + 14, x1 + 10, y1 + 14), 40, (0, 0, 0, 60))
    _rounded(d, (x0, y0, x1, y1), 40, (255, 255, 255, 245))
    photo = product.get("image")
    if photo and os.path.exists(photo):
        p = Image.open(photo).convert("RGB")
        box = (x1 - x0 - 80, y1 - y0 - 230)
        r = min(box[0] / p.width, box[1] / p.height)
        p = p.resize((max(1, int(p.width * r)), max(1, int(p.height * r))), Image.LANCZOS)
        im.paste(p, (x0 + 40 + (box[0] - p.width) // 2, y0 + 40 + (box[1] - p.height) // 2))
    name = product.get("display", "")
    d.text(((x0 + x1) / 2, y1 - 140), name[:22], font=font(54), fill=(40, 40, 40), anchor="mm")
    price = product.get("price")
    sub = f"{int(price):,}원" if price else "가격은 링크에서"
    d.text(((x0 + x1) / 2, y1 - 70), sub, font=font(42, bold=False), fill=(90, 90, 90), anchor="mm")
    im.save(out)
    return out


def stamp_png(stamp: str, out: str) -> str:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = int(W * 0.76), int(H * 0.34), 170
    col = STAMP_COLOR.get(stamp, (47, 93, 78))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col + (255,), width=18)
    d.text((cx, cy), stamp, font=font(150 if len(stamp) == 1 else 110), fill=col + (255,), anchor="mm")
    im = im.rotate(-12, resample=Image.BICUBIC, center=(cx, cy))
    im.save(out)
    return out


# ---------------------------------------------------------------- 움직임
def sfx(kind: str, out: str) -> str | None:
    spec = {"stamp": ("sine=frequency=160:duration=0.18", "afade=t=out:st=0.03:d=0.15,volume=0.9"),
            "drawer": ("sine=frequency=520:duration=0.10", "afade=t=out:st=0.02:d=0.08,volume=0.5"),
            "pop": ("sine=frequency=900:duration=0.08", "afade=t=out:st=0.01:d=0.07,volume=0.4")}
    if kind not in spec:
        return None
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", spec[kind][0], "-af", spec[kind][1], out],
                       check=True, capture_output=True)
        return out
    except Exception:  # noqa: BLE001
        return None


def motion(keyframe: str, seconds: float, out: str, prompt: str, allow_veo: bool = True) -> tuple[str, str]:
    """(mp4, 'veo'|'kenburns'). Veo는 4초 클립을 받아 길이에 맞춰 자르거나 마지막 프레임을 늘린다."""
    if allow_veo:
        raw = veo.clip(prompt, keyframe, out + ".veo.mp4", seconds=4)
        if raw:
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},tpad=stop_mode=clone:stop_duration=6"
            subprocess.run(["ffmpeg", "-y", "-i", raw, "-an", "-t", f"{seconds:.2f}", "-vf", vf, "-r", "30",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", out], check=True, capture_output=True)
            return out, "veo"
    visuals.motion_clip([keyframe], seconds, out, style="zoom")
    return out, "kenburns"


def _segment(video: str, overlays: list[tuple[str, float]], audio: str | None, seconds: float, out: str,
             extra_audio: list[tuple[str, float]] | None = None) -> str:
    """영상 + 오버레이(PNG, 등장 시각) + 음성(+효과음) → 길이 고정 세그먼트."""
    cmd = ["ffmpeg", "-y", "-i", video]
    for png, _ in overlays:
        cmd += ["-loop", "1", "-i", png]
    a_inputs = []
    if audio:
        cmd += ["-i", audio]; a_inputs.append((len(overlays) + 1, 0.0))
    for path, at in (extra_audio or []):
        cmd += ["-i", path]; a_inputs.append((len(overlays) + 1 + len(a_inputs), at))
    fc, last = [], "[0:v]"
    for i, (_, at) in enumerate(overlays, start=1):
        fc.append(f"{last}[{i}:v]overlay=0:0:enable='gte(t,{at:.2f})'[v{i}]")
        last = f"[v{i}]"
    fc.append(f"{last}trim=duration={seconds:.2f},setpts=PTS-STARTPTS[vout]")
    if a_inputs:
        parts = []
        for j, (idx, at) in enumerate(a_inputs):
            fc.append(f"[{idx}:a]adelay={int(at * 1000)}|{int(at * 1000)},apad[a{j}]")
            parts.append(f"[a{j}]")
        fc.append(f"{''.join(parts)}amix=inputs={len(parts)}:duration=longest:dropout_transition=0,"
                  f"atrim=duration={seconds:.2f}[aout]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{seconds:.2f}", "-i", "anullsrc=r=24000:cl=mono"]
        fc.append(f"[{len(overlays) + 1}:a]atrim=duration={seconds:.2f}[aout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-t", f"{seconds:.2f}",
            "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac", "-ar", "24000", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def plan_durations(cuts: list[dict], voice_dur: dict[int, float]) -> dict[int, float]:
    """컷 길이: 대사 길이 + 0.5초, 컷 최소값 이상. 25초를 넘기면 컷 2 축소 → 컷 5 제거(0)."""
    d = {}
    for c in cuts:
        n = int(c["n"])
        d[n] = max(MIN_CUT.get(n, 2.0), voice_dur.get(n, 0.0) + 0.5)
    total = sum(d.values())
    if total > HARD_CAP and 2 in d:
        d[2] = max(1.2, d[2] - (total - HARD_CAP))
        total = sum(d.values())
    if total > HARD_CAP and 5 in d:
        d[5] = 0.0
        total = sum(d.values())
    if total > HARD_CAP:                      # 그래도 넘치면 전 컷 비례 축소 — 컷을 더 빼진 않는다
        k = HARD_CAP / total
        for n in d:
            d[n] = round(d[n] * k, 2)
    return d


def render(script: dict, frames: dict[int, str], product: dict, out_dir: str = "out/clay",
           allow_veo: bool = True) -> dict:
    """→ {"video", "seconds", "sources": {컷: 'veo'|'kenburns'}, "dropped": [...]}"""
    os.makedirs(out_dir, exist_ok=True)
    cuts = sorted(script.get("cuts", []), key=lambda c: int(c["n"]))
    voices, vd = {}, {}
    for c in cuts:
        n = int(c["n"])
        p = tts_line(c.get("line", ""), c.get("who", "wife"), os.path.join(out_dir, f"v{n}.mp3"))
        if p:
            voices[n] = p
            vd[n] = dur(p)
    durs = plan_durations(cuts, vd)
    segs, sources, dropped = [], {}, []
    last_frame = None
    stamp_wav = sfx("stamp", os.path.join(out_dir, "sfx_stamp.wav"))
    drawer_wav = sfx("drawer", os.path.join(out_dir, "sfx_drawer.wav"))
    for c in cuts:
        n = int(c["n"])
        if durs.get(n, 0) <= 0:
            dropped.append(n); continue
        frame = frames.get(n) or last_frame
        if not frame:
            dropped.append(n); continue
        last_frame = frame
        seconds = durs[n]
        clip, src = motion(frame, seconds, os.path.join(out_dir, f"m{n}.mp4"), c.get("scene", ""),
                           allow_veo=allow_veo and n != 6)
        sources[n] = src
        overlays = [(subtitle_png(c.get("line", ""), c.get("who", ""), os.path.join(out_dir, f"s{n}.png"),
                                  hook=script.get("hook") if n == 1 else None), 0.0)]
        extra = []
        if n == 6:
            overlays.insert(0, (card_png(product, os.path.join(out_dir, "card.png")), 0.0))
            overlays.append((stamp_png(script.get("stamp", "글쎄"), os.path.join(out_dir, "stamp.png")),
                             max(1.5, vd.get(6, 0) + 0.2)))
            if stamp_wav:
                extra.append((stamp_wav, max(1.5, vd.get(6, 0) + 0.2)))
        if n == 7 and drawer_wav:
            extra.append((drawer_wav, 0.6))
        seg = _segment(clip, overlays, voices.get(n), seconds, os.path.join(out_dir, f"seg{n}.mp4"), extra)
        segs.append(seg)
    lst = os.path.join(out_dir, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(s)}'\n" for s in segs)
    video = os.path.join(out_dir, "short.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
                    "short.mp4"], check=True, capture_output=True, cwd=out_dir)
    return {"video": video, "seconds": round(dur(video), 2), "sources": sources, "dropped": dropped,
            "durations": durs}


def caption(script: dict, product: dict, disclosure: str, pickdam: dict | None = None) -> str:
    """설명란(포맷 3판 §7): 고지 → 🛒 링크 → 제목 → (패스) 대신 이거 → 📄 픽담 → 구독 → 해시태그 ≤5."""
    lines = [disclosure]
    url = product.get("coupang_url")
    if url:
        lines.append(f"🛒 {product.get('display')} 쿠팡 → {url}")
    lines += ["", script.get("title", ""), f"판정: {script.get('stamp')} — {script.get('reason', '')}"]
    if script.get("stamp") == "패스" and script.get("alt_url"):
        lines.append(f"🔁 대신 이거 → {script['alt_url']}")
    if pickdam and pickdam.get("link"):
        lines.append(f"📄 {pickdam.get('title', '픽담 비교')} → {pickdam['link']}")
    lines += ["", "구독은 여기서 👉", "", "#콕이네집 #콕픽 #살림템 #주방꿀템 #쿠팡추천"]
    return "\n".join(lines)

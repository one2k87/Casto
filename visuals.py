"""콕픽 비주얼 레이어 — 클레이 아트 에셋 합성 + ffmpeg 모션.

문제(2026-09-07 사용자 피드백): PIL로 도형을 그린 콕이는 자리 채우기용이라 퀄리티가 낮다.
3D 클레이 질감은 코드로 그릴 수 있는 것이 아니다.

해결 구조 — **에셋이 있으면 쓰고, 없으면 기존 카드로 폴백**한다(발행 중단 없음).
  1) 배경: 파스텔 클레이 아트 이미지 1장(1080×1920)
  2) 캐릭터: 투명 PNG로 뽑은 콕이 표정·동작 세트를 배경 위에 합성
  3) 텍스트: 기존 타이포 규칙 그대로 얹는다(이모지 금지, 도형·한글만)
  4) 모션: ffmpeg zoompan으로 느린 줌, 콕 타격은 정상↔눌림 프레임 교차로 펀치감

정지 이미지 + 모션만으로도 체감 품질이 크게 오르므로, Veo 동영상 클립(클립뱅크)은
그다음 단계로 미룰 수 있다. 에셋 파일명은 `ASSETS` 표에 고정한다.
"""
from __future__ import annotations

import os
import subprocess

from PIL import Image, ImageDraw, ImageFilter

ASSET_DIR = "assets/koki"
W, H = 1080, 1920

# 파일명 → 용도. 사용자가 나노바나나(구글 AI Pro 포함)로 뽑아 이 이름으로 넣는다.
ASSETS = {
    "bg":       "bg.png",           # 배경 1080×1920, 중앙은 비워둘 것(캐릭터·자막 자리)
    "idle":     "koki_idle.png",     # 기본 미소 — 표지·룰 씬
    "excited":  "koki_excited.png",  # 기대(눈 반짝) — 룰 씬
    "squish":   "koki_squish.png",   # 콕 눌림 — 타격 프레임
    "open":     "koki_open.png",     # 개봉(뚜껑 팟 + 꽃가루) — 오늘의 콕/조건콕
    "nope":     "koki_nope.png",     # 도리도리 — 다음콕
}
CHAR_BOX = (int(W * 0.62), int(H * 0.30))   # 캐릭터 최대 크기
CHAR_CENTER = (W // 2, int(H * 0.34))


def path(name: str) -> str | None:
    """에셋 경로. 없으면 None → 호출부가 카드로 폴백한다."""
    f = ASSETS.get(name)
    if not f:
        return None
    p = os.path.join(ASSET_DIR, f)
    return p if os.path.exists(p) else None


def ready() -> bool:
    """최소 세트(배경 + 기본 표정)가 갖춰졌는가."""
    return bool(path("bg") and path("idle"))


def missing() -> list[str]:
    return [f"{k} ({v})" for k, v in ASSETS.items() if not path(k)]


def _fit(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    img = img.copy()
    img.thumbnail(box, Image.LANCZOS)
    return img


def compose(character: str = "idle", bg_name: str = "bg") -> Image.Image | None:
    """배경 + 캐릭터 합성. 텍스트는 호출부가 이 위에 그린다(타이포 규칙을 한곳에 두기 위해)."""
    bgp = path(bg_name)
    if not bgp:
        return None
    bg = Image.open(bgp).convert("RGB")
    if bg.size != (W, H):
        # 비율이 달라도 세로 화면을 채우도록 크롭(썸네일 여백이 생기면 브랜드가 깨진다)
        r = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * r), int(bg.height * r)), Image.LANCZOS)
        left, top = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((left, top, left + W, top + H))
    cp = path(character) or path("idle")
    if cp:
        ch = _fit(Image.open(cp).convert("RGBA"), CHAR_BOX)
        bg.paste(ch, (CHAR_CENTER[0] - ch.width // 2, CHAR_CENTER[1] - ch.height // 2), ch)
    return bg


# ------------------------------------------------------------------ 실제 상품 사진
"""상품 사진 슬롯 — **"어떤 물건인지 모양이 제대로 보여야 한다"**(2026-09-08 요구).

클레이 콕이는 채널의 얼굴이지, 상품 설명이 아니다. 시청자가 "어 이거 내가 봤던 거잖아"로
재인하려면(전략 5-4-10) 피드에서 본 것과 **같은 모양**이 화면에 있어야 한다. 그래서 상품이
확정된 순간부터는 실사진이 주인공이고 콕이는 옆으로 비켜선다.

사진 출처는 catalog.py가 통제한다. 여기서는 "있으면 예쁘게 얹는다"만 한다.
"""
PRODUCT_BOX = (int(W * 0.62), int(H * 0.24))   # 사진 카드 안쪽 최대 크기
PRODUCT_CENTER = (W // 2, int(H * 0.33))


def knockout_white(img: Image.Image, tol: int = 30, floor: int = 200) -> Image.Image:
    """상품컷의 밝은 배경을 투명으로 바꾼다(파스텔 카드 위에 회색 사각형이 뜨지 않게).

    AI·쇼핑몰 상품컷의 배경은 순백(255)이 아니라 **미묘한 회백색**인 경우가 많다(실측: 240~248).
    그래서 고정 임계값 대신 **모서리 색을 기준으로 한 허용오차**로 판정한다.
    가장자리에서 흘러들어오는 flood fill이라 **제품 안쪽의 흰색(가전 본체 등)은 보존**된다.
    """
    im = img.convert("RGBA")
    px = im.load()
    w, h = im.size
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    ref = tuple(sorted(c[i] for c in corners)[len(corners) // 2] for i in range(3))
    if min(ref) < floor:          # 배경이 밝지 않다 → 누끼 대상이 아니다(연출컷 등)
        return im
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + \
            [(x, y) for y in range(h) for x in (0, w - 1)]
    while stack:
        x, y = stack.pop()
        if not (0 <= x < w and 0 <= y < h) or seen[y * w + x]:
            continue
        r, g, b, a = px[x, y]
        if a == 0 or max(abs(r - ref[0]), abs(g - ref[1]), abs(b - ref[2])) > tol:
            continue
        seen[y * w + x] = 1
        px[x, y] = (r, g, b, 0)
        stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    return im


def trim(im: Image.Image, margin: int = 8) -> Image.Image:
    """투명 여백을 잘라낸다 — **쇼핑몰 상품컷은 여백이 절반**이라 그대로 넣으면 제품이 작게 보인다.

    "모양이 제대로 보여야 한다"는 요구의 실제 해결점이 여기다. 잘라내야 카드를 제품이 꽉 채운다.
    """
    bb = im.getbbox() if im.mode == "RGBA" else None
    if not bb:
        return im
    x0, y0, x1, y1 = bb
    x0, y0 = max(x0 - margin, 0), max(y0 - margin, 0)
    x1, y1 = min(x1 + margin, im.width), min(y1 + margin, im.height)
    # 잘린 결과가 원본의 4% 미만이면 누끼가 잘못된 것 → 원본을 쓴다(제품을 지워버리는 사고 방지)
    if (x1 - x0) * (y1 - y0) < im.width * im.height * 0.04:
        return im
    return im.crop((x0, y0, x1, y1))


def product_shot(path: str, box: tuple[int, int] = PRODUCT_BOX,
                 cut_white: bool = True) -> Image.Image | None:
    """상품 사진을 카드에 넣을 크기로 준비한다(누끼 → 여백 제거 → 리사이즈). 실패하면 None."""
    try:
        im = Image.open(path)
    except Exception as e:                                    # noqa: BLE001
        print("[visuals] 상품 사진 열기 실패(무시):", e)
        return None
    im = im.convert("RGBA")
    if im.width * im.height > 4_000_000:      # 큰 원본은 줄여서 flood fill 비용을 낮춘다
        im.thumbnail((1600, 1600), Image.LANCZOS)
    if cut_white:
        im = trim(knockout_white(im))
    im.thumbnail(box, Image.LANCZOS)
    return im


def paste_product(img: Image.Image, path: str, label: str = "",
                  center: tuple[int, int] = PRODUCT_CENTER,
                  box: tuple[int, int] = PRODUCT_BOX,
                  accent: tuple[int, int, int] = (47, 93, 78),
                  font=None, note: str = "", note_font=None) -> tuple[int, int, int, int] | None:
    """파스텔 카드 위에 상품 사진을 얹는다. 반환값은 카드 bbox(호출부가 레이아웃 계산에 쓴다).

    흰 라운드 카드 + 부드러운 그림자 = 제품컷을 배경과 분리해 '진짜 물건'으로 보이게 한다.
    label(브랜드+모델)은 카드 아래에 작게 — 사진과 이름이 붙어 있어야 정보가 전달된다.
    """
    shot = product_shot(path, box)
    if shot is None:
        return None
    pad = 46
    cw, ch = shot.width + pad * 2, shot.height + pad * 2
    x0, y0 = center[0] - cw // 2, center[1] - ch // 2
    bbox = (x0, y0, x0 + cw, y0 + ch)

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (x0 + 6, y0 + 14, x0 + cw + 6, y0 + ch + 18), radius=44, fill=(60, 70, 64, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    img.paste(Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB"), (0, 0))

    d = ImageDraw.Draw(img)
    d.rounded_rectangle(bbox, radius=44, fill=(255, 255, 255), outline=accent, width=5)
    img.paste(shot, (center[0] - shot.width // 2, center[1] - shot.height // 2), shot)
    if label and font is not None:
        d.text((center[0], y0 + ch + 44), label[:24], font=font, fill=accent, anchor="mm")
    if note and note_font is not None:
        # AI 재현 이미지 표기 — 실사진인 척하지 않는다
        tw = d.textlength(note, font=note_font)
        d.rounded_rectangle((x0 + 14, y0 + ch - 52, x0 + 14 + tw + 34, y0 + ch - 10),
                            radius=20, fill=(255, 255, 255), outline=accent, width=3)
        d.text((x0 + 14 + tw / 2 + 17, y0 + ch - 31), note, font=note_font, fill=accent, anchor="mm")
    return bbox


# ------------------------------------------------------------------ 모션
def motion_clip(frames: list[str], seconds: float, out: str, style: str = "zoom",
                fps: int = 30) -> str:
    """정지 이미지에 모션을 얹어 mp4를 만든다.

    - `zoom`  : 느린 줌인(Ken Burns). 정지 화면 특유의 지루함을 없앤다
    - `punch` : 정상↔눌림 프레임을 교차해 콕 타격의 리듬을 만든다(프레임 2장 필요)
    - `pop`   : 살짝 축소→확대로 개봉의 '팟' 느낌

    프레임이 1장뿐이면 자동으로 zoom으로 떨어진다.
    """
    n = max(int(seconds * fps), 1)
    if style == "punch" and len(frames) >= 2:
        # 눌림 프레임을 짧게 끼워 넣어 타격감을 만든다(0.12초 ×2회)
        hit = max(int(0.12 * fps), 2)
        parts = []
        for i, (img, dur) in enumerate([(frames[0], n // 3), (frames[1], hit),
                                        (frames[0], n // 3), (frames[1], hit),
                                        (frames[0], max(n - 2 * (n // 3) - 2 * hit, hit))]):
            p = f"{out}.part{i}.mp4"
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{dur/fps:.3f}",
                            "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264",
                            "-vf", f"scale={W}:{H}", p], check=True, capture_output=True)
            parts.append(p)
        lst = f"{out}.list.txt"
        with open(lst, "w") as f:
            f.writelines(f"file '{os.path.basename(p)}'\n" for p in parts)
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", out], check=True, capture_output=True,
                       cwd=os.path.dirname(out) or ".")
        return out

    zexpr = {"zoom": "min(zoom+0.0012,1.12)", "pop": "if(lte(on,6),1.06,max(1.0,zoom-0.004))"}
    z = zexpr.get(style, zexpr["zoom"])
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", frames[0], "-t", f"{seconds:.2f}",
                    "-r", str(fps), "-pix_fmt", "yuv420p", "-c:v", "libx264",
                    "-vf", (f"scale={W*2}:{H*2},zoompan=z='{z}':d={n}:"
                            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}"),
                    out], check=True, capture_output=True)
    return out


def status() -> str:
    if ready():
        have = [k for k in ASSETS if path(k)]
        return f"[visuals] 클레이 에셋 사용 — 보유 {len(have)}/{len(ASSETS)}: {', '.join(have)}"
    return ("[visuals] 클레이 에셋 없음 — 도형 카드로 폴백(품질 낮음).\n"
            f"[visuals]   필요한 파일: {', '.join(missing())}\n"
            f"[visuals]   생성 프롬프트: docs/콕이_에셋_프롬프트.md")

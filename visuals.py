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

from PIL import Image

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

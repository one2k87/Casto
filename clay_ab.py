"""클레이 A/B 비교 1편 (2026-11-11 사용자: "a와 b 비교해보자 · 그대로 1편을 만들어봐").

A = 무료 스톱모션: Cloudflare Workers AI FLUX.2 [klein] 4B(참고 이미지 최대 4장)로 컷마다 포즈 3장 →
    ffmpeg 움직임 보간(minterpolate, 무료)으로 24fps → 미세한 '숨쉬기' 흔들림. 비용 ₩0(하루 무료 1만 뉴런 안).
B = Flow(구독 Google AI Pro, Gemini Omni 1.2 Flash) — A와 **같은 시작 프레임·같은 음성·같은 자막**으로 컷별 클립을 만들어
    `pilot/ab/<ep>/flow/cutNN.mp4` 로 넣으면 `b` 단계가 조립한다. 영상만 다르고 나머지는 같아야 비교가 공정하다.

실행(GitHub Actions — 키는 Secrets):  python clay_ab.py a pilot/ab/ep1   /   python clay_ab.py b pilot/ab/ep1
FLUX.2 klein REST(11/11 Cloudflare 문서 확인): multipart, prompt·input_image_0~3(각 512x512 미만)·width·height·seed,
스텝 4 고정. 가격표: 출력 512² 타일당 26.05뉴런, 입력 타일당 5.37뉴런.
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys

import requests
from PIL import Image

import render_clay as rc

MODEL = os.getenv("CF_CLAY_MODEL", "@cf/black-forest-labs/flux-2-klein-4b")
RUN = "https://api.cloudflare.com/client/v4/accounts/{}/ai/run/" + MODEL
KW, KH = 576, 1024                      # 키프레임(9:16). 출력 타일 2x2=4 → 약 104뉴런 + 입력
FPS = 24
CAST = "assets/clay_animal"
LOOK = ("handmade stop-motion claymation, plasticine figures with visible fingerprint texture, soft matte clay, "
        "rounded shapes, miniature handmade set, warm cozy lighting, shallow depth of field, Aardman-like charm, "
        "no text, no letters, no watermark")
CAST_LOCK = ("EXACTLY the characters shown in the reference images, same colors and shapes in every frame. "
             "WIFE = small WHITE clay RABBIT with floppy ears and a thin PINK collar with a tiny bell. "
             "HUSBAND = big gentle BROWN-GREY clay SLOTH with long arms, sleepy kind eyes and dark eye patches. "
             "Never add any other character, never a human")
SEED = int(os.getenv("CLAY_SEED", "1111"))

# 11/11 famto 지시(사용자): 토끼 말 빠르게(1.15), 늘보는 '조금'만 느리게(0.85), 앞 뜸 0.3초
rc.ELEVEN_STYLE["wife"]["speed"] = 1.15
rc.ELEVEN_STYLE["husband"]["speed"] = 0.85
LEAD = {"wife": 0.0, "husband": 0.3, "": 0.0}
TAIL = {"wife": 0.35, "husband": 0.7, "": 0.0}
MIN_CUT = {"wife": 2.6, "husband": 3.0, "": 3.0}

NEURONS = {"images": 0, "est": 0.0}


def _small_png(path_or_img, max_side: int = 448) -> bytes:
    im = Image.open(path_or_img) if isinstance(path_or_img, str) else path_or_img
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)          # 입력은 512x512 미만이어야 한다(문서)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def klein(prompt: str, out: str, refs: list = (), w: int = KW, h: int = KH, seed: int = SEED) -> str | None:
    acc, tok = os.getenv("CF_ACCOUNT_ID", "").strip(), os.getenv("CF_API_TOKEN", "").strip()
    if not (acc and tok):
        raise SystemExit("CF_ACCOUNT_ID/CF_API_TOKEN 없음 — 키 금고에서 Casto 배포 필요")
    files = {f"input_image_{i}": (f"ref{i}.png", _small_png(r), "image/png") for i, r in enumerate(refs[:4])}
    data = {"prompt": prompt[:2048], "width": str(w), "height": str(h), "seed": str(seed)}
    for attempt in range(3):
        try:
            parts = {k: (None, v) for k, v in data.items()}      # 참고 이미지가 없어도 multipart 로 보낸다(문서)
            parts.update(files)
            r = requests.post(RUN.format(acc), headers={"Authorization": f"Bearer {tok}"},
                              files=parts, timeout=180)
        except Exception as e:                                   # noqa: BLE001
            print(f"[klein] 예외: {e}")
            continue
        if r.status_code != 200:
            print(f"[klein] 실패 {r.status_code}: {r.text[:240]}")
            if r.status_code in (400, 401, 403):
                return None
            continue
        raw = None
        if r.headers.get("content-type", "").startswith("image/"):
            raw = r.content
        else:
            try:
                j = r.json()
                b64 = (j.get("result") or {}).get("image") or j.get("image")
                raw = base64.b64decode(b64) if b64 else None
            except Exception as e:                               # noqa: BLE001
                print(f"[klein] 응답 파싱 실패: {e} {r.text[:160]}")
        if not raw:
            continue
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        Image.open(io.BytesIO(raw)).convert("RGB").save(out)
        tiles_out = -(-w // 512) * -(-h // 512)
        NEURONS["images"] += 1
        NEURONS["est"] += tiles_out * 26.05 + len(refs) * 5.37
        print(f"[klein] ✅ {os.path.basename(out)} (참고 {len(refs)}장)")
        return out
    return None


def cast_refs() -> dict:
    """클레이 토끼·늘보 기준 그림(한 번만). 실사 배역 사진을 참고로 '같은 동물'을 클레이 인형으로."""
    os.makedirs(CAST, exist_ok=True)
    src = {"wife": "assets/cast_animal/wife_idle.png", "husband": "assets/cast_animal/husband_idle.png"}
    desc = {"wife": "a small WHITE RABBIT with floppy ears and a thin PINK collar with a tiny bell",
            "husband": "a big gentle BROWN-GREY SLOTH with long arms, sleepy kind eyes and dark eye patches"}
    out = {}
    for role in ("wife", "husband"):
        p = os.path.join(CAST, f"{role}.png")
        if not os.path.exists(p):
            klein(f"Turn the animal in image 0 into {desc[role]} as a handmade stop-motion claymation figure. "
                  f"Full body, standing, facing camera, plain warm cream background, centered. {LOOK}",
                  p, refs=[src[role]], w=768, h=768, seed=SEED + (1 if role == "wife" else 2))
        out[role] = p
    p = os.path.join(CAST, "set_bedroom.png")
    if not os.path.exists(p):
        klein("An empty miniature handmade claymation bedroom at night: a low wooden bed with a patchwork quilt, "
              "a window with snow falling outside, a small bedside table, a wall thermostat, warm lamp light, "
              f"cream walls, kraft-brown wooden floor. {LOOK}", p, w=KW, h=KH, seed=SEED + 3)
    out["set"] = p
    return out


def keyframes(ep: dict, ep_dir: str, refs: dict) -> dict:
    """컷마다 포즈 3장: p0 = 배역·세트 참고로 새로 / p1·p2 = p0을 참고로 '그 부분만' 바꾼 편집 → 일관성."""
    frames = {}
    for c in ep["cuts"]:
        n = int(c["n"])
        d = os.path.join(ep_dir, "frames")
        p0 = os.path.join(d, f"cut{n:02d}_p0.png")
        rr = [refs[k] for k in c.get("chars", []) if os.path.exists(refs.get(k, ""))] + [refs["set"]]
        idx = ", ".join(f"image {i} = {k}" for i, k in enumerate(c.get("chars", []) + ["set"]))
        if not os.path.exists(p0):
            klein(f"{c['scene']} Vertical 9:16 frame, characters clearly visible in the middle, empty space at the "
                  f"bottom for subtitles. {CAST_LOCK} ({idx}). {LOOK}", p0, refs=rr, seed=SEED + n * 10)
        got = [p0] if os.path.exists(p0) else []
        for k, delta in enumerate(c.get("poses", []), start=1):
            pk = os.path.join(d, f"cut{n:02d}_p{k}.png")
            if not got:
                break
            if not os.path.exists(pk):
                klein("Keep EVERYTHING in image 0 identical — same characters, same clay style, same set, same "
                      f"camera framing and lighting. Change ONLY this: {delta} {LOOK}",
                      pk, refs=[got[-1]], seed=SEED + n * 10 + k)
            if os.path.exists(pk):
                got.append(pk)
        frames[n] = got
    return frames


def voices(ep: dict, ep_dir: str) -> dict:
    """대사 음성(일레븐 → 실패 시 edge-tts) + 컷 길이. B가 같은 음성을 쓰도록 audio/ 에 남긴다."""
    adir = os.path.join(ep_dir, "audio")
    os.makedirs(adir, exist_ok=True)
    plan = {}
    for c in ep["cuts"]:
        n, who = int(c["n"]), c.get("who", "")
        p = os.path.join(adir, f"cut{n:02d}.mp3")
        vd = 0.0
        if c.get("line"):
            if not os.path.exists(p):
                rc.tts_line(c["line"], who, p)
            vd = rc.dur(p) if os.path.exists(p) else 0.0
        sec = max(MIN_CUT.get(who, 2.6), LEAD.get(who, 0) + vd + TAIL.get(who, 0.4))
        plan[n] = {"seconds": round(sec, 2), "voice": p if vd else None, "voice_sec": round(vd, 2)}
    with open(os.path.join(ep_dir, "durations.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    return plan


def stopmotion(poses: list[str], seconds: float, who: str, out: str) -> str:
    """포즈 3장 → 24fps 부드러운 움직임. 토끼: 짧게 머물고 빠르게 넘어감 / 늘보: 머무름 없이 천천히 이어짐.

    ffmpeg minterpolate 실측(11/11): 마지막 두 장 사이는 내보내지 않는다 → 끝 그림을 두 장 더 붙여 1fps로 보간한 뒤
    setpts 로 컷 길이에 맞춘다(입력 1fps 기준 길이 = 장수-1초).
    """
    tmp = out + ".d"
    os.makedirs(tmp, exist_ok=True)
    seq = ([poses[0], poses[0]] + [p for p in poses[1:] for _ in (0, 1)]) if who == "wife" else list(poses)
    if len(seq) < 2:
        seq = seq * 2
    seq = seq + [seq[-1], seq[-1]]
    for i, p in enumerate(seq):
        Image.open(p).convert("RGB").resize((KW, KH), Image.LANCZOS).save(os.path.join(tmp, f"f{i:03d}.png"))
    k = max(seconds, 0.5) / (len(seq) - 2)
    vf = (f"minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,setpts=PTS*{k:.4f},fps={FPS},"
          f"scale=w='{rc.W}*(1.03+0.012*sin(2*PI*t/2.4))':h=-2:eval=frame:flags=lanczos,"
          f"crop={rc.W}:{rc.H},tpad=stop_mode=clone:stop_duration=3")
    subprocess.run(["ffmpeg", "-y", "-framerate", "1", "-i", os.path.join(tmp, "f%03d.png"),
                    "-vf", vf, "-t", f"{seconds:.2f}", "-r", str(FPS), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-crf", "18", out], check=True, capture_output=True)
    return out


def fit_clip(src: str, seconds: float, out: str) -> str:
    """Flow 클립 → 1080x1920·길이 맞춤(짧으면 마지막 프레임 유지, 소리 제거)."""
    vf = f"scale={rc.W}:{rc.H}:force_original_aspect_ratio=increase,crop={rc.W}:{rc.H},tpad=stop_mode=clone:stop_duration=8"
    subprocess.run(["ffmpeg", "-y", "-i", src, "-an", "-t", f"{seconds:.2f}", "-vf", vf, "-r", str(FPS),
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out], check=True, capture_output=True)
    return out


def assemble(ep: dict, ep_dir: str, plan: dict, clips: dict, name: str) -> str:
    rdir = os.path.join(ep_dir, "render", name)
    os.makedirs(rdir, exist_ok=True)
    pop = rc.sfx("pop", os.path.join(rdir, "pop.wav"))
    segs = []
    for c in ep["cuts"]:
        n, who = int(c["n"]), c.get("who", "")
        if n not in clips:
            print(f"[ab] {name} 컷 {n} 영상 없음 — 건너뜀")
            continue
        sec = plan[str(n)]["seconds"] if str(n) in plan else plan[n]["seconds"]
        voice = (plan.get(str(n)) or plan.get(n) or {}).get("voice")
        overlays = [(rc.subtitle_png(c.get("line", ""), who, os.path.join(rdir, f"s{n}.png"), hook=c.get("hook")), 0.0)]
        extra = [(pop, max(0.3, sec - 0.9))] if c.get("sfx") == "pop" and pop else []
        segs.append(rc._segment(clips[n], overlays, voice, sec, os.path.join(rdir, f"seg{n:02d}.mp4"), extra,
                                lead=LEAD.get(who, 0.0), max_tempo=1.0 if who == "husband" else 1.15))
    with open(os.path.join(rdir, "list.txt"), "w") as f:
        f.writelines(f"file '{os.path.basename(s)}'\n" for s in segs)
    out = os.path.join(ep_dir, f"{name}.mp4")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy",
                    os.path.abspath(out)], check=True, capture_output=True, cwd=rdir)
    print(f"[ab] {name} → {out} ({rc.dur(out):.1f}초)")
    return out


def contact_sheet(frames: dict, out: str) -> None:
    rows = [v for _, v in sorted(frames.items()) if v]
    if not rows:
        return
    tw, th = 192, 341
    sheet = Image.new("RGB", (tw * 3, th * len(rows)), (240, 236, 228))
    for y, poses in enumerate(rows):
        for x, p in enumerate(poses[:3]):
            sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), (x * tw, y * th))
    sheet.save(out)


def stage_a(ep_dir: str) -> None:
    ep = json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))
    refs = cast_refs()
    frames = keyframes(ep, ep_dir, refs)
    contact_sheet(frames, os.path.join(ep_dir, "frames_contact.jpg"))
    # B용 시작 프레임 = 각 컷 p0 (Flow에 올린다)
    sdir = os.path.join(ep_dir, "start")
    os.makedirs(sdir, exist_ok=True)
    for n, poses in frames.items():
        if poses:
            Image.open(poses[0]).save(os.path.join(sdir, f"cut{n:02d}.png"))
    plan = voices(ep, ep_dir)
    clips = {}
    for c in ep["cuts"]:
        n = int(c["n"])
        if frames.get(n):
            clips[n] = stopmotion(frames[n], plan[n]["seconds"], c.get("who", ""),
                                  os.path.join(ep_dir, "render", f"A_m{n:02d}.mp4"))
    video = assemble(ep, ep_dir, plan, clips, "A")
    rep = {"stage": "a", "model": MODEL, "images": NEURONS["images"], "neurons_est": round(NEURONS["est"]),
           "seconds": round(rc.dur(video), 1), "durations": {n: v["seconds"] for n, v in plan.items()}}
    json.dump(rep, open(os.path.join(ep_dir, "report_a.json"), "w"), ensure_ascii=False, indent=1)
    print("[ab] 리포트:", rep)
    from common import telegram_video
    telegram_video(video, f"[A안 · 무료 스톱모션] {ep['title']} — 이미지 {rep['images']}장 · 약 {rep['neurons_est']}뉴런(₩0)")


def stage_b(ep_dir: str) -> None:
    ep = json.load(open(os.path.join(ep_dir, "episode.json"), encoding="utf-8"))
    plan = json.load(open(os.path.join(ep_dir, "durations.json"), encoding="utf-8"))
    fdir = os.path.join(ep_dir, "flow")
    clips = {}
    for c in ep["cuts"]:
        n = int(c["n"])
        src = os.path.join(fdir, f"cut{n:02d}.mp4")
        if os.path.exists(src):
            clips[n] = fit_clip(src, plan[str(n)]["seconds"], os.path.join(ep_dir, "render", f"B_m{n:02d}.mp4"))
    if not clips:
        raise SystemExit("flow/cutNN.mp4 가 하나도 없다")
    video = assemble(ep, ep_dir, plan, clips, "B")
    a = os.path.join(ep_dir, "A.mp4")
    from common import telegram_video
    telegram_video(video, f"[B안 · Flow Omni 1.2] {ep['title']} — 구독 크레딧(추가 ₩0)")
    if os.path.exists(a):
        cmp_ = os.path.join(ep_dir, "AB_side_by_side.mp4")
        subprocess.run(["ffmpeg", "-y", "-i", a, "-i", video, "-filter_complex",
                        "[0:v]scale=540:960[l];[1:v]scale=540:960[r];[l][r]hstack=inputs=2[v]",
                        "-map", "[v]", "-map", "0:a?", "-shortest", "-c:v", "libx264", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", cmp_], check=True, capture_output=True)
        telegram_video(cmp_, "[A | B 나란히] 왼쪽 A(무료 스톱모션) · 오른쪽 B(Flow)")


DESIGN = {
    "wife": ("Design a LOVABLE claymation character based on the white lop-eared rabbit in image 0. Soft white clay "
             "body, chubby round cheeks with a faint pink blush, big sparkly dark eyes with white highlights, tiny pink "
             "nose, long floppy ears with pink inner ears, a thin pink collar with a tiny gold bell, slightly oversized "
             "head (cute chibi proportions), standing upright on two legs, happy lively expression. A stylized cute "
             "CHARACTER, not a realistic animal."),
    "husband": ("Design a FRIENDLY claymation character based on the sloth in image 0. Warm light-brown clay body, a "
                "round soft pale-beige face, small kind sleepy eyes and a big warm gentle smile, NO dark eye patches, "
                "NO sharp claws (soft rounded mitten hands), a navy-blue bandana around the neck, a soft round belly, "
                "chibi proportions with a big round head, standing upright on two legs, relaxed easygoing expression. "
                "A stylized cute CHARACTER, not a realistic animal."),
}
DESIGN_TAIL = ("ONLY this one character in the picture, full body, front view, centered, plain warm cream background, "
               "handmade stop-motion plasticine with subtle fingerprint texture, soft studio light, no text, no props, "
               "no other figures")


def _front(sheet: str) -> Image.Image:
    """배역 시트(3x2) 왼쪽 위 칸 = 정면."""
    im = Image.open(sheet).convert("RGB")
    return im.crop((0, 0, im.width // 3, im.height // 2))


def stage_design(out_dir: str) -> None:
    """캐릭터 디자인 후보 4장씩(사용자가 고른다). 원본 = 10/15 실사 배역 시트의 정면."""
    os.makedirs(out_dir, exist_ok=True)
    src = {"wife": "assets/cast_animal/wife_sheet.png", "husband": "assets/cast_animal/husband_sheet.png"}
    tiles = []
    for role in ("wife", "husband"):
        front = _front(src[role])
        for k in range(1, 5):
            p = os.path.join(out_dir, f"{role}_{k}.png")
            if not os.path.exists(p):
                klein(f"{DESIGN[role]} {DESIGN_TAIL}", p, refs=[front], w=640, h=768, seed=SEED * 7 + k * 31 + len(role))
            if os.path.exists(p):
                tiles.append((role, k, p))
    tw, th = 320, 384
    sheet = Image.new("RGB", (tw * 4, th * 2 + 40), (250, 247, 240))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    f = rc.font(28)
    for role, k, p in tiles:
        y = 0 if role == "wife" else th + 40
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), ((k - 1) * tw, y))
        d.text(((k - 1) * tw + 14, y + 10), f"{'토끼' if role == 'wife' else '늘보'} {k}", font=f, fill=(40, 40, 40))
    cs = os.path.join(out_dir, "candidates.jpg")
    sheet.save(cs, quality=90)
    json.dump({"images": NEURONS["images"], "neurons_est": round(NEURONS["est"])},
              open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    from common import telegram_msg
    import requests as _rq
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat:
        with open(cs, "rb") as fh:
            _rq.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat,
                     "caption": "콕이네 집 캐릭터 후보 — 토끼 1~4 / 늘보 1~4 중 하나씩 골라 캐스토 채팅에 알려 주세요"},
                     files={"photo": fh}, timeout=60)
    else:
        telegram_msg("캐릭터 후보 생성 완료(사진 전송 실패)")


SLOTH_V2 = {
    1: "a tiny clay leaf tucked behind one ear, a soft fluffy tuft of fur on top of the head",
    2: "a cozy oatmeal-colored knit cardigan worn over the navy bandana, hands resting on the belly",
    3: "round soft cheeks with a faint warm blush, a little sprout-shaped hair curl on top of the head",
    4: "a small clay acorn charm hanging from the navy bandana, holding a warm mug with both hands",
}


def stage_design2(out_dir: str) -> None:
    """11/11 사용자: 토끼 = 4번 확정. 늘보는 다시 — 원래 배역(10/15)의 남색 손수건은 지키고, 우리만의 친근한 늘보.
    토끼 4번을 '같은 세계의 짝'으로 같이 넣어 스타일(질감·비율·조명)을 맞춘다."""
    os.makedirs(out_dir, exist_ok=True)
    import shutil
    shutil.copy("pilot/ab/design/wife_4.png", os.path.join(CAST, "wife.png"))       # 토끼 확정본
    front = _front("assets/cast_animal/husband_sheet.png")
    rabbit = "pilot/ab/design/wife_4.png"
    tiles = []
    for k, extra in SLOTH_V2.items():
        p = os.path.join(out_dir, f"husband_v2_{k}.png")
        if not os.path.exists(p):
            klein("Create an ORIGINAL, friendly, lovable claymation SLOTH character as the partner of the rabbit in "
                  "image 1 — exactly the same clay material, the same soft studio lighting, the same cream background "
                  "and the same cute chibi proportions as image 1 (big round head, short round body). Base him on the "
                  "sloth in image 0 but make him a stylized cute character: warm cocoa-brown clay fur, a light cream "
                  "face, gentle crescent-shaped smiling eyes, a big kind smile, long arms with soft rounded mitten "
                  f"hands, the navy-blue bandana around his neck, {extra}. Easygoing, warm, huggable. "
                  "ONLY this one character, full body, front view, centered, no text, no other figures",
                  p, refs=[front, rabbit], w=640, h=768, seed=SEED * 11 + k * 17)
        if os.path.exists(p):
            tiles.append((k, p))
    tw, th = 320, 384
    sheet = Image.new("RGB", (tw * 5, th + 40), (250, 247, 240))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    f = rc.font(28)
    sheet.paste(Image.open(rabbit).convert("RGB").resize((tw, th)), (0, 40))
    d.text((14, 6), "토끼 4 (확정)", font=f, fill=(40, 40, 40))
    for k, p in tiles:
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), (k * tw, 40))
        d.text((k * tw + 14, 6), f"늘보 {k}", font=f, fill=(40, 40, 40))
    cs = os.path.join(out_dir, "candidates.jpg")
    sheet.save(cs, quality=90)
    json.dump({"images": NEURONS["images"], "neurons_est": round(NEURONS["est"])},
              open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    import requests as _rq
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat:
        with open(cs, "rb") as fh:
            _rq.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat,
                     "caption": "늘보 후보 2차 — 토끼 4번과 같은 세계로. 1~4 중 골라 캐스토 채팅에 알려 주세요"},
                     files={"photo": fh}, timeout=60)


MASCOT = ("Character-mascot design that could later become plush toys, stickers and emoji: very simple readable "
          "shapes, an iconic silhouette, a BIG round head (about half of the total height), large glossy eyes with two "
          "white highlights, tiny soft limbs, everything soft and rounded, adorable and heartwarming. Handmade "
          "claymation plasticine with subtle fingerprint texture, soft studio light, plain warm cream background. "
          "ONLY this one character, full body, front view, centered, no text, no props, no other figures.")
RABBIT_V3 = {
    1: "Make her CUTER: rounder chubbier face, bigger sparkling eyes, a tiny smiling mouth, rosy round blush, short stubby body",
    2: "Make her CUTER: an even rounder bun-shaped body, ears a little longer and fluffier, a small heart-shaped pink nose, cheerful open smile",
    3: "Make her CUTER: a slightly smaller body and bigger head, eyes like shiny black beads with big highlights, a small pink bow next to one ear",
    4: "Make her CUTER: a soft pear-shaped body, tiny paws held together at her chest, bright happy eyes, a little tuft of fur on the forehead",
}
SLOTH_V3 = {
    1: "a BIG but CUTE sloth: a large soft round marshmallow-like body twice the rabbit's size, a round face with a cream heart-shaped face patch, small round sparkling eyes, a gentle shy smile",
    2: "a BIG but CUTE sloth: a huge huggable bean-shaped body, short stubby legs, long soft arms hanging down, a peanut-shaped cream face patch, sleepy happy half-moon eyes, rosy cheeks",
    3: "a BIG but CUTE sloth: a chunky round teddy-bear-like body, a big round head, a cream face patch, big round eyes with highlights, a small round nose, a content little smile",
    4: "a BIG but CUTE sloth: a soft pear-shaped big body with a round tummy, tiny feet, long soft arms, a cream oval face patch, droopy relaxed sweet eyes, a wide gentle smile",
}


def stage_design3(out_dir: str) -> None:
    """11/11 사용자: "늘보는 남자니까 덩치는 있지만 더 귀엽게, 토끼도 더 귀엽게 — 동물 아이덴티티는 지키되 나중에 캐릭터화(굿즈)".
    토끼 = 확정 4번을 더 귀엽게 4안 / 늘보 = 2차의 손수건 늘보를 참고로 큰 덩치 + 귀여움 4안. 남색 손수건·분홍 목줄은 공통."""
    os.makedirs(out_dir, exist_ok=True)
    rabbit_ref = "pilot/ab/design/wife_4.png"
    sloth_refs = ["pilot/ab/design2/husband_v2_2.png", "pilot/ab/design2/husband_v2_1.png"]
    tiles = []
    for k, look in RABBIT_V3.items():
        p = os.path.join(out_dir, f"wife_v3_{k}.png")
        if not os.path.exists(p):
            klein(f"Redesign the white lop-eared rabbit in image 0 as the same character. Keep her white fur, floppy "
                  f"pink-lined ears and the thin pink collar with a tiny gold bell. {look}. {MASCOT}",
                  p, refs=[rabbit_ref], w=640, h=768, seed=SEED * 13 + k * 19)
        if os.path.exists(p):
            tiles.append(("wife", k, p))
    for k, look in SLOTH_V3.items():
        p = os.path.join(out_dir, f"husband_v3_{k}.png")
        if not os.path.exists(p):
            klein("Redesign the sloth in image 0 as the husband of the rabbit in image 1. Keep him a recognizable "
                  "SLOTH (warm cocoa-brown fur, long arms, slow gentle vibe) with the navy-blue bandana, but NO dark "
                  f"eye patches and NO sharp claws (soft rounded mitten hands). Make him {look}. {MASCOT}",
                  p, refs=[sloth_refs[0], rabbit_ref], w=640, h=768, seed=SEED * 17 + k * 23)
        if os.path.exists(p):
            tiles.append(("husband", k, p))
    tw, th = 320, 384
    sheet = Image.new("RGB", (tw * 4, (th + 40) * 2), (250, 247, 240))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    f = rc.font(28)
    for role, k, p in tiles:
        y = 40 if role == "wife" else th + 80
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), ((k - 1) * tw, y))
        d.text(((k - 1) * tw + 14, y - 34), f"{'토끼' if role == 'wife' else '늘보'} {k}", font=f, fill=(40, 40, 40))
    cs = os.path.join(out_dir, "candidates.jpg")
    sheet.save(cs, quality=90)
    json.dump({"images": NEURONS["images"], "neurons_est": round(NEURONS["est"])},
              open(os.path.join(out_dir, "report.json"), "w"), indent=1)
    import requests as _rq
    tok, chat = os.getenv("TELEGRAM_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if tok and chat:
        with open(cs, "rb") as fh:
            _rq.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat,
                     "caption": "캐릭터 3차 — 더 귀엽게(굿즈로도 쓸 수 있게). 토끼 1~4 · 늘보 1~4 중 골라 주세요"},
                     files={"photo": fh}, timeout=60)


if __name__ == "__main__":
    stage, ep_dir = sys.argv[1], sys.argv[2]
    {"a": stage_a, "b": stage_b, "design": stage_design, "design2": stage_design2, "design3": stage_design3}[stage](ep_dir)

"""완전 자동 쇼츠 제작 — 픽담 최신 글 1편 → 트렌드 반영 대본 → 씬 이미지 → TTS → mp4 → 텔레그램.

파이프라인(전부 무료 도구):
1) pickdam.com 최신 발행 글 가져오기(wp-json, 공개 API)
2) data/trends.json(주간 갱신)을 대본 프롬프트에 주입 — '지금 먹히는' 훅·형식으로
3) LLM이 쇼츠 대본 생성: 훅 → 씬 4~6개(자막+내레이션) → CTA
4) 씬 비주얼: style=card/character는 PIL 브랜드 카드(비용 0),
   style=realistic이고 LLM_API_KEY가 이미지 지원이면 제미니 이미지 시도 → 실패 시 카드 폴백
5) edge-tts(무료)로 씬별 한국어 내레이션 mp3
6) ffmpeg으로 1080x1920 mp4 합성(씬 길이 = 음성 길이 + 0.3s)
7) 텔레그램 sendVideo → 폰에서 유튜브 쇼츠/인스타 릴스에 1분 내 업로드
"""
import json, os, re, subprocess, asyncio, html
import requests
from PIL import Image, ImageDraw, ImageFont
from common import cfg, llm_json, telegram_video, telegram_msg

W, H = 1080, 1920
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]

def font(size, bold=True):
    for p in (FONTS if bold else FONTS[::-1]):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def latest_post(site):
    r = requests.get(f"{site}/wp-json/wp/v2/posts?per_page=1&_fields=title,link,content,excerpt", timeout=30)
    p = r.json()[0]
    text = re.sub(r"<[^>]+>", " ", p["content"]["rendered"])
    text = html.unescape(re.sub(r"\s+", " ", text))[:4000]
    return {"title": html.unescape(p["title"]["rendered"]), "link": p["link"], "text": text}

def build_script(post, trends, c):
    tr = json.dumps({k: trends.get(k) for k in ("hooks", "formats", "caption_style", "avoid")}, ensure_ascii=False)
    return llm_json(f"""당신은 조회수가 잘 나오는 한국 쇼츠 작가입니다. 니치: {c['niche']}.
[이번 주 트렌드 지침(매주 자동 갱신됨)] {tr}
[원본 글] 제목: {post['title']}
본문 요약: {post['text'][:2500]}

이 글을 {c['video']['target_sec']}초 쇼츠 대본으로 변환하세요. 트렌드 훅 패턴 중 하나로 시작:
{{"title": "쇼츠 제목(궁금증 유발, 40자 이내)",
 "scenes": [
   {{"caption": "화면 자막(15자 이내, 줄바꿈은 \\n)", "voice": "내레이션 문장(구어체, 1~2문장)"}},
   ... 훅 1 + 본문 3~4 + CTA 1 = 총 5~6개
 ],
 "hashtags": ["#태그", ... 8개]}}
규칙: 첫 씬은 3초 훅(트렌드 hooks 패턴 활용). 마지막 씬 CTA는 "자세한 비교는 프로필 링크/픽담에서".
겪지 않은 경험담·과장 금지. 가격은 '~원대'처럼 범위로.""")

def scene_card(caption, idx, total, style):
    """브랜드 씬 카드 — 딥그린 그라데이션 + 큰 자막(캐릭터 톤이면 이모지 오브젝트)."""
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    top, bot = (52, 168, 118), (16, 72, 48)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    # 상단 브랜드
    d.text((W // 2, 150), "픽담 PICK", font=font(52), fill=(210, 240, 225), anchor="mm")
    # 캐릭터 톤: 큰 이모지 스티커 느낌의 원형 배지
    if style == "character":
        d.ellipse([W // 2 - 170, 420, W // 2 + 170, 760], fill=(240, 250, 244))
        emo = ["🤔", "💡", "⚖️", "💸", "✅", "👉"][idx % 6]
        try:
            ef = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
            d.text((W // 2, 590), emo, font=ef, anchor="mm", embedded_color=True)
        except Exception:
            d.text((W // 2, 590), emo, font=font(160), anchor="mm", fill=(31, 122, 82))
    # 자막(중앙 하단, 자동 줄바꿈)
    f = font(84)
    lines = []
    for raw in caption.split("\n"):
        cur = ""
        for ch in raw:
            if d.textlength(cur + ch, font=f) > W - 160:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
    y0 = 1100
    for i, ln in enumerate(lines[:5]):
        d.text((W // 2, y0 + i * 110), ln, font=f, fill=(255, 255, 255), anchor="mm",
               stroke_width=6, stroke_fill=(10, 40, 26))
    # 진행 점
    for i in range(total):
        x = W // 2 + (i - total / 2 + .5) * 44
        d.ellipse([x - 9, 1810, x + 9, 1828], fill=(240, 250, 244) if i <= idx else (90, 140, 115))
    p = f"out/scene{idx}.png"
    img.save(p)
    return p

async def tts(text, path, voice):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+8%").save(path)

def dur(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip() or 3)

def main():
    c = cfg()
    os.makedirs("out", exist_ok=True)
    trends = json.load(open("data/trends.json", encoding="utf-8")) if os.path.exists("data/trends.json") else {}
    post = latest_post(c["source_site"])
    print("[casto] 원본:", post["title"])
    s = build_script(post, trends, c)
    scenes = s["scenes"][:6]
    segs = []
    for i, sc in enumerate(scenes):
        img = scene_card(sc["caption"], i, len(scenes), c.get("style", "card"))
        mp3 = f"out/voice{i}.mp3"
        asyncio.run(tts(sc["voice"], mp3, c["video"]["voice"]))
        d = dur(mp3) + 0.3
        seg = f"out/seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", mp3,
                        "-t", f"{d:.2f}", "-r", "30", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-c:a", "aac", "-shortest", seg],
                       check=True, capture_output=True)
        segs.append(seg)
        print(f"[casto] 씬 {i+1}/{len(scenes)} ({d:.1f}s)")
    with open("out/list.txt", "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in segs)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "out/list.txt",
                    "-c", "copy", "out/short.mp4"], check=True, capture_output=True, cwd=None)
    total = dur("out/short.mp4")
    cap = f"🎬 {s['title']}\n{' '.join(s.get('hashtags', [])[:8])}\n원본: {post['link']}\n({total:.0f}초 · 트렌드 {trends.get('updated','-')} 기준)"
    telegram_video("out/short.mp4", cap) or telegram_msg("쇼츠 생성 완료(전송 실패) — Actions 아티팩트 확인")
    print(f"[casto] 완료 — {total:.0f}초, out/short.mp4")

if __name__ == "__main__":
    main()

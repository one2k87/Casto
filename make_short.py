"""완전 자동 쇼츠 제작 — 픽담 최신 글 1편 → 콕픽 「콕 열리는 상자」 규격 15초 쇼츠 → 텔레그램.

규격 원문: docs/콕픽_쇼츠_포맷.md · 채널: 유튜브 「콕픽」(@kokpick_kr)

한 줄 규칙: **상자는 콕 3번을 통과해야만 열린다.**
| 초 | 화면 |
| 0~1   | 콕이 + 제품명 스탬프 "오늘의 콕: OO" (즉답, 낚시 금지) |
| 1~3   | "콕 3번 통과하면 열립니다" |
| 3~11  | 콕! ×3 — 콕마다 구매 근거 1줄, 콕 사운드(우드블록) |
| 11~15 | 통과 → 개봉 "오늘의 콕 ✅" / 조건부 "조건콕 👆" / 미달 "다음콕 📦" + 픽담 CTA |

파이프라인(전부 무료 도구):
1) pickdam.com 최신 발행 글 가져오기(wp-json, 공개 API)
2) data/trends.json(주간 갱신)을 프롬프트에 주입
3) LLM은 **내용만** 생성(제품명·콕 근거 3줄·판정 사유). 판정어·구조·CTA는 코드가 강제 — 규격 이탈 방지
4) 씬 비주얼: 클립뱅크(assets/clips/)가 있으면 사용, 없으면 콕픽 파스텔 카드 폴백(비용 0)
5) edge-tts(무료)로 씬별 한국어 내레이션 mp3 + 콕 사운드 믹스
6) ffmpeg으로 1080x1920 mp4 합성
7) 텔레그램 sendVideo → 폰에서 업로드(v2: Make로 자동 게시)
"""
import json, os, re, subprocess, asyncio, html
import requests
from PIL import Image, ImageDraw, ImageFont
from common import cfg, llm_json, telegram_video, telegram_msg

W, H = 1080, 1920
FONTS = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
KOK_NUM = ["①", "②", "③"]


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


# ---------------------------------------------------------------- 대본(내용만)
def build_script(post, trends, c):
    """LLM은 제품명·콕 근거 3줄·판정만 만든다. 판정어 문구와 씬 구조는 코드가 붙인다."""
    tr = json.dumps({k: trends.get(k) for k in ("hooks", "formats", "caption_style", "avoid")}, ensure_ascii=False)
    return llm_json(f"""당신은 유튜브 쇼츠 채널 「콕픽」의 작가입니다. 니치: {c['niche']}.
채널 포맷은 「콕 열리는 상자」 — 마스코트 '콕이'(택배상자)가 **구매 근거 '콕' 3개를 통과해야만 열린다**.
[이번 주 트렌드 지침(매주 자동 갱신됨)] {tr}
[원본 글] 제목: {post['title']}
본문 요약: {post['text'][:2500]}

이 글에서 **딱 한 제품**을 고르고 아래 JSON만 출력하세요.
{{"product": "제품 카테고리명(8자 이내, 예: 음식물처리기)",
 "koks": [
   {{"caption": "화면 자막(12자 이내, 줄바꿈 \\n 1회 허용)", "voice": "내레이션 1문장(20자 내외, 구어체)"}},
   ... 정확히 3개 — 서로 다른 축(①비용/전기료 ②크기·설치 ③실사용 조건)
 ],
 "verdict": "buy" | "cond" | "later",
 "verdict_reason": "판정 한 줄(15자 이내)",
 "condition": "조건콕일 때만 '자취생이면'처럼 조건 대상(8자 이내), 아니면 빈 문자열",
 "title": "쇼츠 제목(제품명 포함, 35자 이내)",
 "hashtags": ["#태그", ... 6개]}}

규칙
- 콕 3개는 **구매 결정 근거**여야 한다(감상·수식어 금지). 숫자가 있으면 넣되 가격은 '~원대' 범위로.
- verdict: 대부분 사도 되면 buy, 특정 조건에서만 이득이면 cond, 아직이면 later.
- **부정어 금지** — '별로다/사지 마라' 대신 '아직'의 뉘앙스로 쓴다.
- 겪지 않은 경험담·과장 금지. 판정어("오늘의 콕" 등)는 코드가 넣으니 문장에 쓰지 말 것.""")


# ---------------------------------------------------------------- 씬 구성(코드 강제)
def build_scenes(s, c):
    """LLM 내용 + 콕픽 고정 규격 → 씬 리스트. kind는 카드 렌더/사운드 분기에 쓴다."""
    v = c["verdicts"][s.get("verdict", "buy") if s.get("verdict") in c["verdicts"] else "buy"]
    product = s["product"]
    cond = (s.get("condition") or "").strip()
    scenes = [
        {"kind": "stamp", "caption": f"오늘의 콕\n{product}", "voice": f"오늘의 콕, {product}."},
        {"kind": "rule", "caption": "콕 3번 통과하면\n열립니다", "voice": "콕 세 번 통과하면 열립니다."},
    ]
    for i, k in enumerate(s["koks"][:3]):
        scenes.append({"kind": "kok", "idx": i,
                       "caption": f"{KOK_NUM[i]} {k['caption']}", "voice": k["voice"]})
    reason = (s.get("verdict_reason") or "").strip()
    if reason and reason[-1] not in ".!?…":
        reason += "."
    if v["key"] == "조건콕":
        cap = f"{cond} {v['card']}".strip()
        voice = f"{cond} {v['voice']} {reason} 자세한 비교는 픽담에서."
    else:
        cap = v["card"]
        voice = f"{v['voice']} {reason} 자세한 비교는 픽담에서."
    scenes.append({"kind": "verdict", "verdict": v, "caption": cap, "voice": re.sub(r"\s+", " ", voice).strip()})
    return scenes, v


# ---------------------------------------------------------------- 콕픽 카드 렌더
def wrap(d, text, f, maxw):
    lines = []
    for raw in text.split("\n"):
        cur = ""
        for ch in raw:
            if d.textlength(cur + ch, font=f) > maxw and cur:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def verdict_badge(d, cx, cy, v):
    """판정 배지 — 컬러 이모지 폰트가 없는 러너에서도 깨지지 않도록 전부 도형으로 그린다(두부 렌더 실측)."""
    col = tuple(v.get("color", (47, 143, 104)))
    r = 92
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=col, width=10)
    kind = v.get("badge", "check")
    if kind == "check":
        d.line([(cx - 42, cy + 2), (cx - 10, cy + 38), (cx + 46, cy - 36)], fill=col, width=18, joint="curve")
    elif kind == "arrow":
        d.polygon([(cx, cy - 46), (cx + 40, cy + 4), (cx + 16, cy + 4),
                   (cx + 16, cy + 46), (cx - 16, cy + 46), (cx - 16, cy + 4), (cx - 40, cy + 4)], fill=col)
    else:  # box — 다음콕(다음 기회 예고)
        d.rounded_rectangle([cx - 46, cy - 30, cx + 46, cy + 44], radius=10, fill=col)
        d.line([(cx - 46, cy - 6), (cx + 46, cy - 6)], fill=(255, 255, 255), width=8)


def kok_stamp(d, cx, cy):
    """콕! 도장 — 콕 씬의 타격감(손가락 이모지 대체)."""
    d.ellipse([cx - 86, cy - 86, cx + 86, cy + 86], fill=(255, 255, 255), outline=(214, 90, 78), width=10)
    d.text((cx, cy), "콕!", font=font(74), anchor="mm", fill=(214, 90, 78))


def kok_box(d, cx, cy, w, squish=0.0, open_lid=False):
    """콕이 근사 도형 — 크래프트 상자 + 미소. squish>0이면 눌린 모양(콕 반응)."""
    h = int(w * (0.78 - 0.14 * squish))
    w2 = int(w * (1 + 0.10 * squish))
    x0, y0, x1, y1 = cx - w2 // 2, cy - h // 2, cx + w2 // 2, cy + h // 2
    kraft, edge = (214, 178, 130), (168, 128, 84)
    d.rounded_rectangle([x0, y0, x1, y1], radius=34, fill=kraft, outline=edge, width=8)
    if open_lid:  # 뚜껑 팟! — 위로 열린 플랩
        d.polygon([(x0 + 10, y0), (cx, y0 - int(h * 0.55)), (cx + 40, y0 - int(h * 0.30)), (cx, y0)], fill=edge)
        d.polygon([(x1 - 10, y0), (cx, y0 - int(h * 0.55)), (cx - 40, y0 - int(h * 0.30)), (cx, y0)], fill=kraft)
    else:
        d.line([(x0 + 12, y0 + int(h * 0.26)), (x1 - 12, y0 + int(h * 0.26))], fill=edge, width=7)
    ey = cy - int(h * 0.02)
    for ex in (cx - int(w * 0.20), cx + int(w * 0.20)):  # 눈
        d.ellipse([ex - 15, ey - 20, ex + 15, ey + 20], fill=(60, 48, 36))
    d.arc([cx - int(w * 0.15), ey + 6, cx + int(w * 0.15), ey + int(h * 0.34)], 10, 170, fill=(60, 48, 36), width=9)
    for bx in (x0 - 26, x1 + 26):  # 크림색 손
        d.ellipse([bx - 24, cy - 10, bx + 24, cy + 38], fill=(255, 248, 236), outline=edge, width=4)


def scene_card(sc, i, total, c):
    """콕픽 파스텔 카드 — 크림→민트 그라데이션 + 콕이 + 큰 자막 + 콕 게이지."""
    b = c["brand"]
    cream, mint, sage = tuple(b["cream"]), tuple(b["mint"]), tuple(b["sage"])
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(cream[j] + (mint[j] - cream[j]) * t) for j in range(3)))
    d.text((W // 2, 140), "콕픽 KOKPICK", font=font(48), fill=sage, anchor="mm")

    kind = sc["kind"]
    squish = 0.85 if kind == "kok" else (0.25 if kind == "rule" else 0.0)
    opened = kind == "verdict" and sc["verdict"]["key"] in ("오늘의 콕", "조건콕")
    kok_box(d, W // 2, 640, 420, squish=squish, open_lid=opened)
    if kind == "kok":  # 콕 타격
        kok_stamp(d, W // 2 + 268, 452)
    if kind == "verdict":
        verdict_badge(d, W // 2, 316, sc["verdict"])

    f = font(96 if kind in ("stamp", "verdict") else 84)
    lines = wrap(d, sc["caption"], f, W - 170)[:4]
    y0 = 1180 - (len(lines) - 1) * 58
    for j, ln in enumerate(lines):
        d.text((W // 2, y0 + j * 116), ln, font=f, fill=(255, 255, 255), anchor="mm",
               stroke_width=7, stroke_fill=sage)

    # 콕 게이지 — 통과한 콕 수를 항상 노출(완주 유도)
    done = (sc.get("idx", -1) + 1) if kind == "kok" else (3 if kind == "verdict" else 0)
    for k in range(3):
        x = W // 2 + (k - 1) * 110
        on = k < done
        d.ellipse([x - 42, 1520, x + 42, 1604], fill=sage if on else (255, 255, 255),
                  outline=sage, width=6)
        d.text((x, 1562), "콕", font=font(44), anchor="mm", fill=(255, 255, 255) if on else sage)

    d.text((W // 2, 1790), "자세한 비교는 픽담 · 설명란", font=font(40), fill=sage, anchor="mm")
    d.polygon([(W // 2 - 18, 1822), (W // 2 + 18, 1822), (W // 2, 1846)], fill=sage)
    for k in range(total):  # 진행 점
        x = W // 2 + (k - total / 2 + .5) * 40
        d.ellipse([x - 8, 1866, x + 8, 1882], fill=sage if k <= i else (255, 255, 255))
    p = f"out/scene{i}.png"
    img.save(p)
    return p


def clip_for(sc, c):
    """클립뱅크가 구축돼 있으면 해당 뱅크 클립 경로 반환(없으면 None → 카드 폴백)."""
    bank = {"stamp": "A", "rule": "B", "kok": "C"}.get(sc["kind"])
    if sc["kind"] == "verdict":
        bank = "D" if sc["verdict"]["key"] in ("오늘의 콕", "조건콕") else "E"
    d = c.get("clips", {}).get("dir", "")
    if not (bank and d and os.path.isdir(d)):
        return None
    cands = sorted(f for f in os.listdir(d) if f.startswith(bank) and f.endswith(".mp4"))
    if not cands:
        return None
    return os.path.join(d, cands[(sc.get("idx", 0)) % len(cands)])


# ---------------------------------------------------------------- 오디오
def make_kok_sfx(path):
    """콕 사운드(우드블록 근사) — 짧은 감쇠 톤. 실패해도 파이프라인은 계속."""
    try:
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=1180:duration=0.12",
                        "-af", "afade=t=out:st=0.02:d=0.10,volume=0.5", path],
                       check=True, capture_output=True)
        return path if os.path.exists(path) else None
    except Exception as e:
        print("[casto] 콕 사운드 생성 실패(무시):", e)
        return None


async def tts(text, path, voice):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate="+8%").save(path)


def mix_kok(voice_mp3, sfx, out_path):
    """콕 씬: 내레이션 앞에 콕 사운드를 겹친다."""
    try:
        subprocess.run(["ffmpeg", "-y", "-i", voice_mp3, "-i", sfx,
                        "-filter_complex", "[1:a]adelay=0|0[s];[0:a][s]amix=inputs=2:duration=first:dropout_transition=0",
                        "-c:a", "libmp3lame", out_path], check=True, capture_output=True)
        return out_path
    except Exception:
        return voice_mp3


def dur(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(out.stdout.strip() or 3)


# ---------------------------------------------------------------- 캡션(설명란)
def build_caption(s, v, post, c, total):
    dis = c["disclosure"]
    tags = list(dict.fromkeys(["#오늘의콕", "#콕픽"] + list(s.get("hashtags", []))))[:8]
    head = f"{v['caption']} {s['product']}"
    return "\n".join([
        f"📦 {head} — {s['title']}",
        "",
        f"콕 3번 통과하면 열립니다. 오늘은 {v['key']}!",
        f"👉 자세한 비교는 픽담: {post['link']}",
        "",
        " ".join(tags),
        "",
        dis["coupang"],
        dis["ai"],
        f"({total:.0f}초 · 트렌드 {c.get('_trends_updated','-')} 기준)",
    ])


def main():
    c = cfg()
    os.makedirs("out", exist_ok=True)
    trends = json.load(open("data/trends.json", encoding="utf-8")) if os.path.exists("data/trends.json") else {}
    c["_trends_updated"] = trends.get("updated", "-")
    post = latest_post(c["source_site"])
    print("[casto] 원본:", post["title"])
    s = build_script(post, trends, c)
    scenes, v = build_scenes(s, c)
    print(f"[casto] 콕픽 규격 — 제품 {s['product']} · 판정 {v['caption']}")
    sfx = make_kok_sfx(c["video"]["sfx"]["kok"])

    segs = []
    for i, sc in enumerate(scenes):
        mp3 = f"out/voice{i}.mp3"
        asyncio.run(tts(sc["voice"], mp3, c["video"]["voice"]))
        if sc["kind"] == "kok" and sfx:
            mp3 = mix_kok(mp3, sfx, f"out/voice{i}_kok.mp3")
        d = dur(mp3) + 0.25
        seg = f"out/seg{i}.mp4"
        clip = clip_for(sc, c)
        if clip:  # 클립뱅크 사용(있을 때만) — 씬 길이에 맞춰 루프
            subprocess.run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", clip, "-i", mp3,
                            "-t", f"{d:.2f}", "-r", "30", "-pix_fmt", "yuv420p",
                            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
                            "-c:v", "libx264", "-c:a", "aac", "-shortest", seg],
                           check=True, capture_output=True)
        else:
            img = scene_card(sc, i, len(scenes), c)
            subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-i", mp3,
                            "-t", f"{d:.2f}", "-r", "30", "-pix_fmt", "yuv420p",
                            "-c:v", "libx264", "-c:a", "aac", "-shortest", seg],
                           check=True, capture_output=True)
        segs.append(seg)
        print(f"[casto] 씬 {i+1}/{len(scenes)} [{sc['kind']}] ({d:.1f}s)")

    with open("out/list.txt", "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in segs)
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "out/list.txt",
                    "-c", "copy", "out/short.mp4"], check=True, capture_output=True)
    total = dur("out/short.mp4")
    cap = build_caption(s, v, post, c, total)
    with open("out/caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)
    telegram_video("out/short.mp4", cap) or telegram_msg("쇼츠 생성 완료(전송 실패) — Actions 아티팩트 확인")
    print(f"[casto] 완료 — {total:.0f}초, out/short.mp4 (목표 {c['video']['target_sec']}초)")
    if total > c["video"]["target_sec"] + 6:
        print(f"[casto] ⚠ 규격 초과({total:.0f}초) — 내레이션이 길다. 다음 실행 시 voice 길이 제한 확인")


if __name__ == "__main__":
    main()

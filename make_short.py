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
import catalog
import learn
import schedule as sched
import visuals
import comic
import roundup

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
    raw = p["content"]["rendered"]
    block = catalog.parse_kokpick_block(raw)   # 태그 제거 전에 뽑아야 한다(주석도 태그로 지워진다)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(re.sub(r"\s+", " ", text))[:4000]
    return {"title": html.unescape(p["title"]["rendered"]), "link": p["link"], "text": text,
            "block": block}


# ---------------------------------------------------------------- 상품 확정
def resolve_product(post, name_hint=""):
    """이 영상이 다루는 **정확한 상품**을 확정한다 — 실사진·브랜드 노출의 전제 조건.

    ① 픽담 글의 KOKPICK 블록(브리프 6-C)이 있으면 그것이 정답이다. 픽담이 자체 파트너스
       계정으로 확정한 브랜드·모델·공식 이미지·자체 링크가 그대로 들어온다(완전 자동).
    ② 없으면 로컬 카탈로그에서 이름으로 찾는다(수동 등록분).
    ③ 둘 다 없으면 None → 카테고리명 + 클레이 아트로 나간다. **추정한 브랜드명은 쓰지 않는다.**
    """
    cat = catalog.load()
    block, slug = post.get("block"), None
    if block:
        slug = catalog.adopt_block(cat, block, updated=str(__import__("datetime").date.today()))
        url = catalog.block_image_url(block)
        if slug and url and not catalog.image_path(cat["products"][slug]):
            local = catalog.cache_image(url, slug)
            if local:
                cat["products"][slug]["image"] = local
                cat["products"][slug]["image_source"] = "pickdam"
        if slug:
            catalog.save(cat)
    entry = (dict(cat["products"][slug], slug=slug) if slug
             else catalog.find(cat, name=name_hint))
    mode = catalog.render_mode(entry)
    print(f"[casto] 상품 확정 — {catalog.display_name(entry, name_hint) or '(미확정)'} [{mode}]")
    if mode != "exact":
        print("[casto]   실제 사진 없음 → 제품 이미지 없이 클레이로 나간다(가짜를 쓰지 않는다).")
    return entry, mode


# ---------------------------------------------------------------- 대본(내용만)
def build_script(post, trends, c, entry=None):
    """LLM은 제품명·콕 근거 3줄·판정만 만든다. 판정어 문구와 씬 구조는 코드가 붙인다.

    상품이 이미 확정된 경우(entry) **제품명은 LLM이 만들지 않는다** — 브랜드·모델을 지어내는
    순간 오정보가 되기 때문이다. 그때 LLM의 역할은 근거 3줄과 판정뿐이다.
    """
    tr = json.dumps({k: trends.get(k) for k in ("hooks", "formats", "caption_style", "avoid")}, ensure_ascii=False)
    # 이 채널에서 실제로 먹힌 패턴을 작가에게 준다 — 영상이 쌓일수록 이 줄이 길어진다.
    # 근거(최소 표본)를 통과한 축만 들어오므로, 초반엔 비어 있는 게 정상이다.
    learned = learn.load_hints()
    lesson = ("\n[이 채널에서 검증된 패턴 — 성과 데이터 기반]\n"
              + "\n".join("- " + h for h in learned) + "\n") if learned else ""
    fixed = ""
    if entry:
        fixed = (f'\n[확정된 상품] {catalog.display_name(entry)} (카테고리: {entry.get("category","")})\n'
                 '→ "product" 값은 이 상품을 가리키는 8자 이내 짧은 이름으로만 쓰고, '
                 '브랜드명·모델명을 새로 지어내지 마세요.\n')
    return llm_json(f"""{fixed}{lesson}당신은 유튜브 쇼츠 채널 「콕픽」의 작가입니다. 니치: {c['niche']}.
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
- **첫 콕은 가장 의외이거나 가장 돈이 걸린 근거**를 둔다. 1초 안에 "이건 봐야겠다"가 되어야 완주한다.
- 세 콕은 **점점 세지는 순서**로. 마지막 콕이 가장 약하면 시청자는 중간에 나간다.
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
        voice = f"{cond} {v['voice']} {reason} 링크는 설명란에."
    else:
        cap = v["card"]
        voice = f"{v['voice']} {reason} 링크는 설명란에."
    scenes.append({"kind": "verdict", "verdict": v, "caption": cap, "voice": re.sub(r"\s+", " ", voice).strip()})
    return scenes, v


# ---------------------------------------------------------------- 콕픽 카드 렌더
def wrap(d, text, f, maxw):
    """어절 단위 줄바꿈.

    글자 단위로 자르면 "냄새가 밴다"가 "냄새가 밴 / 다"로 갈린다 — 한 글자짜리
    고아 줄은 15초 안에 한 번 읽고 지나가는 화면에서 특히 눈에 걸린다(실측).
    어절로 먼저 자르고, 한 어절이 통째로 안 들어갈 때만 글자로 쪼갠다.
    """
    def chars(word):
        out, cur = [], ""
        for ch in word:
            if d.textlength(cur + ch, font=f) > maxw and cur:
                out.append(cur); cur = ch
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out

    lines = []
    for raw in text.split("\n"):
        cur = ""
        for word in raw.split(" "):
            cand = f"{cur} {word}".strip()
            if d.textlength(cand, font=f) <= maxw or not cur:
                if d.textlength(cand, font=f) > maxw:   # 어절 하나가 줄보다 길다
                    parts = chars(cand)
                    lines.extend(parts[:-1]); cur = parts[-1]
                else:
                    cur = cand
            else:
                lines.append(cur); cur = word
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


def scene_card(sc, i, total, c, shot=None, label="", note="", hit=False):
    """콕픽 파스텔 카드 — 크림→민트 그라데이션 + 콕이 + 큰 자막 + 콕 게이지.

    `shot`(실제 상품 사진 경로)이 있으면 **상품이 주인공**이 된다 — 사진 카드가 화면 중앙을
    차지하고 콕이는 왼쪽 아래로 작게 비켜선다. 시청자가 피드에서 본 그 모양을 그대로 봐야
    "어 이거 봤던 거잖아"가 일어나기 때문이다(전략 5-4-10). 사진이 없으면 기존 레이아웃 그대로.
    """
    b = c["brand"]
    cream, mint, sage = tuple(b["cream"]), tuple(b["mint"]), tuple(b["sage"])
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(cream[j] + (mint[j] - cream[j]) * t) for j in range(3)))
    d.text((W // 2, 140), "콕픽 KOKPICK", font=font(48), fill=sage, anchor="mm")

    kind = sc["kind"]
    # punch 모션은 이 둘을 교차한다 — **평소 프레임과 눌림 프레임의 차이가 곧 타격감**이다.
    # 예전엔 콕 씬 기본값이 이미 0.85(거의 눌린 상태)라 교차해도 움직임이 안 보였다.
    squish = 0.15 if kind == "kok" else (0.25 if kind == "rule" else 0.0)
    if hit:
        squish = 0.95
    opened = kind == "verdict" and sc["verdict"]["key"] in ("오늘의 콕", "조건콕")

    placed = None
    if shot:
        # 표지 씬은 자막이 이미 제품명을 크게 말하므로 카드 라벨을 생략(중복 방지),
        # 나머지 씬은 브랜드·모델을 화면에 계속 남겨 정보가 새지 않게 한다.
        placed = visuals.paste_product(img, shot, label="" if kind == "stamp" else label,
                                       accent=sage, font=font(44, bold=False),
                                       note=note, note_font=font(30, bold=False))
        d = ImageDraw.Draw(img)
    if placed:
        kok_box(d, 186, 1452, 212, squish=squish, open_lid=opened)   # 콕이는 조연으로
        if kind == "kok":
            kok_stamp(d, W - 176, 300)
        if kind == "verdict":
            verdict_badge(d, W - 176, 300, sc["verdict"])
    else:
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

    d.text((W // 2, 1790), "링크는 설명란 · 비교는 픽담", font=font(40), fill=sage, anchor="mm")
    d.polygon([(W // 2 - 18, 1822), (W // 2 + 18, 1822), (W // 2, 1846)], fill=sage)
    for k in range(total):  # 진행 점
        x = W // 2 + (k - total / 2 + .5) * 40
        d.ellipse([x - 8, 1866, x + 8, 1882], fill=sage if k <= i else (255, 255, 255))
    p = f"out/scene{i}{'_hit' if hit else ''}.png"
    img.save(p)
    return p


# ---------------------------------------------------------------- 2판 카드 렌더
def base_card(c, i=0, total=1):
    """모든 2판 씬의 바탕 — 그라데이션 + 로고 + 하단 CTA + 진행 점.

    바탕을 한 곳에서 그려야 12개 씬이 같은 채널로 보인다.
    """
    b = c["brand"]
    cream, mint, sage = tuple(b["cream"]), tuple(b["mint"]), tuple(b["sage"])
    # 클레이 배경이 있으면 그걸 쓰고, 없으면 그라데이션으로 폴백한다.
    img = visuals.compose(character=None) if visuals.path("bg") else None
    if img is None:
        img = Image.new("RGB", (W, H))
        d0 = ImageDraw.Draw(img)
        for y in range(H):
            t = y / H
            d0.line([(0, y), (W, y)],
                    fill=tuple(int(cream[j] + (mint[j] - cream[j]) * t) for j in range(3)))
    d = ImageDraw.Draw(img)
    d.text((W // 2, 128), "콕픽 KOKPICK", font=font(46), fill=sage, anchor="mm")
    d.text((W // 2, 1808), "링크는 설명란 · 비교는 픽담", font=font(38), fill=sage, anchor="mm")
    for k in range(total):
        x = W // 2 + (k - total / 2 + .5) * 26
        d.ellipse([x - 7, 1862, x + 7, 1876], fill=sage if k <= i else (255, 255, 255))
    return img, d, sage


def big_text(d, text, y, size=92, fill=(255, 255, 255), stroke=None, maxw=W - 150):
    """큰 자막 — 쇼츠는 소리 없이 보는 사람이 많아서 자막이 본문이다."""
    f = font(size)
    lines = wrap(d, text, f, maxw)[:3]
    y0 = y - (len(lines) - 1) * (size * 0.62)
    for j, ln in enumerate(lines):
        d.text((W // 2, y0 + j * size * 1.24), ln, font=f, fill=fill, anchor="mm",
               stroke_width=7, stroke_fill=stroke)
    return y0 + (len(lines) - 1) * size * 1.24


def card_hook(sc, c, shots, i, total):
    """0~3초 — 물건 3개를 먼저 쏟아 놓는다.

    추상적인 '왜 유행일까'로 시작하는 쇼츠는 1천 조회수에서 죽는다(2026-09-10 실측).
    시청자를 붙잡는 건 **물건**이고, 인과는 붙잡은 다음의 깊이다.
    """
    img, d, sage = base_card(c, i, total)
    got = [p for p in shots if p]
    if got:
        # 부채꼴로 겹쳐 놓아 '여러 개'가 한눈에 읽히게 한다
        spots = {1: [(W // 2, 720)], 2: [(330, 700), (750, 780)],
                 3: [(300, 660), (W // 2, 800), (780, 660)]}.get(len(got), [(W // 2, 720)])
        for p, ctr in zip(got, spots):
            visuals.paste_product(img, p, center=ctr, box=(430, 430), accent=sage)
        visuals.paste_koki(img, "idle", (170, 1480), (240, 240))
        d = ImageDraw.Draw(img)
    big_text(d, sc["caption"], 1290, size=88, stroke=sage)
    return img


def card_ask(sc, c, i, total):
    """3~5초 — 콕이가 질문을 세운다. 여기서부터가 이 채널의 차별점이다."""
    img, d, sage = base_card(c, i, total)
    if visuals.paste_koki(img, "magnify", (W // 2, 700), (620, 620)):
        d = ImageDraw.Draw(img)                     # 클레이 콕이(돋보기 포함)
    else:
        kok_box(d, W // 2, 700, 420, squish=0.2)    # 폴백: 도형 + 돋보기
        magnifier(d, W // 2 + 250, 560)
    big_text(d, sc["caption"], 1250, size=110, stroke=sage)
    return img


def card_item(sc, c, shot, i, total):
    """상품 한 개 — 실사진이 주인공. 절대 그림으로 대체하지 않는다."""
    img, d, sage = base_card(c, i, total)
    if shot:
        visuals.paste_product(img, shot, center=(W // 2, 760), box=(760, 760), accent=sage)
        d = ImageDraw.Draw(img)
    big_text(d, sc["caption"], 1360, size=84, stroke=sage)
    return img


def card_comic(sc, c, panel, i, total):
    """인과 컷 — 왜?(원인) / 그래서(결과). 상품은 여기 안 나온다."""
    img, d, sage = base_card(c, i, total)
    if panel and os.path.exists(panel):
        try:
            im = Image.open(panel).convert("RGB")
            bw, bh = 900, 700
            im = im.resize((bw, int(im.height * bw / im.width)))
            if im.height > bh:
                top = (im.height - bh) // 2
                im = im.crop((0, top, bw, top + bh))
            x0, y0 = (W - bw) // 2, 400
            d.rounded_rectangle((x0 - 12, y0 - 12, x0 + bw + 12, y0 + im.height + 12),
                                radius=40, fill=(255, 255, 255), outline=sage, width=5)
            img.paste(im, (x0, y0))
            d = ImageDraw.Draw(img)
        except Exception as e:
            print(f"[casto] 만화 컷 로드 실패({panel}): {e}")
    visuals.paste_koki(img, "think" if sc.get("phase") == "cause" else "idea",
                       (180, 1470), (260, 260))
    d = ImageDraw.Draw(img)
    badge = sc.get("badge", "")
    if badge:
        f = font(52)
        bw2 = d.textlength(badge, font=f) + 72
        d.rounded_rectangle((W // 2 - bw2 / 2, 268, W // 2 + bw2 / 2, 360),
                            radius=34, fill=sage)
        d.text((W // 2, 314), badge, font=f, fill=(255, 255, 255), anchor="mm")
    big_text(d, sc["caption"], 1330, size=80, stroke=sage)
    return img


def card_verdict(sc, c, shots, win, i, total):
    """마지막 — 셋 중 하나에만 도장. 끝까지 봐야 어느 건지 안다."""
    img, d, sage = base_card(c, i, total)
    v = sc["verdict"]
    shot = shots[win] if win < len(shots) else None
    if shot:
        visuals.paste_product(img, shot, center=(W // 2, 720), box=(660, 660), accent=sage)
        d = ImageDraw.Draw(img)
    verdict_badge(d, W - 190, 330, v)
    won = v["key"] in ("오늘의 콕", "조건콕")
    if visuals.paste_koki(img, "stamp" if won else "nope", (200, 1470), (300, 300)):
        d = ImageDraw.Draw(img)
    else:
        kok_box(d, 190, 1500, 190, squish=0.0, open_lid=won)
    big_text(d, sc["caption"], 1300, size=88, stroke=sage)
    return img


def magnifier(d, cx, cy, r=76):
    """돋보기 — 콕이를 심사관에서 **유행 추적가**로 바꾸는 소품(2판 3절)."""
    col = (47, 93, 78)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255), outline=col, width=14)
    d.line([(cx + r * 0.72, cy + r * 0.72), (cx + r * 1.7, cy + r * 1.7)],
           fill=col, width=22)


def scene_card_v2(sc, i, total, c, shots, panels, out="out"):
    """씬 하나를 그려 파일로 저장하고 경로를 반환한다."""
    kind = sc["kind"]
    if kind == "hook":
        img = card_hook(sc, c, shots, i, total)
    elif kind == "ask":
        img = card_ask(sc, c, i, total)
    elif kind == "item":
        img = card_item(sc, c, shots[sc["idx"]] if sc["idx"] < len(shots) else None, i, total)
    elif kind == "comic":
        img = card_comic(sc, c, (panels.get((sc["idx"], sc["phase"])) or {}).get("path"), i, total)
    elif kind == "verdict":
        img = card_verdict(sc, c, shots, sc["idx"], i, total)
    else:
        img = base_card(c, i, total)[0]
    p = f"{out}/v2_{i:02d}_{kind}.png"
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
def build_caption(s, v, post, c, total, entry=None):
    """설명란 — **정확한 상품명이 검색을 만든다**(전략: 제목=검색 / 본문=구독).

    쿠팡 링크는 픽담이 만든 **우리 파트너스 링크**만 넣는다. 발굴 과정에서 본 남의 링크는
    절대 여기 오지 않는다(catalog.put이 걸러낸다).
    """
    dis = c["disclosure"]
    tags = list(dict.fromkeys(["#오늘의콕", "#콕픽"] + list(s.get("hashtags", []))))[:8]
    name = catalog.display_name(entry, s["product"])
    head = f"{v['caption']} {name}"
    buy = (entry or {}).get("coupang_url", "")
    # CTA 순서(2026-09-08 결정): **쿠팡 링크가 있으면 그게 1순위**다.
    # 픽담에 그 제품 글도 쿠팡 링크도 없는 지금, 픽담을 1순위로 두면 낮은 클릭률을 이탈로 날린다.
    # 링크가 없을 때만 픽담이 1순위가 된다(그때는 픽담이 유일한 착지점이다).
    lines = [f"📦 {head} — {s['title']}", ""]
    if buy:
        lines += [f"🛒 {name} 바로가기: {buy}",
                  f"📄 더 자세한 비교는 픽담: {post['link']}"]
    else:
        lines += [f"👉 자세한 비교는 픽담: {post['link']}"]
    lines.append(f"콕 3번 통과하면 열립니다. 오늘은 {v['key']}!")
    return "\n".join(lines + [
        "",
        " ".join(tags),
        "",
        dis["coupang"],
        dis["ai"],
        f"({total:.0f}초 · 트렌드 {c.get('_trends_updated','-')} 기준)",
    ])


def pick_items(n=roundup.N_ITEMS):
    """이번 편에 담을 상품 n개 — **실사진이 있는 것만**.

    사진 없는 물건을 화면에 못 내는 건 1판과 같다. 달라진 건 개수다.
    최근 다룬 상품은 뒤로 미뤄 같은 셋이 반복되지 않게 한다.
    """
    cat = catalog.load()
    ready = sched.ready_products()
    log = sched._load(sched.PUBLISH_LOG, []) if hasattr(sched, "_load") else []
    recent = {x for e in log[-6:] for x in (e.get("products") or [e.get("product")]) if x}
    fresh = [x for x in ready if x not in recent] or ready
    picked = fresh[:n]
    entries = [catalog.find(cat, name=x) for x in picked]
    shots = [catalog.image_path(e) if catalog.render_mode(e) == "exact" else None
             for e in entries]
    return picked, entries, shots


def main():
    c = cfg()
    os.makedirs("out", exist_ok=True)
    trends = json.load(open("data/trends.json", encoding="utf-8")) if os.path.exists("data/trends.json") else {}
    c["_trends_updated"] = trends.get("updated", "-")

    items, entries, shots = pick_items()
    if len(items) < roundup.N_ITEMS:
        # 2판은 묶음이 전제다. 사진이 모자라면 발행하지 않는다 — 빈 자리를 그림으로
        # 메우는 순간 1판에서 금지한 가상 재현이 된다.
        msg = (f"오늘 발행 보류 — 실사진 있는 상품이 {len(items)}개뿐입니다"
               f"(2판은 {roundup.N_ITEMS}개 묶음). 앱 📷로 캡처를 채워주세요.")
        print("[casto] " + msg)
        telegram_msg("⏸ " + msg)
        return
    print("[casto] 이번 편:", " / ".join(items))

    post = None
    try:
        post = latest_post(c["source_site"])
        print("[casto] 참고 글:", post["title"])
    except Exception as e:                                   # 픽담이 비어도 발행은 된다
        print("[casto] 참고 글 없음(무시):", e)

    s = roundup.build_script(items, trends, c, post)

    # 인과 만화 — 상품은 절대 그리지 않는다(comic.guard가 강제한다)
    panels = {}
    for i, name in enumerate(items):
        row = dict((s.get("items") or [{}] * len(items))[i] if i < len(s.get("items", [])) else {})
        row["name"] = name
        made = comic.panels(row, c["brand"], out_dir="out", font=font(62))
        for phase, m in zip(("cause", "effect"), made):
            panels[(i, phase)] = m
        gen = sum(1 for m in made if m["generated"])
        print(f"[casto]   {roundup.NUM[i]} {name} — 인과 컷 {gen}/2 생성"
              + ("" if gen == 2 else " (나머지는 폴백 카드)"))

    scenes, v, win = roundup.build_scenes(s, items, c)
    print(f"[casto] 2판 규격 — {len(scenes)}씬 · 오늘의 콕: {items[win]} [{v['caption']}]")
    sfx = make_kok_sfx(c["video"]["sfx"]["kok"])

    segs = []
    for i, sc in enumerate(scenes):
        mp3 = f"out/voice{i}.mp3"
        asyncio.run(tts(sc["voice"], mp3, c["video"]["voice"]))
        if sc["kind"] == "verdict" and sfx:
            mp3 = mix_kok(mp3, sfx, f"out/voice{i}_kok.mp3")
        d = dur(mp3) + 0.25
        seg = f"out/seg{i}.mp4"
        img = scene_card_v2(sc, i, len(scenes), c, shots, panels)
        style = {"hook": "pop", "verdict": "pop"}.get(sc["kind"], "zoom")
        vid = visuals.motion_clip([img], d, f"out/mo{i}.mp4", style=style)
        subprocess.run(["ffmpeg", "-y", "-i", vid, "-i", mp3,
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
    cap = roundup.build_caption(s, v, items, entries, c, total, post)
    with open("out/caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)
    os.makedirs("data", exist_ok=True)
    today = __import__("datetime").date.today().isoformat()
    with open("data/last_caption.json", "w", encoding="utf-8") as f:
        json.dump({"date": today, "title": s.get("title", ""), "description": cap,
                   "product": " / ".join(items), "verdict": v["key"],
                   "seconds": round(total, 1),
                   "coupang_url": (entries[win] or {}).get("coupang_url", ""),
                   "items": items, "winner": items[win]},
                  f, ensure_ascii=False, indent=1)
    # 발행 이력 — 학습 루프(learn.py)의 유일한 입력이다.
    try:
        sched.record_publish(
            date=today, slot=os.getenv("CASTO_SLOT", ""),
            key=catalog.slugify(items[win]), verdict=s.get("verdict", "buy"),
            title=s.get("title", ""), product=items[win], products=items,
            format="roundup3", price_band=(entries[win] or {}).get("price_band", ""),
            category=(entries[win] or {}).get("category", ""),
            has_photo=all(bool(x) for x in shots),
            brand=(entries[win] or {}).get("brand", ""),
            hook=(s.get("items") or [{}])[0].get("cause", ""),
            seconds=round(total, 1))
        print(f"[casto] 발행 이력 기록 — {items[win]} / {v['key']}")
    except Exception as e:                                   # noqa: BLE001
        print("[casto] 발행 이력 기록 실패(무시):", e)

    telegram_video("out/short.mp4", cap) or telegram_msg("쇼츠 생성 완료(전송 실패) — Actions 아티팩트 확인")
    print(f"[casto] 완료 — {total:.0f}초, out/short.mp4 (목표 {c['video']['target_sec']}초)")
    if total > c["video"]["target_sec"] + 8:
        print(f"[casto] ⚠ 규격 초과({total:.0f}초) — 내레이션이 길다.")


if __name__ == "__main__":
    main()

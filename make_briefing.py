"""「콕 브리핑」 — 주간 유행템 차트를 **쇼츠 60초 + 롱폼 4분 두 벌**로 렌더한다.

설계 근거: `docs/콕픽_채널_전략.md` 5-4-2(차트 포맷) · 5-4-10(재인 모델) · 5-4-6(2벌 렌더)

한 줄 요약: **트렌드를 쫓는 게 아니라 모아서 보여준다.**
"요즘 유행하는 거 뭐야?"는 매주 다시 발생하는 질문이고, 매주 답을 주면 구독 자산이 된다.

이 포맷의 성패를 가르는 두 가지
1. **재인(recognition)** — 시청자가 "어 이거 내가 봤던 거잖아"를 느껴야 한다. 그래서
   제품을 **정식 상품명이 아니라 유행 시점의 통칭·생김새**로 먼저 부른다.
   ("다용도 실리콘 주방 매트"❌ → "그 물결무늬 매트"✅)
2. **차트 구조** — 단순 TOP10 나열은 완결형이라 다시 볼 이유가 없다.
   **NEW / ↑상승 / ↓하락** 델타를 보여줘야 매주 볼 이유가 생긴다(빌보드 논리).

두 벌을 만드는 이유(같은 데이터, 다른 그릇)
- **쇼츠 60초** = 발견(추천 피드). 8~10개를 빠르게 훑고 "자세한 판정은 수요일에".
- **롱폼 3~4분** = 검색·시청시간. 섹션별로 근거를 붙인다. 월간 합본과 **별개의 시청시간 축**.

실행: `python make_briefing.py [short|long|both]`
"""
from __future__ import annotations

import asyncio, datetime as dt, json, os, subprocess, sys

from PIL import Image, ImageDraw

from common import cfg, llm_json, telegram_video, telegram_msg
# 렌더 헬퍼는 콕픽 규격이 이미 구현된 make_short에서 재사용한다(브랜드 문법 일관성).
from make_short import W, H, font, wrap, kok_box, tts, dur

BOARD = "data/trend_board.json"
OUT = "out"
DELTA_LABEL = {"new": "NEW", "up": "상승", "down": "하락", "flat": "유지"}
DELTA_COLOR = {"new": (214, 90, 78), "up": (47, 143, 104), "down": (140, 140, 150), "flat": (150, 150, 150)}
SECTION_ORDER = ["new", "up", "down"]


# ------------------------------------------------------------------ 대본
def build_briefing(board: dict, c: dict, llm=llm_json) -> dict:
    """보드 데이터 → 브리핑 대본. `llm`을 주입받아 테스트에서 LLM 없이 검증할 수 있게 한다."""
    items = board.get("briefing", [])[:10]
    if not items:
        raise SystemExit("[briefing] trend_board.json의 briefing이 비었다 — 먼저 trend_products.py board 실행")
    # 뒤쪽에 섞을 '발견' 재료 — 노출은 낮지만 구매가치가 높은 것(5-4-10 브리핑 구성 ③)
    blue = [r for r in board.get("deep_dive", []) if r["key"] not in {i["key"] for i in items}][:2]

    payload = [{
        "key": r["key"], "name": r["name"], "delta": r.get("delta"),
        "price": r.get("price"), "price_band": r.get("price_band"),
        "videos": r.get("videos"), "channels": r.get("channels"),
        "exposure": r.get("exposure"), "mentions": r.get("mentions"),
        "quadrant": r.get("quadrant"),
    } for r in items + blue]

    today = dt.date.today()
    return llm(f"""당신은 유튜브 채널 「콕픽」의 주간 트렌드 브리핑 작가입니다.
이 코너의 목적은 예측이 아니라 **재인(recognition)** 입니다 — 시청자가 인스타·쇼츠를 넘기다
"이 제품 좀 자주 보이네"라고 느꼈던 것을 여기서 다시 만나 "어 이거 내가 봤던 거잖아"가 되게 하는 것.

[이번 주 수집 데이터] (exposure=총 노출량, channels=다룬 채널 수, delta=지난주 대비)
{json.dumps(payload, ensure_ascii=False, indent=1)}

아래 JSON만 출력하세요.
{{"title": "제목 — **대표 제품 2~3개의 이름을 반드시 포함** + 개수 + ({today.year}년 {today.month}월). 브랜드 서사 금지. 예: '이번 주 유행템 9개 — 물결무늬 매트·계란 슬라이서·미니 제빙기 (2026년 9월)'",
 "opening_voice": "오프닝 1문장 — 판정이 아니라 **확인 질문**으로 연다. 예: '이거, 보신 적 있죠?'",
 "items": [
   {{"key": "위 데이터의 key 그대로",
     "alias": "**유행할 때 사람들이 부르는 통칭**(10자 이내). 정식 상품명 금지 — 못 알아본다. 예: '물결무늬 매트'",
     "look": "생김새 한 줄(12자 이내) — 형태로 먼저 알아보게 한다. 예: '물결 모양 실리콘'",
     "why": "왜 유행하는지 한 줄(20자 이내). 근거 없는 추측 금지 — 데이터의 exposure/channels/delta로 설명",
     "verdict": "kok 또는 next — 간이 판정만. 콕 3번 심층 심사는 주중 편에서 한다",
     "short_voice": "쇼츠용 내레이션 1문장(25자 내외, 구어체)",
     "long_voice": "롱폼용 내레이션 2~3문장(80자 내외) — 조건·가격대·주의점을 덧붙인다"}}
   ... 위 데이터의 모든 제품
 ],
 "next_week": ["다음 주 심사 예고 3개 — 위 데이터에서 아직 심층으로 안 다룬 것 위주"],
 "outro_voice": "마무리 1문장 — '자세한 판정은 수요일에' + 댓글로 심사 신청 유도"}}

규칙
- **정식 상품명·브랜드명 금지.** 시청자가 피드에서 본 형태로 불러야 재인이 일어난다.
- 과장·미검증 효능 주장 금지. 가격은 '~원대' 범위로.
- 판정어는 코드가 붙이니 문장에 '오늘의 콕'·'다음콕'을 쓰지 말 것.""")


# ------------------------------------------------------------------ 카드 렌더
def _bg(d: ImageDraw.ImageDraw, c: dict) -> tuple:
    b = c["brand"]
    cream, mint, sage = tuple(b["cream"]), tuple(b["mint"]), tuple(b["sage"])
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(cream[j] + (mint[j] - cream[j]) * t) for j in range(3)))
    d.text((W // 2, 140), "콕픽 KOKPICK", font=font(48), fill=sage, anchor="mm")
    return cream, mint, sage


def cover_card(title: str, count: int, c: dict, path: str) -> str:
    """표지 — 재인 트리거("이거 보신 적 있죠?")를 가장 크게. 판정이 아니라 확인 질문이다."""
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    _, _, sage = _bg(d, c)
    kok_box(d, W // 2, 600, 380)
    for i, ln in enumerate(["이거,", "보신 적 있죠?"]):
        d.text((W // 2, 1060 + i * 130), ln, font=font(108), fill=(255, 255, 255),
               anchor="mm", stroke_width=8, stroke_fill=sage)
    d.text((W // 2, 1330), f"이번 주 유행템 {count}개", font=font(64), fill=sage, anchor="mm")
    wk = dt.date.today().isocalendar()
    d.text((W // 2, 1420), f"{wk[0]}년 {wk[1]}주차", font=font(44), fill=sage, anchor="mm")
    img.save(path); return path


def item_card(item: dict, rowdata: dict, idx: int, total: int, c: dict, path: str) -> str:
    """항목 카드 — 순위 배지 + 델타 + **통칭**(크게) + 생김새 + 왜 유행 + 간이 판정."""
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    _, _, sage = _bg(d, c)

    # 순위 배지
    d.ellipse([70, 240, 210, 380], fill=sage)
    d.text((140, 310), str(idx + 1), font=font(76), anchor="mm", fill=(255, 255, 255))

    # 델타 배지 — 차트의 핵심. 지난주 대비 변화가 보여야 매주 볼 이유가 생긴다
    dk = rowdata.get("delta", "flat")
    col = DELTA_COLOR.get(dk, (150, 150, 150))
    label = DELTA_LABEL.get(dk, "유지")
    bw = 60 + 46 * len(label)
    d.rounded_rectangle([W - 70 - bw, 248, W - 70, 372], radius=28, fill=col)
    d.text((W - 70 - bw / 2, 310), label, font=font(52), anchor="mm", fill=(255, 255, 255))

    kok_box(d, W // 2, 640, 300, squish=0.2 if dk == "up" else 0.0)

    # 통칭 — 가장 크게. 재인은 이 단어에서 일어난다
    f = font(96)
    lines = wrap(d, item.get("alias", ""), f, W - 180)[:2]
    y0 = 1010 - (len(lines) - 1) * 55
    for j, ln in enumerate(lines):
        d.text((W // 2, y0 + j * 110), ln, font=f, fill=(255, 255, 255), anchor="mm",
               stroke_width=7, stroke_fill=sage)

    if item.get("look"):
        d.text((W // 2, y0 + len(lines) * 110 + 20), item["look"], font=font(50), fill=sage, anchor="mm")
    if item.get("why"):
        for j, ln in enumerate(wrap(d, item["why"], font(46), W - 220)[:2]):
            d.text((W // 2, 1300 + j * 62), ln, font=font(46), fill=sage, anchor="mm")

    # 간이 판정 — 콕 3번 심층 심사는 주중 편에서 한다
    v = c["verdicts"]["buy" if item.get("verdict") == "kok" else "later"]
    vc = tuple(v.get("color", (47, 143, 104)))
    d.rounded_rectangle([W // 2 - 200, 1470, W // 2 + 200, 1580], radius=34, fill=(255, 255, 255), outline=vc, width=8)
    d.text((W // 2, 1525), v["card"], font=font(58), anchor="mm", fill=vc)

    price = rowdata.get("price")
    if price:
        d.text((W // 2, 1650), f"{int(price):,}원대", font=font(48), fill=sage, anchor="mm")

    d.text((W // 2, 1790), "자세한 판정은 수요일 · 픽담", font=font(40), fill=sage, anchor="mm")
    for k in range(total):
        x = W // 2 + (k - total / 2 + .5) * 34
        d.ellipse([x - 7, 1866, x + 7, 1880], fill=sage if k <= idx else (255, 255, 255))
    img.save(path); return path


def section_card(kind: str, c: dict, path: str) -> str:
    """롱폼 전용 섹션 표지 — 챕터 경계를 만들어 검색 유입자가 원하는 지점으로 점프해도 세션이 유지된다."""
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    _, _, sage = _bg(d, c)
    col = DELTA_COLOR[kind]
    txt = {"new": "이번 주 새로 등장", "up": "계속 오르는 중", "down": "이건 요즘 좀 덜 보이죠"}[kind]
    d.rounded_rectangle([W // 2 - 260, 700, W // 2 + 260, 860], radius=48, fill=col)
    d.text((W // 2, 780), DELTA_LABEL[kind], font=font(88), anchor="mm", fill=(255, 255, 255))
    for j, ln in enumerate(wrap(d, txt, font(72), W - 200)[:2]):
        d.text((W // 2, 1040 + j * 92), ln, font=font(72), fill=sage, anchor="mm")
    img.save(path); return path


def outro_card(next_week: list[str], c: dict, path: str) -> str:
    """마무리 — **다음 주 예고 + 댓글 심사신청**. 순위 채널이 구조적으로 못 하는 것이고,
    예고가 곧 구독 전환의 핵심이다(5-1B)."""
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    _, _, sage = _bg(d, c)
    d.text((W // 2, 420), "다음 주 심사 대상", font=font(76), fill=sage, anchor="mm")
    for i, t in enumerate(next_week[:3]):
        d.rounded_rectangle([120, 560 + i * 190, W - 120, 700 + i * 190], radius=36,
                            fill=(255, 255, 255), outline=sage, width=6)
        d.text((W // 2, 630 + i * 190), t[:16], font=font(58), anchor="mm", fill=sage)
    for j, ln in enumerate(["심사받고 싶은 제품", "댓글로 신청받습니다"]):
        d.text((W // 2, 1320 + j * 100), ln, font=font(66), fill=(255, 255, 255), anchor="mm",
               stroke_width=6, stroke_fill=sage)
    d.text((W // 2, 1600), "자세한 판정은 수요일", font=font(52), fill=sage, anchor="mm")
    img.save(path); return path


# ------------------------------------------------------------------ 장면 조립
def scenes_for(variant: str, brief: dict, board: dict, c: dict) -> list[dict]:
    """`short`=발견용(빠르게 훑기) / `long`=검색·시청시간용(섹션+근거).

    브리핑 구성 규칙(5-4-10): **첫 3개는 노출량 최상위**를 배치한다 —
    초반 이탈 방지의 핵심이 재인이므로 가장 많이 본 것을 먼저 준다.
    뒤쪽에는 노출은 낮아도 구매가치가 높은 것을 섞어 발견의 재미를 준다.
    """
    rows = {r["key"]: r for r in board.get("briefing", []) + board.get("deep_dive", [])}
    items = [i for i in brief.get("items", []) if i.get("key") in rows]
    items.sort(key=lambda i: rows[i["key"]].get("recognition", 0), reverse=True)

    scenes: list[dict] = [{"kind": "cover", "voice": brief.get("opening_voice", "이거, 보신 적 있죠?")}]
    if variant == "short":
        for i, it in enumerate(items):
            scenes.append({"kind": "item", "item": it, "row": rows[it["key"]], "idx": i,
                           "voice": it.get("short_voice", it.get("alias", ""))})
    else:
        # 롱폼은 델타 섹션으로 묶는다. 첫 섹션이 NEW라 신선도가 앞에 온다
        idx = 0
        for sec in SECTION_ORDER:
            group = [it for it in items if rows[it["key"]].get("delta") == sec]
            if not group:
                continue
            scenes.append({"kind": "section", "section": sec,
                           "voice": {"new": "먼저 이번 주 새로 등장한 것들입니다.",
                                     "up": "계속 오르고 있는 것들.",
                                     "down": "반대로, 요즘 좀 덜 보이는 것들입니다."}[sec]})
            for it in group:
                scenes.append({"kind": "item", "item": it, "row": rows[it["key"]], "idx": idx,
                               "voice": it.get("long_voice", it.get("short_voice", ""))})
                idx += 1
        rest = [it for it in items if rows[it["key"]].get("delta") not in SECTION_ORDER]
        for it in rest:
            scenes.append({"kind": "item", "item": it, "row": rows[it["key"]], "idx": idx,
                           "voice": it.get("long_voice", "")})
            idx += 1
    scenes.append({"kind": "outro", "voice": brief.get("outro_voice", "자세한 판정은 수요일에.")})
    return scenes


def render(variant: str, brief: dict, board: dict, c: dict) -> str:
    os.makedirs(OUT, exist_ok=True)
    scenes = scenes_for(variant, brief, board, c)
    n_items = sum(1 for s in scenes if s["kind"] == "item")
    segs = []
    for i, sc in enumerate(scenes):
        png = f"{OUT}/br_{variant}_{i}.png"
        if sc["kind"] == "cover":
            cover_card(brief.get("title", ""), n_items, c, png)
        elif sc["kind"] == "section":
            section_card(sc["section"], c, png)
        elif sc["kind"] == "outro":
            outro_card(brief.get("next_week", []), c, png)
        else:
            item_card(sc["item"], sc["row"], sc["idx"], n_items, c, png)
        mp3 = f"{OUT}/br_{variant}_{i}.mp3"
        asyncio.run(tts(sc["voice"], mp3, c["video"]["voice"]))
        d = dur(mp3) + 0.25
        seg = f"{OUT}/br_{variant}_seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-i", mp3, "-t", f"{d:.2f}",
                        "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                        "-shortest", seg], check=True, capture_output=True)
        segs.append(seg)
        print(f"[briefing:{variant}] {i+1}/{len(scenes)} [{sc['kind']}] {d:.1f}s")
    lst = f"{OUT}/br_{variant}_list.txt"
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in segs)
    out = f"{OUT}/briefing_{variant}.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out],
                   check=True, capture_output=True)
    print(f"[briefing:{variant}] 완료 — {dur(out):.0f}초 {out}")
    return out


def build_caption(brief: dict, board: dict, c: dict, total: float, variant: str) -> str:
    dis = c["disclosure"]
    rows = {r["key"]: r for r in board.get("briefing", [])}
    lines = [f"📦 {brief.get('title','')}", ""]
    for i, it in enumerate(brief.get("items", [])[:10], 1):
        r = rows.get(it["key"], {})
        mark = {"new": "🆕", "up": "↑", "down": "↓"}.get(r.get("delta"), "·")
        lines.append(f"{i}. {mark} {it.get('alias','')} — {it.get('why','')}")
    lines += ["", "👉 각 제품 상세와 판정은 픽담: https://pickdam.com/today", ""]
    if brief.get("next_week"):
        lines += ["다음 주 심사 예고: " + " · ".join(brief["next_week"][:3]),
                  "심사받고 싶은 제품은 댓글로 신청해주세요.", ""]
    lines += ["#오늘의콕 #콕픽 #요즘유행하는거 #유행템", "", dis["coupang"], dis["ai"],
              f"({total:.0f}초 · {variant} · 수집 {board.get('updated','-')})"]
    return "\n".join(lines)


def main() -> None:
    variant = sys.argv[1] if len(sys.argv) > 1 else "both"
    c = cfg()
    if not os.path.exists(BOARD):
        raise SystemExit(f"[briefing] {BOARD} 없음 — 먼저 `python trend_products.py board`")
    with open(BOARD, encoding="utf-8") as f:
        board = json.load(f)
    brief = build_briefing(board, c)
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/briefing_script.json", "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, indent=1)
    for v in (["short", "long"] if variant == "both" else [variant]):
        path = render(v, brief, board, c)
        cap = build_caption(brief, board, c, dur(path), v)
        with open(f"{OUT}/briefing_{v}_caption.txt", "w", encoding="utf-8") as f:
            f.write(cap)
        telegram_video(path, cap) or telegram_msg(f"브리핑({v}) 생성 완료 — Actions 아티팩트 확인")


if __name__ == "__main__":
    main()

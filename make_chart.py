"""「콕픽 차트」 — 그 주에 뜬 것 5개를 **쇼츠 1벌**로 렌더한다.

설계 근거: `docs/콕픽_채널구조_보고서.md` §3 (상품 카드·상태 태그·이중 타깃)

이 편이 기존 브리핑과 다른 점 딱 셋
  ① **실사진이 전면이다.** 흰 카드에 오려낸 제품컷이 아니라 사진이 화면을 꽉 채운다.
     (2026-09-10 실측: 100만~473만 쇼츠 썸네일 중 흰 카드 화면은 하나도 없었다)
  ② **순위를 거꾸로 센다.** 5위 → 1위. 1위를 먼저 주면 그 뒤를 볼 이유가 없다.
  ③ **상태 태그로 판정한다.** 예감/유행중/끝물/재점화 — 근거(수요 추이·공급량)가 있을
     때만 붙는다. 근거 없는 판정은 상품을 그림으로 그리는 것과 같은 종류의 거짓말이다.

실측이 말해주는 것(2026-09-13/15): 차트 자체를 본문으로 쓴 영상은 828회·76회로 죽었고,
후회 프레임(238만)·판정형(172만)·가격 충돌(200만)이 살았다. 그래서 차트는 **그릇**이고
각 칸 안에서는 후회·판정·충돌의 언어를 쓴다.

실행: `python make_chart.py`
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess

import cards
import chart
from common import cfg, llm_json, telegram_msg, telegram_video
from make_short import H, W, dur, font, tts, wrap

OUT = "out"


# ------------------------------------------------------------------ 대본
def build_script(ch: dict, c: dict, llm=llm_json) -> dict:
    """차트 데이터 → 대본. `llm`을 주입받아 테스트에서 LLM 없이 검증할 수 있게 한다.

    **데이터에 없는 것은 말하지 않는다.** 가격이 없으면 가격을 말하지 않고, 수요 추이가
    없으면 '급상승'이라고 하지 않는다. 이 채널이 파는 건 판정의 신뢰도뿐이다.
    """
    entries = ch.get("entries") or []
    if len(entries) < chart.MIN_N:
        raise SystemExit(f"[chart] 실사진 확보 {len(entries)}개 — {chart.MIN_N}개 미만이면 내지 않는다")

    payload = [{
        "rank": e["rank"], "key": e["key"], "display": e["display"],
        "status": e.get("status"), "tag": (e.get("tag") or {}).get("label"),
        "headline": e.get("headline"), "price": e.get("price"),
        "delta": (e.get("delta") or {}).get("text"),
        "signals": e.get("signals"),
    } for e in entries]

    return llm(f"""당신은 유튜브 채널 「콕픽」의 주간 차트 작가입니다.
이 코너는 예측이 아니라 **재인(recognition)** 입니다 — 시청자가 피드를 넘기다 "이거 자주
보이네" 했던 걸 여기서 다시 만나 "어 이거 내가 봤던 거잖아"가 되게 하는 것.

[이번 주 차트] {ch['week']} · 수집 {ch.get('source_days')}일
{json.dumps(payload, ensure_ascii=False, indent=1)}

아래 JSON만 출력하세요.
{{"title": "제목 — 1·2위 상품명을 반드시 포함 + '이번 주' + 개수. 브랜드 서사 금지",
 "hook": "첫 3초 자막 (12자 이내). 질문형으로 열어 스크롤을 세운다. 예: '이거 보신 적 있죠'",
 "hook_voice": "훅 내레이션 1문장 (20자 내외)",
 "items": [
   {{"key": "위 데이터의 key 그대로",
     "reason": "**왜 갑자기 보이는가** 한 줄 (22자 이내). 반드시 위 데이터의 signals/headline으로
               설명할 것. 데이터에 없는 효능·후기·가격을 지어내면 안 된다",
     "voice": "내레이션 1~2문장 (45자 내외, 구어체). 상태 태그가 있으면 그 온도를 살린다:
              예감=아직 다들 모른다 / 유행중=지금이 정점 / 끝물=이제 새로 살 필요는 없다 /
              재점화=예전에 보셨던 그거"}}
   ... 위 데이터의 모든 항목
 ],
 "outro_voice": "마무리 1~2문장 — 다음 주에도 같은 시간에 온다는 약속 + 댓글 심사신청 유도"}}

규칙
- **없는 숫자를 만들지 말 것.** headline/signals에 있는 수치만 쓴다.
- 과장·미검증 효능 주장 금지. 가격은 price가 있을 때만 말한다.
- 기성세대와 젊은 세대가 같이 본다. 한 편 안에 "먼저 알면 앞서간다"와 "몰라도 아직
  안 늦었다"가 최소 하나씩 나오게 섞을 것.
- 판정 문구는 코드가 붙이니 문장에 태그 라벨을 그대로 쓰지 말 것.""")


# ------------------------------------------------------------------ 카드
def cover_card(ch: dict, script: dict, c: dict, path: str) -> str:
    """표지 — 1위 사진 위에 훅. 차트 이름보다 **질문**이 크다."""
    from PIL import Image, ImageDraw

    from make_short import fill_frame, punch_text, scrim
    top = ch["entries"][0]
    img = Image.new("RGB", (W, H))
    fill_frame(img, top["image"], dim=0.3)
    scrim(img, top_h=700, bot_h=900, strength=195)
    d = ImageDraw.Draw(img)
    d.text((W // 2, 300), "콕픽 차트", font=font(56), anchor="mm", fill=(235, 240, 236))
    d.text((W // 2, 380), ch["week"], font=font(42, bold=False), anchor="mm", fill=(205, 212, 205))
    punch_text(d, script.get("hook", "이거 보신 적 있죠"), 1020, size=118,
               accent=(214, 90, 78))
    n = len(ch["entries"])
    d.text((W // 2, 1300), f"이번 주 {n}개", font=font(70), anchor="mm",
           fill=(255, 255, 255), stroke_width=9, stroke_fill=(20, 30, 26))
    d.text((W // 2, 1420), "5위부터 셉니다", font=font(50, bold=False), anchor="mm",
           fill=(226, 232, 226), stroke_width=6, stroke_fill=(20, 30, 26))
    img.save(path)
    return path


def outro_card(ch: dict, c: dict, path: str) -> str:
    """마무리 — 다음 주 약속. 순위 채널이 구조적으로 못 하는 것이 **예고**다."""
    from PIL import Image, ImageDraw

    from make_short import fill_frame, scrim
    img = Image.new("RGB", (W, H))
    fill_frame(img, ch["entries"][0]["image"], dim=0.55)
    scrim(img, top_h=800, bot_h=800, strength=200)
    d = ImageDraw.Draw(img)
    for j, ln in enumerate(["다음 주 일요일", "같은 시간에"]):
        d.text((W // 2, 780 + j * 130), ln, font=font(88), anchor="mm",
               fill=(255, 255, 255), stroke_width=9, stroke_fill=(20, 30, 26))
    for j, ln in enumerate(wrap(d, "심사받고 싶은 제품은 댓글로 신청받습니다", font(52), W - 220)[:2]):
        d.text((W // 2, 1180 + j * 70), ln, font=font(52), anchor="mm",
               fill=(226, 232, 226), stroke_width=6, stroke_fill=(20, 30, 26))
    img.save(path)
    return path


# ------------------------------------------------------------------ 조립
def scenes_for(ch: dict, script: dict) -> list[dict]:
    """표지 → **5위부터 1위까지** → 마무리.

    1위를 먼저 주면 그 뒤를 볼 이유가 사라진다. 카운트다운은 완주 장치다.
    """
    reasons = {i.get("key"): i for i in script.get("items", [])}
    scenes = [{"kind": "cover", "voice": script.get("hook_voice", "이거, 보신 적 있죠?")}]
    ordered = sorted(ch["entries"], key=lambda e: -e["rank"])     # 5 → 1
    for i, e in enumerate(ordered):
        it = reasons.get(e["key"], {})
        scenes.append({"kind": "item", "entry": e, "idx": i, "reason": it.get("reason", ""),
                       "voice": it.get("voice") or e.get("headline") or e["display"]})
    scenes.append({"kind": "outro", "voice": script.get("outro_voice", "다음 주 일요일에 또 옵니다.")})
    return scenes


def render(ch: dict, script: dict, c: dict) -> str:
    os.makedirs(OUT, exist_ok=True)
    scenes = scenes_for(ch, script)
    n = sum(1 for s in scenes if s["kind"] == "item")
    segs = []
    for i, sc in enumerate(scenes):
        png = f"{OUT}/ch_{i}.png"
        if sc["kind"] == "cover":
            cover_card(ch, script, c, png)
        elif sc["kind"] == "outro":
            outro_card(ch, c, png)
        else:
            cards.card_rank(sc["entry"], c, png, idx=sc["idx"], total=n,
                            reason=sc["reason"], week=ch["week"])
        mp3 = f"{OUT}/ch_{i}.mp3"
        asyncio.run(tts(sc["voice"], mp3, c["video"]["voice"]))
        d = dur(mp3) + 0.3
        seg = f"{OUT}/ch_seg{i}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-i", mp3, "-t", f"{d:.2f}",
                        "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-c:a", "aac",
                        "-shortest", seg], check=True, capture_output=True)
        segs.append(seg)
        print(f"[chart] {i+1}/{len(scenes)} [{sc['kind']}] {d:.1f}s")
    lst = f"{OUT}/ch_list.txt"
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.basename(p)}'\n" for p in segs)
    out = f"{OUT}/chart.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out],
                   check=True, capture_output=True)
    print(f"[chart] 완료 — {dur(out):.0f}초 {out}")
    return out


def build_caption(ch: dict, script: dict, c: dict, total: float) -> str:
    """설명란 — 순위·이유·**쿠팡 링크**. 링크가 없으면 그 줄을 비운다(가짜 링크 금지)."""
    dis = c["disclosure"]
    reasons = {i.get("key"): i for i in script.get("items", [])}
    lines = [f"📊 {script.get('title', '')}", ""]
    for e in ch["entries"]:
        it = reasons.get(e["key"], {})
        tag = (e.get("tag") or {}).get("label")
        head = f"{e['rank']}. {e['display']}" + (f" · {tag}" if tag else "")
        lines.append(head)
        if it.get("reason"):
            lines.append(f"   {it['reason']}")
        if e.get("price"):
            lines.append(f"   {int(e['price']):,}원")
        if e.get("coupang_url"):
            lines.append(f"   {e['coupang_url']}")
        lines.append("")
    lines += ["다음 주 일요일 같은 시간에 이어집니다.",
              "심사받고 싶은 제품은 댓글로 신청해주세요.", "",
              "#콕픽차트 #유행템 #요즘유행하는거 #쇼핑", "",
              dis["coupang"], dis["ai"],
              f"({total:.0f}초 · {ch['week']} · 수집 {ch.get('source_days')}일)"]
    return "\n".join(lines)


def main() -> None:
    c = cfg()
    ch = chart.build()
    chart.save(ch)
    print(chart.report(ch))
    script = build_script(ch, c)
    os.makedirs(OUT, exist_ok=True)
    with open(f"{OUT}/chart_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=1)
    path = render(ch, script, c)
    cap = build_caption(ch, script, c, dur(path))
    with open(f"{OUT}/chart_caption.txt", "w", encoding="utf-8") as f:
        f.write(cap)
    telegram_video(path, cap) or telegram_msg(f"콕픽 차트 {ch['week']} 생성 완료")


if __name__ == "__main__":
    main()

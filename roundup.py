"""포맷 2판 「왜 갑자기 보이지?」 — 3개 묶음 + 인과 설명의 대본·씬 구성.

규격: docs/콕픽_쇼츠_포맷_2판.md

왜 1판(상품 1개 · 콕 3번)을 버렸는지는 그 문서 5절에 실측이 있다. 한 줄로 줄이면,
이 니치에서 100만을 넘는 건 **전부 2~3개 묶음**이고 단일 상품 심사 포맷은 존재하지 않는다.

이 모듈이 지키는 두 가지:
1. **몰아서** — 상품 3개를 한 편에 담는다(도달)
2. **왜** — 각 상품마다 원인→결과 2컷으로 유행의 이유를 설명한다(차별점)

그리고 도장은 **하나만** 찍힌다 — 끝까지 봐야 어느 게 콕인지 알 수 있어야
순위 영상의 완결형 함정(다 보면 다시 올 이유가 없음)에 빠지지 않는다.
"""
import json

import catalog
import learn
from common import llm_json

N_ITEMS = 3          # 4개는 조회수가 떨어진다(9.2천 vs 3개 46만~473만, 2026-09-10 실측)
NUM = ["①", "②", "③"]


def build_script(items, trends, c, post=None):
    """LLM은 **유행의 원인·결과·용도**만 쓴다. 상품명·구조·판정어는 코드가 정한다.

    `items`는 이미 확정된 상품 목록이다(catalog에서 온 실사진 보유 상품).
    LLM에게 상품을 고르게 하지 않는다 — 브랜드·모델을 지어내는 순간 오정보가 된다.
    """
    tr = json.dumps({k: trends.get(k) for k in ("hooks", "avoid")}, ensure_ascii=False)
    learned = learn.load_hints()
    lesson = ("\n[이 채널에서 검증된 패턴 — 성과 데이터 기반]\n"
              + "\n".join("- " + h for h in learned) + "\n") if learned else ""
    names = "\n".join(f"{NUM[i]} {n}" for i, n in enumerate(items))
    src = f"\n[참고 글]\n{post['text'][:1500]}\n" if post else ""

    return llm_json(f"""{lesson}당신은 유튜브 쇼츠 채널 「콕픽」의 작가입니다. 니치: {c['niche']}.
채널의 존재 이유는 **"요즘 갑자기 많이 보이는 물건 3개를 몰아서 보여주고, 그게 왜 유행인지 알게 하는 것"**입니다.
[이번 주 트렌드 지침] {tr}{src}
[이번 편에 다룰 상품 — 이 셋을 그대로 씁니다. 다른 상품을 고르지 마세요]
{names}

각 상품마다 **왜 지금 유행인지**를 원인→결과로 설명하세요. 아래 JSON만 출력합니다.

{{"items": [
  {{"cause": "유행의 원인 한 줄(화면 자막, 16자 이내)",
    "cause_scene": "원인 장면을 영어로 묘사(그림 지시문). 상품 자체는 절대 묘사하지 말 것 — 상황·사람·다른 유행·계절·매대만",
    "effect": "그래서 생긴 결과 한 줄(화면 자막, 16자 이내)",
    "effect_scene": "결과 장면을 영어로 묘사(그림 지시문). 역시 상품 자체 묘사 금지",
    "use": "어떻게 쓰는 물건인지 한 줄(14자 이내)"}},
  ... 정확히 {len(items)}개, 위 번호 순서대로
 ],
 "winner": 0,
 "verdict": "buy" | "cond" | "later",
 "verdict_reason": "왜 이걸 골랐는지 한 줄(15자 이내)",
 "condition": "조건콕일 때만 '자취생이면'처럼 조건(8자 이내), 아니면 빈 문자열",
 "title": "쇼츠 제목(35자 이내)",
 "hashtags": ["#태그", ... 6개]}}

규칙
- **cause는 진짜 원인이어야 한다.** "인기가 많아서"처럼 동어반복이면 실패다.
  좋은 예: 두쫀쿠가 유행 → 피스타치오 수요 폭증 → 그래서 이게 보인다.
  다른 유행·계절·물가·방송·해외 유행 등 **바깥에서 온 이유**를 찾으세요.
- **cause_scene / effect_scene에 상품 이름을 쓰지 마세요.** 상품은 실제 사진으로 나갑니다.
  그림은 '왜'를 설명하는 상황만 그립니다. (상품명이 섞이면 코드가 그 컷을 버립니다)
- winner는 0-based 인덱스. **셋 중 하나만** 도장을 받습니다.
- 제목 규칙(2026-09-10 실측): 숫자 + 후회/발견 프레임 + 사회적 증거로 만든다.
  ✅ "어쩐지 자꾸 보이더라, 요즘 난리난 주방템 3가지"
  ❌ 브랜드명 나열 — 조회수가 자릿수로 떨어진다.
- **부정어 금지** — '별로다/사지 마라' 대신 '아직'의 뉘앙스.
- 겪지 않은 경험담·과장 금지. 판정어("오늘의 콕" 등)는 코드가 넣으니 쓰지 말 것.""")


def build_scenes(s, items, c):
    """대본 + 2판 고정 규격 → 씬 리스트.

    씬 순서가 곧 포맷이다. 훅에서 물건을 먼저 보여주고(추상적 '왜 유행'은 1천대에서 죽는다),
    붙잡은 다음에 인과를 푼다.
    """
    v = c["verdicts"][s.get("verdict", "buy") if s.get("verdict") in c["verdicts"] else "buy"]
    rows = s.get("items", [])
    n = len(items)

    scenes = [
        {"kind": "hook", "caption": f"이번 주\n갑자기 많이 보이는 것 {n}",
         "voice": f"이번 주 갑자기 많이 보이는 것 {n}개."},
        {"kind": "ask", "caption": "왜 갑자기?", "voice": "왜 갑자기 보일까요?"},
    ]
    for i, name in enumerate(items):
        r = rows[i] if i < len(rows) else {}
        use = (r.get("use") or "").strip()
        scenes.append({"kind": "item", "idx": i, "name": name,
                       "caption": f"{NUM[i]} {name}",
                       "voice": f"{name}." + (f" {use}." if use else "")})
        for kind in ("cause", "effect"):
            line = (r.get(kind) or "").strip()
            if not line:
                continue
            scenes.append({"kind": "comic", "idx": i, "phase": kind,
                           "badge": "왜?" if kind == "cause" else "그래서",
                           "caption": line, "voice": line})

    win = s.get("winner", 0)
    win = win if isinstance(win, int) and 0 <= win < n else 0
    cond = (s.get("condition") or "").strip()
    reason = (s.get("verdict_reason") or "").strip()
    if reason and reason[-1] not in ".!?…":
        reason += "."
    cap = (f"{cond} {v['card']}".strip() if v["key"] == "조건콕" else v["card"])
    voice = (f"{cond} {v['voice']}" if v["key"] == "조건콕" else v["voice"])
    scenes.append({"kind": "verdict", "verdict": v, "idx": win, "name": items[win],
                   "caption": f"{cap}\n{items[win]}",
                   "voice": f"오늘의 콕은 {items[win]}. {reason} 링크는 설명란에."
                            if v["key"] == "오늘의 콕" else
                            f"{voice} {items[win]}. {reason} 링크는 설명란에."})
    return scenes, v, win


def build_caption(s, v, items, entries, c, total, post=None):
    """설명란 — 상품 3개 전부의 링크를 넣는다. 정확한 상품명이 검색을 만든다."""
    dis = c["disclosure"]
    tags = list(dict.fromkeys(["#오늘의콕", "#콕픽"] + list(s.get("hashtags", []))))[:8]
    win = s.get("winner", 0)
    win = win if isinstance(win, int) and 0 <= win < len(items) else 0

    lines = [f"📦 {s.get('title', '')}", ""]
    for i, name in enumerate(items):
        mark = f" {v['emoji']}" if i == win else ""
        url = (entries[i] or {}).get("coupang_url", "")
        lines.append(f"{NUM[i]} {name}{mark}" + (f"\n   🛒 {url}" if url else ""))
    lines += ["", f"오늘의 콕: {items[win]}"]
    if post:
        lines.append(f"📄 더 자세한 비교는 픽담: {post['link']}")
    return "\n".join(lines + [
        "",
        " ".join(tags),
        "",
        dis["coupang"],
        dis["ai"],
        f"({total:.0f}초 · 트렌드 {c.get('_trends_updated', '-')} 기준)",
    ])

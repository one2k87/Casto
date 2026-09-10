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
import evidence
import learn
from common import llm_json

VOICE_MAX = 42        # 한 씬 내레이션 상한(자) — 8자/초 × 약 5초
N_ITEMS = 3          # 4개는 조회수가 떨어진다(9.2천 vs 3개 46만~473만, 2026-09-10 실측)
NUM = ["①", "②", "③"]


def build_script(items, trends, c, post=None, retries=2):
    """LLM은 **유행의 원인·결과·용도**만 쓴다. 상품명·구조·판정어는 코드가 정한다.

    처음엔 상품 이름만 주고 인과를 쓰게 했다. 그러니 "자취 가구 급증" 같은
    아무 데나 붙는 문장이 나왔다 — **이유가 뜬구름인 건 입력 탓이었다.**
    이제 세 가지를 준다.

      ① 우리가 모은 근거 (수요 급등 시점·배수, 확산 속도, 언급량, 발굴 맥락)
      ② 같은 주에 함께 뜬 다른 품목 — 공통 원인의 실마리
      ③ 구글 검색 그라운딩 — 최근 사건은 학습 데이터에 없다

    그리고 나온 인과가 동어반복이면 되돌려 보낸다(evidence.too_vague).
    """
    tr = json.dumps({k: trends.get(k) for k in ("hooks", "avoid")}, ensure_ascii=False)
    learned = learn.load_hints()
    lesson = ("\n[이 채널에서 검증된 패턴 — 성과 데이터 기반]\n"
              + "\n".join("- " + h for h in learned) + "\n") if learned else ""

    snaps = evidence.snapshots()
    briefs = [evidence.brief(n, snaps, live=True) for n in items]
    facts = "\n\n".join(
        f"{NUM[i]} {n}\n" + "\n".join("   · " + l for l in b["lines"])
        for i, (n, b) in enumerate(zip(items, briefs)))
    co = evidence.co_risers(items, snaps)
    co_line = ("\n[같은 주에 함께 뜬 다른 품목 — 공통 원인의 실마리가 될 수 있다]\n"
               + "\n".join(f"   · {x['name']} (영상 {x['videos']}개)" for x in co) + "\n") if co else ""
    src = f"\n[참고 글]\n{post['text'][:1200]}\n" if post else ""

    base = f"""{lesson}당신은 유튜브 쇼츠 채널 「콕픽」의 작가입니다. 니치: {c['niche']}.
채널의 존재 이유는 **"요즘 갑자기 많이 보이는 물건 3개를 몰아서 보여주고, 그게 왜 유행인지 알게 하는 것"**입니다.
[이번 주 트렌드 지침] {tr}{src}
[이번 편에 다룰 상품 — 이 셋을 그대로 씁니다. 다른 상품을 고르지 마세요]
{chr(10).join(f"{NUM[i]} {n}" for i, n in enumerate(items))}

[우리가 실제로 관측한 것 — 숫자는 여기 있는 것만 씁니다]
{facts}
{co_line}
각 상품이 **왜 지금 유행인지**를 원인→결과로 설명하세요. 아래 JSON만 출력합니다.

{{"items": [
  {{"cause": "유행의 계기 한 줄(화면 자막, 24자 이내). 바깥에서 온 구체적 사건이어야 함",
    "cause_detail": "그 계기를 한 문장 더(내레이션용, **20자 이내**)",
    "cause_scene": "계기 장면을 영어로 묘사(그림 지시문). 상품 자체는 절대 묘사 금지 — 상황·사람·다른 유행·계절·매대만",
    "effect": "그래서 생긴 결과 한 줄(화면 자막, 24자 이내)",
    "effect_detail": "결과를 한 문장 더(내레이션용, **20자 이내**). 관측한 숫자가 있으면 여기 넣을 것",
    "effect_scene": "결과 장면을 영어로 묘사(그림 지시문). 역시 상품 자체 묘사 금지",
    "use": "어떻게 쓰는 물건인지 한 줄(14자 이내)",
    "confidence": "high" | "low"}},
  ... 정확히 {len(items)}개, 위 번호 순서대로
 ],
 "winner": 0,
 "verdict": "buy" | "cond" | "later",
 "verdict_reason": "왜 이걸 골랐는지 한 줄(15자 이내)",
 "condition": "조건콕일 때만 '자취생이면'처럼 조건(8자 이내), 아니면 빈 문자열",
 "title": "쇼츠 제목(35자 이내)",
 "hashtags": ["#태그", ... 6개]}}

규칙
- **cause는 바깥에서 온 계기여야 한다.** "인기가 많아서/편리해서/가성비가 좋아서"는 아무것도
  설명하지 못하는 동어반복이라 되돌려 보냅니다. 다른 유행·방송·계절·물가·해외 유행·제도 변화처럼
  **이 물건 밖에서 벌어진 일**을 짚으세요.
  좋은 예: 두쫀쿠가 8월부터 유행 → 피스타치오 수요가 몰림 → 그래서 이게 보인다.
- **시점·숫자·고유명사 중 최소 하나**를 cause에 넣으세요. 없으면 되돌려 보냅니다.
- **숫자는 위 관측 목록에 있는 것만** 씁니다. 없으면 숫자를 쓰지 마세요(지어내면 오정보입니다).
- 「사람들이 실제로 쓴 말」에 **반복해서 나온 말**이 있으면 거기서 계기를 찾으세요.
  여러 사람이 각자 같은 것을 말하고 있다면 그게 원인입니다. 특히 이 물건 **바깥의 것**
  (다른 음식·방송·행사·계절)이 반복되면 그것이 계기일 가능성이 높습니다.
  댓글의 "OO 보고 왔어요" 같은 문장은 **유입 경로를 그대로 알려주는** 단서입니다.
- 관측에 "식는 중"이라고 적혀 있으면 '지금 뜬다'고 쓰지 말고, 그 상품을 winner로 고르지 마세요.
- 근거를 못 찾았으면 confidence를 "low"로 두세요. 그럴듯하게 지어내는 것보다 낫습니다.
- **cause_scene / effect_scene에 상품 이름을 쓰지 마세요.** 상품은 실제 사진으로 나갑니다.
  그림은 '왜'를 설명하는 상황만 그립니다. (상품명이 섞이면 코드가 그 컷을 버립니다)
- winner는 0-based 인덱스. **셋 중 하나만** 도장을 받습니다.
- 제목 규칙(2026-09-10 실측): 숫자 + 후회/발견 프레임 + 사회적 증거로 만든다.
  ✅ "어쩐지 자꾸 보이더라, 요즘 난리난 주방템 3가지"
  ❌ 브랜드명 나열 — 조회수가 자릿수로 떨어진다.
- **부정어 금지** — '별로다/사지 마라' 대신 '아직'의 뉘앙스.
- 겪지 않은 경험담·과장 금지. 판정어("오늘의 콕" 등)는 코드가 넣으니 쓰지 말 것."""

    prompt, s = base, None
    for attempt in range(retries + 1):
        s = llm_json(prompt, search=True)
        bad = []
        for i, row in enumerate((s.get("items") or [])[:len(items)]):
            why = evidence.too_vague(row.get("cause", ""))
            if why:
                bad.append(f"{NUM[i]} {items[i]}: 「{row.get('cause','')}」 — {why}")
        if not bad or attempt == retries:
            if bad:
                print("[roundup] ⚠ 인과가 여전히 뜬구름이다(그대로 진행):")
                for b in bad:
                    print("   -", b)
            return s
        print(f"[roundup] 인과 반려 {attempt+1}/{retries} — 다시 요청한다:")
        for b in bad:
            print("   -", b)
        prompt = base + ("\n\n[이전 답변 반려] 아래 cause는 유행의 이유를 설명하지 못합니다. "
                         "이 물건 **바깥에서** 벌어진 구체적 사건으로 다시 쓰세요.\n"
                         + "\n".join("- " + b for b in bad))
    return s


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
        scenes.append({"kind": "item", "idx": i, "name": name, "use": use,
                       "caption": f"{NUM[i]} {name}",
                       "voice": f"{name}." + (f" {use}." if use else "")})
        for kind in ("cause", "effect"):
            line = (r.get(kind) or "").strip()
            if not line:
                continue
            # 화면 자막은 짧게(한눈에), 내레이션은 한 문장 더 — 자세함은 귀로 들어간다.
            # 자막까지 길게 하면 3초 안에 못 읽고 이탈한다.
            # 자세함에는 값이 있다 — **길이**다. detail을 그대로 읽혔더니 88초가 나왔다
            # (목표 30초, 2026-09-10 실측). 한국어 TTS는 대략 8자/초라
            # 한 씬 내레이션이 40자를 넘으면 5초를 먹는다. 그래서 상한을 둔다.
            detail = (r.get(f"{kind}_detail") or "").strip()
            voice = f"{line}. {detail}" if detail else line
            if len(voice) > VOICE_MAX:
                voice = line                      # 넘치면 자막 줄만 읽는다
            scenes.append({"kind": "comic", "idx": i, "phase": kind,
                           "badge": "왜?" if kind == "cause" else "그래서",
                           "caption": line, "voice": voice,
                           "low": (r.get("confidence") == "low")})

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

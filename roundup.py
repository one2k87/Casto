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
import io
import json

import catalog
import evidence
import learn
from common import llm_json

# 2026-09-16 실측으로 전면 재단했다. Studio 기준 시청률 17.6% / 19.2%였고
# 업계는 50% 미만을 **구조적 결함**으로 본다. 원인의 대부분은 길이 하나였다:
#     13초 ÷ 74초 = 17.6%   →   13초 ÷ 24초 = 54%
# 절대 시청시간을 1초도 못 늘려도 길이만 줄이면 시청률이 3배가 된다.
# 벤치마크는 15~30초에서 80%가 나오고 45초를 넘으면 급락한다고 말한다.
VOICE_MAX = 24        # 한 씬 내레이션 상한(자) — 8자/초 × 약 3초
VERDICT_MAX = 36      # 판정 씬만 예외. 이 편의 결승점이라 이유 한 줄을 지킨다
N_ITEMS = 3          # 4개는 조회수가 떨어진다(9.2천 vs 3개 46만~473만, 2026-09-10 실측)
NUM = ["①", "②", "③"]
CPS = 8              # 한국어 TTS 체감 속도(자/초) — 길이 검산의 기준
SCENE_PAD = 0.4      # 씬 경계 여백(초)
# 유튜브 규격상 쇼츠 상한은 60초지만, 그건 **발행 가능한 한계**이지 볼 만한 길이가 아니다.
# 우리 하드 상한은 30초다 — 이 선을 넘으면 시청률이 구조적으로 무너진다.
SHORTS_MAX_SEC = 30  # 검산의 하드 상한(초)
TARGET_SEC = 24      # 겨냥하는 길이


def fit_voice(base, extra, cap: int | None = None):
    """상한에 들어갈 때만 덧붙인다 — 자세함이 길이가 되는 것을 막는 단일 관문.

    2026-09-10에 detail을 그대로 읽혀 88초가 나갔다. 그때 고친 건 comic 씬 하나였고
    item·verdict 씬은 여전히 무제한이었다(2026-09-11 러너 실측). 상한은 한 곳에서 건다.
    """
    base = (base or "").strip()
    extra = (extra or "").strip()
    if not extra:
        return base
    joined = f"{base} {extra}".strip()
    return joined if len(joined) <= (cap or VOICE_MAX) else base


# 제목에서 **우리 사정**을 말하는 표현들. 2026-09-16 실측:
# 이 표현으로 시작한 우리 제목 3편의 편당 조회수가 62.5회였고, 같은 니치에서
# 이긴 제목들은 전부 시청자의 문제·결과·가격을 말했다(편당 143,400회).
BANNED_TITLE = ("요즘 난리난", "요즘 유행", "다시 유행한다는", "자꾸 보이더라",
                "어쩐지", "요즘 이거", "난리난")


def clean_title(title: str, items: list[str], win: int = 0,
                recent: list[str] | None = None, use: str = "") -> str:
    """제목 규칙 3가지를 **코드로** 건다. 프롬프트만으로는 계속 새어 나온다.

    ① 우리 사정("요즘 유행")을 지운다  ② 최근 편과 같은 머리로 시작하지 않는다
    ③ 둘 다 걸리면 승자 상품 + 쓸모로 다시 만든다.

    프롬프트에도 같은 규칙이 있지만, 그쪽은 **부탁**이고 여기는 **관문**이다.
    3편 중 2편이 같은 템플릿으로 나간 뒤에 배운 것이다.
    """
    t = (title or "").strip()
    for bad in BANNED_TITLE:
        t = t.replace(bad, "").strip(" ,·-")
    t = " ".join(t.split())
    head = t[:10]
    dup = any(head and (r or "")[:10] == head for r in (recent or []))
    if len(t) < 8 or dup:
        name = items[win] if 0 <= win < len(items) else (items[0] if items else "")
        u = (use or "").strip().rstrip(".")
        t = f"{u}, {name}" if u else name
    return t[:80]


def est_seconds(scenes):
    """렌더 전에 길이를 추정한다 — 88초짜리가 또 나가기 전에 테스트가 잡도록."""
    chars = sum(len(s.get("voice") or "") for s in scenes)
    return chars / CPS + len(scenes) * SCENE_PAD


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

{{"hook": "**첫 3초 자막**(12자 이내). 시청자가 이 영상에서 얻는 **결과**를 먼저 말한다.
         채널 사정('이번 주 유행')이 아니라 시청자의 문제·결과·가격이어야 한다.
         ✅ '라면 안 넘치게' '3,900원으로 해결' '칼 없이 사과 껍질'
         ❌ '이번 주 유행템 3개' '갑자기 많이 보이는 것'",
 "hook_voice": "훅 내레이션 1문장(16자 이내, 구어체)",
 "items": [
  {{"cause": "유행의 계기 한 줄(화면 자막, 16자 이내). 바깥에서 온 구체적 사건이어야 함",
    "cause_detail": "그 계기를 한 문장 더(내레이션용, **12자 이내**)",
    "cause_scene": "계기 장면을 영어로 묘사(그림 지시문). 상품 자체는 절대 묘사 금지 — 상황·사람·다른 유행·계절·매대만",
    "effect": "그래서 생긴 결과 한 줄(화면 자막, 16자 이내)",
    "effect_detail": "결과를 한 문장 더(내레이션용, **12자 이내**). 관측한 숫자가 있으면 여기 넣을 것",
    "effect_scene": "결과 장면을 영어로 묘사(그림 지시문). 역시 상품 자체 묘사 금지",
    "use": "어떻게 쓰는 물건인지 한 줄(10자 이내)",
    "confidence": "high" | "low"}},
  ... 정확히 {len(items)}개, 위 번호 순서대로
 ],
 "winner": 0,
 "verdict": "buy" | "cond" | "later",
 "verdict_reason": "왜 이걸 골랐는지 한 줄(12자 이내)",
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
- **제목 규칙 3가지**(2026-09-16 실측 교체). 같은 니치에서 이긴 제목을 그대로 뜯어본 결과다.
  ① 상품이 해결하는 **문제나 결과**를 먼저 쓴다  ② **숫자나 가격**을 하나 넣는다
  ③ "요즘 유행/난리난/자꾸 보이더라"는 **쓰지 않는다** — 그건 우리 사정이지 시청자가 얻는 게 아니다.
  ✅ "좁은 주방이 2배 넓어지는 틈새 선반"     (편당 143,400회)
  ✅ "9천원대로 이게 된다고? 넘침 걱정 없는 냄비뚜껑"
  ✅ "라면 넘치는 거 이제 끝입니다"
  ❌ "요즘 이거 다시 유행한다는 주방템 3가지"  (우리가 쓴 제목 — 62.5회)
  ❌ 브랜드명 나열 — 조회수가 자릿수로 떨어진다.
- **모든 문장을 짧게.** 이 편은 24초에 끝난다. 한 씬 내레이션이 24자를 넘으면 코드가 잘라낸다.
- **부정어 금지** — '별로다/사지 마라' 대신 '아직'의 뉘앙스.
- **구어체로 쓰세요.** `~습니다/~됩니다/~입니다` 금지. 말하듯이 짧게 끊습니다.
  문어체는 TTS가 읽을 때 가장 크게 티가 나는 지점입니다.
  ❌ "수요가 급증하였습니다"  ✅ "갑자기 다들 찾아요"
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


def build_scenes(s, items, c, proofs=None):
    """대본 + 2판 고정 규격 → 씬 리스트.

    씬 순서가 곧 포맷이다. 훅에서 물건을 먼저 보여주고(추상적 '왜 유행'은 1천대에서 죽는다),
    붙잡은 다음에 인과를 푼다.
    """
    v = c["verdicts"][s.get("verdict", "buy") if s.get("verdict") in c["verdicts"] else "buy"]
    rows = s.get("items", [])
    n = len(items)

    # ── 씬 구성 (2026-09-16 재단: 13씬 73초 → 7씬 24초) ─────────────────
    # 잘라낸 것은 **상품마다 붙던 인과 2컷**이다. 3개 상품 × (원인+결과) = 6씬 27초였다.
    # 인과는 이 채널의 정체성이라 없앨 수 없지만, 6번 반복할 필요도 없다.
    # **승자 하나에만** 남긴다 — 어차피 도장을 받는 건 하나고, 시청자가 끝까지 남는
    # 이유도 그것이다. 나머지 둘의 인과는 설명란으로 내린다(§build_caption).
    hook_cap = (s.get("hook") or "").strip()
    hook_voice = (s.get("hook_voice") or "").strip()
    scenes = [
        # 0초는 **결과**다. 채널 사정("이번 주 유행")이 아니라 시청자가 얻는 것.
        # 이탈의 50~60%가 첫 3초에 일어난다 — 여기서 채널 소개를 하면 그대로 넘어간다.
        {"kind": "hook", "idx": (s.get("winner") if isinstance(s.get("winner"), int)
                                 and 0 <= s.get("winner") < n else 0),
         "caption": hook_cap or f"이번 주 쓸 만한 것 {n}",
         "voice": (hook_voice or hook_cap or f"쓸 만한 것 {n}개.")[:VOICE_MAX]},
    ]
    # **역순으로 공개한다: ③ → ② → ①.**
    # `Best3` 관례가 역순인 데는 이유가 있다 — 1번이 마지막이면 **1번을 보려고 남는다.**
    # ①②③ 순이면 뒤로 갈수록 볼 이유가 줄어든다(2026-09-11 전략 3판 4절).
    # 번호는 상품에 고정이고 **등장 순서만** 뒤집는다.
    for i in reversed(range(n)):
        name = items[i]
        r = rows[i] if i < len(rows) else {}
        use = (r.get("use") or "").strip()
        scenes.append({"kind": "item", "idx": i, "name": name, "use": use,
                       "caption": f"{NUM[i]} {name}",
                       "voice": fit_voice(f"{name}.", f"{use}." if use else "")})

    # 인과는 승자 한 번만. 배경은 증거 그래프가 있으면 그것을 쓴다.
    win0 = s.get("winner", 0)
    win0 = win0 if isinstance(win0, int) and 0 <= win0 < n else 0
    rw = rows[win0] if win0 < len(rows) else {}
    cause = (rw.get("cause") or "").strip()
    if cause:
        scenes.append({"kind": "comic", "idx": win0, "phase": "cause", "badge": "왜?",
                       "caption": cause,
                       "voice": fit_voice(f"{cause}.", (rw.get("cause_detail") or "").strip()),
                       "proof": ((proofs or {}).get(win0) or {}).get("kind"),
                       "low": (rw.get("confidence") == "low")})

    win = s.get("winner", 0)
    win = win if isinstance(win, int) and 0 <= win < n else 0
    cond = (s.get("condition") or "").strip()
    reason = (s.get("verdict_reason") or "").strip()
    if reason and reason[-1] not in ".!?…":
        reason += "."
    cap = (f"{cond} {v['card']}".strip() if v["key"] == "조건콕" else v["card"])
    voice = (f"{cond} {v['voice']}" if v["key"] == "조건콕" else v["voice"])
    # 판정 씬도 상한을 넘길 수 있다 — 이유가 길면 이유를 버리고 **CTA는 남긴다**.
    # 설명란 유도가 쿠팡 전환의 유일한 입구라 이 문장은 길이와 맞바꾸지 않는다.
    head = (f"오늘의 콕은 {items[win]}." if v["key"] == "오늘의 콕"
            else f"{voice} {items[win]}.")
    cta = "링크는 설명란에."
    body = fit_voice(head, reason, VERDICT_MAX)
    scenes.append({"kind": "verdict", "verdict": v, "idx": win, "name": items[win],
                   "caption": f"{cap}\n{items[win]}",
                   "voice": f"{body} {cta}"})
    # 마지막 컷 = **첫 컷과 같은 구도**. 쇼츠는 끝나면 자동으로 다시 시작하는데,
    # 이음매가 안 보이면 그대로 한 번 더 본다. 재생률 10%만 붙어도 배포가 붙는다.
    # 예고(teaser) 씬은 뺐다 — 3초를 먹으면서 루프를 끊었다.
    t = next_teaser()
    if t:
        scenes.append({"kind": "loop", "idx": win, "name": items[win],
                       "caption": f"다음 편\n{t['product']}",
                       "voice": f"다음 편은 {t['product']}."[:VOICE_MAX]})
    return scenes, v, win


def josa(word: str, pair: str = "은/는") -> str:
    """받침에 맞는 조사. "얼음보관통는"처럼 읽히면 그 순간 기계가 읽는 티가 난다.

    TTS는 틀린 조사를 그대로 읽는다 — AI티가 나는 가장 싼 실수다.
    """
    with_batchim, without = pair.split("/")
    w = (word or "").strip()
    if not w:
        return without
    ch = w[-1]
    if not ("가" <= ch <= "힣"):
        return without                                       # 숫자·영문은 보수적으로
    has = (ord(ch) - 0xAC00) % 28 != 0
    if pair == "으로/로" and (ord(ch) - 0xAC00) % 28 == 8:   # ㄹ 받침은 '로'
        return without
    return with_batchim if has else without


def next_teaser(path: str = "data/next_plan.json") -> dict | None:
    """다음 편 예고 — **오늘 편이 끝나는 순간에 다음 편을 심는다.**

    구독은 "다음 편이 이번 편의 결과에 달려 있을 때" 생긴다(전략 5-1).
    다음에 무엇을 다룰지는 이미 next_plan.json에 정해져 있으므로,
    사람이 쓸 것도 없이 마지막 1.5초에 붙일 수 있다.

    ⚠️ 다음 편 상품을 **여기서 판정하지 않는다.** "OO는 콕일까?"까지만 말한다 —
    미리 답을 주면 다음 편을 볼 이유가 사라진다.
    """
    try:
        with io.open(path, encoding="utf-8") as f:
            items = json.load(f).get("items") or []
    except Exception:                                        # noqa: BLE001
        return None
    import datetime as dt
    today = dt.date.today().isoformat()
    for it in items:
        if it.get("date", "") > today and it.get("product"):
            return {"label": it.get("label", ""), "product": it["product"]}
    return None


def build_caption(s, v, items, entries, c, total, post=None):
    """설명란 — 상품 3개 전부의 링크를 넣는다. 정확한 상품명이 검색을 만든다."""
    dis = c["disclosure"]
    tags = list(dict.fromkeys(["#오늘의콕", "#콕픽"] + list(s.get("hashtags", []))))[:8]
    win = s.get("winner", 0)
    win = win if isinstance(win, int) and 0 <= win < len(items) else 0

    lines = [f"📦 {s.get('title', '')}", ""]
    rows = s.get("items", [])
    for i, name in enumerate(items):
        mark = f" {v['emoji']}" if i == win else ""
        url = (entries[i] or {}).get("coupang_url", "")
        lines.append(f"{NUM[i]} {name}{mark}" + (f"\n   🛒 {url}" if url else ""))
        # 화면에서는 승자 하나만 인과를 보여준다(24초 재단). 나머지 둘의 인과는
        # 여기로 내린다 — 버리는 게 아니라 **검색되는 자리로 옮기는** 것이다.
        # 상품명이 설명란에 두 번 이상 나오는 효과도 같이 생긴다(키워드 밀도).
        r = rows[i] if i < len(rows) else {}
        why = (r.get("cause") or "").strip()
        if why:
            lines.append(f"   왜 갑자기 보이나 — {why}")
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

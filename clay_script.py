"""「콕이네 집」 대본 생성기 — 포맷 3판(docs/콕픽_포맷_3판_콕이네집_2026-10-13.md) 8컷을 JSON으로 만든다.

흐름: 상품 사실(이름·카테고리·가격·링크·우리 데이터 근거) + 상황(라이브러리) → LLM → `check()`(정직 검사)
→ 통과 못 하면 `fallback()`(템플릿 대사). 폴백 사실은 대본에 `fallback=True`로 남겨 발행 로그가 안다.

정직 규칙(§4)은 여기서 **코드로** 건다. 프롬프트에 "하지 마"라고 적는 것만으로는 안 지켜진다(픽담 integrity 교훈).
  · 금지어(체험 주장·과장·후기 인용)가 대사에 있으면 탈락
  · 가격을 모르는데 대사에 원화 숫자가 있으면 탈락
  · 판정 근거(reason)에 제공한 evidence에 없는 숫자가 있으면 탈락
  · 컷이 8개가 아니거나 대사 줄이 12자를 크게 넘기면 탈락
이름은 자리표시자 {wife} {husband} {guide} — 렌더 때 `casto.json` cast.names 로 치환한다(미정이면 그대로 두지 않고
'아내·남편·콕픽'으로 치환해 영상엔 중괄호가 안 나간다).
"""
from __future__ import annotations

import json
import random
import re

ROLES = ("wife", "husband", "guide")
BANNED = ("써 보니", "써보니", "직접 써", "써봤", "써 봤", "최고", "인생템", "100%", "무조건", "효과 보장",
          "평점", "리뷰가", "후기가", "다들 극찬", "대박")
MAX_LINE = 18          # 자막 두 줄 안. 구어체는 12자에 안 들어간다 — 18자까지(사용자 10/14 피드백)
MAX_LINE_WIFE = 24     # 빠른 아내는 2~3마디를 잇는다(10/16 속도 대비) — 자막은 두 줄로 접는다(render_clay.wrap_line)
STAMPS = ("콕", "글쎄", "패스")

# 상황 라이브러리(포맷 3판 §5). 상품은 여기 '끼운다'.
SITUATIONS = [
    {"id": 1, "scene": "아침 계란 요리 중 노른자 터짐", "fits": ["계란", "흰자", "달걀"]},
    {"id": 2, "scene": "야식 라면, 냄비 넘침", "fits": ["냄비", "라면", "조리"]},
    {"id": 3, "scene": "설거지 산, 수세미 전쟁", "fits": ["수세미", "세척", "식기세척", "설거지"]},
    {"id": 4, "scene": "손님 오기 30분 전 청소", "fits": ["청소", "먼지", "걸레"]},
    {"id": 5, "scene": "장마철 빨래 안 마름", "fits": ["건조", "제습", "빨래", "세탁"]},
    {"id": 6, "scene": "택배 상자 뜯다 손 베임", "fits": ["커터", "수납", "박스"]},
    {"id": 7, "scene": "냉장고 정리, 유통기한 지난 것 발견", "fits": ["용기", "밀폐", "보관", "트레이"]},
    {"id": 8, "scene": "주말 늦잠 브런치", "fits": ["토스터", "커피", "팬"]},
    {"id": 9, "scene": "쌀통에 벌레", "fits": ["쌀통", "라이스"]},
    {"id": 10, "scene": "가위가 안 들어 포장 못 뜯음", "fits": ["가위", "칼"]},
    {"id": 11, "scene": "문 닫히다 손 끼일 뻔", "fits": ["끼임", "안전", "가드"]},
    {"id": 12, "scene": "반찬통 뚜껑 짝 못 찾음", "fits": ["반찬통", "뚜껑"]},
]

CUT_PLAN = [  # (컷, 담당, 역할 설명) — 포맷 3판 §2
    (1, "wife", "일상 속 사고. 상품 때문이 아니라 일상 때문에. 훅 한 줄. 빠르게 2~3마디 이어 붙임"),
    (2, "husband", "아내의 엉뚱한 시도에 한 박자 늦은 건조한 리액션. 2~4어절, 줄임표로 뜸"),
    (3, "wife", "남편이 밀어 준 택배/이미 사 둔 상품을 발견. '뭐야 이거, 언제 샀어, 왜 말 안 했어'처럼 숨 없이"),
    (4, "wife", "점토 상품을 써 보는 장면. 결과가 눈에 보임"),
    (5, "husband", "느린 한 방(펀치라인). 아내를 놀리는 말, 2~4어절, 설명 금지"),
    (6, "guide", "실물 카드 소개 + 판정 도장. 상품명(+가격) 그리고 '판정은—'"),
    (7, "wife", "서랍 꼬리: '저번에 산 그거…' 서랍에서 안 쓴 템 발굴"),
    (8, "husband", "루프 컷. 컷 1과 같은 장소로 돌아오며 느린 한마디(또는 무대사)"),
]


def pick_situation(product: dict, rnd: random.Random | None = None) -> dict:
    """상품명·카테고리에 맞는 상황. 없으면 무작위 — 억지로 맞추진 않는다(상황 추가는 사람이)."""
    text = f"{product.get('display', '')} {product.get('category', '')}"
    hits = [s for s in SITUATIONS if any(k in text for k in s["fits"])]
    rnd = rnd or random.Random(product.get("display", ""))
    return rnd.choice(hits or SITUATIONS)


def decide(evidence: dict) -> tuple[str, str]:
    """판정(§3). 근거 넷 중 있는 것만 센다. 근거가 없으면 '글쎄 — 데이터 부족'."""
    pos = neg = 0
    notes = []
    s = evidence.get("search_trend")            # "up" | "flat" | "down" | None
    if s == "up":
        pos += 1; notes.append("검색 상승")
    elif s == "down":
        neg += 1; notes.append("검색 하락")
    m = evidence.get("mentions")                # 언급 수(정수) | None
    if isinstance(m, (int, float)) and m >= 100:
        pos += 1; notes.append(f"언급 {int(m)}건")
    b = evidence.get("blog_verdict")            # "positive" | "negative" | None
    if b == "positive":
        pos += 1; notes.append("비교글 긍정")
    elif b == "negative":
        neg += 1; notes.append("비교글은 다른 제품")
    if evidence.get("price_band") == "고가" and pos < 2:
        neg += 1; notes.append("가격 부담")
    if neg >= 1 and pos < 2:
        return "패스", " · ".join(notes) or "근거 부족"
    if pos >= 2:
        return "콕", " · ".join(notes)
    return "글쎄", (" · ".join(notes) + " · " if notes else "") + "데이터 부족"


BIBLE = "docs/콕이네집_바이블.md"


def load_bible(path: str = BIBLE) -> str | None:
    """바이블의 <!-- prompt:start --> ~ <!-- prompt:end --> 구간. 사용자가 파일을 고치면 다음 편부터 반영된다."""
    try:
        with open(path, encoding="utf-8") as f:
            t = f.read()
        a, b = t.index("\n<!-- prompt:start -->"), t.index("\n<!-- prompt:end -->")   # 줄 머리의 표식만
        return t[a + len("\n<!-- prompt:start -->"):b].strip()
    except (OSError, ValueError):
        return None


_BUILTIN_GUIDE = """[말투 바이블 — 진짜 부부처럼]
- 반말. 서로를 "자기/여보"보다는 이름이나 "야"로 부른다. 존댓말·안내문 말투 금지.
- 모든 대사는 **반응**이거나 **태도**다. 상황을 설명하는 대사("노른자가 터졌네", "그게 그 용도야")는 쓰지 않는다 —
  화면이 이미 보여 준다. 설명이 필요하면 자막 카드가 한다.
- 웃음은 남편의 **건조한 한 방**에서 난다. 핀잔·눙침·한 박자 늦은 지적. 절대 친절하게 설명하지 않는다.
- 아내는 감탄·억울함·우기기. 말끝이 짧고 빠르다("아 또!", "이거 왜 돼?", "내가 산 거 아니야").
- 컷 5(남편의 한 방)가 이 편의 펀치라인이다. 상품 칭찬이 아니라 **아내를 놀리는 말**이어야 한다.
- 컷 7·8은 러닝개그: 아내가 "저번에 산 그거"를 찾고, 남편은 "서랍 열지 마"류로 막는다.
- 줄임표·감탄사 OK. 이모지·영어 금지. 한 줄 18자 이내.

[좋은 예 — 계란 흰자 분리기]
1 아내: 아 또 터졌어… 세 번째야
2 남편: 계란이 너 싫어하나 봐
3 아내: 뭐야 이거, 언제 샀어?
4 아내: 어? 왜 돼?
5 남편: 그거 네가 산 거야. 지난달에.
7 아내: 지난달에 산 게 또 있다고?
8 남편: 서랍 열지 마

[나쁜 예 — 쓰지 말 것]
"노른자 터졌잖아!"(설명) / "그러게, 조심 좀."(훈계, 재미 없음) / "오, 신기하다!"(감상 없음) / "그게 그 용도야."(로봇)
"""
STYLE_GUIDE = load_bible() or _BUILTIN_GUIDE


def _prompt(product: dict, situation: dict, evidence: dict, stamp: str, reason: str, narrative: str) -> str:
    price = product.get("price")
    facts = product.get("facts") or []
    return f"""당신은 20초짜리 클레이 시트콤 「콕이네 집」의 코미디 작가다. 시트콤이다 — 광고 대본이 아니다.
등장: {{wife}}(아내, 빠른 토끼 — 유행템 다 사고 싶음, 행동이 먼저, 말이 빠르고 많음, 감탄·억울함·우기기),
{{husband}}(남편, 아주 느린 나무늘보 — 느긋·현실파, 말이 적고 느림, 뜸 들인 건조한 한 방), {{guide}}(콕픽 안내 캐릭터,
이야기 밖에서 들어와 상품 카드와 판정 도장. 또박또박).
**이 편의 재미는 둘의 속도 대비다.** 아내 줄은 2~3마디를 쉼표로 이어 붙여 급하게, 남편 줄은 2~4어절에 줄임표로 느리게.

{STYLE_GUIDE}

상품: {product.get('display')} (카테고리: {product.get('category', '')})
가격: {price if price else '모름 — 가격을 말하지 말 것'}
상품의 확인된 기능(이것 외의 효과·수치는 말하지 말 것): {', '.join(facts) if facts else '이름에서 바로 알 수 있는 기본 용도만'}
상황(여기에 상품을 끼운다, 상품 때문에 사고가 나면 안 됨): {situation['scene']}
서사 유형: {narrative}
판정(이미 정해짐, 바꾸지 말 것): {stamp} — 근거: {reason}

8컷. 컷마다 담당·역할:
{chr(10).join(f'{n}. {who}: {desc}' for n, who, desc in CUT_PLAN)}

추가 규칙:
- "써 보니", "최고", "인생템", "100%", "무조건", "효과 보장", 리뷰·평점 인용 금지. 체험 주장 금지.
- 상품은 이미 집에 있다(남편이 밀어 주거나 아내가 사 둔 것). 찾아 나서지 않는다.
- 컷 6의 대사는 "{product.get('display')}{', ' + format(int(price), ',') + '원' if price else ''}. 판정은—" 으로 끝낸다.
- 컷 8은 컷 1과 같은 장소. 한 마디 또는 빈 문자열.
- scene 필드는 영어, 이미지 생성용: 장소·인물 배치·동작·표정. 인물은 바닥에 서서 조리대/식탁 '옆'에 있다("standing at the counter",
  절대 "on the table"). 카메라는 medium close-up(허리 위). 상품은 "{__import__('style').PRODUCT_WORD}"라고만(브랜드명 금지).
  캐릭터는 "the wife {__import__('style').SPECIES.get('wife','')}", "the husband {__import__('style').SPECIES.get('husband','')}"로 부르고,
  동물이 사람처럼 서서 앞발로 물건을 다루는 장면으로 쓴다. 아내 컷은 "mid-motion, quick, doing two things at once",
  남편 컷은 "very slow, barely moving, mid-blink, relaxed"를 꼭 넣는다 — 속도 대비가 화면에도 보여야 한다.

JSON: {{"title": "제목(생활 문제형, 20자 이내)", "hook": "컷1 큰 자막(10자 이내, 설명 말고 감정)",
"cuts": [{{"n":1,"who":"wife","line":"...","scene":"..."}}, … 8개], "drawer_item": "컷7 서랍에서 나오는 지난 템(짧게)"}}"""


def _punch_up(script: dict) -> str:
    """2차 패스 — 설명형·로봇 대사를 부부 말투로 다시 쓴다. 구조·담당·scene은 유지."""
    lines = "\n".join(f"{c.get('n')} {c.get('who')}: {c.get('line')}" for c in script.get("cuts", []))
    return f"""아래는 클레이 시트콤 「콕이네 집」 초고다. 대사만 고친다 — 컷 번호·담당·scene은 그대로.
{STYLE_GUIDE}

초고:
{lines}

고칠 기준: 상황을 설명하는 줄, 훈계하는 줄, "신기하다"처럼 감상만 있는 줄, 로봇 같은 줄은 전부 부부의 **반응**으로 바꾼다.
컷 5는 반드시 남편이 아내를 놀리는 한 방. 컷 6(guide)은 손대지 않는다. 컷 8은 "서랍" 러닝개그로 닫는다.
속도 대비: 아내(wife) 줄은 2~3마디를 쉼표로 숨 없이 잇고, 남편(husband) 줄은 2~4어절 + 줄임표로 뜸을 들인다.
남편 줄이 5어절을 넘으면 잘라서 한 생각만 남긴다.
금지어("써 보니", "최고", "인생템", "100%", "무조건", "효과 보장")와 가격·수치 추가 금지. 한 줄 18자 이내.

JSON: {{"cuts": [{{"n":1,"line":"..."}}, … 8개]}}"""


def _shorten(script: dict, errs: list[str]) -> str:
    """길이 초과 줄만 줄여 달라는 3차 패스. 뜻·말투는 유지."""
    bad = sorted({int(m.group(1)) for e in errs for m in [re.match(r"컷(\d+)", e)] if m})
    lines = "\n".join(f"{c.get('n')} {c.get('who')}: {c.get('line')}" for c in script.get("cuts", []) if int(c.get("n", 0)) in bad)
    return f"""아래 대사가 자막에 안 들어간다. 뜻과 말투(아내는 빠르고 급하게, 남편은 느리고 짧게)는 그대로 두고 **글자 수만** 줄여라.
아내(wife) 줄은 공백 빼고 {MAX_LINE_WIFE}자 이내(2~3마디 유지), 남편(husband) 줄은 {MAX_LINE}자 이내·6어절 이내, 그 외 {MAX_LINE}자 이내.
{lines}

JSON: {{"cuts": [{{"n":번호,"line":"..."}}, …]}}"""


def check(script: dict, product: dict, evidence: dict) -> list[str]:
    """정직·형식 검사. 빈 리스트면 통과. 사유를 전부 모아 돌려준다(하나 고치면 다음이 터지지 않게)."""
    errs = []
    cuts = script.get("cuts") or []
    if len(cuts) != 8:
        errs.append(f"컷 수 {len(cuts)} ≠ 8")
    for c in cuts:
        line = str(c.get("line", ""))
        if c.get("who") not in ROLES:
            errs.append(f"컷{c.get('n')} 담당 불명 {c.get('who')}")
        for b in BANNED:
            if b in line:
                errs.append(f"컷{c.get('n')} 금지어 '{b}'")
        limit = 30 if c.get("n") == 6 else MAX_LINE_WIFE if c.get("who") == "wife" else MAX_LINE   # 컷 6은 상품명+가격
        if len(line.replace(" ", "")) > limit:
            errs.append(f"컷{c.get('n')} 대사 {len(line)}자 — 너무 김")
        if c.get("who") == "husband" and len(line.split()) > 6:        # 느린 남편은 말이 적다(10/16 속도 대비)
            errs.append(f"컷{c.get('n')} 남편 대사 {len(line.split())}어절 — 6어절 초과")
        if not product.get("price") and re.search(r"\d[\d,]*\s*원", line):
            errs.append(f"컷{c.get('n')} 가격 모름인데 원화 숫자")
        if not c.get("scene"):
            errs.append(f"컷{c.get('n')} scene 없음")
    # 판정 근거의 숫자는 evidence에서 온 것만
    reason = str(script.get("reason", ""))
    allowed = {str(int(evidence["mentions"]))} if isinstance(evidence.get("mentions"), (int, float)) else set()
    for num in re.findall(r"\d+", reason):
        if num not in allowed:
            errs.append(f"판정 근거에 출처 없는 숫자 {num}")
    if script.get("stamp") not in STAMPS:
        errs.append(f"도장 불명 {script.get('stamp')}")
    return errs


def fallback(product: dict, situation: dict, stamp: str, reason: str) -> dict:
    """생성 실패 시 템플릿 대사(§6). 밋밋하지만 거짓은 없다."""
    name = product.get("display", "이것")
    price = product.get("price")
    kitchen = "the shared kitchen set from the reference image"
    cuts = [
        (1, "wife", "아 또, 또 터졌어, 세 번째야", f"{kitchen}; wife mid-accident at the counter, mid-motion, quick, doing two things at once, {situation['scene']} mood, startled"),
        (2, "husband", "…또?", f"{kitchen}; husband at the table, very slow, barely moving, mid-blink over his phone, deadpan"),
        (3, "wife", "뭐야 이거, 언제 샀어, 왜 말 안 했어", f"{kitchen}; husband slides a small parcel box across the table very slowly, {__import__('style').PRODUCT_WORD} pops out, wife mid-motion, quick, grabbing it"),
        (4, "wife", "어? 왜 돼?", f"{kitchen}; wife using {__import__('style').PRODUCT_WORD} at the counter, result visible, eyes wide"),
        (5, "husband", "그거… 네가 산 거야", f"{kitchen}; husband very slow, barely moving, small smile, one slow blink"),
        (6, "guide", f"{name}{', ' + format(int(price), ',') + '원' if price else ''}. 판정은—",
         "plain cream studio backdrop; guide character standing center holding a blank white card up, presenting"),
        (7, "wife", "지난달에 산 게 또 있다고?", f"{kitchen}; wife opening a kitchen drawer stuffed with unused gadgets, sheepish"),
        (8, "husband", "서랍… 열지 마", f"{kitchen}; same framing as cut 1, husband very slowly lifting a coffee cup, wife back at the counter mid-motion"),
    ]
    return {"title": f"{name}, 진짜 필요할까?", "hook": situation["scene"][:10],
            "cuts": [{"n": n, "who": w, "line": l, "scene": s} for n, w, l, s in cuts],
            "drawer_item": "지난주 템", "stamp": stamp, "reason": reason, "fallback": True}


def build(product: dict, evidence: dict | None = None, narrative: str = "A_사고해결",
          situation: dict | None = None, use_llm: bool = True) -> dict:
    evidence = evidence or {}
    situation = situation or pick_situation(product)
    stamp, reason = decide(evidence)
    script, rejected = None, []
    if use_llm:
        try:
            from common import llm_json
            script = llm_json(_prompt(product, situation, evidence, stamp, reason, narrative),
                              max_tokens=3000, temperature=1.0)
            script["stamp"], script["reason"] = stamp, reason
            draft = json.loads(json.dumps(script, ensure_ascii=False))
            try:   # 2차 패스: 대사만 부부 말투로 — 실패하면 초고로 간다
                fixed = llm_json(_punch_up(script), max_tokens=1500, temperature=1.0)
                by_n = {int(c["n"]): c.get("line", "") for c in fixed.get("cuts", []) if "n" in c}
                for c in script["cuts"]:
                    if int(c["n"]) != 6 and by_n.get(int(c["n"])) is not None:
                        c["line"] = by_n[int(c["n"])]
                script["punched"] = True
            except Exception as e:  # noqa: BLE001
                print(f"[clay_script] 펀치업 실패({e}) — 초고 사용")
            errs = check(script, product, evidence)
            if errs and all("너무 김" in e or "어절 초과" in e for e in errs):
                # 길이만 문제면 버리지 않고 그 줄만 줄여 달라고 한다(12호: 좋은 대본이 글자 수로 폴백됐다)
                try:
                    fixed = llm_json(_shorten(script, errs), max_tokens=800, temperature=0.7)
                    by_n = {int(c["n"]): c.get("line", "") for c in fixed.get("cuts", []) if "n" in c}
                    for c in script["cuts"]:
                        if int(c["n"]) != 6 and by_n.get(int(c["n"])):
                            c["line"] = by_n[int(c["n"])]
                    rejected.append({"stage": "shorten", "errors": errs, "fixed": by_n})
                    errs = check(script, product, evidence)
                except Exception as e:  # noqa: BLE001
                    print(f"[clay_script] 줄이기 실패({e})")
            if errs:
                print("[clay_script] ⛔ 펀치업본 탈락:", "; ".join(errs), "— 초고로 재검사")
                rejected.append({"stage": "punch_up", "errors": errs,
                                 "lines": [c.get("line") for c in script.get("cuts", [])]})
                script = draft
                errs = check(script, product, evidence)
                if errs:
                    print("[clay_script] ⛔ 초고도 탈락:", "; ".join(errs))
                    rejected.append({"stage": "draft", "errors": errs,
                                     "lines": [c.get("line") for c in script.get("cuts", [])]})
                    script = None
        except Exception as e:  # noqa: BLE001
            print(f"[clay_script] 생성 실패({e}) — 폴백")
            rejected.append({"stage": "llm", "errors": [str(e)[:300]]})
            script = None
    if script is None:
        script = fallback(product, situation, stamp, reason)
    if rejected:
        script["rejected"] = rejected          # 왜 폴백/재검사가 됐는지 대본 파일에 남긴다(11호: 사유를 알 수 없었다)
    script.update({"product": product.get("display"), "slug": product.get("slug"), "situation": situation["scene"],
                   "narrative": narrative, "price": product.get("price"), "coupang_url": product.get("coupang_url")})
    return script


def substitute_names(script: dict, names: dict | None) -> dict:
    """{wife} 등 자리표시자 치환. 미정이면 '아내·남편·콕픽' — 영상에 중괄호가 나가지 않게."""
    names = {"wife": "아내", "husband": "남편", "guide": "콕픽", **(names or {})}
    def sub(s: str) -> str:
        for k, v in names.items():
            s = s.replace("{" + k + "}", v)
        return s
    out = json.loads(json.dumps(script, ensure_ascii=False))
    for c in out.get("cuts", []):
        c["line"] = sub(str(c.get("line", "")))
    out["title"] = sub(str(out.get("title", "")))
    return out

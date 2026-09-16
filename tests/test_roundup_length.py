"""영상 길이가 쇼츠 규격을 넘지 않는지 — **실제로 새나간 구멍**을 막는 테스트.

2026-09-10에 86.5초·88.1초 영상이 두 편 발행됐다(`data/publish_log.json` 실측).
쇼츠는 60초가 상한이라 그 두 편은 쇼츠로 취급되지 않는다. 원인은 전날 붙인
상세 내레이션(cause_detail/effect_detail)을 그대로 읽힌 것이었고, 09-11 아침 수정은
**comic 씬에만** 상한을 걸었다. item·verdict 씬은 여전히 무제한이었다.

그리고 `roundup.build_scenes`에는 테스트가 한 줄도 없었다 — 그래서 조용히 나갔다.
여기서 막는 것은 "LLM이 길게 쓰는 것"이 아니라 **길게 써도 길어지지 않는 것**이다.
"""
import json

import roundup


def _c():
    return json.load(open("casto.json", encoding="utf-8"))


ITEMS = ["늘어나는 밀폐용기", "레이저가이드가위", "얼음틀 얼음보관통"]


def _script(verdict="buy", long=False):
    """LLM이 상한을 무시하고 길게 써 보낸 최악의 응답."""
    pad = "아주아주 길게 늘여 쓴 설명이 끝도 없이 이어지는 문장입니다" if long else "짧게"
    return {
        "verdict": verdict,
        "winner": 0,
        "condition": pad if long else "좁은 주방이면",
        "verdict_reason": pad if long else "부피가 준다",
        "items": [{"use": pad, "cause": "미국 쇼츠에서 번졌다",
                   "cause_detail": pad, "effect": "검색이 늘었다",
                   "effect_detail": pad} for _ in ITEMS],
    }


def test_모든_씬_내레이션이_상한_안에_있다():
    """LLM이 무엇을 보내도 한 씬이 5초를 넘지 않는다."""
    scenes, _, _ = roundup.build_scenes(_script(long=True), ITEMS, _c())
    over = [s["voice"] for s in scenes
            if len(s.get("voice") or "") > roundup.VOICE_MAX + len("링크는 설명란에.") + 1]
    assert not over, f"상한 초과 씬: {over}"
    for s in scenes:
        if s["kind"] in ("item", "comic"):
            assert len(s["voice"]) <= roundup.VOICE_MAX, s["voice"]


def test_추정_길이가_쇼츠_상한을_넘지_않는다():
    """88초 사고의 직접 재현 — 최악 입력에서도 60초 밑이어야 한다."""
    for verdict in ("buy", "cond", "later"):
        scenes, _, _ = roundup.build_scenes(_script(verdict, long=True), ITEMS, _c())
        sec = roundup.est_seconds(scenes)
        assert sec < roundup.SHORTS_MAX_SEC, f"{verdict}: {sec:.1f}초"


def test_판정_씬은_길어도_CTA를_버리지_않는다():
    """설명란 유도는 쿠팡 전환의 유일한 입구 — 길이와 맞바꾸지 않는다."""
    scenes, _, _ = roundup.build_scenes(_script(long=True), ITEMS, _c())
    verdict = next(s for s in scenes if s["kind"] == "verdict")
    assert verdict["voice"].endswith("링크는 설명란에.")


def test_fit_voice는_들어갈_때만_붙인다():
    assert roundup.fit_voice("짧다.", "조금") == "짧다. 조금"
    assert roundup.fit_voice("짧다.", "가" * roundup.VOICE_MAX) == "짧다."
    assert roundup.fit_voice("짧다.", "") == "짧다."
    assert roundup.fit_voice("짧다.", None) == "짧다."


# ── 24초 재단 (2026-09-16) ────────────────────────────────────────────────
def test_씬이_일곱개를_넘지_않는다():
    """13씬 73초를 7씬 24초로 재단했다. Studio 실측 시청률 17.6%의 원인이 길이였다:
    13초 ÷ 74초 = 17.6% → 13초 ÷ 24초 = 54%. 내용을 안 고쳐도 3배가 된다."""
    scenes, _, _ = roundup.build_scenes(_script(long=True), ITEMS, _c())
    assert len(scenes) <= 7, [s["kind"] for s in scenes]


def test_인과는_승자_하나에만_붙는다():
    """상품마다 원인·결과를 달면 6씬 27초다. 도장을 받는 건 하나고
    시청자가 끝까지 남는 이유도 그것이다 — 나머지는 설명란으로 내린다."""
    scenes, _, win = roundup.build_scenes(_script(), ITEMS, _c())
    comics = [s for s in scenes if s["kind"] == "comic"]
    assert len(comics) <= 1
    if comics:
        assert comics[0]["idx"] == win


def test_첫_컷은_결과다():
    """0초는 채널 사정이 아니라 시청자가 얻는 것이다 — 이탈의 50~60%가 여기서 난다."""
    s = _script()
    s["hook"] = "라면 안 넘치게"
    s["hook_voice"] = "라면 넘치는 거, 이제 끝입니다."
    scenes, _, win = roundup.build_scenes(s, ITEMS, _c())
    assert scenes[0]["kind"] == "hook"
    assert scenes[0]["caption"] == "라면 안 넘치게"
    assert scenes[0]["idx"] == win        # 승자 사진 한 장으로 채운다


def test_마지막_컷은_루프다():
    """쇼츠는 끝나면 자동으로 다시 시작한다. 이음매가 안 보이면 한 번 더 본다."""
    scenes, _, _ = roundup.build_scenes(_script(), ITEMS, _c())
    assert scenes[-1]["kind"] in ("loop", "verdict")


def test_정상_입력이_목표_길이_안에_있다():
    """느슨한 상한(+15초)으로는 73초가 그대로 통과했다. 목표 근처로 조인다."""
    c = _c()
    scenes, _, _ = roundup.build_scenes(_script(), ITEMS, c)
    assert roundup.est_seconds(scenes) <= c["video"]["target_sec"] + 4


# ── 제목 관문 ─────────────────────────────────────────────────────────────
def test_우리_사정을_말하는_제목은_버린다():
    """2026-09-16 실측: 이 표현으로 시작한 우리 제목 3편이 편당 62.5회,
    같은 니치에서 이긴 제목(문제·결과·가격)은 편당 143,400회였다."""
    got = roundup.clean_title("요즘 이거 다시 유행한다는 주방템 3가지", ITEMS, 0, use="접으면 반")
    assert "유행" not in got and "요즘" not in got
    assert ITEMS[0] in got


def test_좋은_제목은_건드리지_않는다():
    good = "좁은 주방이 2배 넓어지는 틈새 선반"
    assert roundup.clean_title(good, ITEMS, 0) == good


def test_최근_편과_같은_머리로_시작하지_않는다():
    """3편 중 2편이 같은 템플릿으로 나갔다 — 프롬프트만으로는 계속 새어 나온다."""
    t = "라면 넘치는 거 이제 끝입니다"
    assert roundup.clean_title(t, ITEMS, 0, recent=[t]) != t

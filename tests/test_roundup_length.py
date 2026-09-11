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


def test_정상_입력은_목표_길이_근처다():
    c = _c()
    scenes, _, _ = roundup.build_scenes(_script(), ITEMS, c)
    sec = roundup.est_seconds(scenes)
    assert sec <= c["video"]["target_sec"] + 15, f"{sec:.1f}초"


def test_판정_씬은_길어도_CTA를_버리지_않는다():
    """설명란 유도는 쿠팡 전환의 유일한 입구 — 길이와 맞바꾸지 않는다."""
    scenes, _, _ = roundup.build_scenes(_script(long=True), ITEMS, _c())
    verdict = [s for s in scenes if s["kind"] == "verdict"][0]
    assert verdict["voice"].endswith("링크는 설명란에.")


def test_fit_voice는_들어갈_때만_붙인다():
    assert roundup.fit_voice("짧다.", "조금") == "짧다. 조금"
    assert roundup.fit_voice("짧다.", "가" * roundup.VOICE_MAX) == "짧다."
    assert roundup.fit_voice("짧다.", "") == "짧다."
    assert roundup.fit_voice("짧다.", None) == "짧다."

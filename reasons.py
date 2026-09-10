"""왜 유행인가 — **사람들이 직접 쓴 말**을 모아 원인을 찾는다.

유튜브 조회수·수요 곡선은 "얼마나·언제"를 말한다. 그런데 "왜"는 숫자에 없다.
그건 사람들이 글로 써 둔다 — 블로그에 "두바이 초콜릿 만들려고 샀다", 댓글에
"그 방송 보고 왔어요", 뉴스에 "품귀로 가격 2배". 우리는 그걸 **개수만 세고 버리고
있었다**(naver_mentions는 display=1로 불러 total만 읽었다).

모으는 곳 — 전부 **이미 가진 자격증명**으로 된다:

| 출처 | 무엇이 나오나 |
|---|---|
| 네이버 뉴스 | 인과를 직접 설명(품귀·가격·방송·제도) |
| 네이버 블로그·카페 | 구매 동기가 사람 말로 |
| 유튜브 댓글 | **유입 경로** — "OO 보고 왔어요" |
| 유튜브 제목(한/영) | 유행을 부르는 이름 |

그리고 핵심은 `common_terms()`다. 모은 글 전체에서 **반복되는 낱말**을 센다.
30개 글 중 7개가 '두바이초콜릿'을 말하면 그게 원인이다 — 모델이 추측할 필요 없이
빈도가 답을 준다. LLM은 그 위에서 문장을 만들 뿐이다.
"""
import re
from collections import Counter

import trend_sources as src

# 어디에나 나오는 말 — 원인이 될 수 없다
STOP = set("""
그리고 그래서 하지만 그런데 이거 저거 요거 이것 저것 정말 진짜 완전 너무 아주 매우 조금
사용 사용법 후기 리뷰 추천 구매 구입 가격 최저가 할인 쿠폰 배송 무료배송 링크 파트너스
제품 상품 아이템 브랜드 정품 국내 해외 오늘 어제 내일 요즘 최근 지금 이번 다음 우리 저희
사람 사람들 여러분 안녕하세요 감사합니다 구독 좋아요 영상 채널 유튜브 인스타 블로그
주방 살림 생활 꿀템 필템 신박 대박 가성비 존예 쿠팡 네이버 다이소 마켓 스토어
있는 있어요 있습니다 없는 없어요 합니다 했어요 해서 하는 되는 됩니다 같아요 같은 위해
""".split())

TERM = re.compile(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9]{2,}")

# 서술어 꼬리 — 원인이 아니라 말투다. 낱말 목록으로는 다 못 막아서 규칙으로 자른다
#   ("샀어요"가 '두바이초콜릿' 바로 아래 올라와 있었다)
VERBISH = ("어요", "에요", "예요", "아요", "해요", "네요", "구요", "군요", "세요", "죠",
           "습니다", "합니다", "됩니다", "입니다", "했다", "한다", "된다", "이다",
           "했어", "하는", "되는", "하고", "해서", "더라", "드라", "거든", "니까")


def _verbish(w: str) -> bool:
    return any(w.endswith(t) for t in VERBISH)


def tokens(text: str) -> list[str]:
    return [t for t in TERM.findall(text or "")
            if t not in STOP and len(t) >= 2 and not _verbish(t)]


def _merge_substrings(rows):
    """'두바이'와 '두바이초콜릿'이 따로 잡히면 둘 다 약해 보인다 — 긴 쪽으로 합친다.

    긴 말이 짧은 말을 품고 문서 수가 비슷하면(짧은 쪽이 크게 많지 않으면)
    같은 것을 가리키는 셈이다. 긴 쪽이 더 구체적이라 원인으로도 쓸모 있다.
    """
    rows = sorted(rows, key=lambda r: -len(r[0]))
    out = []
    for w, n in rows:
        dup = next((i for i, (w2, n2) in enumerate(out)
                    if w in w2 and n <= n2 * 1.5), None)
        if dup is None:
            out.append((w, n))
    return sorted(out, key=lambda r: -r[1])


def common_terms(texts, exclude=(), top=12, min_docs=2):
    """여러 글에 **걸쳐** 반복되는 말. 한 글에서 열 번 나온 건 한 번으로 센다.

    문서 빈도로 세는 게 중요하다 — 한 블로거가 자기 글에서 같은 단어를 도배해도
    그건 유행의 근거가 아니다. 여러 사람이 각자 말해야 근거다.
    """
    drop = set()
    for e in exclude:
        drop |= set(tokens(e)) | {re.sub(r"\s+", "", e or "")}
    df = Counter()
    for t in texts:
        seen = set(tokens(t)) - drop
        df.update(seen)
    rows = [(w, n) for w, n in df.most_common(top * 4) if n >= min_docs]
    return _merge_substrings(rows)[:top]


def gather(name: str, keyword: str = "", en_keyword: str = "",
           video_ids=(), per_source: int = 8) -> dict:
    """한 상품에 대해 사람이 쓴 글을 모은다. 실패한 출처는 조용히 건너뛴다."""
    kw = keyword or name
    out = {"name": name, "quotes": [], "sources": {}, "terms": []}
    texts = []

    for kind, label in (("news", "뉴스"), ("blog", "블로그"), ("cafearticle", "카페")):
        rows = src.naver_texts(kw, kind=kind, n=per_source) or []
        out["sources"][label] = len(rows)
        for r in rows:
            body = f"{r['title']} {r['text']}".strip()
            if body:
                texts.append(body)
                out["quotes"].append({"src": label, "text": body[:180], "date": r.get("date", "")})

    seen_comments = 0
    for vid in list(video_ids)[:3]:
        cs = src.youtube_comments(vid, n=15) or []
        seen_comments += len(cs)
        for cmt in cs:
            texts.append(cmt)
            out["quotes"].append({"src": "댓글", "text": cmt[:180], "date": ""})
    out["sources"]["댓글"] = seen_comments

    out["terms"] = common_terms(texts, exclude=(name, kw, en_keyword))
    out["n_texts"] = len(texts)
    return out


def lines(g: dict, max_quotes: int = 8) -> list[str]:
    """프롬프트에 넣을 형태. **인용은 인용인 채로** 넘긴다 — 요약하면 단서가 죽는다."""
    out = []
    src_line = " · ".join(f"{k} {v}건" for k, v in (g.get("sources") or {}).items() if v)
    if src_line:
        out.append(f"수집: {src_line}")
    if g.get("terms"):
        out.append("여러 글에 **반복해서 나온 말**(문서 수): "
                   + ", ".join(f"{w}({n})" for w, n in g["terms"][:10]))
        out.append("   → 이 중 이 물건 **바깥의 것**이 유행의 계기일 가능성이 높다")
    for q in (g.get("quotes") or [])[:max_quotes]:
        d = f" {q['date']}" if q.get("date") else ""
        out.append(f"[{q['src']}{d}] {q['text']}")
    if not out:
        out.append("(사람들이 쓴 글을 못 모았다 — 이유를 지어내지 말 것)")
    return out

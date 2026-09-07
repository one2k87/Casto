"""영상 설명란의 **제휴 링크에서 실제 상품을 역추적**한다 — 후보 발굴의 핵심.

사용자 지적(2026-09-07): 제목 텍스트로는 '코팅팬' 수준까지밖에 못 간다. 쿠팡 링크를 걸려면
"정확히 어느 브랜드의 어떤 제품"이어야 하고, 그게 선행되지 않으면 나머지가 의미가 없다.

**해법: 크리에이터가 설명란에 건 제휴 링크가 곧 정답이다.**
- 링크는 상품을 **고유 ID로** 특정한다 — 제목 파싱과 달리 애매함이 없다
- **서로 다른 채널이 같은 상품에 링크했다 = 진짜 유행**이라는 합의 신호를 동시에 얻는다
- 유튜브 Data API가 description을 공식 제공하고, 이미 호출하는 `videos.list`에 필드만
  추가하면 되므로 **추가 할당량이 0**이다

⚠️ **남의 파트너스 링크는 절대 재사용하지 않는다.** 여기서 얻는 것은 *어떤 상품인가*(상품 ID)뿐이고,
실제 게시용 링크는 픽담이 자체 파트너스 링크로 만든다. 남의 추적 코드가 붙은 URL을 그대로 쓰면
수수료가 그쪽으로 가고 정책 위반이 된다.

인스타그램은 Graph API 제약으로 같은 방식이 어렵다(5-4-9⑨). 다만 유행 품목은 플랫폼 간 대체로
겹치고, 설명란 링크는 유튜브가 훨씬 풍부하므로 유튜브만으로도 목적을 달성할 수 있다.
"""
from __future__ import annotations

import re
from collections import defaultdict

URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)

# 제휴/상품 링크 패턴 → (플랫폼, 정규화 함수용 그룹)
COUPANG_PRODUCT = re.compile(r"coupang\.com/vp/products/(\d+)", re.I)
COUPANG_SHORT = re.compile(r"(?:link\.coupang\.com/a|coupa\.ng)/([A-Za-z0-9]+)", re.I)
SMARTSTORE = re.compile(r"smartstore\.naver\.com/([\w-]+)/products/(\d+)", re.I)
NAVER_SHOP = re.compile(r"shopping\.naver\.com/.*?/products/(\d+)", re.I)

NOISE_HOSTS = ("youtube.com", "youtu.be", "instagram.com", "tiktok.com", "blog.naver.com",
               "cafe.naver.com", "open.kakao", "linktr.ee", "bit.ly/subscribe")


def extract_urls(text: str) -> list[str]:
    return [u.rstrip(".,)") for u in URL.findall(text or "")]


def identify(url: str) -> dict | None:
    """상품 링크를 **플랫폼 + 고유 ID**로 정규화. 상품 링크가 아니면 None.

    단축 링크(link.coupang.com/a/XXXX)는 리다이렉트를 풀지 않아도 **코드 자체가 고유**하므로
    그대로 지문으로 쓴다. 여러 영상이 같은 단축 코드를 쓰면 같은 상품·같은 캠페인이다.
    """
    low = url.lower()
    if any(h in low for h in NOISE_HOSTS):
        return None
    m = COUPANG_PRODUCT.search(url)
    if m:
        return {"platform": "coupang", "id": m.group(1), "kind": "product", "url": url}
    m = COUPANG_SHORT.search(url)
    if m:
        return {"platform": "coupang", "id": f"short:{m.group(1)}", "kind": "short", "url": url}
    m = SMARTSTORE.search(url)
    if m:
        return {"platform": "smartstore", "id": f"{m.group(1)}/{m.group(2)}", "kind": "product", "url": url}
    m = NAVER_SHOP.search(url)
    if m:
        return {"platform": "naver", "id": m.group(1), "kind": "product", "url": url}
    return None


def label_for(text: str, url: str) -> str:
    """링크 **바로 앞의 제품명**을 집는다.

    크리에이터는 보통 `제품명 ▶ https://...` 또는
    ```
    제품명
    https://...
    ```
    형태로 쓴다. 그래서 같은 줄의 앞부분 → 없으면 직전 줄 순으로 본다.
    """
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if url not in line:
            continue
        head = line.split(url)[0]
        head = re.sub(r"[▶▷➡→\-–—:|·>\s]+$", "", head).strip()
        head = re.sub(r"^[\d]+[.)]\s*", "", head)          # "1) 제품명"
        if len(head) >= 2:
            return head[:40]
        for j in range(i - 1, max(i - 3, -1), -1):          # 직전 줄들
            prev = lines[j].strip()
            if prev and not URL.search(prev) and len(prev) >= 2:
                return re.sub(r"^[\d]+[.)]\s*", "", prev)[:40]
        break
    return ""


def links_in(video: dict) -> list[dict]:
    """영상 1편의 설명란에서 상품 링크를 뽑는다."""
    desc = video.get("description") or ""
    out = []
    for u in extract_urls(desc):
        info = identify(u)
        if not info:
            continue
        info["label"] = label_for(desc, u)
        info["video_id"] = video.get("id")
        info["channel_id"] = video.get("channel_id")
        info["title"] = video.get("title")
        info["views"] = video.get("views", 0)
        out.append(info)
    return out


def cluster(videos: list[dict], min_channels: int = 2) -> list[dict]:
    """같은 상품에 링크한 영상들을 묶는다.

    **서로 다른 채널 수가 유행의 강도**다. 한 채널이 같은 링크를 반복한 건 그 채널의 소재일 뿐이므로
    `min_channels`로 거른다. 이 합의 신호가 제목 n-gram보다 훨씬 정확하다.
    """
    groups: dict[tuple[str, str], dict] = {}
    for v in videos:
        for lk in links_in(v):
            key = (lk["platform"], lk["id"])
            g = groups.setdefault(key, {
                "platform": lk["platform"], "product_id": lk["id"], "kind": lk["kind"],
                "channels": set(), "videos": set(), "labels": [], "views": 0,
                "sample_url": lk["url"], "sample_titles": [],
            })
            g["channels"].add(lk["channel_id"] or lk["video_id"])
            g["videos"].add(lk["video_id"])
            g["views"] += lk.get("views", 0)
            if lk["label"] and lk["label"] not in g["labels"]:
                g["labels"].append(lk["label"])
            if lk["title"] and len(g["sample_titles"]) < 3:
                g["sample_titles"].append(lk["title"])
    rows = []
    for g in groups.values():
        if len(g["channels"]) < min_channels:
            continue
        g["channels"], g["videos"] = len(g["channels"]), len(g["videos"])
        g["name"] = best_label(g["labels"])
        rows.append(g)
    rows.sort(key=lambda r: (r["channels"], r["views"]), reverse=True)
    return rows


def best_label(labels: list[str]) -> str:
    """여러 크리에이터가 붙인 이름 중 **가장 흔한 표현**을 고른다.

    사람들이 실제로 부르는 이름이어야 재인이 일어나므로(5-4-10), 최빈값이 정답에 가깝다.
    동률이면 정보량이 많은(긴) 쪽을 택한다.
    """
    if not labels:
        return ""
    norm = defaultdict(list)
    for l in labels:
        norm[re.sub(r"\s+", "", l).lower()].append(l)
    best = max(norm.values(), key=lambda v: (len(v), max(len(x) for x in v)))
    return max(best, key=len)


def summary(rows: list[dict], limit: int = 20) -> str:
    """LLM에 넘길 근거 블록 — **링크로 확인된 실제 상품만** 보여준다."""
    lines = []
    for r in rows[:limit]:
        lines.append(
            f'- {r["name"] or "(이름 미상)"} | {r["platform"]}:{r["product_id"]} '
            f'| 채널 {r["channels"]}개 · 영상 {r["videos"]}개 · 합산 조회 {r["views"]:,} '
            f'| 예: {" / ".join(t[:34] for t in r["sample_titles"][:2])}')
    return "\n".join(lines)

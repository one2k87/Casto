"""상품 카탈로그 — **"정확히 어떤 물건인가"를 확정해서 보관하는 단 하나의 장소**.

사용자 요구(2026-09-08): "정확한 상품의 브랜드명이 나오면 그거 사진 정확하게 넣을 수 있어?
채널을 보는 사람에게 어떤 상품인지 모양 제대로 보여야 하고 정보를 제대로 전달해야 해."

발굴(product_links.py)이 알려주는 것은 **상품 ID와 사람들이 부르는 이름**까지다. 영상에 띄울
브랜드·모델·사진은 여기서 확정한다. 둘을 분리한 이유는 명확하다 —
**틀린 사진을 띄우는 것은 사진이 없는 것보다 나쁘다.** 그래서 카탈로그에 확정된 상품만
실사진·브랜드명을 노출하고, 확정 전에는 카테고리명 + 클레이 아트로 나간다(render_mode 참고).

사진이 들어오는 경로는 둘뿐이다.
  A) **픽담 글의 KOKPICK 블록**(자동) — 픽담이 자체 파트너스 계정으로 만든 이미지·링크.
     쿠팡 파트너스는 자사 상품 이미지를 파트너 홍보용으로 제공하므로 이 경로가 정당하다.
  B) **수동 등록**(반자동) — 쿠팡 파트너스 웹에서 링크·이미지를 받아 assets/products/에 넣고
     이 파일에 등록. `python catalog.py`가 무엇이 필요한지 요청서를 뽑아준다.

절대 하지 않는 것:
  ✗ 다른 크리에이터의 썸네일·릴스 캡처를 가져다 쓰는 것(저작권 침해)
  ✗ 남의 파트너스 링크를 게시용으로 재사용하는 것(수수료 탈취 + 정책 위반)
  ✗ 확인되지 않은 브랜드명을 추정해서 자막에 쓰는 것(오정보)
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

CATALOG_PATH = "data/catalog.json"
IMAGE_DIR = "assets/products"

# 우리가 이미지를 내려받아도 되는 출처. 픽담(우리 사이트)과 쿠팡 상품 이미지 CDN만 허용한다.
ALLOWED_IMAGE_HOSTS = ("pickdam.com", "coupangcdn.com", "ads-partners.coupang.com")

# 남의 제휴 코드가 붙은 링크의 지문. 게시용 링크로 들어오면 거부한다.
FOREIGN_AFFILIATE = re.compile(r"(?:link\.coupang\.com/a|coupa\.ng)/", re.I)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "").strip().lower()
    s = re.sub(r"[^0-9a-z가-힣]+", "-", s).strip("-")
    return s[:60] or "unknown"


def _key(name: str) -> str:
    """이름 비교용 정규화 — 공백·기호·대소문자를 무시한다."""
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", name or "").lower())


# ------------------------------------------------------------------ 저장소
def load(path: str = CATALOG_PATH) -> dict:
    if not os.path.exists(path):
        return {"updated": "", "products": {}}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("products", {})
    return data


def save(cat: dict, path: str = CATALOG_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
    return path


# ------------------------------------------------------------------ 조회
def find(cat: dict, name: str = "", product_id: str = "") -> dict | None:
    """상품 ID가 있으면 그것이 정답이다(고유). 없으면 이름으로 찾는다.

    이름 매칭은 완전일치 → 포함관계 순. 포함관계는 "코팅팬"으로 "테팔 코팅팬"을 찾기 위한 것이지만,
    **여러 개가 걸리면 특정 실패로 보고 None**을 준다(엉뚱한 제품 사진을 띄우지 않기 위해서다).
    """
    prods = cat.get("products", {})
    if product_id:
        for slug, p in prods.items():
            if p.get("product_id") == product_id:
                return dict(p, slug=slug)
    if not name:
        return None
    k = _key(name)
    if not k:
        return None
    exact = [(s, p) for s, p in prods.items()
             if k in (_key(p.get("display", "")), _key(p.get("model", "")),
                      _key(p.get("category", "")), _key(s))]
    if len(exact) == 1:
        return dict(exact[0][1], slug=exact[0][0])
    partial = [(s, p) for s, p in prods.items()
               if k and (k in _key(p.get("display", "")) or _key(p.get("category", "")) == k)]
    if len(partial) == 1:
        return dict(partial[0][1], slug=partial[0][0])
    return None


def image_path(entry: dict | None) -> str | None:
    """실제 파일이 있을 때만 경로를 준다. 없으면 None → 렌더러가 클레이로 폴백."""
    if not entry:
        return None
    p = entry.get("image") or ""
    return p if p and os.path.exists(p) else None


def display_name(entry: dict | None, fallback: str = "") -> str:
    """영상 자막에 쓸 이름. **확정된 것만** 브랜드·모델로 나간다."""
    if entry and entry.get("display"):
        return entry["display"]
    if entry and entry.get("brand") and entry.get("model"):
        return f"{entry['brand']} {entry['model']}"
    return fallback


REAL_IMAGE_SOURCES = ("pickdam", "coupang_partners", "maker", "capture")


def render_mode(entry: dict | None) -> str:
    """이 상품을 어떻게 그릴지 한 단어로 답한다.

    exact  : **실제 사진** 보유 → 그대로 띄운다
    named  : 이름만 확정, 사진 없음 → 클레이 아트 + 정확한 이름
    generic: 아무것도 없음 → 카테고리명 + 클레이 아트

    ⚠️ **제품을 AI로 재현하는 단계는 없다**(2026-09-08 결정). 실물과 다른 그림은 시청자가
    즉시 알아채고 돌아선다. 사진이 없으면 **아무 제품 이미지도 넣지 않는다** — 없는 게 가짜보다 낫다.
    """
    if not entry:
        return "generic"
    if image_path(entry) and entry.get("image_source") in REAL_IMAGE_SOURCES:
        return "exact"
    named = bool(entry.get("display") or (entry.get("brand") and entry.get("model")))
    return "named" if named else "generic"


# ------------------------------------------------------------------ 등록
def put(cat: dict, *, name: str, brand: str = "", model: str = "", category: str = "",
        product_id: str = "", image: str = "", image_source: str = "", coupang_url: str = "",
        price_band: str = "", updated: str = "") -> str:
    """카탈로그에 한 건 등록/갱신하고 slug를 돌려준다.

    게시용 링크는 **우리 링크만** 받는다. 남의 제휴 코드가 붙은 URL은 조용히 버리고
    상품 ID만 남긴다(그게 우리가 그 링크에서 취할 유일한 정보다).
    """
    slug = slugify(brand and model and f"{brand} {model}" or name)
    prev = cat.setdefault("products", {}).get(slug, {})
    if coupang_url and FOREIGN_AFFILIATE.search(coupang_url):
        coupang_url = ""          # 남의 추적 코드 — 게시에 쓰지 않는다
    entry = {
        "display": (f"{brand} {model}".strip() if brand and model else name).strip(),
        "brand": brand or prev.get("brand", ""),
        "model": model or prev.get("model", ""),
        "category": category or prev.get("category", "") or name,
        "product_id": product_id or prev.get("product_id", ""),
        "image": image or prev.get("image", ""),
        "image_source": image_source or prev.get("image_source", ""),
        "coupang_url": coupang_url or prev.get("coupang_url", ""),
        "price_band": price_band or prev.get("price_band", ""),
        "updated": updated or prev.get("updated", ""),
    }
    cat["products"][slug] = entry
    return slug


# ------------------------------------------------------------------ 픽담 구조화 블록
KOKPICK_BLOCK = re.compile(r"<!--\s*KOKPICK\s*(.*?)\s*KOKPICK\s*-->", re.S | re.I)


def parse_kokpick_block(html_text: str) -> dict | None:
    """픽담 글 본문의 `<!--KOKPICK {...} KOKPICK-->` 블록을 읽는다(브리프 6-C).

    이 블록이 오면 **완전 자동**이다 — 픽담이 자기 파트너스 계정으로 확정한 브랜드·모델·
    공식 이미지·자체 링크가 그대로 들어오므로 사람이 손댈 일이 없다.
    """
    m = KOKPICK_BLOCK.search(html_text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def adopt_block(cat: dict, block: dict, updated: str = "") -> str | None:
    """KOKPICK 블록 → 카탈로그 등록. 이름조차 없으면 등록하지 않는다."""
    if not block:
        return None
    p = block.get("product")
    p = p if isinstance(p, dict) else {"name": p} if isinstance(p, str) else {}
    name = (p.get("name") or block.get("name") or "").strip()
    brand = (p.get("brand") or block.get("brand") or "").strip()
    model = (p.get("model") or block.get("model") or "").strip()
    if not (name or (brand and model)):
        return None
    return put(cat, name=name or f"{brand} {model}", brand=brand, model=model,
               category=(p.get("category") or block.get("category") or "").strip(),
               product_id=str(p.get("product_id") or block.get("product_id") or ""),
               image=block.get("image_local", ""),
               image_source="pickdam" if (p.get("image_url") or block.get("image_url")) else "",
               coupang_url=(block.get("coupang_url") or p.get("coupang_url") or "").strip(),
               updated=updated)


def block_image_url(block: dict) -> str:
    """블록이 준 이미지 URL 중 **허용 출처만** 통과시킨다."""
    p = block.get("product") if isinstance(block.get("product"), dict) else {}
    url = (block.get("image_url") or p.get("image_url") or "").strip()
    if not url.lower().startswith("https://"):
        return ""
    host = url.split("/")[2].lower()
    return url if any(host == h or host.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS) else ""


def cache_image(url: str, slug: str, session=None, dir_: str = IMAGE_DIR) -> str | None:
    """허용 출처 이미지를 로컬에 캐시한다. 실패해도 파이프라인은 계속(클레이 폴백)."""
    if not url:
        return None
    import requests
    os.makedirs(dir_, exist_ok=True)
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
    out = os.path.join(dir_, f"{slug}{ext}")
    try:
        r = (session or requests).get(url, timeout=20)
        r.raise_for_status()
        with open(out, "wb") as f:
            f.write(r.content)
        return out
    except Exception as e:                                    # noqa: BLE001
        print("[catalog] 이미지 캐시 실패(무시):", e)
        return None


# ------------------------------------------------------------------ 캡처 번호표
"""캡처를 **번호로** 주고받는다 — 사람이 하는 일을 최소로 줄이기 위해서다.

파일명을 제품명으로 정확히 타이핑하는 건 생각보다 번거롭고, 한 글자만 달라도 매칭이 깨진다.
그래서 시스템이 상품마다 **고정 번호**를 붙이고, 사람은 `3.png` 로만 저장하면 되게 한다.

번호는 **한 번 붙으면 재사용하지 않는다.** 어제 3번을 보고 캡처해 둔 게 오늘 다른 상품의
3번이 되면 엉뚱한 사진이 붙기 때문이다(이 채널에서 제일 피해야 할 사고).
"""
QUEUE_PATH = "data/shot_queue.json"
INBOX_DIR = os.path.join(IMAGE_DIR, "캡처_넣는곳")
LIST_FILE = os.path.join(INBOX_DIR, "_목록.md")
LIST_HTML = os.path.join(INBOX_DIR, "_목록.html")


def queue_load(path: str = QUEUE_PATH) -> dict:
    if not os.path.exists(path):
        return {"next": 1, "items": {}}
    with open(path, encoding="utf-8") as f:
        q = json.load(f)
    q.setdefault("next", 1)
    q.setdefault("items", {})
    return q


def queue_save(q: dict, path: str = QUEUE_PATH) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=1)
    return path


def number_for(q: dict, name: str, slug: str = "") -> int:
    """이 상품의 캡처 번호. 없으면 새로 발급한다(기존 번호는 절대 바뀌지 않는다)."""
    k = _key(name)
    for n, it in q["items"].items():
        if it.get("key") == k or (slug and it.get("slug") == slug):
            return int(n)
    n = int(q.get("next", 1))
    q["items"][str(n)] = {"name": name, "slug": slug, "key": k, "done": False}
    q["next"] = n + 1
    return n


COUPANG_SEARCH = "https://www.coupang.com/np/search?q={}"


def set_details(q: dict, n: int | str, **kw) -> dict | None:
    """번호에 브랜드·모델·검색어·상품 링크를 붙인다.

    캡처하는 사람이 **무엇을 검색해야 하는지**까지 알아야 손이 멈추지 않는다.
    브랜드를 특정하지 못한 항목은 브랜드를 비워두고 검색어만 준다 — 지어내지 않는다.

    ⚠️ 쿠팡은 두 브라우저 모두 정책상 차단이라 **캐스토가 대신 스크린샷을 찍을 수 없다**(2026-09-08 실측).
    그래서 사람의 손이 닿는 지점을 "링크 클릭 → 캡처 → 번호로 저장" 세 동작으로 줄이는 것이 최선이다.
    """
    it = q["items"].get(str(int(n)))
    if it is None:
        return None
    for k in ("brand", "model", "search", "confidence", "note", "hold", "url"):
        if k in kw:
            it[k] = kw[k]
    if it.get("brand") and it.get("model"):
        it["display"] = f"{it['brand']} {it['model']}"
    # 링크는 **항상 검색 URL**로 만든다. 상품 ID 직링크는 우리가 열어서 확인할 수 없고
    # (쿠팡은 브라우저·서버 양쪽에서 차단), 죽은 링크는 검색보다 나쁘다 — "상품을 찾을 수 없다"가
    # 뜨는 순간 사람 손이 멈춘다(2026-09-08 실측). 확인된 URL을 명시적으로 넘길 때만 그것을 쓴다.
    if kw.get("url"):
        it["url"] = kw["url"]
    else:
        from urllib.parse import quote_plus
        it["url"] = COUPANG_SEARCH.format(quote_plus(it.get("search") or it.get("name", "")))
    return it


def by_number(q: dict, n: int | str) -> dict | None:
    return q["items"].get(str(int(n)))


def mark_done(q: dict, n: int | str) -> None:
    it = q["items"].get(str(int(n)))
    if it:
        it["done"] = True


def refresh_queue(cat: dict, watchlist: dict, q: dict | None = None) -> dict:
    """사진이 필요한 상품 전부에 번호를 붙인다(이미 있으면 유지)."""
    q = q or queue_load()
    for r in needs(cat, watchlist):
        number_for(q, r["name"])
    for slug, e in cat.get("products", {}).items():
        if render_mode(e) != "exact":
            number_for(q, e.get("display") or e.get("category") or slug, slug)
    return q


def write_list(q: dict, path: str = LIST_FILE) -> str:
    """캡처하는 폴더 **안에** 번호표를 둔다 — 저장하면서 바로 보이도록.

    검색어까지 적는다. 사람이 "이게 정확히 뭐지"를 다시 찾게 만들면 거기서 작업이 멈춘다.
    """
    conf_mark = {"높음": "◎", "중간": "○", "낮음": "△"}

    def row(n, it):
        who = it.get("display") or (f"{it.get('brand','')} {it.get('model','')}".strip() or "—")
        mark = conf_mark.get(it.get("confidence", ""), "")
        note = it.get("note", "")
        link = f'[열기]({it["url"]})' if it.get("url") else ""
        return (f'| **{n}** | {it["name"]} | {who} {mark} | `{it.get("search") or it["name"]}` '
                f'| {link} | {note} |')

    todo = sorted((int(n), it) for n, it in q["items"].items()
                  if not it.get("done") and not it.get("hold"))
    hold = sorted((int(n), it) for n, it in q["items"].items()
                  if not it.get("done") and it.get("hold"))
    lines = ["# 캡처 번호표", "",
             "**링크 → 캡처 → 번호로 저장**, 세 동작이면 끝입니다.",
             "링크를 열어 상품 대표 이미지를 캡처하고 `4.png` 처럼 번호로 저장해 이 폴더에 넣으세요.",
             "(쿠팡은 브라우저 정책상 차단이라 캐스토가 대신 찍을 수 없습니다.)", "",
             "브랜드 옆 표시 — ◎ 확실 · ○ 유력 · △ 브랜드 특정 실패(검색 결과 상위 아무거나 캡처)", ""]
    if todo:
        lines += ["| 번호 | 카테고리 | 브랜드·모델 | 쿠팡 검색어 | 링크 | 메모 |",
                  "|---|---|---|---|---|---|"]
        lines += [row(n, it) for n, it in todo]
    else:
        lines.append("지금 필요한 캡처가 없습니다. 👍")
    if hold:
        lines += ["", "## 보류 — 지금 유행 근거가 없는 항목", "",
                  "최근 수집에서 언급이 잡히지 않았습니다. **캡처하지 마세요**(다시 뜨면 위로 올라옵니다).", "",
                  "| 번호 | 카테고리 |", "|---|---|"]
        lines += [f'| {n} | {it["name"]} |' for n, it in hold]
    done = sorted((int(n), it) for n, it in q["items"].items() if it.get("done"))
    if done:
        lines += ["", "---", "",
                  f"완료 {len(done)}건: " + ", ".join(f"{n}번 {it['name']}" for n, it in done[-12:])]
    lines += ["", "번호는 한 번 붙으면 바뀌지 않습니다. 완료된 번호는 다시 쓰이지 않습니다."]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def write_html(q: dict, path: str = LIST_HTML) -> str:
    """더블클릭하면 브라우저로 열리는 번호표 — **링크를 바로 누를 수 있게** 하는 것이 목적.

    마크다운 표는 링크가 원문 그대로 보여서 읽기도 누르기도 어렵다(2026-09-08 피드백).
    이 파일은 캡처 폴더 안에 같이 두므로, 폴더를 열면 목록과 저장 위치가 한 화면에 있다.
    """
    conf = {"높음": ("확실", "#2f8f68"), "중간": ("유력", "#c9932f"), "낮음": ("브랜드 미확정", "#8a8a8a")}

    def card(n, it):
        who = it.get("display") or f"{it.get('brand','')} {it.get('model','')}".strip()
        label, color = conf.get(it.get("confidence", ""), ("", "#8a8a8a"))
        chip = f'<span class="chip" style="--c:{color}">{label}</span>' if label else ""
        who_html = (f'<div class="who">{who} {chip}</div>' if who
                    else f'<div class="who none">브랜드 없음 {chip}</div>')
        note = f'<div class="note">{it["note"]}</div>' if it.get("note") else ""
        url = it.get("url", "")
        btn = (f'<a class="go" href="{url}" target="_blank" rel="noopener">쿠팡에서 열기 →</a>'
               if url else "")
        return f'''<li class="card">
      <div class="n">{n}</div>
      <div class="body">
        <div class="cat">{it["name"]}</div>
        {who_html}
        <div class="q">검색어 <code>{it.get("search") or it["name"]}</code></div>
        {note}
      </div>
      <div class="act">{btn}<div class="save">저장 → <b>{n}.png</b></div></div>
    </li>'''

    todo = sorted((int(n), it) for n, it in q["items"].items()
                  if not it.get("done") and not it.get("hold"))
    hold = sorted((int(n), it) for n, it in q["items"].items()
                  if not it.get("done") and it.get("hold"))
    done = sorted((int(n), it) for n, it in q["items"].items() if it.get("done"))
    body = "\n".join(card(n, it) for n, it in todo) or \
        '<li class="empty">지금 필요한 캡처가 없습니다 👍</li>'
    hold_html = ""
    if hold:
        rows = "".join(f"<li>{n}. {it['name']}</li>" for n, it in hold)
        hold_html = (f'<section class="hold"><h2>보류 — 지금 유행 근거 없음</h2>'
                     f'<p>최근 수집에서 언급이 잡히지 않았습니다. <b>캡처하지 마세요.</b> '
                     f'다시 뜨면 위로 올라옵니다.</p><ul>{rows}</ul></section>')
    done_html = ""
    if done:
        rows = ", ".join(f"{n}번 {it['name']}" for n, it in done[-12:])
        done_html = f'<section class="done"><h2>완료 {len(done)}건</h2><p>{rows}</p></section>'

    html = f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>콕픽 캡처 번호표</title>
<style>
:root{{--bg:#fbf6ec;--card:#fff;--ink:#2f5d4e;--sub:#6b7f76;--line:#dfe8e3;--mint:#b0e0d2}}
*{{box-sizing:border-box}}
body{{margin:0;padding:28px 18px 60px;background:var(--bg);color:var(--ink);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}}
.wrap{{max-width:860px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 6px}}
.lead{{color:var(--sub);margin:0 0 26px;font-size:15px}}
.lead b{{color:var(--ink)}}
ul{{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:12px}}
.card{{display:flex;gap:16px;align-items:center;background:var(--card);border:1px solid var(--line);
 border-radius:16px;padding:16px 18px;flex-wrap:wrap}}
.n{{flex:0 0 46px;height:46px;border-radius:14px;background:var(--mint);color:#1f4a3c;
 font-weight:800;font-size:20px;display:grid;place-items:center}}
.body{{flex:1 1 320px;min-width:0}}
.cat{{font-size:13px;color:var(--sub)}}
.who{{font-size:18px;font-weight:700;margin:1px 0 4px}}
.who.none{{color:var(--sub);font-weight:600}}
.chip{{font-size:11px;font-weight:700;color:#fff;background:var(--c);border-radius:999px;
 padding:2px 9px;vertical-align:2px;margin-left:4px}}
.q{{font-size:14px;color:var(--sub)}}
code{{background:#eef5f1;border-radius:6px;padding:2px 7px;font-size:14px;color:var(--ink)}}
.note{{font-size:13px;color:#9a7b3f;margin-top:5px}}
.act{{flex:0 0 auto;text-align:right}}
.go{{display:inline-block;background:var(--ink);color:#fff;text-decoration:none;font-weight:700;
 border-radius:12px;padding:11px 18px;font-size:15px}}
.go:hover{{background:#24493d}}
.save{{font-size:13px;color:var(--sub);margin-top:7px}}
.save b{{color:var(--ink)}}
.empty{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;text-align:center}}
section{{margin-top:34px}}
h2{{font-size:16px;margin:0 0 8px}}
.hold p,.done p{{color:var(--sub);font-size:14px;margin:0 0 8px}}
.hold ul{{flex-direction:row;flex-wrap:wrap;gap:8px}}
.hold li{{background:#eef1ef;color:var(--sub);border-radius:999px;padding:5px 12px;font-size:13px}}
footer{{margin-top:40px;color:var(--sub);font-size:13px;border-top:1px solid var(--line);padding-top:16px}}
@media(max-width:620px){{.act{{width:100%;text-align:left}}.go{{width:100%;text-align:center}}}}
</style>
<div class="wrap">
<h1>콕픽 캡처 번호표</h1>
<p class="lead">버튼을 눌러 상품 페이지를 열고, 제품 대표 이미지를 캡처해서
<b>번호로 저장</b>해 이 폴더에 넣으세요. 예) 4번 → <b>4.png</b><br>
쿠팡은 브라우저 정책상 차단이라 캐스토가 대신 찍을 수 없습니다.</p>
<ul>
{body}
</ul>
{hold_html}
{done_html}
<footer>번호는 한 번 붙으면 바뀌지 않고, 완료된 번호는 다시 쓰이지 않습니다.<br>
파일명에 <code>4 씨밀렉스 라이스키퍼 쌀통.png</code>처럼 이름을 덧붙이면 그 이름이 영상 자막에 나갑니다.</footer>
</div>
</html>'''
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ------------------------------------------------------------------ 요청서
def needs(cat: dict, watchlist: dict) -> list[dict]:
    """지금 추적 중인 상품 중 **아직 사진·브랜드가 확정 안 된 것**을 뽑는다."""
    rows = []
    for slug, w in (watchlist or {}).items():
        name = w.get("name") or slug.replace("_", " ")
        e = find(cat, name=name, product_id=w.get("product_id", ""))
        mode = render_mode(e)
        if mode == "exact":
            continue
        rows.append({"name": name, "mode": mode, "product_id": w.get("product_id", ""),
                     "brand": (e or {}).get("brand", "") or w.get("brand", ""),
                     "evidence": w.get("evidence", "")})
    return rows


def request_sheet(rows: list[dict]) -> str:
    """사람이 쿠팡 파트너스에서 채워 올 목록. 한 줄씩 그대로 처리하면 된다."""
    if not rows:
        return "# 콕픽 상품 이미지 요청서\n\n필요한 항목 없음 — 추적 중인 상품 전부 사진·브랜드 확정됨.\n"
    q = queue_load()
    out = ["# 콕픽 상품 이미지 요청서", "",
           f"캡처를 **번호로 저장**해 `{INBOX_DIR}/` 에 넣으면 끝입니다(예: 3번 → `3.png`).",
           "쿠팡 상품 페이지의 대표 이미지를 제품만 나오게 잘라 저장하세요.",
           "남의 썸네일·릴스 캡처는 쓰지 않습니다(저작권).", "",
           "| 번호 | 상품 | 상태 | 상품 ID |", "|---|---|---|---|"]
    label = {"named": "이름만 확정(사진 없음)", "generic": "미확정"}
    for r in rows:
        n = number_for(q, r["name"])
        out.append(f'| **{n}** | {r["name"]} | {label.get(r["mode"], r["mode"])} '
                   f'| {r["product_id"] or "-"} |')
    out += ["", "브랜드·모델을 정확히 아시면 파일명을 `3 락앤락 밀폐용기 800ml.png` 처럼 "
            "**번호 + 제품명**으로 저장하세요. 번호만 있어도 동작합니다."]
    return "\n".join(out)


def main():
    cat = load()
    wl = {}
    if os.path.exists("data/watchlist.json"):
        with open("data/watchlist.json", encoding="utf-8") as f:
            wl = json.load(f)
    rows = needs(cat, wl)
    q = refresh_queue(cat, wl)
    queue_save(q)
    write_list(q)
    write_html(q)
    sheet = request_sheet(rows)
    os.makedirs("out", exist_ok=True)
    with open("out/이미지_요청서.md", "w", encoding="utf-8") as f:
        f.write(sheet)
    todo = [n for n, it in q["items"].items() if not it.get("done")]
    print(f"[catalog] 등록 {len(cat.get('products', {}))}건 · 캡처 필요 {len(todo)}건")
    print(f"[catalog] 번호표 → {LIST_HTML} (더블클릭해서 열기) · {LIST_FILE}")


if __name__ == "__main__":
    main()

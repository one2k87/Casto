#!/usr/bin/env python3
"""Tailored 캐릭터 도구 — 세계관 충돌을 등장 전에 잡는다.

  python tailored_cast.py lint                 # 바이블 전체 점검(오류가 있으면 종료 코드 1)
  python tailored_cast.py check s1e03          # 그 화에 나오는 캐릭터가 등장 준비가 됐는지
  python tailored_cast.py prompt mochi kong    # 그림 지시문에 넣을 표준 문장(캐릭터·애착템·키·계절)
  python tailored_cast.py prompt mochi --back  # 뒷모습 컷용
  python tailored_cast.py page                 # 도감 페이지 tailored/cast_page.html 생성

데이터: tailored/characters.json · world.json · continuity.json · inventions.json · episodes/<화>/(conti.json|beats.md)
"""
import base64
import colorsys
import datetime
import html
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tailored")
NAMES = {"mochi": ["모찌"], "mom": ["엄마"], "kong": ["콩"], "mu": ["고양이 셰프", "셰프 무"], "raccoon": ["검표원"],
         "crab": ["아기 게"], "spider": ["거미"], "firefly": ["반딧불이"]}


def J(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def chars():
    d = J("characters.json")
    return {k: v for k, v in d.items() if not k.startswith("_")}, d.get("_required", [])


def get(d, path):
    for p in path.split("."):
        d = d.get(p) if isinstance(d, dict) else None
        if d is None:
            return None
    return d


def lab(hexv):
    r, g, b = [int(hexv[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92
    r, g, b = f(r), f(g), f(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    g2 = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    x, y, z = g2(x), g2(y), g2(z)
    return 116 * y - 16, 500 * (x - y), 200 * (y - z)


def delta_e(a, b):
    la, lb = lab(a), lab(b)
    return sum((p - q) ** 2 for p, q in zip(la, lb)) ** 0.5


KO = {"ref.turnaround": "기준 그림(앞·옆·뒤)", "home": "사는 곳", "first_ep": "첫 등장 화", "never": "금지 사항", "item_rule": "애착템 그리는 법",
      "size_prompt": "키 지시문", "build": "체형", "height": "키", "look": "생김새 문장", "color": "고유색", "item": "애착템"}


def ko(fields):
    return ", ".join(KO.get(f, f) for f in fields)


def missing(c, required):
    out = []
    for f in required:
        v = get(c, f)
        if v in (None, "", [], {}) or (isinstance(v, str) and v.startswith("미정")):
            out.append(f)
    return out


def episode_cast(ep):
    """콘티(cast 필드 또는 action 문장)나 비트 시트에서 등장 캐릭터를 찾는다."""
    d = os.path.join(ROOT, "episodes", ep)
    text, explicit, published = "", set(), False
    cp = os.path.join(d, "conti.json")
    if os.path.exists(cp):
        c = json.load(open(cp, encoding="utf-8"))
        published = bool(get(c, "upload.video_id"))
        for cut in c.get("cuts", []):
            explicit.update(cut.get("cast", []))
            text += " " + cut.get("action", "")
    bp = os.path.join(d, "beats.md")
    if os.path.exists(bp):
        text += " " + open(bp, encoding="utf-8").read()
    found = set(explicit)
    for cid, words in NAMES.items():
        for w in words:
            if re.search(r"(?<![가-힣])" + re.escape(w), text):
                found.add(cid)
    return sorted(found), published, os.path.exists(cp)


def episodes():
    d = os.path.join(ROOT, "episodes")
    return sorted(e for e in os.listdir(d) if os.path.isdir(os.path.join(d, e)))


def lint(only_ep=None):
    cs, required = chars()
    world, cont, inv = J("world.json"), J("continuity.json"), J("inventions.json")
    errs, warns, infos = [], [], []
    classes = {c["class"]: c["range"] for c in world["scale"]["classes"]}

    # 1. 설정 빠짐
    for cid, c in cs.items():
        miss = missing(c, required)
        if c.get("status") == "확정" and miss == ["ref.turnaround"]:
            warns.append(f"{c['name']}: 기준 그림(앞·옆·뒤)이 없음 — 다음 등장 전에 만들 것")
        elif c.get("status") == "확정" and miss:
            errs.append(f"{c['name']}: 확정인데 빠진 항목 — {ko(miss)}")
        elif miss:
            warns.append(f"{c['name']}: 첫 등장({c.get('first_ep', '미정')}) 전에 채울 항목 — {ko(miss)}")

    # 2. 고유색 충돌
    ids = list(cs)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            de = delta_e(cs[a]["color"]["hex"], cs[b]["color"]["hex"])
            msg = f"고유색이 가깝다: {cs[a]['name']} {cs[a]['color']['hex']} ↔ {cs[b]['name']} {cs[b]['color']['hex']} (색 차이 {de:.0f})"
            if de < 12:
                errs.append(msg + " — 구분 불가")
            elif de < 25:
                warns.append(msg + " — 한 컷에 함께 나오면 헷갈릴 수 있음")

    # 3. 키가 분류 범위 안인지
    alias = {"아기": "아기·작은 종", "작은 종 어른": "아기·작은 종", "꼬마": "꼬마·벌레", "꼬마 벌레": "꼬마·벌레"}
    for cid, c in cs.items():
        h, sc = c.get("height"), alias.get(c.get("size_class"), c.get("size_class"))
        if h is None:
            continue
        if sc in classes and not (classes[sc][0] <= h <= classes[sc][1]):
            errs.append(f"{c['name']}: 키 {h}가 '{sc}' 범위 {classes[sc]} 밖")
    for r in world.get("residents", []):
        if r["class"] in classes and not (classes[r["class"]][0] <= r["height"] <= classes[r["class"]][1]):
            errs.append(f"주민 {r['id']}: 키 {r['height']}가 '{r['class']}' 범위 밖")
        if "미정" in str(r.get("mark", "")) or "확정 예정" in str(r.get("mark", "")):
            warns.append(f"주민 {r['species']}({r['job']}): 구분 표시가 미정 — 등장 전에 정할 것")

    # 4. 애착템 겹침
    kinds = {"모자": ["모자", "cap", "hat", "beanie", "헬멧"], "목도리": ["목도리", "scarf"], "가방": ["배낭", "가방", "bag", "backpack"]}
    for kind, words in kinds.items():
        who = [c["name"] for c in cs.values() if any(w in (c.get("item", "") + " " + c.get("item_rule", "")) for w in words)]
        if len(who) > 1:
            infos.append(f"{kind} 종류 애착템이 여럿: {', '.join(who)} — 색과 모양으로 구분되는지 확인")

    # 5. 같은 종이 두 가지 일을 함
    by = {}
    for it in inv["items"]:
        sp = it["id"].split("_")[0]
        by.setdefault(sp, []).append(it["animal"])
    multi = [" / ".join(jobs) for jobs in by.values() if len(jobs) > 1]
    if multi:
        infos.append("같은 종이 두 가지 일을 하는 발명품: " + ", ".join(multi) + " — 세계 법칙 '발명품 = 직업'으로 허용. 한 화에 둘을 함께 쓰지 않는다")

    # 6. 장부: 물건은 한 곳, 캐릭터는 한 곳
    seen = {}
    for p in cont["props"]:
        if p["id"] in seen:
            errs.append(f"소지품 {p['name']}이 두 번 적혀 있음")
        seen[p["id"]] = p
        if p["holder"] not in cs and p["holder"] != "-":
            errs.append(f"소지품 {p['name']}의 주인 '{p['holder']}'가 캐릭터 목록에 없음")
    for ep, places in cont["whereabouts"].items():
        for who in places:
            if who not in cs and who not in [r["id"] for r in world.get("residents", [])]:
                errs.append(f"{ep} 위치 장부의 '{who}'가 목록에 없음")

    # 7. 화별 등장 준비
    order = episodes()
    for ep in order:
        if only_ep and ep != only_ep:
            continue
        cast, published, has_conti = episode_cast(ep)
        for cid in cast:
            c = cs[cid]
            fe = c.get("first_ep", "")
            if re.match(r"s\d+e\d+", fe) and ep < fe:
                errs.append(f"{ep}: {c['name']}이(가) 설정된 첫 등장({fe})보다 먼저 나옴")
            if published:
                continue
            if c.get("status") != "확정":
                errs.append(f"{ep}: {c['name']}이(가) 아직 '{c.get('status')}' — 그림 생성 전에 설정을 확정할 것")
            elif not get(c, "ref.turnaround"):
                errs.append(f"{ep}: {c['name']}의 기준 그림(앞·옆·뒤)이 없음 — 그림 생성 전에 만들 것")
    return errs, warns, infos


def prompt(ids, back=False):
    cs, _ = chars()
    world = J("world.json")
    out = [world["style_lock"] + "."]
    for cid in ids:
        c = cs[cid]
        out.append(f"{c['name']} ({cid}): {c['look']}. Must show: {c.get('item_rule', c['item'])}. Size: {c.get('size_prompt', '')}.")
    if back and "mochi" in ids:
        out.append("BACK VIEW: Mochi's cherry-red backpack sits centered on his back with two shoulder straps, exactly like the back view of his reference sheet; not a side bag.")
    if len(ids) > 1:
        hs = sorted(((cs[i].get("height", 1), cs[i]["name"], i) for i in ids), reverse=True)
        out.append("Relative heights (Mochi = 1.0): " + ", ".join(f"{i} {h}" for h, _, i in hs) + ". Keep every character's own body proportions; do not stretch anyone.")
    out.append("World: late spring city (green trees, flowers, clear sky) unless the scene is Antarctica or the snow railway. No text, no letters; signs, labels and maps show pictures only. Exactly one of each character.")
    return "\n".join(out)


# ───────────────────────── 도감 페이지 ─────────────────────────
CSS = """
/* 배치: 위에서 아래로 한 줄 — 점검 결과 → 키 재기 → 캐릭터 카드 → 세계 법칙 → 주민 → 장부 */
:root{--bg:#FBFAFE;--surface:#FFFFFF;--ink:#2F2733;--muted:#6F6477;--line:#E4DDF0;--accent:#6A50B5;--accent-soft:#EFEAFB;
--ok:#2B7A4B;--warn:#9A5B00;--bad:#B5362E;--bar:#C9C0D6;
--display:"Jua","Noto Sans KR",system-ui,sans-serif;--body:"Noto Sans KR",system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#1A1620;--surface:#241F2C;--ink:#EFEAF5;--muted:#A99FB6;--line:#3A3346;--accent:#BBA7F0;--accent-soft:#2F2840;--ok:#6FC897;--warn:#E3AC52;--bad:#F0857D;--bar:#5A5068;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#1A1620;--surface:#241F2C;--ink:#EFEAF5;--muted:#A99FB6;--line:#3A3346;--accent:#BBA7F0;--accent-soft:#2F2840;--ok:#6FC897;--warn:#E3AC52;--bad:#F0857D;--bar:#5A5068;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--body);font-size:15px;line-height:1.65}
.wrap{max-width:1080px;margin:0 auto;padding-block:28px 56px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:flex;flex-direction:column;gap:36px}
h1{font-family:var(--display);font-weight:400;font-size:2rem;line-height:1.2;margin:0;text-wrap:balance}
h2{font-family:var(--display);font-weight:400;font-size:1.35rem;margin:0 0 12px;text-wrap:balance}
p{margin:0}.lead{color:var(--muted);max-width:62ch;margin-top:8px}
.meta{color:var(--muted);font-size:.85rem;margin-top:6px}
section{min-width:0}
.sum{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.pill{display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:999px;border:1px solid var(--line);background:var(--surface);font-size:.9rem;white-space:nowrap}
.pill b{font-variant-numeric:tabular-nums}
.pill.bad{border-color:var(--bad);color:var(--bad)}.pill.warn{border-color:var(--warn);color:var(--warn)}.pill.ok{border-color:var(--ok);color:var(--ok)}
ul.find{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
ul.find li{padding:10px 14px;border:1px solid var(--line);border-left-width:4px;background:var(--surface);border-radius:6px}
li.bad{border-left-color:var(--bad)}li.warn{border-left-color:var(--warn)}li.info{border-left-color:var(--bar)}
li .tag{font-size:.78rem;letter-spacing:.04em;margin-right:8px}li.bad .tag{color:var(--bad)}li.warn .tag{color:var(--warn)}li.info .tag{color:var(--muted)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
.chart{position:relative;height:330px;min-width:720px;padding:16px 16px 0 56px}
.grid{position:absolute;left:56px;right:16px;border-top:1px dashed var(--line)}
.grid span{position:absolute;left:-48px;top:-10px;font-size:.75rem;color:var(--muted);font-variant-numeric:tabular-nums}
.bars{position:absolute;left:56px;right:16px;bottom:62px;height:250px;display:flex;align-items:flex-end;gap:10px}
.bar{flex:1;min-width:38px;border:1.5px solid var(--ink);border-bottom:0;border-radius:12px 12px 0 0;position:relative}
.bar.res{border-style:dashed;border-color:var(--muted);background:var(--bar)}
.bar i{position:absolute;top:-22px;left:0;right:0;text-align:center;font-style:normal;font-size:.75rem;font-variant-numeric:tabular-nums;color:var(--muted)}
.bar em{position:absolute;bottom:-52px;left:-6px;right:-6px;text-align:center;font-style:normal;font-size:.75rem;line-height:1.25;height:46px;overflow:hidden}
.base{position:absolute;left:56px;right:16px;bottom:62px;border-top:2px solid var(--ink)}
.note{color:var(--muted);font-size:.88rem;margin-top:10px;max-width:70ch}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{border:1px solid var(--line);border-radius:12px;background:var(--surface);overflow:hidden;display:flex;flex-direction:column;min-width:0}
.card img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#FFFDF8;border-bottom:1px solid var(--line)}
.card .noimg{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:.85rem;border-bottom:1px dashed var(--line);background:var(--accent-soft)}
.cb{padding:14px 16px 16px;display:flex;flex-direction:column;gap:10px}
.ch{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.ch strong{font-family:var(--display);font-weight:400;font-size:1.25rem}
.ch span{color:var(--muted);font-size:.88rem}
.st{margin-left:auto;font-size:.78rem;padding:2px 10px;border-radius:999px;border:1px solid var(--line)}
.st.ok{color:var(--ok);border-color:var(--ok)}.st.draft{color:var(--warn);border-color:var(--warn)}
.sw{display:flex;align-items:center;gap:8px;font-size:.9rem}
.sw b{width:22px;height:22px;border-radius:50%;border:1.5px solid var(--ink);flex:none}
.sw code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem;color:var(--muted)}
dl{display:grid;grid-template-columns:5.2em 1fr;gap:4px 10px;margin:0;font-size:.9rem}
dt{color:var(--muted)}dd{margin:0;min-width:0;overflow-wrap:anywhere}
.never{font-size:.86rem;color:var(--bad)}
.miss{font-size:.86rem;color:var(--warn);border-top:1px dashed var(--line);padding-top:8px}
ol.laws{margin:0;padding-left:1.3em;display:flex;flex-direction:column;gap:8px;max-width:72ch}
table{border-collapse:collapse;width:100%;font-size:.9rem;min-width:640px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:500;color:var(--muted);font-size:.8rem;letter-spacing:.03em;white-space:nowrap}
tr:last-child td{border-bottom:0}td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.two>div{min-width:0}
h3{font-family:var(--display);font-weight:400;font-size:1.05rem;margin:0 0 8px}
"""


def b64(path):
    return "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()


def page():
    cs, required = chars()
    world, cont = J("world.json"), J("continuity.json")
    errs, warns, infos = lint()
    E = html.escape
    confirmed = sum(1 for c in cs.values() if c.get("status") == "확정")
    today = datetime.date.today().isoformat()
    P = []
    P.append('<title>Tailored 캐릭터 도감</title>\n<meta name="claude:viewport-fit-sides" content="cover">')
    P.append('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Jua&family=Noto+Sans+KR:wght@400;500&display=swap">')
    P.append(f"<style>{CSS}</style>")
    P.append('<div class="wrap">')
    P.append(f'<header><h1>Tailored 캐릭터 도감</h1><p class="lead">캐릭터가 처음 나오기 전에 설정을 채우고, 세계 안에서 서로 어긋나는 곳을 찾는 곳입니다. 키는 모찌를 1.0으로 잽니다.</p>'
             f'<p class="meta">{today} 기준 · 원본은 Casto 레포 tailored/ 폴더 · 고칠 곳은 캐스토 채팅에 번호나 이름으로 알려 주세요</p>'
             f'<div class="sum"><span class="pill ok">확정 <b>{confirmed}</b></span><span class="pill">초안 <b>{len(cs) - confirmed}</b></span>'
             f'<span class="pill {"bad" if errs else "ok"}">충돌 <b>{len(errs)}</b></span><span class="pill {"warn" if warns else "ok"}">등장 전 할 일 <b>{len(warns)}</b></span></div></header>')

    P.append('<section><h2>점검 결과</h2><ul class="find">')
    if not (errs or warns or infos):
        P.append('<li class="info">어긋난 곳이 없습니다.</li>')
    for kind, label, items in (("bad", "충돌", errs), ("warn", "할 일", warns), ("info", "참고", infos)):
        for m in items:
            P.append(f'<li class="{kind}"><span class="tag">{label}</span>{E(m)}</li>')
    P.append("</ul></section>")

    # 키 재기
    unit = 100  # 1.0 = 100px
    rows = [(c["height"], c["name"], c["color"]["hex"], False) for c in cs.values() if c.get("height")]
    rows += [(r["height"], r.get("label", r["species"]), None, True)
             for r in world.get("residents", []) if r["height"] <= 2.6 and r["id"] != "chicks"]
    rows.sort(key=lambda r: r[0])
    P.append('<section><h2>키 재기</h2><div class="scroll"><div class="chart">')
    for g in (0.5, 1.0, 1.5, 2.0, 2.5):
        P.append(f'<div class="grid" style="bottom:{62 + g * unit}px"><span>×{g:.1f}</span></div>')
    P.append('<div class="bars">')
    for h, name, hexv, res in rows:
        style = f"height:{h * unit:.0f}px;" + (f"background:{hexv}" if hexv else "")
        P.append(f'<div class="bar{" res" if res else ""}" style="{style}"><i>{h:g}</i><em>{E(name)}</em></div>')
    P.append('</div><div class="base"></div></div></div>')
    giants = [f'{r.get("label", r["species"])}(약 ×{r["height"]:g})' for r in world.get("residents", []) if r["height"] > 2.6]
    P.append(f'<p class="note">색 막대는 이름 있는 캐릭터의 고유색, 점선 막대는 주민입니다. 일터 거인은 표에 넣지 않았습니다: {E(", ".join(giants))}. {E(world["scale"]["note"])}</p></section>')

    # 카드
    P.append('<section><h2>캐릭터</h2><div class="cards">')
    for cid, c in cs.items():
        img = os.path.join(ROOT, "cast_img", cid + ".jpg")
        P.append('<article class="card">')
        P.append(f'<img src="{b64(img)}" alt="{E(c["name"])} 기준 그림">' if os.path.exists(img) else '<div class="noimg">기준 그림 없음</div>')
        ok = c.get("status") == "확정"
        P.append(f'<div class="cb"><div class="ch"><strong>{E(c["name"])}</strong><span>{E(c["species"])} · {E(c["role"])}</span><span class="st {"ok" if ok else "draft"}">{E(c.get("status", "초안"))}</span></div>')
        P.append(f'<div class="sw"><b style="background:{c["color"]["hex"]}"></b>{E(c["color"]["name"])} <code>{c["color"]["hex"]}</code></div>')
        P.append("<dl>")
        for k, v in (("애착템", c.get("item")), ("키", f'×{c.get("height", "미정")} ({c.get("size_class", "미정")})'), ("체형", c.get("build")),
                     ("성격", c.get("personality")), ("버릇", c.get("habit")), ("첫 등장", c.get("first_ep")), ("사는 곳", c.get("home")), ("하는 일", c.get("job"))):
            if v:
                P.append(f"<dt>{k}</dt><dd>{E(str(v))}</dd>")
        P.append("</dl>")
        if c.get("never"):
            P.append(f'<div class="never">이렇게 그리지 않는다: {E(" · ".join(c["never"]))}</div>')
        miss = missing(c, required)
        if miss:
            P.append(f'<div class="miss">등장 전에 채울 것: {E(ko(miss))}</div>')
        if c.get("note"):
            P.append(f'<p class="meta">{E(c["note"])}</p>')
        P.append("</div></article>")
    P.append("</div></section>")

    P.append('<section><h2>세계 법칙</h2><ol class="laws">')
    for law in world["laws"]:
        P.append(f"<li>{E(law['law'])}</li>")
    P.append("</ol></section>")

    P.append('<section><h2>주민과 일터 거인</h2><div class="scroll"><table><thead><tr><th>종</th><th>하는 일</th><th>키</th><th>구분 표시</th><th>나온 화</th></tr></thead><tbody>')
    for r in world["residents"]:
        P.append(f'<tr><td>{E(r["species"])}</td><td>{E(r["job"])}</td><td class="n">×{r["height"]:g} · {E(r["class"])}</td><td>{E(r["mark"])}</td><td class="n">{E(", ".join(r["seen"]) or "아직")}</td></tr>')
    P.append("</tbody></table></div></section>")

    P.append('<section><h2>이어지는 사실</h2><div class="two"><div><h3>누가 무엇을 갖고 있나</h3><div class="scroll"><table style="min-width:420px"><thead><tr><th>물건</th><th>지금 있는 곳</th><th>부터</th></tr></thead><tbody>')
    for p in cont["props"]:
        holder = cs[p["holder"]]["name"] if p["holder"] in cs else "두고 옴"
        P.append(f'<tr><td>{E(p["name"])}</td><td>{E(holder)} · {E(p["where"])}</td><td class="n">{E(p["since"])}</td></tr>')
    P.append('</tbody></table></div></div><div><h3>화가 끝났을 때 어디에 있나</h3><div class="scroll"><table style="min-width:420px"><thead><tr><th>화</th><th>누구</th><th>어디</th></tr></thead><tbody>')
    resn = {r["id"]: r["species"] for r in world["residents"]}
    for ep, places in cont["whereabouts"].items():
        for who, where in places.items():
            nm = cs[who]["name"] if who in cs else resn.get(who, who)
            P.append(f'<tr><td class="n">{E(ep)}</td><td>{E(nm)}</td><td>{E(where)}</td></tr>')
    P.append("</tbody></table></div></div></div>")
    P.append('<h3 style="margin-top:20px">아직 풀리지 않은 것</h3><ol class="laws">')
    for t in cont["threads"]:
        P.append(f'<li>{E(t["q"])} <span class="meta">({E(t["open_since"])}부터)</span></li>')
    P.append("</ol></section></div>")
    out = os.path.join(ROOT, "cast_page.html")
    open(out, "w", encoding="utf-8").write("\n".join(P))
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "lint"
    if cmd in ("lint", "check"):
        ep = argv[2] if cmd == "check" and len(argv) > 2 else None
        errs, warns, infos = lint(ep)
        for label, items in (("충돌", errs), ("할 일", warns), ("참고", infos)):
            for m in items:
                print(f"[{label}] {m}")
        print(f"— 충돌 {len(errs)} · 할 일 {len(warns)} · 참고 {len(infos)}")
        if ep:
            cast, pub, _ = episode_cast(ep)
            print(f"{ep} 등장: {', '.join(cast) or '없음'}" + (" (게시됨)" if pub else ""))
        return 1 if errs else 0
    if cmd == "prompt":
        ids = [a for a in argv[2:] if not a.startswith("--")]
        print(prompt(ids, back="--back" in argv))
        return 0
    if cmd == "page":
        print(page())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

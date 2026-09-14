"""유튜브 자동 게시 — 렌더된 쇼츠를 사람 손 없이 콕픽 채널에 올린다.

2026-09-14 스튜디오 확인: 파이프라인이 9/10부터 매일 영상을 만들어 텔레그램으로 보냈지만
**채널에 올라간 영상은 0편**이었다. 업로드가 사람 손이었기 때문이다.
올라가지 않은 영상의 수익은 0이다 — 그래서 이 파일이 수익화 1순위다.

경로 (docs/콕픽_수익화_보고서.md §5-1):
  유튜브 Data API로 직접 올리면 **미검증 프로젝트라 강제 비공개**가 된다.
  Make의 유튜브 모듈은 검증된 앱이라 공개 게시가 바로 된다. 그래서 Make를 거친다.

    out/short.mp4
      → ① GitHub Release 자산으로 올려 공개 URL 확보 (저장소가 public이라 그대로 내려받힌다)
      → ② Make 웹훅 POST {title, description, tags, file_url, ...}
      → ③ Make: 파일 받기 → youtube:uploadVideo(public) → 웹훅 응답 {video_id}
      → ④ 응답이 40초 안에 안 오면 Data API(키만)로 채널 최신 영상을 폴링해 확인
      → ⑤ publish_log에 video_id 기록 + 텔레그램에 링크

비밀은 전부 GitHub 시크릿에만 있다: MAKE_UPLOAD_HOOK(웹훅 URL), YT_API_KEY, TELEGRAM_*.
GITHUB_TOKEN은 Actions가 준다. 이 파일은 어떤 토큰도 코드에 적지 않는다.

MAKE_UPLOAD_HOOK이 없으면 아무것도 하지 않고 False를 돌려준다 — make_short.py는 그때만
예전처럼 텔레그램으로 mp4를 보낸다(수동 업로드 폴백).
"""
import datetime as dt
import json
import os
import re
import sys
import time

import requests

from common import cfg, telegram_msg

PUBLISH_LOG = "data/publish_log.json"
LAST_CAPTION = "data/last_caption.json"
CATEGORY_HOWTO = "26"                  # Howto & Style — 살림·주방 채널의 관례 카테고리


# ------------------------------------------------------------------ 텍스트 규격
def clean_title(t: str, limit: int = 100) -> str:
    """유튜브 제목: `<` `>` 금지, 100자."""
    t = re.sub(r"[<>]", "", t or "").strip()
    return t[:limit].rstrip()


def clean_description(d: str, limit: int = 5000) -> str:
    d = re.sub(r"[<>]", "", d or "").strip()
    return d[:limit].rstrip()


def tags_from(caption: str, extra=("콕픽", "유행템", "Shorts")) -> list[str]:
    """설명란 해시태그 + 고정 태그. 태그 합계 500자 제한을 지킨다."""
    found = [h.lstrip("#") for h in re.findall(r"#([^\s#]+)", caption or "")]
    out, used = [], 0
    for t in list(dict.fromkeys(found + list(extra))):
        if used + len(t) + 1 > 480:
            break
        out.append(t)
        used += len(t) + 1
    return out


# ------------------------------------------------------------------ ① 공개 URL
def github_release_asset(path: str, tag: str, name: str | None = None) -> str | None:
    """mp4를 GitHub Release 자산으로 올리고 **공개 다운로드 URL**을 돌려준다.

    저장소가 public이라 `github.com/<repo>/releases/download/<tag>/<name>` 은 인증 없이 열린다.
    Make의 HTTP 'Get a file' 모듈이 이 URL을 받는다.
    """
    tok, repo = os.getenv("GITHUB_TOKEN", ""), os.getenv("GITHUB_REPOSITORY", "")
    if not (tok and repo):
        print("[publish] GITHUB_TOKEN/GITHUB_REPOSITORY 없음 — Release 업로드 불가")
        return None
    name = name or os.path.basename(path)
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}
    r = requests.post(f"https://api.github.com/repos/{repo}/releases", headers=h, timeout=60,
                      json={"tag_name": tag, "name": tag, "body": "캐스토 자동 렌더 — 유튜브 게시용 자산",
                            "prerelease": True})
    if r.status_code == 422:                       # 같은 태그가 있으면 그걸 쓴다
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=h, timeout=60)
    if r.status_code not in (200, 201):
        print("[publish] Release 생성 실패", r.status_code, r.text[:200])
        return None
    rel = r.json()
    up = rel["upload_url"].split("{")[0]
    with open(path, "rb") as f:
        u = requests.post(f"{up}?name={name}", headers={**h, "Content-Type": "video/mp4"},
                          data=f, timeout=600)
    if u.status_code not in (200, 201):
        print("[publish] 자산 업로드 실패", u.status_code, u.text[:200])
        return None
    url = u.json().get("browser_download_url") or f"https://github.com/{repo}/releases/download/{tag}/{name}"
    print("[publish] 공개 URL:", url)
    return url


# ------------------------------------------------------------------ ② Make 웹훅
def request_upload(payload: dict, hook: str, timeout: int = 60) -> dict:
    """Make 시나리오에 업로드를 요청한다. 응답에 video_id가 있으면 그대로 쓴다.

    Make 웹훅 응답 모듈은 40초 안에 끝나야 본문을 돌려준다. 업로드가 그보다 길면
    본문 없이 돌아오고, 시나리오는 계속 돈다 — 그 경우는 ④ 폴링으로 확인한다.
    """
    try:
        r = requests.post(hook, json=payload, timeout=timeout)
    except requests.RequestException as e:
        print("[publish] 웹훅 호출 실패:", e)
        return {}
    print("[publish] 웹훅", r.status_code, r.text[:160].replace("\n", " "))
    try:
        body = r.json() if r.text.strip().startswith("{") else {}
    except ValueError:
        body = {}
    return body if r.status_code < 400 else {}


# ------------------------------------------------------------------ ④ 확인 폴링
def find_new_video(channel_id: str, title: str, since: dt.datetime,
                   tries: int = 6, wait: int = 45) -> str | None:
    """채널 최신 영상 중 제목이 일치하는 것을 찾는다(키만 필요, OAuth 불필요).

    search.list는 호출당 100유닛이라 6번(600유닛)까지만 본다.
    """
    key = os.getenv("YT_API_KEY", "")
    if not (key and channel_id):
        return None
    after = (since - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(tries):
        time.sleep(wait)
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=30, params={
                "key": key, "channelId": channel_id, "part": "snippet", "order": "date",
                "type": "video", "maxResults": 5, "publishedAfter": after})
            items = r.json().get("items", []) if r.status_code == 200 else []
        except requests.RequestException:
            items = []
        for it in items:
            t = (it.get("snippet") or {}).get("title", "")
            if t and (t == title or t[:40] == title[:40]):
                return (it.get("id") or {}).get("videoId")
        print(f"[publish] 아직 안 보임 ({i + 1}/{tries})")
    return None


# ------------------------------------------------------------------ ⑤ 기록
def record_video(video_id: str, date: str) -> None:
    """publish_log의 오늘 행과 last_caption에 video_id를 남긴다 — 대시보드가 이걸로 '게시됨'을 띄운다."""
    for path, is_list in ((PUBLISH_LOG, True), (LAST_CAPTION, False)):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if is_list:
            for row in reversed(data):
                if row.get("date") == date and not row.get("video_id"):
                    row["video_id"] = video_id
                    break
        else:
            data["video_id"] = video_id
            data["video_url"] = f"https://youtube.com/shorts/{video_id}"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------ 진입점
def publish(video_path: str = "out/short.mp4", caption_path: str = "out/caption.txt",
            privacy: str = "public") -> bool:
    hook = os.getenv("MAKE_UPLOAD_HOOK", "")
    if not hook:
        print("[publish] MAKE_UPLOAD_HOOK 없음 — 자동 게시 생략(텔레그램 수동 폴백)")
        return False
    if not os.path.exists(video_path):
        print("[publish] 영상 없음:", video_path)
        return False

    c = cfg()
    try:
        with open(LAST_CAPTION, encoding="utf-8") as f:
            last = json.load(f)
    except (OSError, ValueError):
        last = {}
    try:
        with open(caption_path, encoding="utf-8") as f:
            caption = f.read()
    except OSError:
        caption = last.get("description", "")

    today = last.get("date") or dt.date.today().isoformat()
    title = clean_title(last.get("title") or f"콕픽 {today}")
    desc = clean_description(caption)
    run = os.getenv("GITHUB_RUN_NUMBER", "0")
    tag = f"short-{today}-r{run}"
    fname = f"kokpick-{today}-r{run}.mp4"

    url = github_release_asset(video_path, tag, fname)
    if not url:
        return False

    started = dt.datetime.utcnow()
    payload = {
        "title": title, "description": desc, "tags": tags_from(caption),
        "file_url": url, "file_name": fname, "privacy": privacy,
        "category_id": CATEGORY_HOWTO, "made_for_kids": False,
        "synthetic": False,                  # 실사 조작·실존 인물 없음. AI 고지는 설명란 문구로 한다
        "date": today, "key": last.get("verdict", ""), "product": last.get("winner", ""),
    }
    body = request_upload(payload, hook)
    vid = (body or {}).get("video_id") or (body or {}).get("id")
    if not vid:
        vid = find_new_video((c.get("channel") or {}).get("id", ""), title, started)
    if not vid:
        telegram_msg(f"⚠️ 유튜브 게시 확인 실패 — Make 시나리오 실행 기록을 확인하세요\n제목: {title}")
        return False

    record_video(vid, today)
    link = f"https://youtube.com/shorts/{vid}"
    print("[publish] ✅ 게시됨", link)
    telegram_msg(f"✅ 유튜브에 올라갔습니다\n{link}\n\n{title}")
    return True


if __name__ == "__main__":
    ok = publish(privacy=(sys.argv[1] if len(sys.argv) > 1 else "public"))
    # 웹훅이 아직 등록 안 된 상태는 실패가 아니다(수동 폴백). 등록됐는데 못 올렸을 때만 빨간불.
    sys.exit(0 if ok or not os.getenv("MAKE_UPLOAD_HOOK") else 1)

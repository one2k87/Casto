"""유튜브 OAuth 1회 승인 — 사용자 PC에서 한 번만 실행해 refresh token을 받는다.

왜 필요한가(2026-10-16): Make의 youtube:uploadVideo가 간헐적으로 [403]을 내면서 파일만 올리고 메타데이터를 못 붙여
제목 "unknown" 공개 영상(좀비)을 만든다. Make 커뮤니티에 2025-10부터 같은 보고가 있고 원인 미상. 그래서 우리 쪽에서
채널 소유자 권한(OAuth)으로 ① 좀비를 찾아 제목·설명·태그를 붙여 '정상 발행'으로 되살리고 ② 남는 중복은 비공개로 돌린다.
(직접 업로드는 미감사 프로젝트라 강제 비공개가 되므로 안 쓴다 — 업로드는 Make가, 수리는 우리가.)

사용(사용자 PC, 한 번):
    python yt_auth.py <client_secret.json 경로>
→ 브라우저가 열리면 콕픽 채널이 있는 계정(브랜드 계정 '픽핸드'를 고르는 화면이 나오면 그걸 선택)으로 승인
→ 터미널에 refresh_token 한 줄이 찍힌다 → GitHub Secrets `YT_REFRESH_TOKEN`에 붙여넣기.
   client_secret.json의 client_id / client_secret 도 각각 `YT_CLIENT_ID` / `YT_CLIENT_SECRET` 에.

famto는 이 값을 절대 보지 않는다. 이 파일은 토큰을 저장하지 않고 화면에만 찍는다.
"""
import http.server
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SCOPES = "https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/yt-analytics.readonly"
PORT = 8765


def _code_from(text: str) -> str:
    """브라우저 주소(…127.0.0.1:포트/?code=…&scope=…) 또는 code 값 자체에서 code 를 뽑는다."""
    text = (text or "").strip()
    if "code=" in text:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(text).query)
        return (q.get("code") or [""])[0]
    return text if len(text) > 20 and " " not in text else ""


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    c = raw.get("installed") or raw.get("web") or raw
    cid, sec = c["client_id"], c["client_secret"]
    got: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("code"):
                got["code"] = q["code"][0]
                msg = "승인 완료 — 이 창을 닫고 터미널을 보세요."
            elif q.get("error"):
                got["error"] = q["error"][0]
                msg = "승인이 거부/취소됐습니다: " + q["error"][0]
            else:
                msg = "대기 중…"                  # 파비콘·미리 연결 같은 다른 요청은 무시하고 계속 기다린다
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg.encode())

        def log_message(self, *a):  # noqa: D102
            pass

    # 2026-11-02 사용자 실측: 동의 후 "사이트에 연결할 수 없음". 옛 코드는 요청을 **딱 1개**만 받고 서버가 멈췄다 —
    # 크롬의 미리 연결(빈 연결) 하나가 그 1개를 먹으면 진짜 리디렉션은 아무도 안 받는다. 이제 code 가 올 때까지 계속 받는다.
    # 앞 실행이 포트를 잡고 있을 수 있어 8765~8775 중 빈 포트를 쓴다(데스크톱 앱 루프백은 포트 무관 허용).
    srv, port = None, None
    for port in range(PORT, PORT + 11):
        try:
            srv = http.server.HTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("8765~8775 포트가 모두 사용 중 — 터미널 창을 전부 닫고 다시 실행하세요.")
    redirect = f"http://127.0.0.1:{port}/"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES,
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})

    def serve():
        while "code" not in got and "error" not in got:
            srv.handle_request()

    def paste():
        # 예비 경로: 브라우저에 오류가 떠도 주소창에 code 가 들어 있다 — 그 주소를 붙여넣으면 된다.
        try:
            line = input()
        except EOFError:
            return
        code = _code_from(line)
        if code:
            got["code"] = code

    threading.Thread(target=serve, daemon=True).start()
    threading.Thread(target=paste, daemon=True).start()
    print("브라우저에서 승인하세요. 자동으로 열리지 않으면 이 주소를 여세요:\n", url)
    print("\n※ 승인 뒤 브라우저에 '사이트에 연결할 수 없음'이 떠도 괜찮습니다 — 그 창 **주소창의 주소 전체**를 복사해"
          " 여기 붙여넣고 Enter 를 누르세요.\n")
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        time.sleep(0.5)
    if "error" in got:
        sys.exit("승인이 취소됐습니다(" + got["error"] + ") — 다시 실행하세요.")
    body = urllib.parse.urlencode({"code": got["code"], "client_id": cid, "client_secret": sec,
                                   "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    try:
        with urllib.request.urlopen("https://oauth2.googleapis.com/token", body) as r:
            tok = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit("토큰 교환 실패 " + str(e.code) + ": " + e.read().decode()[:300]
                 + "\n(코드는 1회용·10분 유효 — 명령을 처음부터 다시 실행하세요)")
    rt = tok.get("refresh_token")
    if not rt:
        print("refresh_token이 없습니다 — 이미 승인된 앱이면 https://myaccount.google.com/permissions 에서 접근 권한을 지우고 다시 실행하세요.")
        return
    print("\n=== GitHub Secrets 에 넣을 값 ===")
    print("YT_CLIENT_ID     =", cid)
    print("YT_CLIENT_SECRET =", sec)
    print("YT_REFRESH_TOKEN =", rt)
    print("================================\n(이 값은 어디에도 저장되지 않았습니다. 복사 후 터미널을 닫으세요.)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용: python yt_auth.py <client_secret.json>"); sys.exit(1)
    main(sys.argv[1])

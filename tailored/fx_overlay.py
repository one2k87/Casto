"""fx 모듈 v1.1 — 그림·클립 위에 방향이 고정된 효과를 덧그린다(AI가 방향을 틀리게 그리는 것을 막기 위해).

사용: python3 fx_overlay.py <in.mp4|in.png> <out.mp4> '<효과 JSON 목록>' [--sec 4]
  좌표는 화면 비율(0~1). t=[시작초, 끝초].
  scent_trail   {"type":"scent_trail","t":[0,3],"from":[0.75,0.6],"to":[0.42,0.45],"color":"#ffe7a3"}
                음식(from, 굵음) → 코(to, 가늘어짐)로 물결 줄 2~3개가 흘러 들어간다. 방향은 항상 from→to.
  steam_breath  {"type":"steam_breath","t":[0,3],"at":[0.45,0.5],"dir":[1,-0.3],"color":"#ffffff"}
                입·코(at)에서 dir 쪽으로 김이 퐁퐁 나와 커지며 사라진다.
  flash_whiteout{"type":"flash_whiteout","t":[0,2.5],"in":0.6,"out":0.6,"snow":true}
                하얗게 덮였다가(눈보라) 걷힌다. 1화 w1·w4 전환용.
워터마크(오른쪽 아래)는 건드리지 않는다: 효과는 화면 오른쪽 아래 12% 구역에 그리지 않는다.
"""
import json, math, random, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter


def probe(p):
    o = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height,r_frame_rate:format=duration", "-of", "json", p]).decode()
    j = json.loads(o); s = j["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return s["width"], s["height"], float(n) / float(d), float(j["format"].get("duration", 0) or 0)


def rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def env(t, a, b, fade=0.35):
    if t < a or t > b: return 0.0
    return max(0.0, min(1.0, (t - a) / fade, (b - t) / fade))


def safe_mask(W, H):
    """워터마크(오른쪽 아래 「Veo」) 자리는 효과를 비운다 — 가장자리를 부드럽게 해서 네모가 보이지 않게."""
    m = Image.new("L", (W, H), 255); ImageDraw.Draw(m).rectangle([int(W * 0.935), int(H * 0.925), W, H], fill=0)
    return m.filter(ImageFilter.GaussianBlur(H * 0.025))


def scent(dr, W, H, t, e, k):
    (fx, fy), (nx, ny) = e["from"], e["to"]; c = rgb(e.get("color", "#ffe7a3"))
    x0, y0, x1, y1 = fx * W, fy * H, nx * W, ny * H
    L = math.hypot(x1 - x0, y1 - y0) or 1; px, py = -(y1 - y0) / L, (x1 - x0) / L
    for j, off in enumerate((-0.05, 0.0, 0.05)):
        pts = []
        for i in range(41):
            u = i / 40
            # 흘러 들어가는 물결: 위상이 시간에 따라 from→to 쪽으로 이동
            amp = H * 0.022 * (1 - 0.7 * u)
            w = math.sin(u * 9 - t * 7 + j * 1.7) * amp
            spread = off * H * (1 - u)  # 음식 쪽은 퍼지고 코 쪽에서 모임
            pts.append((x0 + (x1 - x0) * u + px * (w + spread), y0 + (y1 - y0) * u + py * (w + spread)))
        for i in range(40):
            u = i / 40
            width = max(3, int(H * 0.02 * (1 - 0.7 * u)))  # 음식 쪽 굵고 코 쪽 가늘다
            dr.line([pts[i], pts[i + 1]], fill=c + (int(110 * k),), width=width + 6)  # 은은한 번짐
            dr.line([pts[i], pts[i + 1]], fill=c + (int(235 * k * (0.6 + 0.4 * (1 - u))),), width=width)
        for m in range(3):  # 줄을 따라 코 쪽으로 이동하는 냄새 알갱이 — 방향이 한눈에 보이게
            u = (t * 0.45 + m / 3 + j * 0.11) % 1
            i = min(39, int(u * 40)); x, y = pts[i]; r = H * 0.016 * (1 - 0.6 * u)
            dr.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, int(250 * k)))


def steam(dr, W, H, t, e, k):
    ax, ay = e["at"]; dx, dy = e.get("dir", [1, -0.3]); c = rgb(e.get("color", "#ffffff"))
    n = math.hypot(dx, dy) or 1; dx, dy = dx / n, dy / n
    for i in range(5):
        ph = (t * 0.9 + i / 5) % 1
        r = H * (0.012 + 0.05 * ph); d = H * 0.16 * ph
        x, y = ax * W + dx * d, ay * H + dy * d - H * 0.03 * ph
        a = int(200 * k * (1 - ph))
        dr.ellipse([x - r, y - r, x + r, y + r], fill=c + (a,))


def whiteout(img, W, H, t, e, k, flakes):
    a, b = e["t"]; fi, fo = e.get("in", 0.6), e.get("out", 0.6)
    if t < a or t > b: return
    lv = min(1.0, (t - a) / fi, (b - t) / fo)
    ov = Image.new("RGBA", (W, H), (245, 248, 255, int(250 * lv)))
    if e.get("snow", True):
        d = ImageDraw.Draw(ov)
        for (sx, sy, sp, sr) in flakes:
            x = (sx * W + t * sp * W * 0.6) % W; y = (sy * H + t * sp * H * 0.25) % H
            d.ellipse([x - sr, y - sr, x + sr, y + sr], fill=(255, 255, 255, 255))
    img.alpha_composite(ov)


def main(src, out, effects, sec=None):
    still = src.lower().endswith((".png", ".jpg", ".jpeg"))
    if still:
        W, H = Image.open(src).size; fps, dur = 30.0, float(sec or 4)
        inp = ["-loop", "1", "-t", f"{dur}", "-i", src]
    else:
        W, H, fps, dur = probe(src); inp = ["-i", src]
    N = int(round(dur * fps)); mask = safe_mask(W, H); random.seed(7)
    flakes = [(random.random(), random.random(), 0.3 + random.random(), 1 + random.random() * H * 0.006) for _ in range(160)]
    cmd = ["ffmpeg", "-v", "error", "-y", *inp, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
           "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]", "-map", "[v]"]
    if not still: cmd += ["-map", "0:a?", "-c:a", "copy"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-movflags", "+faststart", "-t", f"{dur:.3f}", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    blank = Image.new("RGBA", (W, H), (0, 0, 0, 0)).tobytes()
    for f in range(N):
        t = f / fps
        act = [e for e in effects if e["t"][0] <= t <= e["t"][1]]
        if not act:
            p.stdin.write(blank); continue
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dr = ImageDraw.Draw(lay)
        for e in act:
            k = env(t, *e["t"])
            if e["type"] == "scent_trail": scent(dr, W, H, t, e, k)
            elif e["type"] == "steam_breath": steam(dr, W, H, t, e, k)
        lay = lay.filter(ImageFilter.GaussianBlur(H * 0.0025))
        for e in act:
            if e["type"] == "flash_whiteout": whiteout(lay, W, H, t, e, 1, flakes)
        from PIL import ImageChops; lay.putalpha(ImageChops.multiply(lay.getchannel("A"), mask))  # 워터마크 구역은 항상 비움
        p.stdin.write(lay.tobytes())
    p.stdin.close(); p.wait()
    if p.returncode: sys.exit(p.returncode)
    print("fx 완성", out, f"{dur:.1f}s", [e["type"] for e in effects])


if __name__ == "__main__":
    a = sys.argv[1:]; sec = None
    if "--sec" in a: i = a.index("--sec"); sec = a[i + 1]; del a[i:i + 2]
    main(a[0], a[1], json.loads(a[2]), sec)

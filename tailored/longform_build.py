"""Tailored 롱폼(가로 16:9) 한 화 / 시즌 묶음 렌더.

사용:
  python3 longform_build.py <ep> [--clips <가로 클립 폴더>] [--out out.mp4] [--sec 6]
  python3 longform_build.py --season s1e01,s1e02,... --out season1.mp4   (화별 결과를 이어 붙임)

- 컷 순서는 episodes/<ep>/conti.json 그대로, c00(쇼츠용 콜드 오픈)은 뺀다.
- 가로 클립(<clips>/<ep>/<cut>.mp4, Flow 720p)이 있으면 1배속으로 앞 --sec 초까지 쓴다(queue.json use_sec가 있으면 그 초까지). 화면은 자르지 않는다(워터마크 유지).
- 없으면 임시 화면: 세로 그림을 가운데 두고 양옆은 같은 그림을 흐리게 — 클립이 모일수록 진짜 화면으로 바뀐다.
- 세로 영상 컷(엔딩 실제 영상)도 같은 임시 화면 방식으로 가운데에 둔다.
- 소리: 그 화 쇼츠 완성본의 음악을 반복해 길이에 맞추고 0.45배, 끝 2초 페이드아웃.
- 자막: 컷 narr로 ko·en·ja·es SRT를 새 시간에 맞춰 만든다(<out>.<lang>.srt).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1280, 720, 30
ENC = ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def sh(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode())


def pillar(src_args, sec, out, zoom=True):
    """세로 그림/영상을 가로 화면 가운데에, 양옆은 같은 그림 흐리게."""
    z = f",zoompan=z='min(1+0.0006*on,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}" if zoom else ""
    f = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,eq=brightness=-0.07[bg];"
         f"[0:v]scale=-2:{H}[fg];[bg][fg]overlay=(W-w)/2:0,setsar=1{z}[v]")
    sh(*src_args, "-t", f"{sec:.2f}", "-filter_complex", f, "-map", "[v]", *ENC, out)


def build_episode(ep, clips, out, sec):
    ed = os.path.join(ROOT, "episodes", ep)
    conti = json.load(open(os.path.join(ed, "conti.json"), encoding="utf-8"))
    tmp = tempfile.mkdtemp(prefix=f"lf_{ep}_")
    # 검수(QA 2단계)에서 「앞 N초만」으로 정한 컷: longform/queue.json 의 use_sec
    qp = os.path.join(ROOT, "longform", "queue.json")
    use = {i["cut"]: i["use_sec"] for i in (json.load(open(qp, encoding="utf-8"))["items"] if os.path.exists(qp) else [])
           if i.get("ep") == ep and i.get("use_sec")}
    segs, subs, t, real = [], [], 0.0, 0
    for c in conti["cuts"]:
        if c["id"] == "c00":
            continue
        seg = os.path.join(tmp, f"{c['id']}.mp4")
        wide = os.path.join(clips, ep, f"{c['id']}.mp4") if clips else ""
        if wide and os.path.exists(wide):
            d = min(sec, use.get(c["id"], sec), dur(wide))
            sh("-i", wide, "-t", f"{d:.2f}", "-vf", f"scale={W}:{H},setsar=1", *ENC, seg)
            real += 1
        elif c.get("video") and os.path.exists(os.path.join(ed, c["video"])):
            v = os.path.join(ed, c["video"])
            d = dur(v)
            pillar(["-i", v], d, seg, zoom=False)
        else:
            d = max(3.5, c["sec"] * 1.5)
            pillar(["-loop", "1", "-i", os.path.join(ed, c["img"])], d, seg)
        d = dur(seg)
        segs.append(seg)
        if c.get("narr"):
            subs.append((t, t + d, c["narr"]))
        t += d
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{s}'\n" for s in segs))
    vid = os.path.join(tmp, "v.mp4")
    sh("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid)
    music = os.path.join(ed, f"{ep}.mp4")
    # 쇼츠 끝의 무음(엔딩 뒤)을 잘라 낸 한 바퀴를 만들어 반복 — 이음매에서 2초씩 끊기지 않게
    md = dur(music)
    log = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{max(md - 8, 0):.2f}", "-i", music, "-af", "silencedetect=n=-45dB:d=0.3",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x.split("silence_start: ")[1].split()[0]) for x in log.splitlines() if "silence_start" in x]
    end = max(md - 8, 0) + starts[0] if starts else md
    loop = os.path.join(tmp, "loop.wav")
    sh("-i", music, "-vn", "-t", f"{end:.2f}", "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(end - 0.6, 0):.2f}:d=0.6", loop)
    sh("-i", vid, "-stream_loop", "-1", "-i", loop, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
       "-af", f"volume=0.45,afade=t=out:st={max(t - 2, 0):.2f}:d=2", "-c:a", "aac", "-b:a", "160k", "-t", f"{t:.2f}", out)

    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    for lang in ("ko", "en", "ja", "es"):
        with open(f"{os.path.splitext(out)[0]}.{lang}.srt", "w", encoding="utf-8") as f:
            for i, (a, b, n) in enumerate([s for s in subs if s[2].get(lang)], 1):
                f.write(f"{i}\n{ts(a + 0.15)} --> {ts(b - 0.15)}\n{n[lang]}\n\n")
    print(f"[longform] {ep}: {t:.1f}s, 가로 클립 {real}컷 / 임시 화면 {len(segs) - real}컷 → {out}")
    return out


def build_season(parts, out):
    lst = out + ".list.txt"
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    sh("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    os.remove(lst)
    print(f"[longform] 시즌 묶음 {dur(out):.1f}s → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("ep", nargs="?")
    ap.add_argument("--clips", default=os.path.join(ROOT, "longform"))
    ap.add_argument("--out")
    ap.add_argument("--sec", type=float, default=6.0)
    ap.add_argument("--season")
    a = ap.parse_args()
    if a.season:
        eps = a.season.split(",")
        parts = [build_episode(e, a.clips, f"/tmp/lf_{e}.mp4", a.sec) for e in eps]
        build_season(parts, a.out or "season_longform.mp4")
    else:
        build_episode(a.ep, a.clips, a.out or f"{a.ep}_longform.mp4", a.sec)

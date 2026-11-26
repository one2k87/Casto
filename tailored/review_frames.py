"""review 모듈 — 화면 검수용 프레임 묶음 만들기.
완성 영상에서 컷마다 시작·가운데·끝 3장을 뽑아 한 장에 9컷씩 모은다(컷 id 표시).
사용: python3 review_frames.py <ep_dir(conti.json 있는 폴더)> <완성 mp4> <출력 폴더>
→ 출력 폴더의 sheetN.jpg 를 캐스토가 직접 보고 modules/review/rules.json 체크 항목으로 판정, episodes/<화>/review.json 에 기록.
"""
import json, os, subprocess, sys

ep_dir, video, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
cuts = json.load(open(os.path.join(ep_dir, "conti.json"), encoding="utf-8"))["cuts"]
FPS = 30
t, ids = 0.0, []
for c in cuts:
    d = max(1, round(c["sec"] * FPS)) / FPS
    for k, x in enumerate([t + 0.1, t + d / 2, t + d - 0.12]):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{x:.2f}", "-i", video, "-frames:v", "1", "-vf",
                        f"scale=180:320,drawtext=text='{c['id']}':x=6:y=6:fontsize=22:fontcolor=yellow:box=1:boxcolor=black@0.6",
                        f"{out}/{c['id']}_{k}.png"], check=True)
    ids.append(c["id"])
    t += d
for s in range(0, len(ids), 9):
    grp = ids[s:s + 9]
    ins = sum([["-i", f"{out}/{cid}_{k}.png"] for cid in grp for k in range(3)], [])
    n = len(grp) * 3
    lay = "|".join(f"{(i % 9) * 180}_{(i // 9) * 320}" for i in range(n))
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", f"xstack=inputs={n}:layout={lay}:fill=black",
                    f"{out}/sheet{s // 9 + 1}.jpg"], check=True)
print("검수용 묶음", out)

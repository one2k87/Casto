"""Flow 클립으로 한 화를 다시 렌더한다.
사용: python3 flow_build.py s1e02 <c00이 빌려 쓸 컷 id> <그 클립에서 건너뛸 초>
- 입력 클립: /mnt/user-data/uploads/SolvUp_Workspace/Casto/tailored/episodes/<ep>/flow/cNN_flow.mp4
- 첫 프레임을 cNN.jpg와 대조해 컷이 맞는지 확인(어긋나면 중단)
- 2배속·무음으로 바꿔 콘티 video에 연결, 엔딩 영상 컷은 그대로
- 소리는 원본 완성본에서 가져와 음악 0.45배
"""
import json, os, shutil, subprocess, sys
import numpy as np
from PIL import Image

ep, c00src, skip = sys.argv[1], sys.argv[2], float(sys.argv[3])
# 검수(review 모듈) 결과 반영: {"c12": "still", "c05": 3.0} — still=정지 그림(카메라 연출), 숫자=원본 클립 앞 N초만 컷 길이에 맞춰 사용
OVR = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
SRC = f"/mnt/user-data/uploads/SolvUp_Workspace/Casto/tailored/episodes/{ep}/flow"
ORIG = f"/home/claude/Casto/tailored/episodes/{ep}"
WORK = f"/home/claude/e3/{ep}_flow"
conti = json.load(open(f"{ORIG}/conti.json"))
ids = [c["id"] for c in conti["cuts"] if not c.get("video") and c["id"] != "c00"]

def thumb(path):
    return np.asarray(Image.open(path).convert("L").resize((90, 160)), float)

refs = {i: thumb(f"{ORIG}/{next(c['img'] for c in conti['cuts'] if c['id']==i)}") for i in ids}
bad = []
for i in ids:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{SRC}/{i}_flow.mp4", "-frames:v", "1", "-vf", "scale=90:160", "/tmp/claude-0/f.png"], check=True)
    a = thumb("/tmp/claude-0/f.png")
    best = min(refs, key=lambda k: np.abs(a - refs[k]).mean())
    if best != i:
        bad.append((i, best))
if bad:
    sys.exit(f"컷 불일치: {bad}")
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree(ORIG, WORK)
os.makedirs(f"{WORK}/flow", exist_ok=True)
enc = ["-an", "-vf", "setpts=PTS/2", "-r", "30", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast"]
secs = {c["id"]: c["sec"] for c in conti["cuts"]}
for i in ids:
    if OVR.get(i) == "still":
        continue
    e = list(enc)
    if isinstance(OVR.get(i), (int, float)):
        e[e.index("setpts=PTS/2")] = f"setpts=PTS*{secs[i] / float(OVR[i]):.4f}"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{SRC}/{i}_flow.mp4", *e, f"{WORK}/flow/{i}.mp4"], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(skip), "-i", f"{SRC}/{c00src}_flow.mp4", *enc, f"{WORK}/flow/c00.mp4"], check=True)
for c in conti["cuts"]:
    if not c.get("video") and OVR.get(c["id"]) != "still":
        c["video"] = f"flow/{c['id']}.mp4"
json.dump(conti, open(f"{WORK}/conti.json", "w"), ensure_ascii=False, indent=1)
sys.path.insert(0, "/home/claude/Casto")
os.chdir("/home/claude/Casto")
import tailored_render_fx as F
tmp = f"/home/claude/e3/{ep}_flowanim_raw.mp4"
F.render(WORK, tmp, f"{ORIG}/{ep}.mp4", depth=False, sfx=False)
out = f"/home/claude/e3/{ep}_flowanim.mp4"
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:v", "copy", "-af", "volume=0.45", "-c:a", "aac", "-b:a", "160k", out], check=True)
os.remove(tmp)
print("완성", out)

"""원본 에셋에서 표정 프레임을 굽는다 — 생성 할당량 0장.

    python make_faces.py

`faces.parts()`가 얼굴을 못 읽는 에셋은 조용히 건너뛴다(돋보기·별눈 등).
결과가 마음에 안 들면 이 파일을 지우고 다시 돌리면 된다 — 원본은 안 건드린다.
"""
import os

import faces
import visuals

JOBS = [("idle", "blink", faces.blink), ("idle", "wide", faces.wide)]


def main() -> None:
    made, skipped = [], []
    for base, kind, fn in JOBS:
        src = visuals.koki(base)
        if src is None:
            skipped.append(f"{base}({kind}): 원본 없음")
            continue
        out = fn(src)
        if out is None:
            skipped.append(f"{base}({kind}): 얼굴을 못 읽음")
            continue
        name = visuals.EXTRA.get(kind)
        if not name:
            skipped.append(f"{kind}: visuals.EXTRA에 이름이 없음")
            continue
        p = os.path.join(visuals.ASSET_DIR, name)
        out.save(p)
        made.append(p)
    for m in made:
        print(f"[faces] 구움 → {m}")
    for s in skipped:
        print(f"[faces] 건너뜀 — {s}")


if __name__ == "__main__":
    main()

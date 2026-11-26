"""쇼츠 맨 앞 3.5초에 「자막을 켜면 이야기가 보여요」 안내 한 줄을 얹는다(사용자 결정 11/26).
이야기는 자막 트랙(ko·en·ja·es)에 있으므로 화면 자막을 따로 넣지 않고, 켜는 방법만 알린다.
사용: python3 cc_notice.py <in.mp4> <out.mp4>
"""
import os
import subprocess
import sys
import tempfile

ASS = r"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CC,Noto Sans CJK KR Black,54,&H00FFFFFF,&H00FFFFFF,&H00B8A0E6,&H00000000,0,0,0,0,100,100,0,0,3,16,0,8,60,60,250,1
Style: CCen,Noto Sans CJK KR Black,40,&H00FFFFFF,&H00FFFFFF,&H00B8A0E6,&H00000000,0,0,0,0,100,100,0,0,3,12,0,8,60,60,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.50,CC,,0,0,0,,{\fad(150,350)}자막(CC)을 켜면 이야기가 보여요
Dialogue: 0,0:00:00.00,0:00:03.50,CCen,,0,0,0,,{\fad(150,350)}Turn on captions (CC) to follow the story
"""


def main(src, out):
    d = tempfile.mkdtemp()
    a = os.path.join(d, "cc.ass")
    open(a, "w", encoding="utf-8").write(ASS)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"ass={a}", "-c:v", "libx264", "-preset", "medium",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", out], check=True)
    print("완성", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

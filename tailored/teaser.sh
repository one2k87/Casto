#!/bin/bash
# $1 in.mp4  $2 out.mp4  $3 엔딩 영상 컷 시작(초) — 그 2초를 맨 앞에 붙인다
ffmpeg -y -v error -ss "$3" -t 2 -i "$1" -i "$1" -filter_complex "[0:a]afade=t=out:st=1.7:d=0.3[ta];[0:v][ta][1:v][1:a]concat=n=2:v=1:a=1[v][a]" -map "[v]" -map "[a]" -c:v libx264 -crf 21 -preset veryfast -pix_fmt yuv420p -c:a aac -b:a 160k "$2"

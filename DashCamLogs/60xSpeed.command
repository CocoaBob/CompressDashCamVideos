#!/bin/bash
cd "$(dirname "$0")"
ffmpeg -i 2024_0807_172134_00_a.mp4 -filter_complex "[0:v]setpts=(PTS-STARTPTS)/60,fps=60[v];[0:a]atempo=2.0,atempo=2.0,atempo=2.0,atempo=2.0,atempo=2.0,atempo=1.875[a]" -map "[v]" -map "[a]" -vtag hvc1 -c:v libx265 -crf 30 -c:a aac -ar 16000 -b:a 48k 2024_0807_172134_00_a_60x.mp4

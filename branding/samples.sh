#!/usr/bin/env bash
# samples.sh - the example video and picture every user finds in ~/Videos and
# ~/Pictures (modules/tutorial.nix; the tutorial opens them too): a 30 s clip
# of the Earth at night (NASA's Black Marble, public domain) from
# file-examples.com, and a frame of it. Run from the repo root to fetch them
# again:
#
#   nix shell nixpkgs#ffmpeg nixpkgs#curl -c branding/samples.sh
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p samples
curl -fsSL -A "Mozilla/5.0" -o samples/example.mp4 \
    "https://file-examples.com/storage/fe43bf4ad66ac5e5f9c9dc3/2017/04/file_example_MP4_480_1_5MG.mp4"
# Europe and Africa, 5 s in; twice the video's 480x270.
ffmpeg -v error -y -ss 5 -i samples/example.mp4 -frames:v 1 -vf "scale=960:540:flags=lanczos" samples/example.png
ls -l samples

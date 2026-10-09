#!/usr/bin/env python3
"""mos-tutorial-encode WORK OUT FONTDIR - the tutorial's recording -> OUT.mp4
(scripts/mos-tutorial-video.sh runs it).

WORK holds what the recorder VM saved: raw.mkv (screen and sound), start (when
the recording started, seconds since the epoch) and cues.tsv (the tour's
spoken lines, "start<TAB>seconds<TAB>text", waits it marked to leave out,
"cut<TAB>start<TAB>end", and still moments to keep whole, "hold<TAB>start<TAB>end").

The video starts shortly before the first spoken line and leaves out:
  - the waits the tour marked (Brave starting and closing);
  - pauses: over a second of silence while nothing changes on the screen
    (the top bar, whose CPU reading ticks, aside); a little of each is kept,
    and all of it where the tour marked a hold (a page left up to be seen).
The spoken lines are burnt in as subtitles: one line each, all the same size.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
try:
    from mos_i18n import translator  # noqa: E402
    T = translator("mos-tour")
except ImportError:  # run on its own from the Nix store (flake.nix): English
    def T(text):
        return text

PAUSE = 1.0  # silence + still screen at least this long is a pause
KEEP = 0.35  # seconds of a pause kept on each side
PANEL = 40  # px of the top bar left out when looking for changes
W, H = 1920, 1080


def ffmpeg(*args, capture=False):
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", *args]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stderr
    subprocess.run(cmd, check=True)


def pauses(raw, skip):
    """Stretches with no sound and no change on the screen, from skip on."""
    log = ffmpeg("-nostats", "-ss", f"{skip:.3f}", "-i", raw,
                 # mpdecimate keeps only frames that differ from the last kept
                 # one, in any 8x8 block: a typed letter counts, noise doesn't.
                 "-vf", f"crop=iw:ih-{PANEL}:0:{PANEL},mpdecimate=max=0:hi=768:lo=320:frac=0,showinfo",
                 "-af", f"silencedetect=n=-45dB:d={PAUSE}", "-f", "null", "-", capture=True)
    changes, silences, start = [], [], None
    for line in log.splitlines():
        if "showinfo" in line and (m := re.search(r"pts_time:([\d.]+)", line)):
            changes.append(float(m.group(1)))
        elif m := re.search(r"silence_start: ([\d.]+)", line):
            start = float(m.group(1))
        elif (m := re.search(r"silence_end: ([\d.]+)", line)) and start is not None:
            silences.append((start, float(m.group(1))))
    still = [(a, b) for a, b in zip(changes, changes[1:]) if b - a >= PAUSE]
    out = []
    for a, b in still:
        for c, d in silences:
            x, y = max(a, c) + KEEP, min(b, d) - KEEP
            if y - x > 0.25:
                out.append((x, y))
    return out


def minus(cuts, holds):
    """The cuts with the held stretches taken out of them."""
    for h0, h1 in holds:
        out = []
        for a, b in cuts:
            if b <= h0 or a >= h1:
                out.append((a, b))
                continue
            if a < h0:
                out.append((a, h0))
            if b > h1:
                out.append((h1, b))
        cuts = out
    return cuts


def merge(cuts):
    out = []
    for a, b in sorted(cuts):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def ass_time(s):
    cs = round(max(0.0, s) * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def main(work, out, fontdir):
    t0 = float(open(f"{work}/start").read())
    cues, marked, holds = [], [], []
    for line in open(f"{work}/cues.tsv"):
        a, b, c = line.rstrip("\n").split("\t", 2)
        if a == "cut":
            marked.append((float(b) - t0, float(c) - t0))
        elif a == "hold":
            holds.append((float(b) - t0, float(c) - t0))
        else:
            cues.append((float(a) - t0, float(b), c))
    skip = max(0.0, cues[0][0] - 2.5)
    found = minus(pauses(f"{work}/raw.mkv", skip), [(a - skip, b - skip) for a, b in holds])
    cuts = merge([(a - skip, b - skip) for a, b in marked if b > a] + found)
    print(T("Leaving out {count} waits and pauses, {seconds} s in all.").format(
        count=len(cuts), seconds=f"{sum(b - a for a, b in cuts):.0f}"))

    def shift(t):
        """Where a moment of the recording ends up once the cuts are gone."""
        t -= skip
        # Every cut before t, measured on the recording's own clock.
        return t - sum(min(t, b) - a for a, b in cuts if t > a)

    # One size for every line: the longest one fits the width (DejaVu Sans
    # averages about 0.46 em per character), at most 40 px.
    longest = max(len(text) for _, _, text in cues)
    size = min(40, int((W - 160) / (0.46 * longest)))
    with open(f"{work}/subs.ass", "w") as f:
        f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size},&H00FFFFFF,&H00FFFFFF,&H64000000,&H64000000,0,0,0,0,100,100,0,0,3,10,0,2,40,40,36,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
        for i, (start, dur, text) in enumerate(cues):
            end = start + dur
            if i + 1 < len(cues):
                end = min(end, cues[i + 1][0] - 0.05)
            f.write(f"Dialogue: 0,{ass_time(shift(start))},{ass_time(shift(end))},Default,,0,0,0,,{text}\n")

    # One select per 40 cuts: ffmpeg's expression parser runs out of memory on
    # one expression with a hundred or more. Each sees the original times
    # (setpts renumbers only after the last).
    groups = ["+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in cuts[i:i + 40])
              for i in range(0, len(cuts), 40)]
    vsel = "".join(f"select='not({g})'," for g in groups)
    asel = "".join(f"aselect='not({g})'," for g in groups)
    ffmpeg("-y", "-loglevel", "error", "-stats", "-ss", f"{skip:.3f}", "-i", f"{work}/raw.mkv",
           "-filter_complex",
           f"[0:v]{vsel}setpts=N/FRAME_RATE/TB,ass={work}/subs.ass:fontsdir={fontdir}[v];"
           f"[0:a]{asel}asetpts=N/SR/TB[a]",
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-movflags", "+faststart", out)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(T(__doc__).strip())
    try:
        main(*sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit(130)

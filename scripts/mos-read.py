"""mos-read: read text aloud with Piper (offline), in a small terminal UI.

  mos-read            read the clipboard (or the mouse selection if it is empty)
  mos-read FILE       read a text file
  ... | mos-read -    read standard input

Keys: Space pause/resume · ←/→ previous/next sentence · +/- speed · q/Esc stop

Only one voice speaks at a time: it waits for `say` (or another reader) to
finish first. Speech is made one sentence at a time (the next one is prepared while the
current one plays) and fed to PipeWire in small slices, so pausing, skipping
and stopping react within a fraction of a second.
"""
import curses
import fcntl
import os
import re
import subprocess
import sys
import textwrap
import threading
import time

# The look shared by MeccanicOS TUIs: MECCANICOS_PYLIB from the Nix wrapper, else next to this file.
sys.path.insert(0, os.environ.get("MECCANICOS_PYLIB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import mos_tui as tui  # noqa: E402

# 1.0x: a bit faster than Piper's own pace, as `say` (voice.nix).
LENGTH_SCALE = 0.8

VOICE = os.environ.get("PIPER_VOICE") or os.environ["MECCANICOS_READ_VOICE"]
PW_PLAY = os.environ.get("MECCANICOS_READ_PWPLAY", "pw-play")
XCLIP = os.environ.get("MECCANICOS_READ_XCLIP", "xclip")
AHEAD = 0.15  # seconds of audio queued ahead of playback (pause latency)
CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "mos-read")
LAST = os.path.join(CACHE, "last.txt")  # the last text read, for reading again
SPEECH_LOCK = os.environ.get("MECCANICOS_SPEECH_LOCK") or os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "mos-speech.lock")
# Words Piper says wrong, spelled as they sound (as in `say`).
SOUNDS_LIKE = [(re.compile(r"\bnixpkgs\b", re.I), "nix packages"), (re.compile(r"\bMeccanicOS\b"), "Meccanic O S")]


def speakable(text):
    for word, sound in SOUNDS_LIKE:
        text = word.sub(sound, text)
    return text


def get_text(argv):
    if len(argv) > 1 and argv[1] in ("-h", "--help", "help"):
        print(__doc__.strip())
        sys.exit(0)
    if len(argv) > 1:
        if argv[1] == "-":
            text = sys.stdin.read()
            # Keys come from the terminal, not from the pipe.
            tty = os.open("/dev/tty", os.O_RDONLY)
            os.dup2(tty, 0)
            return text
        with open(argv[1], errors="replace") as f:
            return f.read()
    # Reading a selection never changes it (xclip -o only asks its owner).
    for selection in ("clipboard", "primary"):
        try:
            text = subprocess.run(
                [XCLIP, "-o", "-selection", selection],
                capture_output=True, text=True, timeout=3,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            text = ""
        if text.strip():
            return text
    # Nothing selected (e.g. the app you copied from has closed): read the
    # last text again, so "Read from clipboard" works every time.
    try:
        with open(LAST, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def remember(text):
    try:
        os.makedirs(CACHE, exist_ok=True)
        with open(LAST, "w") as f:
            f.write(text)
        os.chmod(LAST, 0o600)
    except OSError:
        pass


def split_sentences(text):
    sentences = []
    for para in re.split(r"\n\s*\n", text.replace("\r", "")):
        para = " ".join(para.split())
        if para:
            sentences += [s for s in re.split(r"(?<=[.!?…])\s+", para) if s]
    return sentences


class Reader:
    """Synthesis (prefetch) and playback threads around shared state."""

    def __init__(self, voice, sentences):
        self.voice = voice
        self.sentences = sentences
        self.rate = voice.config.sample_rate
        self.idx = 0
        self.speed = 1.0
        self.paused = False
        self.finished = False
        self.quit = False
        self.gen = 0  # bumped on skip/speed change: abandons the current audio
        self.cache = {}
        self.cond = threading.Condition()

    # -- controls (called from the UI thread) --
    def jump(self, delta):
        with self.cond:
            self.idx = max(0, min(len(self.sentences) - 1, self.idx + delta))
            self.gen += 1
            self.cond.notify_all()

    def change_speed(self, delta):
        with self.cond:
            self.speed = round(max(0.5, min(2.0, self.speed + delta)), 1)
            self.gen += 1
            self.cond.notify_all()

    def stop(self):
        with self.cond:
            self.quit = True
            self.cond.notify_all()

    # -- synthesis: keep the current and the next sentence ready --
    def prefetch_loop(self):
        from piper import SynthesisConfig

        while True:
            with self.cond:
                if self.quit:
                    return
                want = [(i, self.speed) for i in (self.idx, self.idx + 1) if i < len(self.sentences)]
                todo = next((k for k in want if k not in self.cache), None)
                for k in list(self.cache):
                    if k not in want:
                        del self.cache[k]
                if todo is None:
                    self.cond.wait(0.2)
                    continue
            i, speed = todo
            cfg = SynthesisConfig(length_scale=LENGTH_SCALE / speed)
            audio = b"".join(c.audio_int16_bytes for c in self.voice.synthesize(speakable(self.sentences[i]), syn_config=cfg))
            with self.cond:
                self.cache[todo] = audio
                self.cond.notify_all()

    # -- playback --
    def _player(self):
        return subprocess.Popen(
            # --raw: PCM on stdin (without it pw-play expects a sound file
            # and plays nothing).
            [PW_PLAY, "--raw", "--rate", str(self.rate), "--channels", "1", "--format", "s16",
             "--latency", "50ms", "-"],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def play_loop(self):
        proc = None
        slice_bytes = self.rate * 2 // 20  # 50 ms
        while True:
            with self.cond:
                while not self.quit and (self.idx, self.speed) not in self.cache:
                    if self.idx >= len(self.sentences):
                        break
                    self.cond.wait(0.1)
                if self.quit or self.idx >= len(self.sentences):
                    break
                i, gen = self.idx, self.gen
                audio = self.cache[(i, self.speed)]
            proc = proc or self._player()
            pos, played, start = 0, 0.0, time.monotonic()
            interrupted = False
            while pos < len(audio):
                if self.quit or self.gen != gen:
                    interrupted = True
                    break
                if self.paused:
                    time.sleep(0.05)
                    start = time.monotonic() - played
                    continue
                ahead = played - (time.monotonic() - start)
                if ahead > AHEAD:
                    time.sleep(ahead - AHEAD)
                    continue
                piece = audio[pos:pos + slice_bytes]
                try:
                    proc.stdin.write(piece)
                    proc.stdin.flush()
                except BrokenPipeError:
                    proc = self._player()
                    continue
                pos += len(piece)
                played += len(piece) / (self.rate * 2)
            if interrupted:
                proc.kill()  # drop what is already queued
                proc.wait()
                proc = None
                continue
            with self.cond:
                if self.gen == gen and self.idx == i:
                    self.idx += 1
                    self.cond.notify_all()
        if proc:
            if self.quit:
                proc.kill()
            else:
                proc.stdin.close()  # let the last sentence finish
            proc.wait()
        with self.cond:
            self.finished = True


def draw(scr, reader):
    h, w = scr.getmaxyx()
    scr.erase()
    width = max(20, w - 4)
    lines = []  # (text, sentence index)
    for n, s in enumerate(reader.sentences):
        for line in textwrap.wrap(s, width) or [""]:
            lines.append((line, n))
    body = max(1, h - 4)
    cur = min(reader.idx, len(reader.sentences) - 1)
    first = next(k for k, (_, n) in enumerate(lines) if n == cur)
    top = max(0, min(first - body // 3, len(lines) - body))
    state = "Paused" if reader.paused else "Reading"
    tui.bar(scr, 0, "Reading aloud · Piper / Amy", f"{state}  {cur + 1}/{len(reader.sentences)}  {reader.speed:.1f}x")
    for row, (text, n) in enumerate(lines[top:top + body]):
        # The sentence being read: dark on orange, as what has focus in every tool.
        if n == cur:
            tui.put(scr, 2 + row, 1, f" {text} ", tui.attr(tui.SELECTED))
        else:
            tui.put(scr, 2 + row, 2, text, tui.attr(tui.NORMAL))
    tui.keybar(scr, h - 1, [("Space", "pause"), ("←→", "sentence"), ("+/-", "speed"), ("q", "stop")])
    scr.refresh()


def ui(scr, reader):
    tui.init()
    scr.timeout(100)
    while not reader.finished:
        draw(scr, reader)
        key = scr.getch()
        if key in (ord("q"), ord("Q"), 27):
            reader.stop()
        elif key == ord(" "):
            reader.paused = not reader.paused
        elif key in (curses.KEY_RIGHT, ord("l"), ord("n")):
            reader.jump(+1)
        elif key in (curses.KEY_LEFT, ord("h"), ord("p")):
            reader.jump(-1)
        elif key in (ord("+"), ord("=")):
            reader.change_speed(+0.1)
        elif key == ord("-"):
            reader.change_speed(-0.1)


def main():
    text = get_text(sys.argv)
    sentences = split_sentences(text)
    if sentences:
        remember(text)
    if not sentences:
        print("Nothing to read: the clipboard is empty. Copy some text first.")
        time.sleep(3)
        return 1
    # Held until we exit: another voice waits for this one, and vice versa.
    lock = open(SPEECH_LOCK, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Waiting for the other voice to finish…", flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
    print("Loading the voice…", flush=True)
    # onnxruntime/espeak may print to stderr, which would scribble over the UI.
    log = os.path.join(CACHE, "mos-read.log")
    os.makedirs(CACHE, exist_ok=True)
    os.dup2(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644), 2)
    from piper import PiperVoice

    reader = Reader(PiperVoice.load(VOICE), sentences)
    threads = [threading.Thread(target=reader.prefetch_loop, daemon=True),
               threading.Thread(target=reader.play_loop, daemon=True)]
    for t in threads:
        t.start()
    try:
        curses.wrapper(ui, reader)
    except KeyboardInterrupt:
        reader.stop()
    threads[1].join(timeout=2)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:  # Ctrl+C: curses.wrapper has restored the terminal
        sys.exit(130)

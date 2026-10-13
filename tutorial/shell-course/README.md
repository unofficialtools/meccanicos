# The Linux shell, explained with mechanics

A 17-minute video for college freshmen, made with [Remotion](https://www.remotion.dev)
(React → video) and narrated offline by Piper, the voice that ships with MeccanicOS.

| | Chapter | The machine |
|---|---|---|
| | Welcome | the desktop, Super+Space and `terminal`; the machine shop: hardware, kernel, tools, and the shell as the control panel |
| 1 | The shell and the filesystem | one cabinet of drawers; yazi from `/` to `/home/student`; every top-level folder on one page |
| 2 | Help and shortcuts | Tab, ↑, Ctrl+R, Ctrl+C, `tldr`, `--help`, `man` |
| 3 | Files | `pwd ls cd mkdir touch cp mv cat`; editing in Jed, then `open`, `codium`, `print`; `rm` and `trash` |
| 4 | Pipes and redirection | the assembly line: `|`, `>`, `>>`, `grep`, `wc`, `sort` |
| 5 | Permissions and sudo | locks on the drawers: `rwx`, `chmod`, `sudo` |
| 6 | Environment and PATH | the tool wall searched in order: `$PATH`, `which`, `.bashrc` |
| 7 | Your first C++ program | `hello.cpp` in Jed, `nix-shell -p gcc` to borrow the compiler, `g++`, `./hello`, `exit` |
| 8 | Processes | the shop floor: `ps`, `pgrep`, `btop`, memory (`ps -o rss`, `/proc`, `free`), `kill` |
| 9 | Network and ports | a street address and loading docks: `ip`, `ping`, `curl`, `ss -tulpn`, `lsof` |
| 10 | Configuring MeccanicOS | `mos`, `mos-config`, `mos-doctor` |
| 11 | Disks | warehouses and rooms: `lsblk`, `df`, `du`, `ncdu`, `udisksctl`, a warning about `dd` |
| | Cheat sheet | every tool on one page |

## Make it

```sh
npm install
npm run voice      # Piper reads every scene (public/audio/), timings in src/durations.json
npm run studio     # preview in the browser, scene by scene
npm run render     # out/shell-course.mp4
```

`npm run voice` needs `piper` and `PIPER_VOICE` (both set on MeccanicOS); it
only re-reads scenes whose text changed. Rendering uses the system's Brave or
Chromium (`remotion.config.ts`; `REMOTION_BROWSER=/path` to pick one), because
Remotion's own headless Chrome doesn't run on NixOS.

## Change it

Everything said and shown is in `src/script.tsx`, one entry per scene:

- `text`: narration and captions; `` `code` `` shows in the monospace. `|` splits
  it into segments: each is spoken after a short pause (about a second), and
  is a *beat*: a command introduced in a segment is typed on its beat
  (`beat: k` on a terminal step, a diagram element, a yazi state);
- `say`: how the voice should read it, when that differs (`ls` → "L S"),
  with the same `|` segments;
- `visual`: what's on screen. The choices:
  - `term([...])`: a terminal: commands typed, then their output. The first
    time a command is typed, a callout says what it does (`src/commands.ts`,
    which must describe every command; `note: false` on a step skips it);
  - `yazi([...])`: yazi's three columns;
  - `<Jed>` and `<Codium>`: the editors;
  - `board([...])`: a mechanics drawing (boxes, arrows, gears, a conveyor belt);
  - `title(...)`: a chapter's opening card;
  - `then(cmd, ...)`: a command typed in the terminal, then the program it opens;
  - `<Desktop>`: the desktop, Super+Space and the command bar (the intro).

A scene lasts as long as its narration. Colours and fonts are MeccanicOS's
(`src/theme.ts`).

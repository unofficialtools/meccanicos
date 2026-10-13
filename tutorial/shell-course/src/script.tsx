// The whole video: one entry per scene, in order.
//   text    narration and captions. "|" splits it into segments: each one is
//           spoken after a short pause, and is the beat things start on (a
//           command is typed as the voice introduces it). `code` in
//           backticks: monospace in the captions.
//   say     how the voice reads it, when that differs (same "|" segments)
//   visual  what is on screen (steps and elements start on `beat: k`)
// A scene lasts as long as its narration (src/durations.json, `npm run voice`).
import React from "react";
import { Phases } from "./components/Beats";
import { Board, El } from "./components/Board";
import { Desktop } from "./components/Desktop";
import { Codium, Jed } from "./components/Editors";
import { Folders, Sheet } from "./components/Pages";
import { Step, Terminal } from "./components/Terminal";
import { Title } from "./components/Title";
import { Yazi, YaziState } from "./components/Yazi";
import { C } from "./theme";
import { COMMANDS, commandNames } from "./commands";

export type Scene = { id: string; chapter: string; text: string; say?: string; visual: () => React.ReactNode; tail?: number };

// The first time a command is typed (scenes are built in order), its step
// gets a callout saying what it does (COMMANDS). `note: false` skips one.
const seen = new Set<string>();
const annotate = (steps: Step[]): Step[] => steps.map((s) => {
  if (!s.cmd || s.note !== undefined) return s;
  const names = commandNames(s.cmd).filter((n) => !seen.has(n));
  names.forEach((n) => {
    if (!COMMANDS[n]) throw new Error(`commands.ts: no description for ${n}`);
    seen.add(n);
  });
  return names.length ? { ...s, note: names } : s;
});

type TermOpts = Partial<React.ComponentProps<typeof Terminal>>;
const term = (steps: Step[], o: TermOpts = {}) => {
  const all = annotate(steps);
  return () => <Terminal steps={all} {...o} />;
};
const board = (els: El[]) => () => <Board els={els} />;
const yazi = (states: YaziState[]) => () => <Yazi states={states} />;
const title = (n: number | string, t: string, m: string) => () => <Title n={n} title={t} metaphor={m} />;
// A command typed in the terminal (beat 0), then the program it opens (from `beat`).
const then = (cmd: string, cwd: string, beat: number, program: () => React.ReactNode, before: Step[] = []) => {
  const typing = term([...before, { cmd, beat: 0, delay: before.length ? 3 : 0.6, typed: 12 }], { cwd, busy: true });
  return () => <Phases phases={[{ beat: 0, render: typing }, { beat, render: program }]} />;
};

const HOME = ["Desktop/", "Documents/", "Downloads/", "Music/", "Pictures/", "Videos/", "projects/"];
const ROOT = ["bin/", "boot/", "dev/", "etc/", "home/", "nix/", "proc/", "root/", "run/", "sys/", "tmp/", "usr/", "var/"];
const ETC = ["fonts/", "nixos/", "ssh/", "hostname", "hosts", "os-release", "passwd", "timezone"];
const LS_HOME = "{b}Desktop{/}  {b}Documents{/}  {b}Downloads{/}  {b}Music{/}  {b}Pictures{/}  {b}Videos{/}  {b}projects{/}";
const NOTES = ["Gearbox project", "", "Input shaft: 1500 rpm", "Gear ratio: 3 to 1", "Output shaft: 500 rpm"];
const PHYS = ["Physics 101 notes", "", "F = m · a", "torque = r × F", "power = torque × ω"];
const GB = "~/projects/gearbox";

const ch = {
  intro: "Welcome",
  c1: "1 · The shell and the filesystem",
  c2: "2 · Help and shortcuts",
  c3: "3 · Files: move, make, edit, delete",
  c4: "4 · Pipes and redirection",
  c5: "5 · Permissions and sudo",
  c6: "6 · Environment and PATH",
  c7: "7 · Your first C++ program",
  c8: "8 · Processes",
  c9: "9 · Network and ports",
  c10: "10 · Configuring MeccanicOS",
  c11: "11 · Disks",
  end: "Cheat sheet",
};

// The filesystem as a tree, root at the top, down to /home/student.
const tree = (highlight: boolean): El[] => {
  const top = ["bin", "boot", "dev", "etc", "home", "nix", "tmp", "var"];
  const els: El[] = [{ t: "box", x: 860, y: 10, w: 200, h: 80, title: "/", body: "root", at: 0.01 }];
  top.forEach((d, i) => {
    const x = 70 + i * 225;
    const hot = d === "home" && highlight;
    els.push({ t: "arrow", from: [960, 92], to: [x + 95, 222], beat: highlight ? 0 : 1, delay: i * 0.12, color: hot ? C.amber : C.line });
    els.push({ t: "box", x, y: 225, w: 190, h: 70, title: `/${d}`, size: 26, beat: highlight ? 0 : 1, delay: 0.2 + i * 0.12, color: hot ? C.amber : C.dim });
  });
  const hx = 70 + 4 * 225 + 95;
  els.push({ t: "arrow", from: [hx, 297], to: [hx, 395], beat: highlight ? 0 : 2, color: C.amber });
  els.push({ t: "box", x: hx - 150, y: 398, w: 300, h: 74, title: "/home/student", size: 26, beat: highlight ? 0 : 2, delay: 0.3 });
  ["Documents", "Pictures", "projects"].forEach((d, i) => {
    const x = hx - 470 + i * 330;
    els.push({ t: "arrow", from: [hx, 474], to: [x + 140, 588], beat: highlight ? 1 : 2, delay: 0.8 + i * 0.2 });
    els.push({ t: "box", x, y: 590, w: 280, h: 66, title: d, size: 24, beat: highlight ? 1 : 2, delay: 1 + i * 0.2, color: C.blue });
  });
  if (highlight) els.push({ t: "text", x: 1400, y: 420, text: "a path is the route\nfrom the root:\n{a}/home/student/projects{/}\n\n{a}~{/} is your home", size: 30, beat: 1 });
  return els;
};

export const scenes: Scene[] = [
  // ---------------------------------------------------------------- intro
  { id: "intro-1", chapter: ch.intro, text: "Welcome to the workshop. In this video you'll learn to drive a computer the way engineers do: by typing commands into a shell.",
    visual: title("THE LINUX SHELL", "Driving a computer by typing", "explained with gears, cabinets and conveyor belts") },
  { id: "intro-desktop", chapter: ch.intro,
    text: "This is the MeccanicOS desktop. | To get to the shell, press the Super key, the one with the Windows logo, together with the space bar. That opens the command bar. | Type `terminal`, | and press Enter. | Here it is: the terminal, a window with the shell inside, waiting for your orders.",
    visual: () => <Desktop barBeat={1} typeBeat={2} enterBeat={3} /> },
  { id: "intro-2", chapter: ch.intro, text: "Think of the computer as a machine shop. | The hardware is the heavy machinery. | The kernel is the engine room that runs it. | And programs are the tools on the wall.",
    visual: board([
      { t: "box", x: 80, y: 520, w: 1760, h: 150, title: "Hardware", body: "processor · memory · disks · network card", color: C.dim, beat: 1 },
      { t: "box", x: 280, y: 330, w: 1360, h: 140, title: "Kernel (Linux)", body: "the engine room: shares the machines between the programs", color: C.tealHi, beat: 2 },
      { t: "box", x: 200, y: 110, w: 360, h: 150, title: "ls", body: "lists things", beat: 3, size: 30 },
      { t: "box", x: 620, y: 110, w: 360, h: 150, title: "jed", body: "edits text", beat: 3, delay: 0.3, size: 30 },
      { t: "box", x: 1040, y: 110, w: 360, h: 150, title: "firefox", body: "browses", beat: 3, delay: 0.6, size: 30 },
      { t: "text", x: 1450, y: 150, text: "programs:\nthe tools", size: 34, color: C.dim, beat: 3, delay: 0.9 },
      { t: "gear", x: 1760, y: 400, r: 70, teeth: 10, beat: 2 },
    ]) },
  { id: "intro-3", chapter: ch.intro, text: "The shell is the control panel in front of all of it. | You type an order, | it finds the right tool and runs it, | and shows you the result. Then it waits for the next order.",
    visual: board([
      { t: "box", x: 80, y: 260, w: 330, h: 170, title: "You", body: "type an order", color: C.text, beat: 0 },
      { t: "arrow", from: [415, 345], to: [640, 345], label: "ls Documents", beat: 1, color: C.amber },
      { t: "box", x: 645, y: 220, w: 420, h: 250, title: "The shell", body: ["reads the order", "finds the tool", "starts it"], beat: 0, delay: 0.6 },
      { t: "arrow", from: [1070, 345], to: [1290, 345], beat: 2, color: C.amber },
      { t: "box", x: 1295, y: 260, w: 330, h: 170, title: "ls", body: "does the work", color: C.tealHi, beat: 2, delay: 0.3 },
      { t: "arrow", from: [1460, 435], to: [1460, 600], beat: 3 },
      { t: "arrow", from: [1460, 600], to: [245, 600], label: "the result, on your screen", beat: 3, delay: 0.3 },
      { t: "arrow", from: [245, 600], to: [245, 435], beat: 3, delay: 0.8 },
      { t: "gear", x: 1780, y: 130, r: 60, teeth: 10, beat: 0 },
      { t: "gear", x: 1690, y: 205, r: 38, teeth: 8, speed: -0.95, beat: 0 },
    ]) },
  { id: "intro-4", chapter: ch.intro, text: "The two lines at the bottom are the prompt: who you are, on which computer, and in which folder. | The amber arrow means: your turn.",
    visual: term([{ cmd: "", beat: 0 }]) },

  // ------------------------------------------------- 1 shell + filesystem
  { id: "c1-title", chapter: ch.c1, text: "Chapter one. The shell, and the filesystem: one giant cabinet of labelled drawers.",
    visual: title(1, "The shell and the filesystem", "one cabinet, drawers inside drawers") },
  { id: "c1-tree", chapter: ch.c1, text: "Every file on the computer sits in one tree of folders. At the very top is the root, written as a single slash. | Inside it are the top-level folders. | One of them, home, holds a folder for every person.",
    visual: board(tree(false)) },
  { id: "c1-path", chapter: ch.c1, text: "Your folder is `/home/student`. | A path like `/home/student/projects` is the route from the root to a drawer, one folder at a time. The tilde, `~`, is the shell's shorthand for your home folder.",
    say: "Your folder is slash home slash student. | A path like slash home slash student slash projects is the route from the root to a drawer, one folder at a time. The tilde is the shell's shorthand for your home folder.",
    visual: board(tree(true)) },
  { id: "c1-yazi-1", chapter: ch.c1, text: "Let's walk the cabinet with yazi, a file browser that runs in the terminal. Type `yazi` and press Enter. | You start in your home folder. The middle column is where you are, the left one is the folder above, and the right one previews what's selected.",
    say: "Let's walk the cabinet with yazi, a file browser that runs in the terminal. Type yazi and press Enter. | You start in your home folder. The middle column is where you are, the left one is the folder above, and the right one previews what's selected.",
    visual: then("yazi", "~", 1, yazi([
      { cwd: "~", parent: ["student/"], parentSel: 0, items: HOME, sel: 3, preview: ["Albums/", "playlist.m3u"] },
      { at: 0.6, cwd: "~", parent: ["student/"], parentSel: 0, items: HOME, sel: 1, preview: ["lab-report.odt", "notes.txt", "syllabus.pdf"], keys: "k" },
    ])) },
  { id: "c1-yazi-2", chapter: ch.c1, text: "Press `h`, or the left arrow, to go up a level. | Up again, and you reach the root: slash. Every drawer of the computer is now in front of you.",
    say: "Press H, or the left arrow, to go up a level. | Up again, and you reach the root: slash. Every drawer of the computer is now in front of you.",
    visual: yazi([
      { cwd: "~", parent: ["student/"], parentSel: 0, items: HOME, sel: 1, preview: ["lab-report.odt", "notes.txt", "syllabus.pdf"] },
      { beat: 0, cwd: "/home", parent: ROOT, parentSel: 4, items: ["student/"], sel: 0, preview: HOME, keys: "h" },
      { beat: 1, cwd: "/", parent: [], items: ROOT, sel: 4, preview: ["student/"], keys: "h" },
    ]) },
  { id: "c1-folders", chapter: ch.c1, text: "Here is the whole cabinet on one page. Your files live in home. Settings live in etc. Devices like disks appear in dev. Running programs show up in proc. Logs grow in var. And on MeccanicOS, every program is kept in nix, each version in its own drawer.",
    say: "Here is the whole cabinet on one page. Your files live in home. Settings live in E T C. Devices like disks appear in dev. Running programs show up in proc. Logs grow in var. And on MeccanicOS, every program is kept in nix, each version in its own drawer.",
    visual: () => <Folders /> },
  { id: "c1-yazi-3", chapter: ch.c1, text: "Open etc with `l`, or the right arrow, and pick a file: yazi shows what's inside. `os-release` names the system. | `hostname` is the computer's name. Plain text, like most settings on Linux.",
    say: "Open E T C with L, or the right arrow, and pick a file: yazi shows what's inside. O S release names the system. | Hostname is the computer's name. Plain text, like most settings on Linux.",
    visual: yazi([
      { cwd: "/etc", parent: ROOT, parentSel: 3, items: ETC, sel: 5,
        preview: ['NAME={g}"MeccanicOS"{/}', 'PRETTY_NAME={g}"MeccanicOS 26.05"{/}', 'ID={g}meccanicos{/}', 'ID_LIKE={g}nixos{/}', 'VERSION_ID={g}"26.05"{/}', 'HOME_URL={g}"https://meccanicos.com"{/}'], previewIsFile: true, keys: "l", info: "-rw-r--r--  root  412 B" },
      { beat: 1, cwd: "/etc", parent: ROOT, parentSel: 3, items: ETC, sel: 3, preview: ["meccanicos"], previewIsFile: true, keys: "k k", info: "-rw-r--r--  root  11 B" },
    ]) },
  { id: "c1-yazi-4", chapter: ch.c1, text: "Back home, in Documents, a text file previews the same way. | `Enter` opens it, and `q` quits yazi, back to the shell.",
    say: "Back home, in Documents, a text file previews the same way. | Enter opens it, and Q quits yazi, back to the shell.",
    visual: yazi([
      { cwd: "~/Documents", parent: HOME, parentSel: 1, items: ["lab-report.odt", "notes.txt", "syllabus.pdf"], sel: 1, preview: PHYS, previewIsFile: true, info: "-rw-r--r--  student  58 B" },
      { beat: 1, cwd: "~/Documents", parent: HOME, parentSel: 1, items: ["lab-report.odt", "notes.txt", "syllabus.pdf"], sel: 1, preview: PHYS, previewIsFile: true, info: "-rw-r--r--  student  58 B", keys: "q" },
    ]) },

  // ----------------------------------------------------------- 2 help
  { id: "c2-title", chapter: ch.c2, text: "Chapter two. Help and shortcuts. Before using any tool, learn where its manual is, and how to work fast.",
    visual: title(2, "Help and shortcuts", "every tool comes with its manual") },
  { id: "c2-tab", chapter: ch.c2, text: "Never type a whole name. Type the start and press `Tab`: the shell completes it. | Press it twice, and you see every match.",
    say: "Never type a whole name. Type the start and press Tab: the shell completes it. | Press it twice, and you see every match.",
    visual: term([
      { cmd: "cd Doc", beat: 0, typed: 8, complete: "uments/", completeIn: 2.4, keys: "Tab", keysIn: 2.2, cd: "~/Documents" },
      { cmd: "ls D", beat: 1, typed: 8, keys: "Tab Tab", keysIn: 0.8, out: ["{b}Desktop/{/}  {b}Documents/{/}  {b}Downloads/{/}"] },
    ]) },
  { id: "c2-history", chapter: ch.c2, text: "The up arrow brings back your last commands. | `Control R` searches all of them: type a few letters of something you ran last week, and there it is.",
    say: "The up arrow brings back your last commands. | Control R searches all of them: type a few letters of something you ran last week, and there it is.",
    visual: term([
      { cmd: "ls ~/Documents", beat: 0, delay: 0.5, keys: "↑", typed: 60 },
      { cmd: "cd ~/Documents", beat: 1, delay: 0.5, keys: "Ctrl+R", typed: 30 },
    ]) },
  { id: "c2-ctrlc", chapter: ch.c2, text: "Some commands go on and on, like `ping`, which keeps checking a machine on the network. | `Control C` stops them. It's the emergency stop button, and it's always safe to press.",
    say: "Some commands go on and on, like ping, which keeps checking a machine on the network. | Control C stops them. It's the emergency stop button, and it's always safe to press.",
    visual: term([
      { cmd: "ping meccanicos.com", beat: 0, delay: 0.5, out: ["PING meccanicos.com (185.199.108.153) 56 data bytes", "64 bytes from 185.199.108.153: icmp_seq=1 ttl=57 time=12.1 ms", "64 bytes from 185.199.108.153: icmp_seq=2 ttl=57 time=11.8 ms", "64 bytes from 185.199.108.153: icmp_seq=3 ttl=57 time=12.4 ms"] },
      { noPrompt: true, beat: 1, delay: 0.3, keys: "Ctrl+C", out: ["{d}^C{/}", "--- meccanicos.com ping statistics ---", "3 packets transmitted, 3 received, 0% packet loss"] },
    ]) },
  { id: "c2-tldr", chapter: ch.c2, text: "To learn a command, start with `tldr`: a short page of examples. | `ls --help` lists every option. | And `man ls` opens the full manual; `q` leaves it.",
    say: "To learn a command, start with T L D R: a short page of examples. | L S dash dash help lists every option. | And man L S opens the full manual; Q leaves it.",
    visual: term([
      { cmd: "tldr ls", beat: 0, delay: 0.5, out: ["  {w}ls{/}", "  List directory contents.", "  {g}- List all files, including hidden files:{/}", "    {a}ls -a{/}", "  {g}- Long format (permissions, owner, size, date):{/}", "    {a}ls -l{/}"] },
      { cmd: "ls --help | head -2", beat: 1, delay: 0.3, out: ["Usage: ls [OPTION]... [FILE]...", "List information about the FILEs (the current directory by default)."] },
      { cmd: "man ls", beat: 2, delay: 0.3 },
    ]) },

  // ------------------------------------------------------- 3 files
  { id: "c3-title", chapter: ch.c3, text: "Chapter three. Moving around and handling files: the shell's hand tools.",
    visual: title(3, "Files: move, make, edit, delete", "hand tools for the cabinet") },
  { id: "c3-pwd", chapter: ch.c3, text: "`pwd` prints the working directory: the drawer you're standing at. | `ls` lists what's in it. Folders show in blue.",
    say: "P W D prints the working directory: the drawer you're standing at. | L S lists what's in it. Folders show in blue.",
    visual: term([
      { cmd: "pwd", beat: 0, delay: 0.6, out: ["/home/student"] },
      { cmd: "ls", beat: 1, delay: 0.3, out: [LS_HOME] },
    ]) },
  { id: "c3-ls", chapter: ch.c3, text: "Options change how a tool works. `ls -l` gives the long form, with sizes and dates. | `ls -a` also shows hidden files, whose names start with a dot: that's where programs keep their settings.",
    say: "Options change how a tool works. L S dash L gives the long form, with sizes and dates. | L S dash A also shows hidden files, whose names start with a dot: that's where programs keep their settings.",
    visual: term([
      { cmd: "ls -l Documents", beat: 0, delay: 1.2, out: [".{s}rw-r--r--{/}  21k student 12 Oct 09:14 lab-report.odt", ".{s}rw-r--r--{/}   58 student 12 Oct 09:20 notes.txt", ".{s}rw-r--r--{/} 340k student 30 Sep 16:02 syllabus.pdf"] },
      { cmd: "ls -a", beat: 1, delay: 0.3, out: ["{d}.bashrc{/}  {b}.cache{/}  {b}.config{/}  {b}.local{/}  " + LS_HOME] },
    ]) },
  { id: "c3-cd", chapter: ch.c3, text: "`cd` changes directory: `cd projects` moves into a folder. | `cd ..` goes up one level: two dots always mean the folder above. | And `cd` alone takes you home, from anywhere.",
    say: "C D changes directory: C D projects moves into a folder. | C D dot dot goes up one level: two dots always mean the folder above. | And C D alone takes you home, from anywhere.",
    visual: term([
      { cmd: "cd projects", beat: 0, delay: 1.2, cd: "~/projects" },
      { cmd: "cd ..", beat: 1, delay: 0.3, cd: "~" },
      { cmd: "cd /etc", beat: 1, delay: 2.4, cd: "/etc" },
      { cmd: "cd", beat: 2, delay: 0.5, cd: "~" },
    ]) },
  { id: "c3-make", chapter: ch.c3, text: "Now let's build. `mkdir` makes a directory. | `touch` makes an empty file. | And `cp` copies, from a source to a destination, always in that order.",
    say: "Now let's build. Make dir makes a directory. | Touch makes an empty file. | And C P copies, from a source to a destination, always in that order.",
    visual: term([
      { cmd: "mkdir -p projects/gearbox", beat: 0, delay: 0.8 },
      { cmd: "cd projects/gearbox", beat: 0, delay: 3, cd: GB },
      { cmd: "touch notes.txt", beat: 1, delay: 0.3 },
      { cmd: "cp notes.txt notes-backup.txt", beat: 2, delay: 0.3 },
      { cmd: "ls", beat: 2, delay: 3.6, out: ["notes-backup.txt  notes.txt"] },
    ]) },
  { id: "c3-mv", chapter: ch.c3, text: "`mv` moves a file, or renames it, which is the same thing: a new label, or a new drawer.",
    say: "M V moves a file, or renames it, which is the same thing: a new label, or a new drawer.",
    visual: term([
      { cmd: "mv notes-backup.txt old-notes.txt", beat: 0, delay: 0.5 },
      { cmd: "mv old-notes.txt ~/Documents/", beat: 0, delay: 3.4 },
    ], { cwd: GB }) },
  { id: "c3-jed-1", chapter: ch.c3, text: "To write in a file, use an editor. MeccanicOS comes with Jed, which runs right in the terminal. Type `jed notes.txt`. | Jed opens the file, and you type away.",
    say: "To write in a file, use an editor. MeccanicOS comes with Jed, which runs right in the terminal. Type jed notes dot T X T. | Jed opens the file, and you type away.",
    visual: then("jed notes.txt", GB, 1, () => <Jed file="notes.txt" lines={NOTES} typeFrom={0.15} typeTo={0.95} />) },
  { id: "c3-jed-2", chapter: ch.c3, text: "Jed uses Emacs keys. `Control X`, then `Control S`, saves. | `Control X`, then `Control C`, quits. | Can't remember? `F10` opens the menu, with everything in it.",
    say: "Jed uses Emacs keys. Control X, then Control S, saves. | Control X, then Control C, quits. | Can't remember? F10 opens the menu, with everything in it.",
    visual: () => <Jed file="notes.txt" lines={NOTES} keys={[{ keys: "Ctrl+X Ctrl+S", beat: 0 }, { keys: "Ctrl+X Ctrl+C", beat: 1 }, { keys: "F10", beat: 2 }]} /> },
  { id: "c3-cat", chapter: ch.c3, text: "Back in the shell, `cat` prints a file. | For long files, `less` lets you scroll, and `q` quits.",
    say: "Back in the shell, cat prints a file. | For long files, less lets you scroll, and Q quits.",
    visual: term([
      { cmd: "cat notes.txt", beat: 0, delay: 0.8, out: NOTES },
      { cmd: "less /etc/os-release", beat: 1, delay: 0.3 },
    ], { cwd: GB }) },
  { id: "c3-open", chapter: ch.c3, text: "Any file can also go to a desktop program. `open` picks the right app for the file, like a double click. | And `codium` opens files, or whole folders, in VSCodium, a full code editor.",
    say: "Any file can also go to a desktop program. Open picks the right app for the file, like a double click. | And codium opens files, or whole folders, in VS Codium, a full code editor.",
    visual: term([
      { cmd: "open ~/Documents/syllabus.pdf", beat: 0, delay: 1 },
      { cmd: "codium .", beat: 1, delay: 0.5 },
    ], { cwd: GB }) },
  { id: "c3-codium", chapter: ch.c3, text: "Same file, different tool: the shell doesn't care which editor you use. A file is a file.",
    visual: () => <Codium file="notes.txt" tree={["v GEARBOX", "  notes.txt"]} lines={NOTES} /> },
  { id: "c3-print", chapter: ch.c3, text: "`print` sends a file to a printer: it asks which one, or makes a PDF. | With `--pdf`, it saves the PDF right next to the file.",
    say: "Print sends a file to a printer: it asks which one, or makes a PDF. | With dash dash P D F, it saves the PDF right next to the file.",
    visual: term([
      { cmd: "print notes.txt", beat: 0, delay: 0.5, out: ["notes.txt → Lab_Printer  (Lab_Printer-42)"] },
      { cmd: "print --pdf notes.txt", beat: 1, delay: 0.5, out: ["Saved /home/student/projects/gearbox/notes.pdf"] },
    ], { cwd: GB }) },
  { id: "c3-rm", chapter: ch.c3, text: "`rm` removes a file, | and `rm -r` removes a folder, with everything in it. | Careful: `rm` has no trash can. Removed means gone. Read the command twice before pressing Enter.",
    say: "R M removes a file, | and R M dash R removes a folder, with everything in it. | Careful: R M has no trash can. Removed means gone. Read the command twice before pressing Enter.",
    visual: term([
      { cmd: "rm notes.pdf", beat: 0, delay: 0.4 },
      { cmd: "mkdir scratch", beat: 1, delay: 0.2 },
      { cmd: "rm -r scratch", beat: 1, delay: 1.6 },
      { cmd: "rm missing.txt", beat: 2, delay: 1.5, out: ["{r}rm: cannot remove 'missing.txt': No such file or directory{/}"] },
    ], { cwd: GB }) },
  { id: "c3-trash", chapter: ch.c3, text: "When in doubt, use `trash` instead: it moves files to the desktop's trash can, so you can change your mind. | `trash-list` shows what's in it, | and `trash-restore` puts a file back where it was.",
    say: "When in doubt, use trash instead: it moves files to the desktop's trash can, so you can change your mind. | Trash list shows what's in it, | and trash restore puts a file back where it was.",
    visual: term([
      { cmd: "trash ~/Documents/old-notes.txt", beat: 0, delay: 1.5 },
      { cmd: "trash-list", beat: 1, delay: 0.3, out: ["2026-10-12 10:14:03 /home/student/Documents/old-notes.txt"] },
      { cmd: "trash-restore", beat: 2, delay: 0.3, out: ["   0 2026-10-12 10:14:03 /home/student/Documents/old-notes.txt", "What file to restore [0..0]: 0"] },
    ], { cwd: GB }) },

  // ------------------------------------------------------- 4 pipes
  { id: "c4-title", chapter: ch.c4, text: "Chapter four. Pipes and redirection: the assembly line. This is the big idea of the shell.",
    visual: title(4, "Pipes and redirection", "small machines, one assembly line") },
  { id: "c4-idea", chapter: ch.c4, text: "Each tool does one job well. A pipe, the vertical bar, connects the output of one tool to the input of the next, like stations on a conveyor belt. | `cat` feeds the lines. | `grep` keeps only those with rpm. | And `wc -l` counts them.",
    say: "Each tool does one job well. A pipe, the vertical bar, connects the output of one tool to the input of the next, like stations on a conveyor belt. | Cat feeds the lines. | Grep keeps only those with R P M. | And W C dash L counts them.",
    visual: board([
      { t: "belt", x: 60, y: 420, w: 1800, beat: 0 },
      { t: "box", x: 120, y: 220, w: 330, h: 170, title: "cat notes.txt", body: "feeds every line", beat: 1, size: 28 },
      { t: "text", x: 560, y: 260, text: "|", size: 110, color: C.amber, mono: true, beat: 0, delay: 3 },
      { t: "box", x: 700, y: 220, w: 400, h: 170, title: "grep rpm", body: "keeps lines with 'rpm'", beat: 2, size: 28, color: C.tealHi },
      { t: "text", x: 1210, y: 260, text: "|", size: 110, color: C.amber, mono: true, beat: 0, delay: 3.3 },
      { t: "box", x: 1350, y: 220, w: 380, h: 170, title: "wc -l", body: "counts the lines", beat: 3, size: 28, color: C.green },
      { t: "part", path: [[180, 433], [500, 433], [760, 433]], label: "Gearbox project", beat: 2, delay: 0.4, dur: 1.6, color: C.dim },
      { t: "part", path: [[180, 433], [900, 433], [1300, 433], [1400, 433]], label: "Input shaft: 1500 rpm", beat: 2, delay: 1, dur: 2.2 },
      { t: "part", path: [[180, 433], [900, 433], [1300, 433], [1400, 433]], label: "Output shaft: 500 rpm", beat: 3, dur: 2.2 },
      { t: "part", path: [[1600, 433], [1800, 433], [1800, 600]], label: "2", beat: 3, delay: 2, dur: 1.4, color: C.green },
      { t: "text", x: 120, y: 540, text: "{a}cat notes.txt | grep rpm | wc -l{/}", size: 44, mono: true, beat: 3, delay: 0.5 },
    ]) },
  { id: "c4-pipe", chapter: ch.c4, text: "In the terminal it reads left to right. | Add `sort` to put lines in order, or `head` to keep just the first few. Any tool that reads and writes text can join the line.",
    say: "In the terminal it reads left to right. | Add sort to put lines in order, or head to keep just the first few. Any tool that reads and writes text can join the line.",
    visual: term([
      { cmd: "cat notes.txt | grep rpm", beat: 0, delay: 0.2, out: ["Input shaft: 1500 {r}rpm{/}", "Output shaft: 500 {r}rpm{/}"] },
      { cmd: "cat notes.txt | grep rpm | wc -l", beat: 0, delay: 2.8, out: ["2"] },
      { cmd: "ls /etc | sort -r | head -3", beat: 1, delay: 0.4, out: ["zoneinfo", "xdg", "wpa_supplicant.conf"] },
    ], { cwd: GB }) },
  { id: "c4-redirect", chapter: ch.c4, text: "Redirection sends the output into a file instead of the screen. One arrow, `>`, fills the file, replacing what was there. | Two arrows, `>>`, add to the end. Like a valve: replace the tank, or top it up.",
    say: "Redirection sends the output into a file instead of the screen. One arrow fills the file, replacing what was there. | Two arrows add to the end. Like a valve: replace the tank, or top it up.",
    visual: term([
      { cmd: "grep rpm notes.txt > speeds.txt", beat: 0, delay: 2 },
      { cmd: "echo 'Idle: 800 rpm' >> speeds.txt", beat: 1, delay: 0.3 },
      { cmd: "cat speeds.txt", beat: 1, delay: 3.2, out: ["Input shaft: 1500 rpm", "Output shaft: 500 rpm", "Idle: 800 rpm"] },
    ], { cwd: GB }) },

  // ------------------------------------------------------ 5 permissions
  { id: "c5-title", chapter: ch.c5, text: "Chapter five. Permissions, and sudo: locks on the drawers, and the master key.",
    visual: title(5, "Permissions and sudo", "locks on the drawers, one master key") },
  { id: "c5-rwx", chapter: ch.c5, text: "Every file has an owner, a group, and everybody else. | Each gets three switches: r to read, w to write, x to execute, which means run it as a program. | `ls -l` shows them on the left.",
    say: "Every file has an owner, a group, and everybody else. | Each gets three switches: R to read, W to write, X to execute, which means run it as a program. | L S dash L shows them on the left.",
    visual: board([
      { t: "box", x: 190, y: 190, w: 440, h: 240, title: "owner", body: ["{s}r w -{/}", "student may read", "and write"], color: C.sand, beat: 0, delay: 1.2 },
      { t: "box", x: 740, y: 190, w: 440, h: 240, title: "group", body: ["{t}r - -{/}", "the group users", "may read"], color: C.tealHi, beat: 0, delay: 1.8 },
      { t: "box", x: 1290, y: 190, w: 440, h: 240, title: "others", body: ["{d}r - -{/}", "everyone else", "may read"], color: C.dim, beat: 0, delay: 2.6 },
      { t: "text", x: 960, y: 500, text: "r  read      w  write      x  execute (run it)", size: 38, mono: true, align: "center", w: 1500, color: C.amber, beat: 1 },
      { t: "text", x: 960, y: 20, text: "{s}rw-{/}{t}r--{/}{d}r--{/}  student  users  notes.txt", size: 52, mono: true, align: "center", w: 1600, beat: 2 },
    ]) },
  { id: "c5-chmod", chapter: ch.c5, text: "A script is a file of commands. This one won't run yet: permission denied. | `chmod` changes the switches: `chmod +x` adds the execute switch. | Then dot slash runs it, from this folder.",
    say: "A script is a file of commands. This one won't run yet: permission denied. | Change mod changes the switches: change mod plus X adds the execute switch. | Then dot slash runs it, from this folder.",
    visual: term([
      { cmd: "echo 'echo Gears turning!' > spin.sh", beat: 0, delay: 0.2 },
      { cmd: "./spin.sh", beat: 0, delay: 3, out: ["{r}bash: ./spin.sh: Permission denied{/}"] },
      { cmd: "chmod +x spin.sh", beat: 1, delay: 1.5 },
      { cmd: "./spin.sh", beat: 2, delay: 0.3, out: ["Gears turning!"] },
    ], { cwd: GB }) },
  { id: "c5-sudo", chapter: ch.c5, text: "Some drawers belong to the system, and only the administrator, root, may open them. | `sudo`, for superuser do, runs one command with the master key. Use it only when you must, and read the command first: root can break anything.",
    say: "Some drawers belong to the system, and only the administrator, root, may open them. | Sue doo, for superuser do, runs one command with the master key. Use it only when you must, and read the command first: root can break anything.",
    visual: term([
      { cmd: "cat /etc/shadow", beat: 0, delay: 0.5, out: ["{r}cat: /etc/shadow: Permission denied{/}"] },
      { cmd: "sudo head -2 /etc/shadow", beat: 1, delay: 0.5, out: ["root:!:1::::::", "student:$y$j9T$Fq…:20373::::::"] },
    ]) },

  // ------------------------------------------------------ 6 environment
  { id: "c6-title", chapter: ch.c6, text: "Chapter six. The environment, and the PATH: how the shell finds its tools.",
    visual: title(6, "Environment and PATH", "the tool wall, searched in order") },
  { id: "c6-vars", chapter: ch.c6, text: "The shell keeps variables: named values that every program it starts can read. | A dollar sign reads one: `HOME` is your folder, `USER` your name. | `export` sets your own.",
    say: "The shell keeps variables: named values that every program it starts can read. | A dollar sign reads one: home is your folder, user your name. | Export sets your own.",
    visual: term([
      { cmd: "echo $HOME", beat: 1, delay: 0.3, out: ["/home/student"] },
      { cmd: "echo \"Hello, $USER\"", beat: 1, delay: 2.4, out: ["Hello, student"] },
      { cmd: "export RATIO=3", beat: 2, delay: 0.3 },
      { cmd: "echo $RATIO", beat: 2, delay: 1.8, out: ["3"] },
    ]) },
  { id: "c6-path", chapter: ch.c6, text: "When you type a command, the shell looks for a program of that name on the walls listed in `PATH`, in order, and runs the first one it finds. | `which` tells you which one that is.",
    say: "When you type a command, the shell looks for a program of that name on the walls listed in PATH, in order, and runs the first one it finds. | Which tells you which one that is.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "{a}$PATH{/} = ~/.nix-profile/bin : /run/wrappers/bin : /run/current-system/sw/bin", size: 34, mono: true, beat: 0 },
      { t: "box", x: 80, y: 120, w: 520, h: 300, title: "~/.nix-profile/bin", body: ["apps you installed", "", "vlc  gimp"], beat: 0, delay: 1.5, size: 26, mono: true },
      { t: "box", x: 700, y: 120, w: 520, h: 300, title: "/run/wrappers/bin", body: ["tools with special rights", "", "sudo  ping"], beat: 0, delay: 2, size: 26, mono: true, color: C.tealHi },
      { t: "box", x: 1320, y: 120, w: 520, h: 300, title: "/run/current-system/sw/bin", body: ["the system's programs", "", "ls  cat  grep  yazi  jed"], beat: 0, delay: 2.5, size: 26, mono: true, color: C.green },
      { t: "part", path: [[340, 520], [960, 520], [1580, 520], [1580, 440]], label: "grep?", beat: 0, delay: 4.5, dur: 3 },
      { t: "text", x: 80, y: 600, text: "{a}which grep{/}  →  /run/current-system/sw/bin/grep", size: 36, mono: true, beat: 1 },
    ]) },
  { id: "c6-notfound", chapter: ch.c6, text: "If no wall has it, you get: command not found. | Usually a typo, like this one. Or a program that isn't installed: in the next chapter you'll borrow one.",
    visual: term([{ cmd: "gerp rpm notes.txt", beat: 0, delay: 0.3, note: false, out: ["{r}bash: gerp: command not found{/}"] }], { cwd: GB }) },
  { id: "c6-bashrc", chapter: ch.c6, text: "To keep a variable or a shortcut for good, open `.bashrc`, a hidden file in your home folder that bash reads at every start. | Add an export, and an alias: a short name for a long command.",
    say: "To keep a variable or a shortcut for good, open dot bash R C, a hidden file in your home folder that bash reads at every start. | Add an export, and an alias: a short name for a long command.",
    visual: then("jed ~/.bashrc", "~", 1, () => <Jed file=".bashrc" mode="SH" dir="~/" lines={["# My shell settings", "export RATIO=3", "alias gb='cd ~/projects/gearbox'", "alias ll='ls -l'"]} typeFrom={0.1} typeTo={0.9} />) },

  // ------------------------------------------------------- 7 c++
  { id: "c7-title", chapter: ch.c7, text: "Chapter seven. Your first program in C plus plus: from a drawing, to a machined part.",
    visual: title(7, "Your first C++ program", "from the drawing to the machined part") },
  { id: "c7-code", chapter: ch.c7, text: "First, the drawing: the source code. Make a folder, and open `hello.cpp` in Jed. | Include the input-output library, and in main, print a line.",
    say: "First, the drawing: the source code. Make a folder, and open hello dot C P P in Jed. | Include the input output library, and in main, print a line.",
    visual: then("jed hello.cpp", "~/projects/hello", 1, () => <Jed file="hello.cpp" mode="C++" dir="~/projects/hello/" lines={["{t}#include{/} {g}<iostream>{/}", "", "{s}int{/} main() {", "    std::cout << {g}\"Hello, workshop!\"{/} << std::endl;", "    {s}return{/} {a}0{/};", "}"]} typeFrom={0.1} typeTo={0.9} />,
      [{ cmd: "mkdir ~/projects/hello && cd ~/projects/hello", beat: 0, delay: 0.3, typed: 40, cd: "~/projects/hello" }]) },
  { id: "c7-gcc", chapter: ch.c7, text: "Next, the compiler, `g++`. It isn't installed, and you don't have to install it for good. | `nix-shell -p gcc` borrows it from the tool crib: a new shell, with the compiler on its wall. The prompt changes, to remind you. | Now `g++` is found.",
    say: "Next, the compiler, G plus plus. It isn't installed, and you don't have to install it for good. | Nix shell dash P G C C borrows it from the tool crib: a new shell, with the compiler on its wall. The prompt changes, to remind you. | Now G plus plus is found.",
    visual: term([
      { cmd: "nix-shell -p gcc", beat: 1, delay: 0.3, nix: true, out: ["{d}copying path '/nix/store/…-gcc-15.3.0' from 'https://cache.nixos.org'...{/}", "{d}copying path '/nix/store/…-gcc-wrapper-15.3.0' from 'https://cache.nixos.org'...{/}"] },
      { cmd: "g++ --version", beat: 2, delay: 0.2, out: ["g++ (GCC) 15.3.0"] },
    ], { cwd: "~/projects/hello" }) },
  { id: "c7-compile", chapter: ch.c7, text: "The compiler is the machine shop: it turns the drawing into a part the processor can run. | `g++ hello.cpp -o hello` reads the source, and writes the program, hello.",
    say: "The compiler is the machine shop: it turns the drawing into a part the processor can run. | G plus plus hello dot C P P dash O hello reads the source, and writes the program, hello.",
    visual: board([
      { t: "box", x: 100, y: 180, w: 420, h: 260, title: "hello.cpp", body: ["source code", "text you can read"], beat: 0, color: C.sand },
      { t: "arrow", from: [525, 310], to: [730, 310], beat: 0, delay: 1.5, color: C.amber },
      { t: "box", x: 735, y: 150, w: 450, h: 320, title: "g++", body: ["the compiler", "checks it, translates it", "to machine code"], beat: 0, delay: 1.8 },
      { t: "gear", x: 960, y: 560, r: 70, teeth: 12, beat: 0, delay: 1.8 },
      { t: "gear", x: 1080, y: 600, r: 45, teeth: 9, speed: -0.95, beat: 0, delay: 1.8 },
      { t: "arrow", from: [1190, 310], to: [1395, 310], beat: 0, delay: 3.5, color: C.amber },
      { t: "box", x: 1400, y: 180, w: 420, h: 260, title: "hello", body: ["the program", "the processor runs it"], beat: 0, delay: 3.8, color: C.green },
      { t: "text", x: 960, y: 640, text: "{a}g++ hello.cpp -o hello{/}", size: 40, mono: true, align: "center", w: 1200, beat: 1 },
    ]) },
  { id: "c7-run", chapter: ch.c7, text: "Compile it. | The new file, hello, already has its execute switch. | Run it with dot slash hello. The dot slash says: this folder, because the shell only searches the PATH walls by itself.",
    visual: term([
      { cmd: "g++ hello.cpp -o hello", beat: 0, delay: 0.2 },
      { cmd: "ls -l", beat: 1, delay: 0.2, out: [".{s}rwxr-xr-x{/}  18k student 12 Oct 10:02 {g}hello{/}", ".{s}rw-r--r--{/}  103 student 12 Oct 10:01 hello.cpp"] },
      { cmd: "./hello", beat: 2, delay: 0.5, out: ["Hello, workshop!"] },
    ], { cwd: "~/projects/hello", nix: true }) },
  { id: "c7-error", chapter: ch.c7, text: "Make a mistake, like a missing semicolon, and the compiler tells you the file, the line and the column. | Fix it in the editor, compile again. That loop, edit, compile, run, is programming. | When you are done, `exit` leaves the nix-shell, and the compiler goes back to the crib. To keep a program for good, `mos-apps install` installs it.",
    say: "Make a mistake, like a missing semicolon, and the compiler tells you the file, the line and the column. | Fix it in the editor, compile again. That loop, edit, compile, run, is programming. | When you are done, exit leaves the nix shell, and the compiler goes back to the crib. To keep a program for good, mos apps install installs it.",
    visual: term([
      { cmd: "g++ hello.cpp -o hello", beat: 0, delay: 0.2, out: ["{w}hello.cpp:4:52:{/} {r}error:{/} expected ';' before 'return'", "    4 |     std::cout << \"Hello, workshop!\" << std::endl", "      |                                                    {g}^{/}", "      |                                                    {g};{/}"] },
      { cmd: "exit", beat: 2, delay: 0.4, nix: false },
    ], { cwd: "~/projects/hello", nix: true }) },

  // -------------------------------------------------------- 8 processes
  { id: "c8-title", chapter: ch.c8, text: "Chapter eight. Processes: the machines running on the shop floor right now.",
    visual: title(8, "Processes", "machines running on the shop floor") },
  { id: "c8-what", chapter: ch.c8, text: "A program on the disk is a machine in storage. | Started, it becomes a process: a running machine, with a number, its PID, | and its share of memory: the floor space it takes.",
    visual: board([
      { t: "box", x: 100, y: 120, w: 500, h: 200, title: "PID 1", body: ["systemd", "starts everything else"], color: C.dim, beat: 1 },
      { t: "box", x: 710, y: 120, w: 500, h: 200, title: "PID 2381", body: ["bash", "your shell · 8 MB"], beat: 1, delay: 0.6, color: C.tealHi },
      { t: "box", x: 1320, y: 120, w: 500, h: 200, title: "PID 3127", body: ["firefox", "a browser · 640 MB"], beat: 2 },
      { t: "box", x: 400, y: 420, w: 500, h: 200, title: "PID 4410", body: ["sleep 600", "waits, does nothing"], beat: 2, delay: 0.6, color: C.green },
      { t: "box", x: 1020, y: 420, w: 500, h: 200, title: "PID 4502", body: ["./hello", "ran, printed, ended"], beat: 2, delay: 1.2, color: C.line },
      { t: "gear", x: 260, y: 560, r: 50, beat: 1 },
      { t: "gear", x: 1680, y: 560, r: 60, teeth: 11, speed: -0.5, beat: 2 },
    ]) },
  { id: "c8-ps", chapter: ch.c8, text: "Start one that just waits: `sleep 600 &`. The ampersand keeps it in the background. | `ps` lists your processes. | `ps aux` lists every process on the computer, so pipe it through grep to find one. | `pgrep` does both at once, and prints just the PID.",
    say: "Start one that just waits: sleep 600, and an ampersand. The ampersand keeps it in the background. | P S lists your processes. | P S A U X lists every process on the computer, so pipe it through grep to find one. | P grep does both at once, and prints just the P I D.",
    visual: term([
      { cmd: "sleep 600 &", beat: 0, delay: 0.8, out: ["[1] 4410"] },
      { cmd: "ps", beat: 1, delay: 0.2, out: ["    PID TTY          TIME CMD", "   2381 pts/0    00:00:00 bash", "   4410 pts/0    00:00:00 sleep", "   4415 pts/0    00:00:00 ps"] },
      { cmd: "ps aux | grep firefox", beat: 2, delay: 0.3, out: ["student   3127  4.2  3.9 11853240 640312 ?  Sl  09:05  1:12 /nix/store/…-firefox/bin/firefox"] },
      { cmd: "pgrep sleep", beat: 3, delay: 0.3, out: ["4410"] },
    ]) },
  { id: "c8-btop", chapter: ch.c8, text: "For the whole shop floor, live, run `btop`. | Every process, sorted by how hard it works, with the processor and memory gauges on top. `q` quits.",
    say: "For the whole shop floor, live, run B top. | Every process, sorted by how hard it works, with the processor and memory gauges on top. Q quits.",
    visual: term([
      { cmd: "btop", beat: 0, delay: 1 },
      { noPrompt: true, beat: 1, out: [
        "{t}── cpu ─────────────────────────────── 18% ──  ── mem ──────────────{/}",
        " {a}██████████{/}{d}··························{/}              used  {a}3.1 GiB{/}",
        " {d}4 cores · 2.1 GHz · 52 °C{/}                         free  12.4 GiB",
        "",
        "{t}── proc ──────────────────────────────────────────────────────────────{/}",
        " {B}  Pid  Program   Command                 Threads   MemB   Cpu%{/}",
        "   3127  firefox   /nix/store/…/firefox         92   640M    4.2",
        "   1806  Xorg      /nix/store/…/Xorg            12   210M    1.1",
        "   2381  bash      -bash                         1     8M    0.0",
        "   4410  sleep     sleep 600                     1     2M    0.0",
      ] },
    ], { busy: true }) },
  { id: "c8-mem", chapter: ch.c8, text: "How much memory is one process using? `ps -o` picks the columns: rss is the resident memory, in kilobytes, really occupied in RAM. | The kernel's own report is in slash proc, under the PID. | And `free -h` shows the whole computer's.",
    say: "How much memory is one process using? P S dash O picks the columns: R S S is the resident memory, in kilobytes, really occupied in RAM. | The kernel's own report is in slash proc, under the P I D. | And free dash H shows the whole computer's.",
    visual: term([
      { cmd: "ps -o pid,rss,comm -p 3127", beat: 0, delay: 2.2, out: ["    PID   RSS COMMAND", "   3127 640312 firefox"] },
      { cmd: "grep VmRSS /proc/3127/status", beat: 1, delay: 0.3, out: ["VmRSS:\t  640312 kB"] },
      { cmd: "free -h", beat: 2, delay: 0.3, out: ["               total        used        free      shared  buff/cache   available", "Mem:            15Gi       3.1Gi        9.6Gi       412Mi       2.8Gi        12Gi", "Swap:          7.7Gi          0B       7.7Gi"] },
    ]) },
  { id: "c8-kill", chapter: ch.c8, text: "To stop a machine, `kill` sends it a signal. Plain kill asks politely: shut down, and clean up first. | If it won't listen, `kill -9` cuts the power. | `pkill` stops processes by name.",
    say: "To stop a machine, kill sends it a signal. Plain kill asks politely: shut down, and clean up first. | If it won't listen, kill dash nine cuts the power. | P kill stops processes by name.",
    visual: term([
      { cmd: "kill 4410", beat: 0, delay: 1.2, out: ["[1]+  Terminated              sleep 600"] },
      { cmd: "sleep 900 &", beat: 1, out: ["[1] 4620"] },
      { cmd: "kill -9 4620", beat: 1, delay: 1.2, out: ["[1]+  Killed                  sleep 900"] },
      { cmd: "pkill firefox", beat: 2, delay: 0.3 },
    ]) },

  // ---------------------------------------------------------- 9 network
  { id: "c9-title", chapter: ch.c9, text: "Chapter nine. Networks and ports: addresses, and loading docks.",
    visual: title(9, "Network and ports", "a street address, and numbered loading docks") },
  { id: "c9-idea", chapter: ch.c9, text: "Every computer on a network has an IP address, like a street address for a factory. | Each program that talks to the network gets a port: a numbered loading dock. Web servers use dock 443, SSH uses 22. | An address plus a port reaches one program.",
    visual: board([
      { t: "box", x: 600, y: 60, w: 720, h: 560, title: "this computer", body: [], beat: 0, color: C.text, top: true },
      { t: "text", x: 960, y: 125, text: "IP address {a}192.168.1.42{/}", size: 36, mono: true, align: "center", w: 700, beat: 0, delay: 2 },
      { t: "box", x: 650, y: 240, w: 300, h: 110, title: "port 22", body: "sshd", beat: 1, delay: 1, size: 26, color: C.tealHi },
      { t: "box", x: 970, y: 240, w: 300, h: 110, title: "port 8000", body: "your web server", beat: 1, delay: 1.4, size: 26 },
      { t: "box", x: 650, y: 390, w: 300, h: 110, title: "port 631", body: "printing (cups)", beat: 1, delay: 1.8, size: 26, color: C.dim },
      { t: "box", x: 970, y: 390, w: 300, h: 110, title: "port 53", body: "name lookups", beat: 1, delay: 2.2, size: 26, color: C.dim },
      { t: "box", x: 60, y: 260, w: 380, h: 170, title: "a laptop", body: "192.168.1.7", beat: 2, color: C.dim },
      { t: "arrow", from: [445, 345], to: [645, 295], label: "to :22", beat: 2, delay: 0.5, color: C.amber },
      { t: "box", x: 1480, y: 260, w: 380, h: 170, title: "a website", body: "185.199.108.153 :443", beat: 2, delay: 1, color: C.dim },
      { t: "arrow", from: [1325, 560], to: [1560, 435], label: "out to :443", beat: 2, delay: 1.4 },
    ]) },
  { id: "c9-ip", chapter: ch.c9, text: "`ip -br addr` shows your addresses, one line per network card. `lo` is the loopback, 127.0.0.1: the computer talking to itself. | On MeccanicOS, `mos-config network` sums it all up, internet included.",
    say: "I P dash B R adder shows your addresses, one line per network card. L O is the loopback, 127.0.0.1: the computer talking to itself. | On MeccanicOS, mos config network sums it all up, internet included.",
    visual: term([
      { cmd: "ip -br addr", beat: 0, delay: 0.3, out: ["lo               UNKNOWN        127.0.0.1/8 ::1/128", "wlp2s0           {g}UP{/}             {a}192.168.1.42/24{/} fe80::8c1e:22ff:fe41:9a0c/64"] },
      { cmd: "mos-config network", beat: 1, delay: 0.5, out: ["{w}network{/}", "  connection  Campus-Net (Wi-Fi 78%, 192.168.1.42)", "  device      wlp2s0", "  internet    {g}yes{/}", "  vpn         none set up"] },
    ]) },
  { id: "c9-ping", chapter: ch.c9, text: "`ping` checks if a machine answers, and how fast. | `curl` fetches a page. ifconfig dot me answers with your public address: the one the internet sees.",
    say: "Ping checks if a machine answers, and how fast. | Curl fetches a page. If config dot me answers with your public address: the one the internet sees.",
    visual: term([
      { cmd: "ping -c 2 meccanicos.com", beat: 0, delay: 0.3, out: ["64 bytes from 185.199.108.153: icmp_seq=1 ttl=57 time=12.0 ms", "64 bytes from 185.199.108.153: icmp_seq=2 ttl=57 time=11.6 ms"] },
      { cmd: "curl ifconfig.me", beat: 1, delay: 0.3, out: ["203.0.113.84"] },
    ]) },
  { id: "c9-ports", chapter: ch.c9, text: "Let's open a dock: Python's built-in web server, on port 8000. | Then `ss -tulpn` lists every port in use, and which program holds it. With sudo, it can name the system's programs too.",
    say: "Let's open a dock: Python's built in web server, on port 8000. | Then S S dash T U L P N lists every port in use, and which program holds it. With sue doo, it can name the system's programs too.",
    visual: term([
      { cmd: "python3 -m http.server 8000 &", beat: 0, delay: 0.5, out: ["[1] 5120", "Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ..."] },
      { cmd: "sudo ss -tulpn", beat: 1, delay: 0.3, out: ["Netid State  Local Address:Port  Process", "udp   UNCONN 127.0.0.54:53       users:((\"systemd-resolve\",pid=702))", "tcp   LISTEN 0.0.0.0:22          users:((\"sshd\",pid=1033))", "tcp   LISTEN 127.0.0.1:631       users:((\"cupsd\",pid=1120))", "tcp   LISTEN {a}0.0.0.0:8000{/}        users:(({a}\"python3\",pid=5120{/}))"] },
    ]) },
  { id: "c9-lsof", chapter: ch.c9, text: "To ask about one dock, `lsof -i` with the port number. | Fetch the page from it, through the loopback. | And stop the server: `kill`, with its PID.",
    say: "To ask about one dock, L S O F dash I with the port number. | Fetch the page from it, through the loopback. | And stop the server: kill, with its P I D.",
    visual: term([
      { cmd: "lsof -i :8000", beat: 0, delay: 0.5, out: ["COMMAND  PID    USER   FD   TYPE  NODE NAME", "python3 5120 student    3u  IPv4   TCP *:8000 (LISTEN)"] },
      { cmd: "curl -s localhost:8000 | head -3", beat: 1, delay: 0.2, out: ["<!DOCTYPE HTML>", "<html lang=\"en\">", "<head>"] },
      { cmd: "kill 5120", beat: 2, delay: 0.3, out: ["[1]+  Terminated              python3 -m http.server 8000"] },
    ], { cwd: "~/projects" }) },

  // ---------------------------------------------------------- 10 mos
  { id: "c10-title", chapter: ch.c10, text: "Chapter ten. Configuring the system, with MeccanicOS's own control panel.",
    visual: title(10, "Configuring MeccanicOS", "the maintenance panel") },
  { id: "c10-mos", chapter: ch.c10, text: "Type `mos` for the list of MeccanicOS's own commands. | Each one explains itself with dash dash help, and `mos help` opens the manual on any topic.",
    say: "Type mos for the list of MeccanicOS's own commands. | Each one explains itself with dash dash help, and mos help opens the manual on any topic.",
    visual: term([
      { cmd: "mos", beat: 0, delay: 0.6, out: ["{w}Fix and set up{/}", "  {a}mos-doctor{/}      find and fix problems: Wi-Fi, Bluetooth, sound, display, disk", "  {a}mos-config{/}      common settings in one place; export them to another computer", "{w}Apps and files{/}", "  {a}mos-apps{/}        find, try, install and remove apps", "  {a}mos-open{/}        open any file with the right app (also: open)", "  {a}mos-print{/}       print a file, or save it as PDF (also: print)", "{w}System{/}", "  {a}mos-updates{/}     updates in one place: system and apps, and how to go back", "  {a}mos-upgrade{/}     update to the newest MeccanicOS and NixOS packages"] },
    ]) },
  { id: "c10-config", chapter: ch.c10, text: "`mos-config list` shows the common settings and their values. | `mos-config set` with just a name explains it. | Add a value, and it changes: here, a bigger text size.",
    say: "Mos config list shows the common settings and their values. | Mos config set with just a name explains it. | Add a value, and it changes: here, a bigger text size.",
    visual: term([
      { cmd: "mos-config list | head -5", beat: 0, delay: 0.6, out: ["{w}display{/}", "  display.scale             auto          size of text on screen", "  display.rotation          landscape     landscape or portrait", "{w}keyboard{/}", "  keyboard.layout           us            keyboard layouts, first is the default"] },
      { cmd: "mos-config set power.screen_off", beat: 1, delay: 0.3, out: ["power.screen_off: turn the screen off after this many minutes (never)", "now: 15 min", "example: mos-config set power.screen_off 10"] },
      { cmd: "mos-config set display.scale 1.5", beat: 2, delay: 0.3, out: ["{g}display.scale = 1.5{/}"] },
    ]) },
  { id: "c10-doctor", chapter: ch.c10, text: "Something not working? `mos-doctor` checks the network, sound, display and disk, explains what's wrong, and asks before fixing it. | And `mos-updates` keeps the whole system current, with a way back.",
    say: "Something not working? Mos doctor checks the network, sound, display and disk, explains what's wrong, and asks before fixing it. | And mos updates keeps the whole system current, with a way back.",
    visual: term([
      { cmd: "mos-doctor", beat: 0, delay: 1.2, out: ["{g}✓{/} Wi-Fi or internet: OK", "{g}✓{/} Bluetooth: OK", "{g}✓{/} Sound: OK", "{g}✓{/} Screen or graphics: OK", "{g}✓{/} Disk space: OK", "{g}✓{/} Logins and SSH: OK"] },
      { cmd: "mos-updates", beat: 1, delay: 0.5 },
    ]) },

  // ----------------------------------------------------------- 11 disks
  { id: "c11-title", chapter: ch.c11, text: "Chapter eleven. Disks: the warehouses where the cabinet is stored.",
    visual: title(11, "Disks", "warehouses, rooms, and doors into the cabinet") },
  { id: "c11-idea", chapter: ch.c11, text: "A disk is a warehouse. It's split into partitions, like rooms, and each partition holds a filesystem. | Mounting a filesystem attaches it to a folder of the one big tree: a door from the cabinet into that room.",
    visual: board([
      { t: "box", x: 80, y: 40, w: 760, h: 540, title: "disk nvme0n1 · 512 GB", body: [], beat: 0, color: C.text, top: true },
      { t: "box", x: 120, y: 140, w: 360, h: 400, title: "nvme0n1p2", body: ["511 GB", "encrypted", "your system", "and files"], beat: 0, delay: 2, size: 26 },
      { t: "box", x: 510, y: 140, w: 290, h: 150, title: "nvme0n1p1", body: "1 GB · boot", beat: 0, delay: 2.4, size: 26, color: C.dim },
      { t: "box", x: 120, y: 620, w: 720, h: 110, title: "USB stick · sda1 · 32 GB", beat: 0, delay: 3.5, size: 26, color: C.tealHi },
      { t: "arrow", from: [845, 400], to: [1120, 385], label: "mounted on", beat: 1, color: C.amber },
      { t: "box", x: 1125, y: 330, w: 280, h: 110, title: "/", size: 30, beat: 1, delay: 0.3 },
      { t: "arrow", from: [845, 215], to: [1120, 175], beat: 1, delay: 1, color: C.dim },
      { t: "box", x: 1125, y: 120, w: 280, h: 100, title: "/boot", size: 28, beat: 1, delay: 1.3, color: C.dim },
      { t: "arrow", from: [845, 675], to: [1120, 615], beat: 1, delay: 2, color: C.tealHi },
      { t: "box", x: 1125, y: 560, w: 690, h: 110, title: "/run/media/student/USB", size: 28, beat: 1, delay: 2.3, color: C.tealHi },
    ]) },
  { id: "c11-lsblk", chapter: ch.c11, text: "`lsblk` lists the disks and their partitions, and where each is mounted. | `df -h` shows how full each filesystem is, in human sizes.",
    say: "L S block lists the disks and their partitions, and where each is mounted. | D F dash H shows how full each filesystem is, in human sizes.",
    visual: term([
      { cmd: "lsblk", beat: 0, delay: 0.5, out: ["NAME          SIZE TYPE  MOUNTPOINTS", "sda          28.9G disk", "└─sda1       28.9G part", "nvme0n1     476.9G disk", "├─nvme0n1p1     1G part  /boot", "└─nvme0n1p2 475.9G part", "  └─cryptroot 475.9G crypt /nix/store", "                         /"] },
      { cmd: "df -h / /boot", beat: 1, delay: 0.3, out: ["Filesystem             Size  Used Avail Use% Mounted on", "/dev/mapper/cryptroot  468G  189G  256G  {a}43%{/} /", "/dev/nvme0n1p1        1022M  211M  812M  21% /boot"] },
    ]) },
  { id: "c11-du", chapter: ch.c11, text: "Running out of space? `du -sh` measures folders. | `ncdu` lets you walk through them, biggest first, and delete what you don't need.",
    say: "Running out of space? D U dash S H measures folders. | N C D U lets you walk through them, biggest first, and delete what you don't need.",
    visual: term([
      { cmd: "du -sh ~/* | sort -h", beat: 0, delay: 1, out: ["4.0K\t/home/student/Desktop", "312K\t/home/student/projects", "1.2M\t/home/student/Documents", "820M\t/home/student/Pictures", "{a}6.4G{/}\t/home/student/Videos"] },
      { cmd: "ncdu ~", beat: 1, delay: 0.2 },
      { noPrompt: true, beat: 1, delay: 1.2, out: ["{t}ncdu 2.9.2 ~ Use the arrow keys to navigate, press ? for help{/}", "--- /home/student ------------------------------------------", "    {a}6.4 GiB{/} [{a}##########{/}] /Videos", "  820.0 MiB [{a}#{/}         ] /Pictures", "    1.2 MiB [          ] /Documents", "  312.0 KiB [          ] /projects"] },
    ], { busy: true }) },
  { id: "c11-usb", chapter: ch.c11, text: "Plug in a USB stick: `lsblk` shows it as a new disk, sda. | `udisksctl mount` attaches it, with no password, and tells you where. | Before pulling it out, unmount it, so every file is completely written.",
    say: "Plug in a USB stick: L S block shows it as a new disk, S D A. | U disks control mount attaches it, with no password, and tells you where. | Before pulling it out, unmount it, so every file is completely written.",
    visual: term([
      { cmd: "udisksctl mount -b /dev/sda1", beat: 1, delay: 0.2, out: ["Mounted /dev/sda1 at /run/media/student/USB"] },
      { cmd: "cp notes.txt /run/media/student/USB/", beat: 1, delay: 3.6 },
      { cmd: "udisksctl unmount -b /dev/sda1", beat: 2, delay: 0.3, out: ["Unmounted /dev/sda1."] },
    ], { cwd: GB }) },
  { id: "c11-careful", chapter: ch.c11, text: "One warning: tools that write disks directly, like `dd`, `mkfs` or `wipefs`, erase whatever they point at, with no question asked. | Check the device name with lsblk, twice. For disk health, `mos-doctor disk` has you covered.",
    say: "One warning: tools that write disks directly, like D D, make F S or wipe F S, erase whatever they point at, with no question asked. | Check the device name with L S block, twice. For disk health, mos doctor disk has you covered.",
    visual: board([
      { t: "box", x: 360, y: 80, w: 1200, h: 300, title: "⚠  dd · mkfs · wipefs", body: ["write straight to a disk, no trash, no undo", "{a}of=/dev/sda{/} is the USB stick · {r}of=/dev/nvme0n1{/} is your whole computer"], color: C.red, beat: 0, size: 40 },
      { t: "text", x: 960, y: 470, text: "check with {a}lsblk{/}, twice · health: {a}mos-doctor disk{/}", size: 40, align: "center", w: 1500, beat: 1 },
    ]) },

  // -------------------------------------------------------------- end
  { id: "end-sheet", chapter: ch.end, text: "That's the workshop tour. Here is every tool on one sheet: pause the video and keep it. | Practice a little every day, and in a week the shell will feel like your own hands.",
    visual: () => <Sheet />, tail: 90 },
];

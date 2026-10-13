// The whole video: one entry per scene, in order.
//   text    narration and captions. "|" splits it into segments: each one is
//           spoken after a short pause, and is the beat things start on.
//           `code` in backticks: monospace in the captions.
//   say     how the voice reads it, when that differs (same "|" segments)
//   visual  what is on screen (steps and elements start on `beat: k`)
// A scene lasts as long as its narration (src/durations.json, `npm run voice`).
import React from "react";
import { Phases } from "./components/Beats";
import { Board, El } from "./components/Board";
import { Jed } from "./components/Editors";
import { Installer } from "./components/Installer";
import { Net, NetProps } from "./components/Net";
import { Sheet } from "./components/Pages";
import { Step, Terminal } from "./components/Terminal";
import { Title } from "./components/Title";
import { Disk, Vault } from "./components/Vault";
import { COMMANDS, commandNames } from "./commands";
import { C } from "./theme";

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

// The computers a shell can be on: its prompt, and the callout saying which.
const HOSTS = {
  hq: { who: "admin@hq", on: { name: "hq", role: "the server", color: C.tealHi } },
  me: { who: "mrossi@laptop", on: { name: "laptop", role: "your own computer, the admin's", color: C.amber } },
  live: { who: "live@meccanicos", on: { name: "ws-001", role: "the new computer, started from the stick", color: C.blue } },
  ws2: { who: "lbianchi@ws-002", on: { name: "ws-002", role: "a computer of the fleet: Laura's laptop", color: C.blue } },
};
type Host = keyof typeof HOSTS;
type TermOpts = Partial<React.ComponentProps<typeof Terminal>>;
const term = (host: Host, steps: Step[], o: TermOpts = {}) => {
  const all = annotate(steps);
  return () => <Terminal steps={all} {...HOSTS[host]} {...o} />;
};
const board = (els: El[]) => () => <Board els={els} />;
const net = (p: NetProps) => () => <Net {...p} />;
const title = (n: number | string, t: string, m: string) => () => <Title n={n} title={t} metaphor={m} />;
// A command typed in the terminal (beat 0), then the program it opens (from `beat`).
const then = (host: Host, cwd: string, cmd: string, beat: number, program: () => React.ReactNode, before: Step[] = []) => {
  const typing = term(host, [...before, { cmd, beat: 0, delay: before.length ? 3 : 0.6, typed: 12 }], { cwd, busy: true });
  return () => <Phases phases={[{ beat: 0, render: typing }, { beat, render: program }]} />;
};
const vaults = (vs: React.ComponentProps<typeof Vault>[]) => () => <>{vs.map((v, i) => <Vault key={i} {...v} />)}</>;
const GRID: [number, number][] = [[110, 10], [1010, 10], [110, 400], [1010, 400]];

const SERVER = "hq.corp.example.com";
const FP = "SHA256:VJ6Poo/MledBAdyYrrTivq9nssPmggAqjcNzbrshjrc";
const WS_FP = "SHA256:Qm4xT2c8LrWq0pHn5ZbE1yGk9vJd3sFa6uXo7iN7Ka0";
const ALL = ["admin", "ws1", "ws2", "ws3"] as NetProps["show"];
const OFFICE = ["{d}# Profile office: the computers whose host.toml says profile = \"office\".{/}", "{d}# Who may log in: the groups whose profiles include \"office\" (groups.toml).{/}", "{ pkgs, ... }:", "{", "  environment.systemPackages = with pkgs; [", "    libreoffice", "    thunderbird", "  ];", "}"];
const RECOVERY = "bkrhcveg-tnjdlfiu-ghvcrkeb-lnjtuhdf-vbkcrthg-ijfnedvl-cuhkgbrt-dnvlfjie";
const PUSHED = ["{d}mos-fleet: accepted; the server builds the computers now (mos-fleet status).{/}", "Pushed main."];
const SERVICES = ["ssh", "git", "build", "state", "secrets", "tang"] as const;

const ch = {
  intro: "Welcome",
  c1: "1 · The big picture",
  c2: "2 · Before you start",
  c3: "3 · The server",
  c4: "4 · The repository",
  c5: "5 · Adding computers",
  c6: "6 · Every day",
  c7: "7 · When something goes wrong",
  c8: "8 · Backups, and safety",
  end: "Cheat sheet",
};

export const scenes: Scene[] = [
  // ---------------------------------------------------------------- intro
  { id: "intro-1", chapter: ch.intro, text: "This video shows how to run all of an organization's computers on MeccanicOS, from one place. It follows the fleet admin guide, step by step. | Fleet management is new, and still experimental: try it on spare machines first.",
    visual: title("MECCANICOS FLEETS", "One server, many computers", "the admin guide, step by step · experimental") },
  { id: "intro-why", chapter: ch.intro,
    text: "A company with ten, or a thousand, computers wants to manage them from one place. | The same software and settings everywhere. People's accounts in one list, so anyone can sit at any desk. Updates rolled out to everyone together. And every disk encrypted, without visiting each desk. | MeccanicOS workstations can do that: each one takes its whole configuration from a central server.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "{a}One place{/} for every computer", size: 44, beat: 0 },
      { t: "box", x: 80, y: 120, w: 820, h: 120, title: "the same software", body: "and settings, everywhere", beat: 1, size: 30, align: "left" },
      { t: "box", x: 80, y: 260, w: 820, h: 120, title: "one list of people", body: "anyone can log in at any desk", beat: 1, delay: 1.5, size: 30, align: "left", color: C.tealHi },
      { t: "box", x: 80, y: 400, w: 820, h: 120, title: "updates together", body: "rolled out to every computer at once", beat: 1, delay: 4, size: 30, align: "left", color: C.green },
      { t: "box", x: 80, y: 540, w: 820, h: 120, title: "encrypted disks", body: "with nobody visiting each desk", beat: 1, delay: 6, size: 30, align: "left", color: C.sand },
      { t: "box", x: 1150, y: 120, w: 500, h: 150, title: "the server", body: "the configuration", beat: 2, color: C.tealHi },
      { t: "arrow", from: [1400, 275], to: [1100, 470], beat: 2, delay: 0.8, color: C.amber },
      { t: "arrow", from: [1400, 275], to: [1400, 470], beat: 2, delay: 1, color: C.amber },
      { t: "arrow", from: [1400, 275], to: [1700, 470], beat: 2, delay: 1.2, color: C.amber },
      { t: "box", x: 980, y: 480, w: 240, h: 110, title: "ws-001", beat: 2, delay: 1.4, color: C.blue, size: 26 },
      { t: "box", x: 1280, y: 480, w: 240, h: 110, title: "ws-002", beat: 2, delay: 1.6, color: C.blue, size: 26 },
      { t: "box", x: 1580, y: 480, w: 240, h: 110, title: "ws-003", beat: 2, delay: 1.8, color: C.blue, size: 26 },
    ]) },
  { id: "intro-nixos", chapter: ch.intro,
    text: "NixOS, the base of MeccanicOS, makes this easier than other operating systems. | Elsewhere, you install a computer and then keep changing it, with scripts, disk images or management agents. Over time, every computer drifts a little. | On NixOS the whole system is described in a few text files. The server builds it once, and every computer gets an identical copy. | And an update is all or nothing: if it fails, nothing changes, and the previous version is still in the boot menu.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "Why {a}NixOS{/} makes it easier", size: 44, beat: 0 },
      { t: "box", x: 80, y: 110, w: 840, h: 600, title: "Other operating systems", top: true, align: "left", color: C.red, beat: 1, size: 42,
        body: ["", "install, then keep changing it:", "scripts, disk images, agents", "", "every computer drifts a little", "", "a failed update: half done"] },
      { t: "box", x: 1000, y: 110, w: 840, h: 600, title: "NixOS, under MeccanicOS", top: true, align: "left", color: C.green, beat: 2, size: 42,
        body: ["", "the whole system: a few text files", "", "built once, on the server;", "every computer: an identical copy", "", "an update: all or nothing,", "the previous one in the boot menu"] },
      { t: "gear", x: 1760, y: 640, r: 50, beat: 3 },
    ]) },
  { id: "intro-tools", chapter: ch.intro,
    text: "And it needs very little. A git repository holds the truth: which computers there are, what they run, and who may log in. | Everything travels over SSH. | Nix builds each computer's system. | And SQLite keeps what the computers report. Nothing else: no web services, no extra databases.",
    say: "And it needs very little. A git repository holds the truth: which computers there are, what they run, and who may log in. | Everything travels over S S H. | Nix builds each computer's system. | And S Q Lite keeps what the computers report. Nothing else: no web services, no extra databases.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "Four tools, {a}nothing else{/}", size: 44, beat: 0 },
      { t: "box", x: 80, y: 130, w: 820, h: 250, title: "git", body: ["one repository: the truth", "computers, profiles, people"], beat: 0, delay: 0.8, color: C.amber },
      { t: "box", x: 1010, y: 130, w: 820, h: 250, title: "SSH", body: ["every connection", "keys, never passwords"], beat: 1, color: C.tealHi },
      { t: "box", x: 80, y: 440, w: 820, h: 250, title: "Nix", body: ["builds each computer's system", "on the server"], beat: 2, color: C.blue },
      { t: "box", x: 1010, y: 440, w: 820, h: 250, title: "SQLite", body: ["what the computers report:", "facts, logs, what they ran"], beat: 3, color: C.green },
    ]) },

  // ---------------------------------------------------- 1 the big picture
  { id: "c1-title", chapter: ch.c1, text: "Chapter one. The big picture: one company, one server, one repository.",
    visual: title(1, "The big picture", "one company, one server, one repository") },
  { id: "c1-company", chapter: ch.c1,
    text: "Here is Example Corp, | with its office network. | On it, one server called hq, also running MeccanicOS, holds everything the fleet needs.",
    say: "Here is Example Corp, | with its office network. | On it, one server called H Q, also running MeccanicOS, holds everything the fleet needs.",
    visual: net({ add: [{ id: "hq", beat: 2 }], hi: [{ id: "hq", beat: 2, delay: 1, for: 3 }] }) },
  { id: "c1-services", chapter: ch.c1,
    text: "One SSH account, called fleet: the only way in, for computers and admins alike, each with their own key. | The fleet repository, a git repository: changing a computer means changing a file there. | The builds: the server turns the repository into every computer's system. | Two SQLite databases: one for what the computers report, | and one for password hashes and disk recovery keys. | And Tang, which lets office desktops unlock their disks by themselves, but only on the office network.",
    say: "One S S H account, called fleet: the only way in, for computers and admins alike, each with their own key. | The fleet repository, a git repository: changing a computer means changing a file there. | The builds: the server turns the repository into every computer's system. | Two S Q Lite databases: one for what the computers report, | and one for password hashes and disk recovery keys. | And Tang, which lets office desktops unlock their disks by themselves, but only on the office network.",
    visual: net({ hi: [{ id: "ssh", beat: 0, for: 7 }, { id: "git", beat: 1, for: 7 }, { id: "build", beat: 2, for: 6 }, { id: "state", beat: 3, for: 4 }, { id: "secrets", beat: 4, for: 5 }, { id: "tang", beat: 5 }] }) },
  { id: "c1-computers", chapter: ch.c1,
    text: "Your own computer, the admin's, is on the same network. | Every other computer runs MeccanicOS in managed mode. Here, three of them.",
    visual: net({ add: [{ id: "admin", beat: 0 }, { id: "ws1", beat: 1, delay: 1 }, { id: "ws2", beat: 1, delay: 1.6 }, { id: "ws3", beat: 1, delay: 2.2 }] }) },
  { id: "c1-managed", chapter: ch.c1,
    text: "Each managed computer keeps one SSH connection open to the server, with its own key. It always calls out, so laptops work from anywhere. | Over it, the server tells it which system to run, and the computer fetches it, already built. | It also gets its people's password hashes, and jobs, such as run a command, or restart. | And it sends back facts and logs, into the database.",
    say: "Each managed computer keeps one S S H connection open to the server, with its own key. It always calls out, so laptops work from anywhere. | Over it, the server tells it which system to run, and the computer fetches it, already built. | It also gets its people's password hashes, and jobs, such as run a command, or restart. | And it sends back facts and logs, into the database.",
    visual: net({ show: ALL, flows: [
      { from: "ws1", to: "ssh", label: "connect", beat: 0, delay: 1.5 }, { from: "ws2", to: "ssh", label: "connect", beat: 0, delay: 2.1 }, { from: "ws3", to: "ssh", label: "connect", beat: 0, delay: 2.7 },
      { from: "build", to: "ws1", label: "system", beat: 1, delay: 0.8, dur: 2.6 }, { from: "build", to: "ws2", label: "system", beat: 1, delay: 1.2, dur: 2.6 }, { from: "build", to: "ws3", label: "system", beat: 1, delay: 1.6, dur: 2.6 },
      { from: "secrets", to: "ws2", label: "hashes", beat: 2, delay: 0.5, color: C.sand }, { from: "ssh", to: "ws3", label: "job", beat: 2, delay: 2.6, color: C.blue },
      { from: "ws1", to: "state", label: "facts", beat: 3, color: C.green }, { from: "ws2", to: "state", label: "logs", beat: 3, delay: 0.5, color: C.green }, { from: "ws3", to: "state", label: "facts", beat: 3, delay: 1, color: C.green },
    ], tags: [{ id: "ws1", text: "connected", beat: 0, delay: 3.6, color: C.tealHi }, { id: "ws2", text: "connected", beat: 0, delay: 4.2, color: C.tealHi }, { id: "ws3", text: "connected", beat: 0, delay: 4.8, color: C.tealHi }],
      hi: [{ id: "ssh", beat: 0, delay: 1.5, for: 4 }, { id: "build", beat: 1, for: 4 }, { id: "secrets", beat: 2, for: 3 }, { id: "state", beat: 3 }] }) },
  { id: "c1-unlock", chapter: ch.c1,
    text: "Every disk is encrypted. A desktop in the office unlocks it with its TPM chip and the Tang server; a laptop with the TPM and a PIN; or with a FIDO2 security key. | A key is never sent over the network. | And every computer has a recovery key, encrypted so that only the admins can read it, kept on the server.",
    say: "Every disk is encrypted. A desktop in the office unlocks it with its T P M chip and the Tang server; a laptop with the T P M and a PIN; or with a Fido two security key. | A key is never sent over the network. | And every computer has a recovery key, encrypted so that only the admins can read it, kept on the server.",
    visual: net({ show: ALL, tags: [{ id: "ws1", text: "TPM + Tang", beat: 0, delay: 1, color: C.tealHi }, { id: "ws2", text: "TPM + PIN", beat: 0, delay: 3.5 }, { id: "ws3", text: "security key", beat: 0, delay: 5.5, color: C.blue }],
      flows: [{ from: "ws1", to: "tang", label: "unlock?", beat: 0, delay: 1 }, { from: "tang", to: "ws1", label: "help", beat: 0, delay: 3.4, color: C.tealHi },
        { from: "ws1", to: "secrets", label: "recovery.age", beat: 2, delay: 1.5, color: C.sand }, { from: "ws2", to: "secrets", label: "recovery.age", beat: 2, delay: 2, color: C.sand }, { from: "ws3", to: "secrets", label: "recovery.age", beat: 2, delay: 2.5, color: C.sand }],
      hi: [{ id: "tang", beat: 0, delay: 1, for: 4 }, { id: "secrets", beat: 2, delay: 1.5 }] }) },
  { id: "c1-repo", chapter: ch.c1,
    text: "The repository has a few files. | `fleet.toml`: the organization and its server. | `groups.toml`, and a file for each person. | A file for each profile, a kind of computer. | And a folder for each computer.",
    say: "The repository has a few files. | fleet dot toml: the organization and its server. | groups dot toml, and a file for each person. | A file for each profile, a kind of computer. | And a folder for each computer.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "{a}~/fleet{/}, the fleet repository", size: 40, beat: 0 },
      { t: "box", x: 80, y: 110, w: 860, h: 120, title: "fleet.toml", body: "Example Corp; the server hq, its SSH key", beat: 1, mono: true, size: 30, align: "left" },
      { t: "box", x: 80, y: 250, w: 860, h: 120, title: "groups.toml", body: "fleet-admins, office: who logs in where, sudo", beat: 2, mono: true, size: 30, align: "left", color: C.tealHi },
      { t: "box", x: 980, y: 250, w: 860, h: 120, title: "people/lbianchi.toml", body: "name, uid, groups, SSH keys", beat: 2, delay: 1.5, mono: true, size: 30, align: "left", color: C.tealHi },
      { t: "box", x: 80, y: 390, w: 860, h: 120, title: "profiles/office.nix", body: "the office computers' software", beat: 3, mono: true, size: 30, align: "left", color: C.green },
      { t: "box", x: 80, y: 530, w: 860, h: 160, title: "hosts/ws-001/", body: ["host.toml: profile, unlock, its SSH key", "and its hardware configuration"], beat: 4, mono: true, size: 30, align: "left", color: C.blue },
      { t: "box", x: 980, y: 530, w: 860, h: 160, title: "common.nix", body: ["every computer's settings"], beat: 4, delay: 1.2, mono: true, size: 30, align: "left", color: C.green },
    ]) },
  { id: "c1-who", chapter: ch.c1,
    text: "Who may log in where is decided by groups, in the repository. | Fleet admins log in everywhere, with sudo, and they're the ones who reach the server. | And each profile, such as office, has a group of the same name, for its own computers.",
    say: "Who may log in where is decided by groups, in the repository. | Fleet admins log in everywhere, with sue doo, and they're the ones who reach the server. | And each profile, such as office, has a group of the same name, for its own computers.",
    visual: board([
      { t: "box", x: 80, y: 40, w: 560, h: 160, title: "groups.toml", body: "in the repository", beat: 0, color: C.amber, mono: true },
      { t: "box", x: 760, y: 40, w: 520, h: 160, title: "fleet-admins", body: "mrossi", beat: 1, color: C.tealHi, mono: true },
      { t: "arrow", from: [1285, 120], to: [1480, 120], beat: 1, delay: 0.6, color: C.tealHi },
      { t: "box", x: 1490, y: 40, w: 360, h: 160, title: "everywhere", body: "sudo; the server", beat: 1, delay: 0.9, color: C.tealHi },
      { t: "box", x: 760, y: 330, w: 520, h: 160, title: "office", body: "lbianchi · gverdi", beat: 2, color: C.blue, mono: true },
      { t: "arrow", from: [1285, 410], to: [1480, 410], beat: 2, delay: 0.6, color: C.blue },
      { t: "box", x: 1490, y: 330, w: 360, h: 160, title: "office computers", body: "ws-001 · ws-002 · ws-003", beat: 2, delay: 0.9, color: C.blue },
      { t: "arrow", from: [640, 120], to: [755, 120], beat: 1 },
      { t: "arrow", from: [400, 205], to: [755, 410], beat: 2 },
    ]) },

  // ------------------------------------------------- 2 before you start
  { id: "c2-title", chapter: ch.c2, text: "Chapter two. Before you start: what you need.",
    visual: title(2, "Before you start", "a server, your computer, a stick") },
  { id: "c2-needs", chapter: ch.c2,
    text: "A server: any 64-bit PC, with 8 gigabytes of memory or more, a 100 gigabyte disk, a fixed address on the office network, and a name the computers can reach. | Your own computer, running MeccanicOS, with an SSH key. | And a MeccanicOS USB stick: it carries your key to the server, and each new computer's settings.",
    say: "A server: any 64-bit PC, with 8 gigabytes of memory or more, a 100 gigabyte disk, a fixed address on the office network, and a name the computers can reach. | Your own computer, running MeccanicOS, with an S S H key. | And a MeccanicOS USB stick: it carries your key to the server, and each new computer's settings.",
    visual: board([
      { t: "box", x: 80, y: 30, w: 1760, h: 220, title: "a server", body: ["64-bit, 8 GB+ memory, 100 GB+ disk", `a fixed address, and a name: {a}${SERVER}{/}`], beat: 0, color: C.tealHi },
      { t: "box", x: 80, y: 300, w: 860, h: 330, title: "your computer", body: ["MeccanicOS", "an SSH key:", "{a}~/.ssh/id_ed25519.pub{/}"], beat: 1, color: C.amber },
      { t: "box", x: 980, y: 300, w: 860, h: 330, title: "a MeccanicOS stick", body: ["made with mos-usb, or Ventoy", "carries keys and settings"], beat: 2, color: C.sand },
    ]) },

  // ------------------------------------------------------- 3 the server
  { id: "c3-title", chapter: ch.c3, text: "Chapter three. The server: install it, then one command.",
    visual: title(3, "The server", "hq: install it, then one command") },
  { id: "c3-install", chapter: ch.c3,
    text: "Install MeccanicOS on the server from the stick, as usual, and name it hq. | Pick a disk password. Write it down, and keep it in a safe: the server can't unlock itself, because it's the one running Tang.",
    say: "Install MeccanicOS on the server from the stick, as usual, and name it H Q. | Pick a disk password. Write it down, and keep it in a safe: the server can't unlock itself, because it's the one running Tang.",
    visual: vaults([{ method: "password", x: 660, y: 200, beat: 1, delay: 2, title: "a password", note: "kept in the safe" }]) },
  { id: "c3-key", chapter: ch.c3,
    text: "The server will only let in SSH keys, so first carry yours to it. On your computer, open the stick's files, | and copy your public key there.",
    say: "The server will only let in S S H keys, so first carry yours to it. On your computer, open the stick's files, | and copy your public key there.",
    visual: term("me", [
      { cmd: "usb-vault stick", beat: 0, delay: 4, out: ["The USB stick's files are at /run/usb-vault/data"] },
      { cmd: "cp ~/.ssh/id_ed25519.pub /run/usb-vault/data/", beat: 1, delay: 0.3 },
    ]) },
  { id: "c3-init", chapter: ch.c3,
    text: "At the server, with the stick, one command turns it into the fleet's server. `--lan` is the office network: only computers there can reach Tang. And `--admin-key` is your key, from the stick. | It rebuilds the system with the fleet's parts: the fleet account, Tang, the builds. | It makes the empty repository and the two databases, and lets your key in, as an admin, for one day. | It ends with the server's SSH fingerprint. Note it: your computer checks it, so it talks to this server and no other.",
    say: "At the server, with the stick, one command turns it into the fleet's server. Dash dash LAN is the office network: only computers there can reach Tang. And dash dash admin key is your key, from the stick. | It rebuilds the system with the fleet's parts: the fleet account, Tang, the builds. | It makes the empty repository and the two databases, and lets your key in, as an admin, for one day. | It ends with the server's S S H fingerprint. Note it: your computer checks it, so it talks to this server and no other.",
    visual: term("hq", [
      { cmd: "mos-fleet server init --lan 10.0.0.0/24 --admin-key /run/usb-vault/data/id_ed25519.pub", beat: 0, delay: 0.5, typed: 32 },
      { noPrompt: true, beat: 1, out: ["{B}== 1/3 The fleet server's settings: /etc/nixos/fleet-server.toml{/}", "   rebuilding the system (the first time downloads what it needs)…"] },
      { noPrompt: true, beat: 2, out: ["{B}== 2/3 The repository, the databases{/}", "   admin key SHA256:t0Yx…mR2e: valid for 24 hours, for the repository's first push", "{B}== 3/3 Done{/}"] },
      { noPrompt: true, beat: 3, out: ["", "{g}The fleet server is ready.{/} Note these two, for the admins' computers:", `  this server's SSH key    {a}${FP}{/}`, "  Tang (disk unlocking)    Kj8xYq0b5TnW2rF…"] },
    ], { fontSize: 23, busy: false }) },
  { id: "c3-net", chapter: ch.c3,
    text: "On the map: the server fetched its parts from the Internet, | and now runs every one of them.",
    visual: net({ show: ["net"], flows: [{ from: "net", to: "hq", label: "MeccanicOS", beat: 0, delay: 0.5, dur: 3 }],
      hi: SERVICES.map((id, i) => ({ id, beat: 1, delay: i * 0.4 })) }) },
  { id: "c3-status", chapter: ch.c3,
    text: "Check it: every line should say ok. There's no repository yet: you make it next, on your own computer.",
    visual: term("hq", [
      { cmd: "mos-fleet server status", beat: 0, delay: 0.5, out: ["{B}== Services{/}", ...["sshd.service", "mos-fleet-setup.service", "mos-fleet-build.path", "mos-fleet-build.timer", "mos-fleet-prune.timer", "tangd.socket"].map((u) => `   {g}ok{/}   ${u.padEnd(28)} active`), "", "{B}== Repository{/}", "   main (none yet: mos-fleet init, on an admin computer)"] },
    ]) },

  // ---------------------------------------------------- 4 the repository
  { id: "c4-title", chapter: ch.c4, text: "Chapter four. The repository, made on your own computer.",
    visual: title(4, "The repository", "made on your computer, kept on the server") },
  { id: "c4-init", chapter: ch.c4,
    text: "Back at your computer, `mos-fleet init` makes the fleet repository. It checks the server's fingerprint first. | It makes your admin key: the recovery keys will be encrypted for it. | It writes the repository in a folder called fleet, with you as a fleet admin, pins the MeccanicOS version, | and pushes it to the server.",
    say: "Back at your computer, mos fleet init makes the fleet repository. It checks the server's fingerprint first. | It makes your admin key: the recovery keys will be encrypted for it. | It writes the repository in a folder called fleet, with you as a fleet admin, pins the MeccanicOS version, | and pushes it to the server.",
    visual: term("me", [
      { cmd: `mos-fleet init --server ${SERVER} --fingerprint SHA256:VJ6P…shjrc --organization "Example Corp" --admin mrossi --full-name "Mario Rossi"`, beat: 0, delay: 0.5, typed: 40 },
      { noPrompt: true, beat: 1, out: ["Your admin key: ~/.config/mos-fleet/admin.key. {r}Back it up now, offline (print it){/}:", "without it you can't read recovery keys."] },
      { noPrompt: true, beat: 2, out: ["Pinning the MeccanicOS version (nix flake lock)…"] },
      { noPrompt: true, beat: 3, out: [...PUSHED, "", "The fleet repository: /home/mrossi/fleet", "Next: mos-fleet profile add office   (a kind of computer)"] },
    ], { fontSize: 23, busy: false }) },
  { id: "c4-init-net", chapter: ch.c4,
    text: "On the map: your repository goes to the server, over SSH, with your key. | From now on, your key is in the repository, as a fleet admin's. Every change starts on your computer.",
    say: "On the map: your repository goes to the server, over S S H, with your key. | From now on, your key is in the repository, as a fleet admin's. Every change starts on your computer.",
    visual: net({ show: ["admin"], flows: [{ from: "admin", to: "ssh", label: "git push", beat: 0, delay: 0.3, dur: 2.4 }, { from: "ssh", to: "git", label: "~/fleet", beat: 0, delay: 2.7, dur: 1.4, color: C.green }],
      hi: [{ id: "admin", beat: 0 }, { id: "git", beat: 1, for: 4 }], tags: [{ id: "admin", text: "fleet admin", beat: 1, delay: 0.5, color: C.tealHi }] }) },
  { id: "c4-profile", chapter: ch.c4,
    text: "Then a profile for each kind of computer; here, office. It adds a file to the repository, and a group with the same name. | Edit the file to list the profile's software.",
    visual: then("me", "~/fleet", "jed profiles/office.nix", 1,
      () => <Jed file="office.nix" mode="nix" dir="~/fleet/profiles/" lines={OFFICE} typeFrom={0.05} typeTo={0.8} keys={[{ keys: "Ctrl+X Ctrl+S", at: 0.86 }]} />,
      [{ cmd: "mos-fleet profile add office", beat: 0, delay: 0.5, out: ["Also the group office, whose members may log in on its computers.", "Committed: profile add office"] }]) },
  { id: "c4-people", chapter: ch.c4,
    text: "Add people: Laura, in the office group. | `mos-fleet validate` checks every file, and builds every computer's configuration in Nix, without installing anything. | Then push. Every command commits; nothing reaches the server until you push.",
    say: "Add people: Laura, in the office group. | mos fleet validate checks every file, and builds every computer's configuration in Nix, without installing anything. | Then push. Every command commits; nothing reaches the server until you push.",
    visual: term("me", [
      { cmd: "mos-fleet person add lbianchi \"Laura Bianchi\" --group office", beat: 0, delay: 0.5, typed: 28, out: ["Committed: person add lbianchi", "   (mos-fleet push sends it to the server)"] },
      { cmd: "mos-fleet validate", beat: 1, delay: 0.3, out: ["Files: ok (0 computers, 2 people, 2 groups, 1 profiles).", "Evaluating every computer's system with Nix…", "Nix: ok (0 computers evaluate)."] },
      { cmd: "mos-fleet push", beat: 2, delay: 0.3, out: PUSHED },
    ], { cwd: "~/fleet" }) },
  { id: "c4-refuse", chapter: ch.c4,
    text: "The server checks every push too. A mistake, say Giulia with Laura's user number, | is refused, with the reason: nothing invalid gets into the repository. | And history can't be rewritten: to undo, you add a commit.",
    visual: term("me", [
      { cmd: "git commit -qam \"gverdi\" && git push", beat: 0, delay: 3.5, typed: 26 },
      { noPrompt: true, beat: 1, out: ["remote: mos-fleet: push refused:", "remote:   main: people/gverdi.toml: {r}uid 2001 is also lbianchi's{/}", " ! [remote rejected] main -> main (pre-receive hook declined)"] },
      { noPrompt: true, beat: 2, out: ["", "{d}# and a force push to main:{/}", "remote:   {r}main can't be rewritten (no force push): add a commit instead (git revert){/}"] },
    ], { cwd: "~/fleet", fontSize: 23 }) },

  // -------------------------------------------------- 5 adding computers
  { id: "c5-title", chapter: ch.c5, text: "Chapter five. Adding computers: three decisions, and one stick.",
    visual: title(5, "Adding computers", "three decisions, one stick") },
  { id: "c5-decide", chapter: ch.c5,
    text: "For each new computer, decide three things. | A name, such as ws-001. | A profile: office. | And how its disk unlocks.",
    say: "For each new computer, decide three things. | A name, such as W S zero zero one. | A profile: office. | And how its disk unlocks.",
    visual: board([
      { t: "box", x: 80, y: 120, w: 540, h: 360, title: "name", body: ["{a}ws-001{/}", "", "lowercase letters,", "digits and -"], beat: 1, color: C.blue, size: 34 },
      { t: "box", x: 690, y: 120, w: 540, h: 360, title: "profile", body: ["{a}office{/}", "", "made with", "mos-fleet profile add"], beat: 2, size: 34 },
      { t: "box", x: 1300, y: 120, w: 540, h: 360, title: "disk unlock", body: ["{a}tang{/}  office desktop", "{a}tpm-pin{/}  laptop", "{a}fido2{/}  security key"], beat: 3, color: C.sand, size: 34 },
    ]) },
  { id: "c5-luks", chapter: ch.c5,
    text: "About that last choice. Every disk is encrypted with LUKS: whatever is written goes through the lock, and on the disk it's just noise. | Without the key, nobody can read it, even with the disk in their hands. | The key can come from different places.",
    say: "About that last choice. Every disk is encrypted with Lux: whatever is written goes through the lock, and on the disk it's just noise. | Without the key, nobody can read it, even with the disk in their hands. | The key can come from different places.",
    visual: () => (
      <>
        <Board els={[
          { t: "box", x: 80, y: 220, w: 460, h: 220, title: "your files", body: ["report.odt", "photos/", "passwords.kdbx"], beat: 0, color: C.green },
          { t: "arrow", from: [545, 330], to: [745, 330], beat: 0, delay: 1, color: C.amber },
          { t: "arrow", from: [1175, 330], to: [1375, 330], beat: 0, delay: 2, color: C.amber },
          { t: "box", x: 1380, y: 220, w: 460, h: 220, title: "on the disk", body: ["9f3a c17e 02d4 b8e1", "77c0 3f9a e215 6bd8", "a04c 19fe 5d72 c3b0"], beat: 0, delay: 2.4, color: C.dim, mono: true },
          { t: "text", x: 960, y: 640, text: "no key: {r}no way in{/}", size: 40, align: "center", w: 1000, beat: 1 },
        ]} />
        <svg width={1920} height={770} style={{ position: "absolute", inset: 0 }}><Disk x={960} y={330} s={1.7} /></svg>
      </>
    ) },
  { id: "c5-ways", chapter: ch.c5,
    text: "Tang, for office desktops: the computer's TPM chip and the Tang server unlock it together, by themselves, but only on the office network. | TPM and PIN, for laptops: the chip in the computer keeps the key, and gives it out only for the right PIN. | FIDO2: a security key, plugged in and touched at power-on. | And always, the recovery key: encrypted for the admins, for when everything else fails.",
    say: "Tang, for office desktops: the computer's T P M chip and the Tang server unlock it together, by themselves, but only on the office network. | T P M and PIN, for laptops: the chip in the computer keeps the key, and gives it out only for the right PIN. | Fido two: a security key, plugged in and touched at power-on. | And always, the recovery key: encrypted for the admins, for when everything else fails.",
    visual: vaults([
      { method: "tang", x: GRID[0][0], y: GRID[0][1], beat: 0, delay: 3 },
      { method: "tpm-pin", x: GRID[1][0], y: GRID[1][1], beat: 1, delay: 2 },
      { method: "fido2", x: GRID[2][0], y: GRID[2][1], beat: 2, delay: 1 },
      { method: "recovery", x: GRID[3][0], y: GRID[3][1], beat: 3, delay: 1.5 },
    ]) },
  { id: "c5-away", chapter: ch.c5,
    text: "That's the point of Tang. A desktop in the office unlocks by itself; | carried away from the office, it can't reach the Tang server, so it stays locked. | And the TPM ties the key to that one computer: the disk alone, taken out, is useless too.",
    say: "That's the point of Tang. A desktop in the office unlocks by itself; | carried away from the office, it can't reach the Tang server, so it stays locked. | And the T P M ties the key to that one computer: the disk alone, taken out, is useless too.",
    visual: vaults([
      { method: "tang", x: GRID[0][0], y: 120, beat: 0, delay: 1, title: "in the office", note: "Tang answers" },
      { method: "tang", x: GRID[1][0], y: 120, beat: 1, delay: 1, fail: true, title: "anywhere else", note: "no Tang server" },
    ]) },
  { id: "c5-serial", chapter: ch.c5,
    text: "Optional: pin the installation to one disk, so that no other disk can be erased by mistake. | Boot the new computer from the stick, open a terminal, and read the internal disk's serial number.",
    visual: term("live", [
      { cmd: "lsblk -d -o NAME,SIZE,MODEL,SERIAL", beat: 1, delay: 0.8, out: ["NAME     SIZE MODEL                SERIAL", "nvme0n1  477G Samsung SSD 980 PRO  {a}S6PNNF0R123456X{/}", "sda       29G USB Flash Disk       0412345678"] },
    ]) },
  { id: "c5-prepare", chapter: ch.c5,
    text: "Back on your computer, plug in the stick, and prepare it for ws-001: its profile, its unlocking, its disk. | It writes a folder on the stick: the settings, the admins' public keys, and a one-time key. | The one-time key lets the new computer introduce itself to the server, once, within a week. Nothing else on the stick is secret.",
    say: "Back on your computer, plug in the stick, and prepare it for W S zero zero one: its profile, its unlocking, its disk. | It writes a folder on the stick: the settings, the admins' public keys, and a one-time key. | The one-time key lets the new computer introduce itself to the server, once, within a week. Nothing else on the stick is secret.",
    visual: term("me", [
      { cmd: "mos-fleet host prepare ws-001 --profile office --unlock tang --disk-serial S6PNNF0R123456X", beat: 0, delay: 3, typed: 32,
        out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-001", "   ws-001: profile office, unlock tang; a one-time key, valid 7 days.", "Boot the computer from this stick and choose Install: it offers the organization install.", "After its first start it introduces itself to the server; then: mos-fleet host add ws-001"] },
    ], { cwd: "~/fleet", fontSize: 24 }) },
  { id: "c5-install", chapter: ch.c5,
    text: "Connect the new computer to the office network with a cable, since Tang needs it. Boot it from the stick and open Install: it finds the folder, and offers the organization install. | Choose the language, the keyboard and the time zone. The organization has already decided the name, the disk and the unlocking. | Install now, and type YES. It checks the server's key, and that Tang answers: if not, nothing has been erased yet. | It sets up the unlocking, and encrypts the recovery key for the admins. | Then it installs MeccanicOS, from the stick. | At the end, it shows the computer's own SSH fingerprint. Note it.",
    say: "Connect the new computer to the office network with a cable, since Tang needs it. Boot it from the stick and open Install: it finds the folder, and offers the organization install. | Choose the language, the keyboard and the time zone. The organization has already decided the name, the disk and the unlocking. | Install now, and type YES. It checks the server's key, and that Tang answers: if not, nothing has been erased yet. | It sets up the unlocking, and encrypts the recovery key for the admins. | Then it installs MeccanicOS, from the stick. | At the end, it shows the computer's own S S H fingerprint. Note it.",
    visual: () => <Installer host="ws-001" unlock="tang" fp="SHA256:Qm4x…7Ka0" at={{ form: 1, install: 2, checks: 2, unlock: 3, download: 4, done: 5 }} /> },
  { id: "c5-install-net", chapter: ch.c5,
    text: "On the map: the new computer binds its disk to Tang. | At its first start, it introduces itself to the server, with the one-time key: its SSH key, its hardware, and its encrypted recovery key. | The one-time key stops working. The server waits for an admin.",
    say: "On the map: the new computer binds its disk to Tang. | At its first start, it introduces itself to the server, with the one-time key: its S S H key, its hardware, and its encrypted recovery key. | The one-time key stops working. The server waits for an admin.",
    visual: net({ show: ["admin"], add: [{ id: "ws1", beat: 0 }], flows: [
      { from: "ws1", to: "tang", label: "bind", beat: 0, delay: 0.6 }, { from: "tang", to: "ws1", label: "bound", beat: 0, delay: 2.8, color: C.tealHi },
      { from: "ws1", to: "ssh", label: "hello (one-time key)", beat: 1, delay: 0.3, dur: 2.6 }, { from: "ssh", to: "secrets", label: "recovery.age", beat: 1, delay: 3, dur: 1.2, color: C.sand },
    ], hi: [{ id: "tang", beat: 0, delay: 0.6, for: 4 }, { id: "ssh", beat: 1, delay: 2.6, for: 3 }],
      tags: [{ id: "ws1", text: "waiting for an admin", beat: 2, color: C.sand }] }) },
  { id: "c5-add", chapter: ch.c5,
    text: "On your computer, `host pending` lists it. | `host add` shows the fingerprint it sent: compare it with the one on its screen. That's how you know the computer is yours. | It writes the computer's folder, and commits. Look at the files, and push.",
    say: "On your computer, host pending lists it. | host add shows the fingerprint it sent: compare it with the one on its screen. That's how you know the computer is yours. | It writes the computer's folder, and commits. Look at the files, and push.",
    visual: term("me", [
      { cmd: "mos-fleet host pending", beat: 0, delay: 1, out: ["ws-001           office       2026-10-13 09:12:40  by mrossi       waiting for: mos-fleet host add"] },
      { cmd: "mos-fleet host add ws-001", beat: 1, delay: 0.3, out: ["ws-001 introduced itself on 2026-10-13 09:40:02 UTC from 10.0.0.31:", `   host key   {a}${WS_FP}{/}`, "   hostname   ws-001, MeccanicOS 26.05", "   disk       nvme0n1 477G Samsung SSD 980 PRO S6PNNF0R123456X", "Add it to the fleet? [y/N] y"] },
      { noPrompt: true, beat: 2, out: ["Committed: host add ws-001"] },
      { cmd: "mos-fleet push", beat: 2, delay: 2.5, out: PUSHED },
    ], { cwd: "~/fleet", fontSize: 23 }) },
  { id: "c5-add-net", chapter: ch.c5,
    text: "Follow the information. Your push reaches the repository, and the new computer's key is now known. | The server builds the new computer's system. | The computer, connected, hears of it within a second, fetches what it lacks, and switches to it. | Now its people can log in.",
    visual: net({ show: ["admin", "ws1"], flows: [
      { from: "admin", to: "ssh", label: "hosts/ws-001", beat: 0, delay: 0.5, dur: 2.4 }, { from: "ssh", to: "git", label: "push", beat: 0, delay: 2.9, dur: 1.2 },
      { from: "git", to: "build", label: "build", beat: 1, dur: 1.8 },
      { from: "ws1", to: "ssh", label: "connect", beat: 1, delay: 0.5 }, { from: "build", to: "ws1", label: "system", beat: 2, dur: 2.6 },
    ], hi: [{ id: "git", beat: 0, delay: 3, for: 3 }, { id: "build", beat: 1, for: 4 }, { id: "ws1", beat: 2, delay: 2.6 }],
      tags: [{ id: "ws1", text: "managed ✓", beat: 3 }] }) },
  { id: "c5-more", chapter: ch.c5,
    text: "Two more computers, the same way. A laptop, ws-002, that unlocks with the TPM and a PIN; | and a desktop, ws-003, with a security key. | Prepare the stick, install, add.",
    say: "Two more computers, the same way. A laptop, W S zero zero two, that unlocks with the T P M and a PIN; | and a desktop, W S zero zero three, with a security key. | Prepare the stick, install, add.",
    visual: term("me", [
      { cmd: "mos-fleet host prepare ws-002 --profile office --unlock tpm-pin", beat: 0, delay: 2, typed: 30, out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-002"] },
      { cmd: "mos-fleet host prepare ws-003 --profile office --unlock fido2", beat: 1, delay: 0.5, typed: 30, out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-003"] },
      { noPrompt: true, beat: 2, out: ["", "{d}# … install each one from the stick, then:{/}"] },
      { cmd: "mos-fleet host add ws-002 && mos-fleet host add ws-003 && mos-fleet push", beat: 2, delay: 1.5, typed: 34, out: ["Committed: host add ws-002", "Committed: host add ws-003", "Pushed main."] },
    ], { cwd: "~/fleet" }) },
  { id: "c5-pin", chapter: ch.c5,
    text: "For the laptop, the installer's form also asks for the disk PIN, | typed at every power-on.",
    visual: () => <Installer host="ws-002" unlock="tpm-pin" at={{ form: 0 }} /> },
  { id: "c5-three", chapter: ch.c5,
    text: "The fleet now has three computers. | `mos-fleet status` shows them all: online or not, what they run, and whether they're up to date.",
    say: "The fleet now has three computers. | mos fleet status shows them all: online or not, what they run, and whether they're up to date.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: net({ show: ["admin", "ws1"], add: [{ id: "ws2", beat: 0, delay: 0.3 }, { id: "ws3", beat: 0, delay: 1 }],
          flows: [{ from: "ws2", to: "ssh", label: "connect", beat: 0, delay: 1.2 }, { from: "ws3", to: "ssh", label: "connect", beat: 0, delay: 1.8 }] }) },
        { beat: 1, render: term("me", [{ cmd: "mos-fleet status", beat: 1, delay: 0.3, out: [
          "COMPUTER                 LAST SEEN (UTC)      PROFILE/BRANCH     RUNS       STATE",
          "ws-001           {g}online{/}  2026-10-13 10:02:11  office/main        3f2a1c94e0 {g}up to date{/}",
          "ws-002           {g}online{/}  2026-10-13 10:02:09  office/main        3f2a1c94e0 {g}up to date{/}",
          "ws-003           {g}online{/}  2026-10-13 10:02:13  office/main        3f2a1c94e0 {g}up to date{/}"] }], { cwd: "~/fleet", fontSize: 22 }) },
      ]} />
    ) },

  // ------------------------------------------------------ 6 every day
  { id: "c6-title", chapter: ch.c6, text: "Chapter six. Every day: every change is a commit.",
    visual: title(6, "Every day", "every change is a commit") },
  { id: "c6-software", chapter: ch.c6,
    text: "Everything that changes a computer is a change in the fleet repository. | To give every office computer a new program, add it to the profile.",
    visual: then("me", "~/fleet", "jed profiles/office.nix", 1,
      () => <Jed file="office.nix" mode="nix" dir="~/fleet/profiles/" lines={OFFICE} insert={{ at: 7, text: "    gimp" }} typeFrom={0.15} typeTo={0.4} keys={[{ keys: "Ctrl+X Ctrl+S", at: 0.6 }]} />) },
  { id: "c6-flow", chapter: ch.c6,
    text: "Commit, and push. | The server builds the office computers' new systems. | Each connected computer hears of it at once, | fetches what changed, and switches to it. | And `git log` shows who changed what, and when.",
    say: "Commit, and push. | The server builds the office computers' new systems. | Each connected computer hears of it at once, | fetches what changed, and switches to it. | And git log shows who changed what, and when.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "git commit -am \"office: gimp\" && mos-fleet push", beat: 0, delay: 0.3, typed: 30, out: ["[main 8e2b6a0] office: gimp", ...PUSHED] }], { cwd: "~/fleet" }) },
        { beat: 1, render: net({ show: ALL, flows: [
          { from: "admin", to: "ssh", label: "push", beat: 1, dur: 1.6 }, { from: "ssh", to: "git", label: "push", beat: 1, delay: 1.6, dur: 1 },
          { from: "git", to: "build", label: "build", beat: 1, delay: 2.6, dur: 1.4 },
          { from: "ssh", to: "ws1", label: "new!", beat: 2 }, { from: "ssh", to: "ws2", label: "new!", beat: 2, delay: 0.3 }, { from: "ssh", to: "ws3", label: "new!", beat: 2, delay: 0.6 },
          { from: "build", to: "ws1", label: "gimp", beat: 3, dur: 2.4 }, { from: "build", to: "ws2", label: "gimp", beat: 3, delay: 0.4, dur: 2.4 }, { from: "build", to: "ws3", label: "gimp", beat: 3, delay: 0.8, dur: 2.4 },
        ], hi: [{ id: "build", beat: 1, delay: 2.6 }],
          tags: [{ id: "ws1", text: "updated ✓", beat: 3, delay: 2.4 }, { id: "ws2", text: "updated ✓", beat: 3, delay: 2.8 }, { id: "ws3", text: "updated ✓", beat: 3, delay: 3.2 }] }) },
        { beat: 4, render: term("me", [{ cmd: "git log --oneline -3", beat: 4, delay: 0.3, out: ["{a}8e2b6a0{/} office: gimp  {d}(Mario Rossi, 2 minutes ago){/}", "{a}c0f9d41{/} host add ws-003  {d}(Mario Rossi, 1 hour ago){/}", "{a}4c1d2e7{/} host add ws-002  {d}(Mario Rossi, 1 hour ago){/}"] }], { cwd: "~/fleet" }) },
      ]} />
    ) },
  { id: "c6-scope", chapter: ch.c6,
    text: "Which file you change decides who gets the change: | `common.nix` for every computer, | a profile's file for its computers, | and a computer's own folder for just that one.",
    say: "Which file you change decides who gets the change: | common dot nix for every computer, | a profile's file for its computers, | and a computer's own folder for just that one.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "{a}~/fleet{/}, the fleet repository", size: 38, beat: 0 },
      { t: "box", x: 80, y: 110, w: 760, h: 150, title: "common.nix", body: "every computer", beat: 1, mono: true, color: C.green },
      { t: "box", x: 80, y: 300, w: 760, h: 150, title: "profiles/office.nix", body: "the office computers", beat: 2, mono: true },
      { t: "box", x: 80, y: 490, w: 760, h: 150, title: "hosts/ws-002/local.nix", body: "only ws-002", beat: 3, mono: true, color: C.blue },
      ...(["ws-001", "ws-002", "ws-003"]).flatMap((n, i): El[] => [
        { t: "box", x: 1250 + i * 210, y: 330, w: 190, h: 100, title: n, beat: 1, size: 24, color: C.blue },
        { t: "arrow", from: [845, 185], to: [1340 + i * 210, 325], beat: 1, delay: 0.4 + i * 0.15, color: C.green },
        { t: "arrow", from: [845, 375], to: [1245 + i * 210, 380], beat: 2, delay: 0.4 + i * 0.15, color: C.amber },
      ]),
      { t: "arrow", from: [845, 565], to: [1550, 435], beat: 3, delay: 0.4, color: C.blue },
    ]) },
  { id: "c6-people", chapter: ch.c6,
    text: "People's passwords. Set Laura's: the hash is made on your computer, and only the hash goes to the server. | Within seconds, every computer where Laura may log in has it. | And Laura changes her own, on any of them, with `mos-passwd`. She types her current password first: the server checks it, so no computer can change anyone's password at will.",
    say: "People's passwords. Set Laura's: the hash is made on your computer, and only the hash goes to the server. | Within seconds, every computer where Laura may log in has it. | And Laura changes her own, on any of them, with mos passwd. She types her current password first: the server checks it, so no computer can change anyone's password at will.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "mos-fleet password set lbianchi", beat: 0, delay: 1, out: ["New password for lbianchi: ••••••••••", "Again: ••••••••••", "lbianchi's password is set: computers get it within seconds (those online)."] }], { cwd: "~/fleet" }) },
        { beat: 1, render: net({ show: ALL, flows: [
          { from: "secrets", to: "ws1", label: "hash", beat: 1, delay: 0.3, color: C.sand }, { from: "secrets", to: "ws2", label: "hash", beat: 1, delay: 0.6, color: C.sand }, { from: "secrets", to: "ws3", label: "hash", beat: 1, delay: 0.9, color: C.sand },
        ], hi: [{ id: "secrets", beat: 1 }] }) },
        { beat: 2, render: term("ws2", [{ cmd: "mos-passwd", beat: 2, delay: 2, out: ["Current password: ••••••••••", "New password: ••••••••••••", "New password again: ••••••••••••", "Password changed, on every computer of the organization."] }]) },
      ]} />
    ) },
  { id: "c6-ops", chapter: ch.c6,
    text: "From your computer, you reach every computer through the server. A command on a computer, as root: it runs at once where the computer is online. | Its logs, as it sent them. | Or a shell on it: SSH runs end to end, with your own key, through the server.",
    say: "From your computer, you reach every computer through the server. A command on a computer, as root: it runs at once where the computer is online. | Its logs, as it sent them. | Or a shell on it: S S H runs end to end, with your own key, through the server.",
    visual: term("me", [
      { cmd: "mos-fleet run --host ws-002 -- df -h /", beat: 0, delay: 3.5, out: ["== ws-002: exit 0  (job 12)", "Filesystem               Size  Used Avail Use% Mounted on", "/dev/mapper/cryptroot    468G   61G  384G  14% /"] },
      { cmd: "mos-fleet logs ws-002 --since 2h", beat: 1, delay: 0.3, out: ["2026-10-13 09:58:02 NetworkManager[4]: <warn> wlan0: link timed out", "2026-10-13 10:01:40 mos-fleet-agent[6]: switch done: exit 0"] },
      { cmd: "mos-fleet shell ws-002", beat: 2, delay: 0.3, out: ["mrossi@ws-002:~$ hostname", "ws-002"] },
    ], { cwd: "~/fleet", fontSize: 23 }) },
  { id: "c6-upgrade", chapter: ch.c6,
    text: "A new MeccanicOS for everyone is one command. | But you can try it on a few computers first: put them on the testing branch, then upgrade with `--testing`. | When they're fine, upgrade everyone.",
    say: "A new MeccanicOS for everyone is one command. | But you can try it on a few computers first: put them on the testing branch, then upgrade with dash dash testing. | When they're fine, upgrade everyone.",
    visual: term("me", [
      { cmd: "mos-fleet host set ws-003 --branch testing --push", beat: 1, delay: 0.5, typed: 30, out: ["Committed: host set ws-003", "Pushed main."] },
      { cmd: "mos-fleet upgrade --testing", beat: 1, delay: 4, out: ["Nix: ok (3 computers evaluate).", "Pushed testing."] },
      { cmd: "mos-fleet upgrade", beat: 2, delay: 0.5, out: ["Nix: ok (3 computers evaluate).", "Pushed main.", "Every computer takes it within minutes (a new kernel: at the next restart)."] },
    ], { cwd: "~/fleet" }) },
  { id: "c6-upgrade-net", chapter: ch.c6,
    text: "The server fetches the new MeccanicOS, and builds the testing computer from its branch. | It takes it first. | Then everyone else. A new kernel takes effect at the next restart.",
    visual: net({ show: ["admin", "ws1", "ws2", "ws3", "net"], flows: [
      { from: "net", to: "build", label: "MeccanicOS", beat: 0, delay: 0.3, dur: 2.6 },
      { from: "build", to: "ws3", label: "new", beat: 1, delay: 0.2, dur: 2.4, color: C.sand },
      { from: "build", to: "ws1", label: "new", beat: 2, dur: 2.4 }, { from: "build", to: "ws2", label: "new", beat: 2, delay: 0.4, dur: 2.4 },
    ], tags: [{ id: "ws3", text: "testing ✓", beat: 1, delay: 2.6, color: C.sand }, { id: "ws1", text: "updated ✓", beat: 2, delay: 2.4 }, { id: "ws2", text: "updated ✓", beat: 2, delay: 2.8 }] }) },
  { id: "c6-retire", chapter: ch.c6,
    text: "A computer leaves the company: retire it. The server ends its connection, and its key no longer opens anything. Its recovery key stays on the server.",
    visual: term("me", [
      { cmd: "mos-fleet host retire ws-003 --push", beat: 0, delay: 1.5, out: ["Its recovery key stays on the server (mos-fleet recover still works).", "Committed: host retire ws-003", "Pushed main."] },
    ], { cwd: "~/fleet" }) },

  // ------------------------------------------- 7 when something goes wrong
  { id: "c7-title", chapter: ch.c7, text: "Chapter seven. When something goes wrong.",
    visual: title(7, "When something goes wrong", "the spare key, and the undo button") },
  { id: "c7-recover", chapter: ch.c7,
    text: "A computer won't unlock: a Tang desktop away from the office, a broken TPM, a lost security key. | On your computer, `mos-fleet recover` prints its recovery key, decrypted with your admin key. | Type it at the disk prompt, and the disk opens.",
    say: "A computer won't unlock: a Tang desktop away from the office, a broken T P M, a lost security key. | On your computer, mos fleet recover prints its recovery key, decrypted with your admin key. | Type it at the disk prompt, and the disk opens.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: vaults([{ method: "tang", x: 660, y: 200, beat: 0, delay: 1, fail: true, title: "ws-001", note: "away from the office" }]) },
        { beat: 1, render: term("me", [{ cmd: "mos-fleet recover ws-001", beat: 1, delay: 0.3, out: ["Recovery key for ws-001 (host key SHA256:Qm4x…7Ka0):", "", `    {a}${RECOVERY}{/}`, "", "Type it when the computer asks for the disk password at power-on."] }], { cwd: "~/fleet" }) },
        { beat: 2, render: vaults([{ method: "recovery", x: 660, y: 200, beat: 2, delay: 0.8, title: "ws-001", note: "the recovery key, typed" }]) },
      ]} />
    ) },
  { id: "c7-config", chapter: ch.c7,
    text: "A computer doesn't update. `mos-fleet status` says its build failed: it keeps running its previous system. | `builds --log` says why.",
    say: "A computer doesn't update. mos fleet status says its build failed: it keeps running its previous system. | builds dash dash log says why.",
    visual: term("me", [
      { cmd: "mos-fleet status ws-002", beat: 0, delay: 1, out: ["ws-002           {g}online{/}  2026-10-13 11:20:31  office/main        8e2b6a0c11 {r}build failed (runs the previous one){/}"] },
      { cmd: "mos-fleet builds ws-002 --log", beat: 1, delay: 0.3, out: ["2026-10-13 11:20:05  ws-002           main       9d1e0c2a51  {r}FAILED{/}", "    error: undefined variable 'gimpp'", "           at hosts/ws-002/local.nix:4:5"] },
    ], { cwd: "~/fleet", fontSize: 22 }) },
  { id: "c7-revert", chapter: ch.c7,
    text: "A bad commit is undone with git revert, and a push. | And a computer that doesn't start after an update: pick the previous entry in its boot menu.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "git revert 9d1e0c2 && mos-fleet push", beat: 0, delay: 0.4, typed: 26, out: ["[main 1a7f3b5] Revert \"ws-002: gimpp\"", ...PUSHED] }], { cwd: "~/fleet" }) },
        { beat: 1, render: board([
          { t: "box", x: 460, y: 60, w: 1000, h: 640, title: "boot menu", top: true, align: "left", color: C.amber, mono: true, size: 30,
            body: ["", "  MeccanicOS 26.05 (generation 42)", "{a}> MeccanicOS 26.05 (generation 41){/}", "  MeccanicOS 26.05 (generation 40)", "", "{d}  the previous one: as it was before{/}"], beat: 1 },
        ]) },
      ]} />
    ) },
  { id: "c7-lockout", chapter: ch.c7,
    text: "You can't reach the server: a lost SSH key, a mistake in your own person file. | At the server's console, let a key in for a day, | then fix the repository, and push.",
    say: "You can't reach the server: a lost S S H key, a mistake in your own person file. | At the server's console, let a key in for a day, | then fix the repository, and push.",
    visual: term("hq", [
      { cmd: "mos-fleet server admin-key /run/usb-vault/data/id_ed25519.pub", beat: 1, delay: 0.5, typed: 30, out: ["   admin key SHA256:t0Yx…mR2e: valid for 24 hours, for the repository's first push (or a fix)"] },
    ]) },

  // ---------------------------------------------------- 8 backups, safety
  { id: "c8-title", chapter: ch.c8, text: "Chapter eight. Backups, and what keeps the fleet safe.",
    visual: title(8, "Backups, and safety", "what you can't afford to lose") },
  { id: "c8-backup", chapter: ch.c8,
    text: "One command copies everything the server holds: the repository, both databases, Tang's keys, and the server's own keys. | Keep it offline, encrypted: it holds password hashes. | And each admin's key, on paper too: it's the only way to read the recovery keys.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("hq", [{ cmd: "mos-fleet server backup /run/usb-vault/data/fleet-backup", beat: 0, delay: 1, typed: 30, out: ["Backed up to /run/usb-vault/data/fleet-backup: keep it offline. It holds password hashes and the server's keys."] }]) },
        { beat: 1, render: board([
          { t: "box", x: 80, y: 20, w: 860, h: 150, title: "fleet.bundle", body: "the repository (every admin has a copy too)", beat: 1, mono: true, size: 32 },
          { t: "box", x: 980, y: 20, w: 860, h: 150, title: "state.db · secrets.db", body: "reports, logs; password hashes, recovery keys", beat: 1, delay: 0.8, mono: true, size: 32, color: C.green },
          { t: "box", x: 80, y: 220, w: 860, h: 150, title: "tang/", body: "{r}lost: Tang computers never unlock by themselves{/}", beat: 1, delay: 1.6, mono: true, size: 32, color: C.red },
          { t: "box", x: 980, y: 220, w: 860, h: 150, title: "ssh-host-keys/", body: "the key every computer trusts", beat: 1, delay: 2.4, mono: true, size: 32, color: C.tealHi },
          { t: "box", x: 80, y: 420, w: 1760, h: 170, title: "~/.config/mos-fleet/admin.key, and the paper copy", body: "{r}each admin's: the only way to read recovery keys{/}", beat: 2, mono: true, size: 36, color: C.red },
        ]) },
      ]} />
    ) },
  { id: "c8-safe", chapter: ch.c8,
    text: "What keeps it safe. Every key may do one thing: an admin's key pushes the repository and runs the commands; | a computer's key opens its own session, and fetches only its own system; | a one-time key introduces one computer, once. | Every other key gets nothing: no shell, no forwarding. | And every push, job and password change is in `mos-fleet audit`.",
    say: "What keeps it safe. Every key may do one thing: an admin's key pushes the repository and runs the commands; | a computer's key opens its own session, and fetches only its own system; | a one-time key introduces one computer, once. | Every other key gets nothing: no shell, no forwarding. | And every push, job and password change is in mos fleet audit.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "One account, {a}one job per key{/}", size: 44, beat: 0 },
      { t: "box", x: 80, y: 110, w: 860, h: 150, title: "an admin's key", body: "push the repository; every command", beat: 0, delay: 1.5, size: 30, color: C.amber },
      { t: "box", x: 980, y: 110, w: 860, h: 150, title: "a computer's key", body: "its own session, its own system", beat: 1, size: 30, color: C.blue },
      { t: "box", x: 80, y: 300, w: 860, h: 150, title: "a one-time key", body: "one computer, once, within a week", beat: 2, size: 30, color: C.sand },
      { t: "box", x: 980, y: 300, w: 860, h: 150, title: "any other key", body: "{r}nothing{/}: no shell, no forwarding", beat: 3, size: 30, color: C.red },
      { t: "box", x: 80, y: 500, w: 1760, h: 150, title: "mos-fleet audit", body: "every push, job, password change, recovery key read", beat: 4, size: 30, color: C.green, mono: true },
    ]) },

  // ---------------------------------------------------------------- end
  { id: "end-sheet", chapter: ch.end,
    text: "That's the whole job, on one sheet. Everything is in the admin guide, in the MeccanicOS repository. | And remember: fleets are experimental. Start with spare machines.",
    visual: () => <Sheet /> },
];

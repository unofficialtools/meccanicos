// The whole video: one entry per scene, in order, in four parts: what it is
// (one slide), what it does (animations, plain words), the commands to set
// it up (slides to read, not read aloud), and the advanced features.
//   text    narration and captions. "|" splits it into segments: each one is
//           spoken after a short pause, and is the beat things start on.
//           `code` in backticks: monospace in the captions.
//   say     how the voice reads it, when that differs (same "|" segments)
//   visual  what is on screen (steps and elements start on `beat: k`)
//   tail    frames held after the narration (time to read a slide)
// A scene lasts as long as its narration (src/durations.json, `npm run voice`).
import React from "react";
import { Board, El } from "./components/Board";
import { Cover } from "./components/Cover";
import { Net, NetProps } from "./components/Net";
import { Recipe, Row } from "./components/Recipe";
import { Screens } from "./components/Screens";
import { Vault } from "./components/Vault";
import { C } from "./theme";

export type Scene = { id: string; chapter: string; text: string; say?: string; visual: () => React.ReactNode; tail?: number };

const board = (els: El[]) => () => <Board els={els} />;
const net = (p: NetProps) => () => <Net {...p} />;
const recipe = (title: string, rows: Row[], footer?: string) => () => <Recipe title={title} rows={rows} footer={footer} />;
const vaults = (vs: React.ComponentProps<typeof Vault>[]) => () => <>{vs.map((v, i) => <Vault key={i} {...v} />)}</>;
const GRID: [number, number][] = [[110, 10], [1010, 10], [110, 400], [1010, 400]];

const ALL = ["admin", "ws1", "ws2", "ws3"] as NetProps["show"];
const WSS = ["ws1", "ws2", "ws3"] as const;
const READ = 4 * 30; // a slide of commands stays this long after the voice

const ch = {
  start: "",
  what: "1 · What it is",
  how: "2 · What it does",
  setup: "3 · Setting it up",
  more: "4 · Advanced features",
};

// A list on a slide: one point per line.
const points = (xs: string[]) => xs.map((x) => (x ? `• ${x}` : ""));

export const scenes: Scene[] = [
  // ---------------------------------------------------------------- start
  { id: "start", chapter: ch.start,
    text: "MeccanicOS: a free and open source Linux distribution, based on NixOS. | How to manage your organization's computer fleet.",
    tail: 30,
    visual: () => <Cover tagline="Free and open source Linux distribution, based on NixOS" title="How to manage your organization's computer fleet" /> },

  // ------------------------------------------------------- 1 what it is
  { id: "what", chapter: ch.what,
    text: "MeccanicOS Fleets lets you manage all your company's computers, users and groups from one git repository. Every computer, person and group, and their software, is described there: change it, and the computers follow. | It's for schools, offices and businesses, looked after by one person or a small team. | Upgrades are atomic: all or nothing, so a failed upgrade leaves a computer as it was. Every computer is built from the same pinned recipe, so it's reproducible. And most updates need no reboot. | Security comes built in: every disk is encrypted, and every change is recorded.",
    say: "MeccanicOS Fleets lets you manage all your company's computers, users and groups from one git repository. Every computer, person and group, and their software, is described there: change it, and the computers follow. | It's for schools, offices and businesses, looked after by one person or a small team. | Upgrades are atomic: all or nothing, so a failed upgrade leaves a computer as it was. Every computer is built from the same pinned recipe, so it's reproducible. And most updates need no reboot. | Security comes built in: every disk is encrypted, and every change is recorded.",
    tail: 4 * 30,
    visual: board([
      { t: "text", x: 80, y: 0, w: 1760, text: "{a}MeccanicOS Fleets{/}: manage all your company computers, users, and groups from {a}one git repo{/}", size: 40, beat: 0 },
      { t: "box", x: 80, y: 90, w: 1760, h: 80, body: "every computer, person and group, and their software, described there: {a}change it, and the computers follow{/}", size: 40, color: C.amber, beat: 0, delay: 4 },
      { t: "box", x: 80, y: 190, w: 560, h: 500, title: "what it's for", top: true, align: "left", beat: 0, delay: 1, size: 36,
        body: points(["keep consistent system environments", "users and groups in one list: anyone can use any desk", "{a}most updates without a reboot{/} (a new kernel: at the next restart)", "once installed, no visits to each desk"]) },
      { t: "box", x: 680, y: 190, w: 560, h: 500, title: "who it's for", top: true, align: "left", beat: 1, size: 36, color: C.blue,
        body: points(["schools, offices, labs, businesses", "one person or a small team looks after the computers", "they can type a few commands"]) },
      { t: "box", x: 1280, y: 190, w: 560, h: 500, title: "reliable, and secure", top: true, align: "left", beat: 2, size: 33, color: C.green,
        body: points(["{g}atomic upgrades{/}: all or nothing, never half done", "{g}a failed upgrade{/} leaves the computer as it was", "{g}reproducible environments{/}: one pinned recipe", "{g}security built in{/}: every disk encrypted", "office computers unlock only in the office", "every change recorded: who, what, when"]) },
    ]) },

  // ----------------------------------------------------- 2 what it does
  { id: "how-map", chapter: ch.how,
    text: "Here's how it works. One server, in the office, holds everything: | the plan for every computer, a logbook of what they report, and a safe for passwords and spare keys. | You, the admin, work from your own computer. | Every other computer keeps a line open to the server: laptops too, from anywhere the server can be reached.",
    visual: net({ add: [{ id: "hq", beat: 0, delay: 2 }, { id: "admin", beat: 2 }, ...WSS.map((id, i) => ({ id, beat: 3, delay: 0.5 + i * 0.5 }))],
      hi: [{ id: "git", beat: 1, for: 3 }, { id: "build", beat: 1, delay: 0.8, for: 2.5 }, { id: "state", beat: 1, delay: 2, for: 3 }, { id: "secrets", beat: 1, delay: 3.8 }, { id: "admin", beat: 2, for: 3 }],
      flows: WSS.map((from, i) => ({ from, to: "ssh" as const, label: "connect", beat: 3, delay: 2 + i * 0.5 })),
      tags: WSS.map((id, i) => ({ id, text: "connected", beat: 3, delay: 4 + i * 0.5, color: C.tealHi })) }) },
  { id: "how-change", chapter: ch.how,
    text: "To change something, you edit the plan once, on your own computer, and send it. | The server prepares each computer's new system. | Every connected computer picks it up within minutes, and switches to it. | And the plan keeps its history: who changed what, and when.",
    visual: net({ show: ALL, flows: [
      { from: "admin", to: "ssh", label: "a change", beat: 0, delay: 2.5, dur: 2 }, { from: "ssh", to: "git", label: "the plan", beat: 0, delay: 4.5, dur: 1.2, color: C.green },
      { from: "git", to: "build", label: "build", beat: 1, dur: 1.6 },
      ...WSS.map((to, i) => ({ from: "build" as const, to, label: "new system", beat: 2, delay: i * 0.4, dur: 2.6 })),
    ], hi: [{ id: "git", beat: 0, delay: 4.5, for: 3 }, { id: "build", beat: 1, for: 4 }, { id: "git", beat: 3 }],
      tags: [...WSS.map((id, i) => ({ id, text: "updated ✓", beat: 2, delay: 2.6 + i * 0.4 })), { id: "admin", text: "who, what, when", beat: 3, color: C.sand }] }) },
  { id: "how-people", chapter: ch.how,
    text: "People are in the plan too: one list, for every computer. | Set someone's password once, and within seconds it works on every computer they may use that is online. | And they can change it themselves, from any of them.",
    visual: net({ show: ALL, flows: [
      ...WSS.map((to, i) => ({ from: "secrets" as const, to, label: "password", beat: 1, delay: 0.5 + i * 0.3, color: C.sand })),
      { from: "ws2", to: "secrets", label: "a new one", beat: 2, delay: 0.5, color: C.blue },
      { from: "secrets", to: "ws1", label: "password", beat: 2, delay: 3, color: C.sand }, { from: "secrets", to: "ws3", label: "password", beat: 2, delay: 3.3, color: C.sand },
    ], hi: [{ id: "secrets", beat: 1 }], tags: [{ id: "ws2", text: "Laura", beat: 0, delay: 1, color: C.blue }] }) },
  { id: "how-new", chapter: ch.how,
    text: "A new computer starts from a USB stick you've prepared. It installs itself, with the organization's settings. | Then it introduces itself to the server, and waits. | You check it's the right one and approve it, and it gets its system. Its people can log in.",
    visual: net({ show: ["admin"], add: [{ id: "ws1", beat: 0, delay: 1 }], flows: [
      { from: "ws1", to: "ssh", label: "hello", beat: 1, delay: 0.3, dur: 2.4 },
      { from: "admin", to: "ssh", label: "approved", beat: 2, delay: 1, dur: 2 }, { from: "build", to: "ws1", label: "system", beat: 2, delay: 3.2, dur: 2.6 },
    ], tags: [{ id: "ws1", text: "installing…", beat: 0, delay: 1.5, for: 6, color: C.dim }, { id: "ws1", text: "waiting for you", beat: 1, delay: 2.7, for: 6, color: C.sand },
      { id: "ws1", text: "ready ✓", beat: 2, delay: 5.8 }], hi: [{ id: "admin", beat: 2, for: 3 }] }) },
  { id: "how-disks", chapter: ch.how,
    text: "Every disk is encrypted: without its key, it's just noise, even in a thief's hands. | An office desktop unlocks by itself, but only in the office. | Carried away, it stays locked. | A laptop asks for a PIN, | and if all else fails, an admin has a spare key, kept safe on the server.",
    say: "Every disk is encrypted: without its key, it's just noise, even in a thief's hands. | An office desktop unlocks by itself, but only in the office. | Carried away, it stays locked. | A laptop asks for a pin, | and if all else fails, an admin has a spare key, kept safe on the server.",
    visual: vaults([
      { method: "tang", x: GRID[0][0], y: GRID[0][1], beat: 1, delay: 1, title: "in the office", note: "unlocks by itself" },
      { method: "tang", x: GRID[1][0], y: GRID[1][1], beat: 2, delay: 1, fail: true, title: "anywhere else", note: "away from the office" },
      { method: "tpm-pin", x: GRID[2][0], y: GRID[2][1], beat: 3, delay: 0.5, title: "a laptop" },
      { method: "recovery", x: GRID[3][0], y: GRID[3][1], beat: 4, delay: 1.5, title: "last resort" },
    ]) },
  { id: "how-undo", chapter: ch.how,
    text: "And mistakes are easy to undo. An update is all or nothing: if it fails, the computer keeps the version it had. | A bad change is easy to take back, and every computer's start-up menu keeps the previous versions.",
    visual: board([
      { t: "box", x: 80, y: 60, w: 760, h: 300, title: "an update fails", body: ["nothing is half done:", "the computer keeps", "the version it had"], beat: 0, delay: 2, color: C.green, size: 34 },
      { t: "box", x: 80, y: 410, w: 760, h: 300, title: "a bad change", body: ["easy to take back;", "every computer follows"], beat: 1, color: C.amber, size: 34 },
      { t: "box", x: 960, y: 60, w: 880, h: 650, title: "start-up menu", top: true, align: "left", color: C.amber, mono: true, size: 30, beat: 1, delay: 3,
        body: ["", "  MeccanicOS (version 42)", "{a}> MeccanicOS (version 41){/}", "  MeccanicOS (version 40)", "", "{d}  the previous one: as it was{/}"] },
    ]) },

  // ---------------------------------------------------- 3 setting it up
  { id: "setup-server", chapter: ch.setup,
    text: "Now the commands. Setting up the server takes these few, run once, in this order. The notes on the right say what each one does. | The admin guide has every detail and option.",
    tail: READ,
    visual: recipe("Once: {a}the server{/}", [
      { where: "server", step: "Install MeccanicOS from the stick, as usual; name it hq", note: "write its disk password down, and keep it in a safe" },
      { where: "you", cmd: ["usb-vault stick", "cp ~/.ssh/id_ed25519.pub /run/usb-vault/data/"], note: "carry your key (how the server knows you) on the stick" },
      { where: "server", cmd: ["mos-fleet server init --lan 10.0.0.0/24 \\", "    --admin-key /run/usb-vault/data/id_ed25519.pub"], note: "makes it the fleet's server; {a}--lan{/}: the office network. {a}Note the fingerprint{/} it prints" },
      { where: "server", cmd: "mos-fleet server status", note: "every line should say {g}ok{/}" },
      { where: "you", cmd: ["mos-fleet init --server hq.corp.example.com --fingerprint SHA256:VJ6P… \\", "    --organization \"Example Corp\" --admin mrossi --full-name \"Mario Rossi\""], note: "creates the plan (the folder ~/fleet) and your admin key: {r}print it, keep it safe{/}" },
      { where: "you", cmd: ["mos-fleet profile add office", "jed profiles/office.nix"], note: "a kind of computer: list its software in its file" },
      { where: "you", cmd: ["mos-fleet person add lbianchi \"Laura Bianchi\" --group office", "mos-fleet password set lbianchi"], note: "add people, and set their passwords" },
      { where: "you", cmd: "mos-fleet validate && mos-fleet push", note: "check everything, then send it to the server" },
    ]) },
  { id: "setup-host", chapter: ch.setup,
    text: "Then, for each new computer: prepare the stick, install, approve. | The one real choice is how its disk unlocks: by itself in the office, with a PIN, or with a security key.",
    say: "Then, for each new computer: prepare the stick, install, approve. | The one real choice is how its disk unlocks: by itself in the office, with a pin, or with a security key.",
    tail: READ,
    visual: recipe("For each {a}new computer{/}", [
      { where: "new", cmd: "lsblk -d -o NAME,SIZE,MODEL,SERIAL", note: "optional, started from the stick: the disk's serial number, so no other disk is erased" },
      { where: "you", cmd: "mos-fleet host prepare ws-001 --profile office --unlock tang", note: "its settings, on the stick. {a}--unlock{/}: tang (office), tpm-pin (laptop), fido2 (security key); {a}--disk-serial{/}" },
      { where: "new", step: "Plug in a network cable, start from the stick: Install › organization install › YES", note: "at the end it shows its {a}fingerprint{/}: note it" },
      { where: "you", cmd: ["mos-fleet host pending", "mos-fleet host add ws-001"], note: "compare the fingerprint with the one on its screen, then answer y" },
      { where: "you", cmd: "mos-fleet push", note: "it gets its system: its people can log in" },
      { where: "you", cmd: "mos-fleet status", note: "every computer: online? up to date?" },
    ]) },
  { id: "setup-daily", chapter: ch.setup,
    text: "And every day: change a file in the plan, commit, and push. That's how every change reaches the computers.",
    tail: READ,
    visual: recipe("Every day", [
      { where: "you", cmd: "jed profiles/office.nix", note: "change the plan: here, the office computers' software. {a}common.nix{/}: all of them; {a}hosts/ws-001/{/}: one" },
      { where: "you", cmd: "git commit -am \"office: gimp\" && mos-fleet push", note: "every computer concerned updates within minutes" },
      { where: "you", cmd: "mos-fleet password set lbianchi", note: "someone's new password, everywhere" },
      { where: "any", cmd: "mos-passwd", note: "anyone changes their own password, on any computer" },
      { where: "you", cmd: "mos-fleet upgrade", note: "a new MeccanicOS for every computer (a new kernel: at the next restart)" },
      { where: "you", cmd: "mos-fleet host retire ws-003 --push", note: "a computer leaves the organization" },
    ], "Every command commits to ~/fleet; nothing reaches the server until you push.") },
  { id: "setup-tui", chapter: ch.setup,
    text: "Prefer menus? Type `mos-fleet` alone, for the same work on one full screen. Every computer, at a glance. | Open one, to see its logs, run a command on it, or restart it. | A new computer waiting for you: compare its fingerprint, and add it. | People, with their groups and passwords. | And your changes, collected, then committed and sent together.",
    say: "Prefer menus? Type mos fleet alone, for the same work on one full screen. Every computer, at a glance. | Open one, to see its logs, run a command on it, or restart it. | A new computer waiting for you: compare its fingerprint, and add it. | People, with their groups and passwords. | And your changes, collected, then committed and sent together.",
    tail: 3 * 30,
    visual: () => <Screens shots={[
      { src: "computers.png", title: "Computers", note: "online or not, up to date or not; {r}red{/}: an update that failed" },
      { src: "computer.png", title: "One computer", note: "its logs, updates and jobs; Run, Shell, Reboot, Recovery key" },
      { src: "waiting.png", title: "Waiting", note: "a new computer: compare the fingerprint, then {a}Same: add it{/}" },
      { src: "people.png", title: "People", note: "groups, where they may log in; Add, Password, Disable" },
      { src: "changes.png", title: "Changes", note: "what isn't on the server yet, and what it changes where; Commit, then Push" },
    ]} /> },

  // ----------------------------------------------- 4 advanced features
  { id: "more", chapter: ch.more,
    text: "Finally, for experienced admins, there's more. | Staged rollouts, remote commands, disk recovery, an audit log, backups, and a tight access model. | Each one is in the admin guide, in the MeccanicOS repository.",
    tail: 8 * 30,
    visual: board([
      { t: "text", x: 80, y: 0, text: "{a}Advanced{/}: in the admin guide", size: 40, beat: 0 },
      ...([
        ["staged rollouts", "host set --branch testing · upgrade --testing", C.amber],
        ["remote operations", "run --host H -- CMD · logs · shell (SSH end to end, via ProxyJump)", C.amber],
        ["disk encryption", "LUKS2 · Clevis/Tang + TPM2 · TPM2 + PIN · FIDO2 · age-encrypted recovery keys: recover", C.sand],
        ["troubleshooting", "builds --log · git revert · NixOS generations · server admin-key at the console", C.sand],
        ["access model", "one SSH account, forced commands: one job per key · one-time enrolment keys · pre-receive checks, no force push", C.tealHi],
        ["audit and backup", "audit · server backup: git bundle, SQLite, Tang and host keys · admin key on paper", C.tealHi],
        ["configuration", "common.nix · profiles/*.nix · hosts/NAME/local.nix · groups.toml · people/*.toml", C.green],
        ["reproducible", "pinned flake · every system built on the server with Nix · validate · diff", C.green],
      ] as [string, string, string][]).map(([title, body, color], i): El => ({
        t: "box", x: i % 2 ? 980 : 80, y: 80 + Math.floor(i / 2) * 170, w: 860, h: 155, title, body, color, align: "left", mono: false, size: 30,
        beat: 1, delay: i * 0.6,
      })),
    ]) },
];

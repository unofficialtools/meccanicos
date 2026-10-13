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
  ws2: { who: "mrossi@ws-002", on: { name: "ws-002", role: "a computer of the fleet", color: C.blue } },
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

const DOMAIN = "corp.example.com";
const ALL = ["admin", "ws1", "ws2", "ws3"] as NetProps["show"];
const OFFICE = ["{d}# Profile office: the computers whose fleet.toml says profile = \"office\".{/}", "{d}# Who may log in: the Kanidm group office, and fleet-admins.{/}", "{ pkgs, ... }:", "{", "  environment.systemPackages = with pkgs; [", "    libreoffice", "    thunderbird", "  ];", "}"];
const RECOVERY = "bkrhcveg-tnjdlfiu-ghvcrkeb-lnjtuhdf-vbkcrthg-ijfnedvl-cuhkgbrt-dnvlfjie";

const ch = {
  intro: "Welcome",
  c1: "1 · The big picture",
  c2: "2 · Before you start",
  c3: "3 · The server",
  c4: "4 · Your computer",
  c5: "5 · Adding computers",
  c6: "6 · Every day",
  c7: "7 · When something goes wrong",
  c8: "8 · Backups",
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

  // ---------------------------------------------------- 1 the big picture
  { id: "c1-title", chapter: ch.c1, text: "Chapter one. The big picture: one company, one domain, one server.",
    visual: title(1, "The big picture", "one company, one domain, one server") },
  { id: "c1-company", chapter: ch.c1,
    text: "Here is Example Corp. It owns a domain, `corp.example.com`, | and it has an office network. | On it, one server called hq, also running MeccanicOS, hosts everything the fleet needs.",
    say: "Here is Example Corp. It owns a domain, corp dot example dot com, | and it has an office network. | On it, one server called H Q, also running MeccanicOS, hosts everything the fleet needs.",
    visual: net({ add: [{ id: "hq", beat: 2 }], hi: [{ id: "hq", beat: 2, delay: 1, for: 3 }] }) },
  { id: "c1-services", chapter: ch.c1,
    text: "Kanidm keeps the people: accounts, groups, passwords and passkeys, and who may log in where. | Forgejo hosts the fleet repository: a git repository with a folder for each computer. Changing a computer means changing a file there. | Harmonia is the cache: the server builds every computer's system, and hands it out ready-made. | Fleet is the inventory: which computers exist, their health, and their versions. | And Tang lets office desktops unlock their disks by themselves, but only on the office network. | Forgejo and Fleet share one MySQL database, and nginx serves them all over HTTPS.",
    say: "Kani D M keeps the people: accounts, groups, passwords and passkeys, and who may log in where. | Forjayo hosts the fleet repository: a git repository with a folder for each computer. Changing a computer means changing a file there. | Harmonia is the cache: the server builds every computer's system, and hands it out ready-made. | Fleet is the inventory: which computers exist, their health, and their versions. | And Tang lets office desktops unlock their disks by themselves, but only on the office network. | Forjayo and Fleet share one My S Q L database, and engine X serves them all over H T T P S.",
    visual: net({ hi: [{ id: "idm", beat: 0, for: 7 }, { id: "git", beat: 1, for: 9 }, { id: "cache", beat: 2, for: 7 }, { id: "fleet", beat: 3, for: 6 }, { id: "tang", beat: 4, for: 7 }, { id: "db", beat: 5 }] }) },
  { id: "c1-computers", chapter: ch.c1,
    text: "Your own computer, the admin's, is on the same network. | Every other computer runs MeccanicOS in managed mode. Here, three of them.",
    visual: net({ add: [{ id: "admin", beat: 0 }, { id: "ws1", beat: 1, delay: 1 }, { id: "ws2", beat: 1, delay: 1.6 }, { id: "ws3", beat: 1, delay: 2.2 }] }) },
  { id: "c1-managed", chapter: ch.c1,
    text: "A managed computer checks the fleet repository every few minutes, with a tool called comin, | and downloads its system, already built, from the cache. | People log in with their organization account; also offline, once they've logged in there before. | And every computer reports to Fleet.",
    say: "A managed computer checks the fleet repository every few minutes, with a tool called come in, | and downloads its system, already built, from the cache. | People log in with their organization account; also offline, once they've logged in there before. | And every computer reports to Fleet.",
    visual: net({ show: ALL, flows: [
      { from: "ws1", to: "git", label: "new?", beat: 0, delay: 0.5 }, { from: "ws2", to: "git", label: "new?", beat: 0, delay: 1.2 }, { from: "ws3", to: "git", label: "new?", beat: 0, delay: 1.9 },
      { from: "cache", to: "ws1", label: "system", beat: 1, dur: 2.6 }, { from: "cache", to: "ws2", label: "system", beat: 1, delay: 0.4, dur: 2.6 }, { from: "cache", to: "ws3", label: "system", beat: 1, delay: 0.8, dur: 2.6 },
      { from: "ws2", to: "idm", label: "lbianchi?", beat: 2, delay: 0.3 }, { from: "idm", to: "ws2", label: "ok", beat: 2, delay: 2.6, color: C.green },
      { from: "ws1", to: "fleet", label: "report", beat: 3, color: C.blue }, { from: "ws2", to: "fleet", label: "report", beat: 3, delay: 0.5, color: C.blue }, { from: "ws3", to: "fleet", label: "report", beat: 3, delay: 1, color: C.blue },
    ], hi: [{ id: "git", beat: 0, for: 4 }, { id: "cache", beat: 1, for: 4 }, { id: "idm", beat: 2, for: 5 }, { id: "fleet", beat: 3 }] }) },
  { id: "c1-unlock", chapter: ch.c1,
    text: "Every disk is encrypted. A desktop in the office unlocks it with its TPM chip and the Tang server; a laptop with the TPM and a PIN; or with a FIDO2 security key. | A key is never sent over the network. | And every computer has a recovery key, encrypted so that only the admins can read it, kept in the fleet repository.",
    say: "Every disk is encrypted. A desktop in the office unlocks it with its T P M chip and the Tang server; a laptop with the T P M and a PIN; or with a Fido two security key. | A key is never sent over the network. | And every computer has a recovery key, encrypted so that only the admins can read it, kept in the fleet repository.",
    visual: net({ show: ALL, tags: [{ id: "ws1", text: "TPM + Tang", beat: 0, delay: 1, color: C.tealHi }, { id: "ws2", text: "TPM + PIN", beat: 0, delay: 3.5 }, { id: "ws3", text: "security key", beat: 0, delay: 5.5, color: C.blue }],
      flows: [{ from: "ws1", to: "tang", label: "unlock?", beat: 0, delay: 1 }, { from: "tang", to: "ws1", label: "help", beat: 0, delay: 3.4, color: C.tealHi },
        { from: "ws1", to: "git", label: "recovery.age", beat: 2, delay: 1.5, color: C.sand }, { from: "ws2", to: "git", label: "recovery.age", beat: 2, delay: 2, color: C.sand }, { from: "ws3", to: "git", label: "recovery.age", beat: 2, delay: 2.5, color: C.sand }],
      hi: [{ id: "tang", beat: 0, delay: 1, for: 4 }, { id: "git", beat: 2, delay: 1.5 }] }) },
  { id: "c1-who", chapter: ch.c1,
    text: "Who may log in where is decided by groups, in Kanidm. | Fleet admins log in everywhere, with sudo. | And each profile, such as office, has a group of the same name, for its own computers.",
    say: "Who may log in where is decided by groups, in Kani D M. | Fleet admins log in everywhere, with sue doo. | And each profile, such as office, has a group of the same name, for its own computers.",
    visual: board([
      { t: "box", x: 80, y: 40, w: 560, h: 160, title: "Kanidm", body: "people and groups", beat: 0, color: C.amber },
      { t: "box", x: 760, y: 40, w: 520, h: 160, title: "fleet-admins", body: "mrossi", beat: 1, color: C.tealHi, mono: true },
      { t: "arrow", from: [1285, 120], to: [1480, 120], beat: 1, delay: 0.6, color: C.tealHi },
      { t: "box", x: 1490, y: 40, w: 360, h: 160, title: "every computer", body: "with sudo", beat: 1, delay: 0.9, color: C.tealHi },
      { t: "box", x: 760, y: 330, w: 520, h: 160, title: "office", body: "lbianchi · gverdi", beat: 2, color: C.blue, mono: true },
      { t: "arrow", from: [1285, 410], to: [1480, 410], beat: 2, delay: 0.6, color: C.blue },
      { t: "box", x: 1490, y: 330, w: 360, h: 160, title: "office computers", body: "ws-001 · ws-002 · ws-003", beat: 2, delay: 0.9, color: C.blue },
      { t: "arrow", from: [640, 120], to: [755, 120], beat: 1 },
      { t: "arrow", from: [400, 205], to: [755, 410], beat: 2 },
    ]) },

  // ------------------------------------------------- 2 before you start
  { id: "c2-title", chapter: ch.c2, text: "Chapter two. Before you start: what you need.",
    visual: title(2, "Before you start", "a server, a domain, your computer, a stick") },
  { id: "c2-needs", chapter: ch.c2,
    text: "A server: any 64-bit PC, with 8 gigabytes of memory or more, a 100 gigabyte disk, and a fixed address on the office network. | A domain the organization owns. | Your own computer, running MeccanicOS, on the same network. | And a MeccanicOS USB stick: it carries the files to new computers.",
    visual: board([
      { t: "box", x: 80, y: 30, w: 820, h: 330, title: "a server", body: ["64-bit, 8 GB+ memory, 100 GB+ disk", "a fixed address: {a}10.0.0.10{/}"], beat: 0, color: C.tealHi },
      { t: "box", x: 1010, y: 30, w: 820, h: 330, title: "a domain", body: ["{a}corp.example.com{/}", "and someone who can add names to it"], beat: 1 },
      { t: "box", x: 80, y: 410, w: 820, h: 330, title: "your computer", body: ["MeccanicOS", "on the same network"], beat: 2, color: C.amber },
      { t: "box", x: 1010, y: 410, w: 820, h: 330, title: "a MeccanicOS stick", body: ["made with mos-usb, or Ventoy", "carries the files to new computers"], beat: 3, color: C.sand },
    ]) },
  { id: "c2-dns", chapter: ch.c2,
    text: "Someone who runs the domain adds five names to it: | idm, git, cache, fleet and tang. All five point to the server's address.",
    say: "Someone who runs the domain adds five names to it: | I D M, git, cache, fleet and tang. All five point to the server's address.",
    visual: board([
      ...["idm", "git", "cache", "fleet", "tang"].flatMap((n, i): El[] => [
        { t: "box", x: 100, y: 20 + i * 145, w: 620, h: 110, title: `${n}.${DOMAIN}`, beat: 1, delay: i * 0.5, size: 30, mono: true },
        { t: "arrow", from: [725, 75 + i * 145], to: [1195, 380], beat: 1, delay: 2.8 + i * 0.15, color: C.amber },
      ]),
      { t: "box", x: 1200, y: 260, w: 600, h: 240, title: "hq", body: ["the server", "{a}10.0.0.10{/}"], beat: 0, color: C.tealHi, size: 40 },
    ]) },

  // ------------------------------------------------------- 3 the server
  { id: "c3-title", chapter: ch.c3, text: "Chapter three. The server: install it, then one command.",
    visual: title(3, "The server", "hq: install it, then one command") },
  { id: "c3-install", chapter: ch.c3,
    text: "Install MeccanicOS on the server from the stick, as usual, and name it hq. | Pick a disk password. Write it down, and keep it in a safe: the server can't unlock itself, because it's the one running Tang.",
    say: "Install MeccanicOS on the server from the stick, as usual, and name it H Q. | Pick a disk password. Write it down, and keep it in a safe: the server can't unlock itself, because it's the one running Tang.",
    visual: vaults([{ method: "password", x: 660, y: 200, beat: 1, delay: 2, title: "a password", note: "kept in the safe" }]) },
  { id: "c3-check", chapter: ch.c3,
    text: "Log in on the server, and check two things. The clock is synchronized, | and the address is the fixed one.",
    visual: term("hq", [
      { cmd: "timedatectl | grep synchronized", beat: 0, delay: 2.5, out: ["System clock synchronized: {g}yes{/}"] },
      { cmd: "ip -4 addr | grep inet", beat: 1, delay: 0.3, out: ["    inet 127.0.0.1/8 scope host lo", "    inet {a}10.0.0.10/24{/} brd 10.0.0.255 scope global enp3s0"] },
    ]) },
  { id: "c3-init", chapter: ch.c3,
    text: "Now one command turns it into the fleet's server. `--lan` is the office network: only computers there can reach Tang. | It rebuilds the system with the fleet's services. The first time, that downloads about a gigabyte. | Then it sets up each service, the certificates, and the fleet repository. | It ends with four passwords: put them in the company's password manager. If it stops with an error, fix what it says and run the same command again.",
    say: "Now one command turns it into the fleet's server. Dash dash LAN is the office network: only computers there can reach Tang. | It rebuilds the system with the fleet's services. The first time, that downloads about a gigabyte. | Then it sets up each service, the certificates, and the fleet repository. | It ends with four passwords: put them in the company's password manager. If it stops with an error, fix what it says and run the same command again.",
    visual: term("hq", [
      { cmd: `mos-fleet server init --domain ${DOMAIN} --organization "Example Corp" --lan 10.0.0.0/24`, beat: 0, delay: 0.5, typed: 30 },
      { noPrompt: true, beat: 1, out: ["{B}== 1/8 The server's settings: /etc/nixos/fleet-server.toml{/}", "   rebuilding the system (the first time takes a while)…"] },
      { noPrompt: true, beat: 2, out: ["{B}== 2/8 The organization's certificate authority{/}", "{B}== 3/8 Kanidm: its administrators, the fleet-admins group{/}", "{B}== 4/8 Forgejo: the fleet repository fleet/config{/}", "{B}== 5/8 Fleet: the administrator and the enroll secret{/}", "{B}== 6/8 Tang and the cache{/}", "{B}== 7/8 The fleet repository's first files{/}", "{B}== 8/8 The admin kit{/}"] },
      { noPrompt: true, beat: 3, out: ["Passwords (also in /var/lib/meccanicos-fleet/server-state.json):", "   Kanidm admin, idm_admin    {a}••••••••••••{/}  {a}••••••••••••{/}", "   Forgejo fleet-admin, Fleet {a}••••••••••••{/}  {a}••••••••••••{/}"] },
    ], { fontSize: 24, busy: false }) },
  { id: "c3-net", chapter: ch.c3,
    text: "On the map: the server fetched MeccanicOS's fleet services from the Internet, | and now runs every one of them.",
    visual: net({ show: ["net"], flows: [{ from: "net", to: "hq", label: "fleet services", beat: 0, delay: 0.5, dur: 3 }],
      hi: ["idm", "git", "cache", "fleet", "tang", "db"].map((id, i) => ({ id: id as "idm", beat: 1, delay: i * 0.4 })) }) },
  { id: "c3-me", chapter: ch.c3,
    text: "Make yourself a fleet admin: a person in the group fleet-admins. It prints a link: open it to set your password, or a passkey, for the web pages. | The second command sets your password for logging in to computers. | Then check the server: every line should say ok.",
    visual: term("hq", [
      { cmd: "mos-fleet person add mrossi \"Mario Rossi\" --group fleet-admins", beat: 0, delay: 0.5, typed: 26, out: ["mrossi created, in fleet-admins.", `{a}https://idm.${DOMAIN}/ui/reset?token=Xk3f-91Qa-77Tz{/}`] },
      { cmd: "mos-fleet person password mrossi", beat: 1, delay: 0.3, out: ["New password: ••••••••••", "Again: ••••••••••"] },
      { cmd: "mos-fleet server status", beat: 2, delay: 0.3, out: ["{B}== Services{/}", ...["kanidm", "forgejo", "harmonia", "fleet", "tang", "mysql", "redis", "nginx"].map((u) => `   {g}ok{/}   ${u.padEnd(28)} active`)] },
    ]) },

  // ---------------------------------------------------- 4 your computer
  { id: "c4-title", chapter: ch.c4, text: "Chapter four. Your own computer: the admin's workbench.",
    visual: title(4, "Your computer", "the admin's workbench") },
  { id: "c4-connect", chapter: ch.c4,
    text: "Everything else happens on your own computer, not the server. | First, let your SSH key log you in to the server. | Then `mos-fleet connect` copies the admin kit from the server, and clones the fleet repository into a folder called fleet, in your home.",
    say: "Everything else happens on your own computer, not the server. | First, let your S S H key log you in to the server. | Then mos fleet connect copies the admin kit from the server, and clones the fleet repository into a folder called fleet, in your home.",
    visual: term("me", [
      { cmd: "ssh-copy-id admin@hq", beat: 1, delay: 0.3, out: ["Number of key(s) added: 1"] },
      { cmd: "mos-fleet connect admin@hq", beat: 2, delay: 0.3, out: ["Fetching the admin kit from admin@hq (ssh admin@hq sudo -n mos-fleet kit)…", "   kit saved in ~/.config/mos-fleet/kit.toml", "   the fleet repository: ~/fleet  (plain git works there too)", "", "Next: mos-fleet admin-key   (your key for reading recovery keys)"] },
    ]) },
  { id: "c4-connect-net", chapter: ch.c4,
    text: "The kit holds the repository's tokens and Fleet's enroll secret: keep your computer's disk encrypted, as MeccanicOS does. | And the repository is now on your computer too. Every change starts there.",
    visual: net({ show: ["admin"], flows: [{ from: "hq", to: "admin", label: "kit", beat: 0, delay: 0.3, dur: 2.6 }, { from: "git", to: "admin", label: "~/fleet", beat: 1, delay: 0.2, dur: 2.6, color: C.green }],
      hi: [{ id: "admin", beat: 0 }, { id: "git", beat: 1, for: 3 }] }) },
  { id: "c4-adminkey", chapter: ch.c4,
    text: "Next, your admin key. Its public half goes into `admins.txt`, in the repository: every computer installed from now on encrypts its recovery key for every key in that file. | Back it up now, offline: print it, and keep the paper in the safe. Without an admin key, no recovery key can be read. Each admin does the same on their own computer.",
    say: "Next, your admin key. Its public half goes into admins dot text, in the repository: every computer installed from now on encrypts its recovery key for every key in that file. | Back it up now, offline: print it, and keep the paper in the safe. Without an admin key, no recovery key can be read. Each admin does the same on their own computer.",
    visual: term("me", [
      { cmd: "mos-fleet admin-key", beat: 0, delay: 1, out: ["Your admin key: ~/.config/mos-fleet/admin.key", "   pushed: admins.txt: mrossi", "Computers installed from now on get recovery keys you can read."] },
      { noPrompt: true, beat: 1, out: ["", "{r}BACK IT UP NOW, offline (a printed copy in the safe): without it you cannot read recovery keys.{/}"] },
    ]) },
  { id: "c4-profile", chapter: ch.c4,
    text: "Then a profile for each kind of computer; here, office. It adds a file to the repository, and a Kanidm group with the same name. | Edit the file to list the profile's software.",
    say: "Then a profile for each kind of computer; here, office. It adds a file to the repository, and a Kani D M group with the same name. | Edit the file to list the profile's software.",
    visual: then("me", "~/fleet", "jed profiles/office.nix", 1,
      () => <Jed file="office.nix" mode="nix" dir="~/fleet/profiles/" lines={OFFICE} typeFrom={0.05} typeTo={0.8} keys={[{ keys: "Ctrl+X Ctrl+S", at: 0.86 }]} />,
      [{ cmd: "mos-fleet profile add office", beat: 0, delay: 0.5, out: ["   pushed: Profile office", "Group office created.", "Edit ~/fleet/profiles/office.nix for its software."] }]) },
  { id: "c4-push", chapter: ch.c4,
    text: "Commit, and push. | Then `mos-fleet doctor` checks everything: the names, the servers, and your own setup.",
    say: "Commit, and push. | Then mos fleet doctor checks everything: the names, the servers, and your own setup.",
    visual: term("me", [
      { cmd: "git commit -am \"office: software\"", beat: 0, delay: 0.2, out: ["[main 4c1d2e7] office: software", " 1 file changed, 2 insertions(+), 1 deletion(-)"] },
      { cmd: "git push", beat: 0, delay: 3.2, out: [`To https://git.${DOMAIN}/fleet/config.git`, "   9b0e1f3..4c1d2e7  main -> main"] },
      { cmd: "mos-fleet doctor", beat: 1, delay: 0.4, out: ["{B}== Names (DNS){/}", ...["idm", "git", "cache", "fleet", "tang"].map((n) => `   {g}ok{/}   ${n}.${DOMAIN} -> 10.0.0.10`), "{B}== Servers{/}", "   {g}ok{/}   idm, git, cache, fleet", "{B}== You{/}", "   {g}ok{/}   fleet repository, admin key, ssh admin@hq with sudo"] },
    ], { cwd: "~/fleet" }) },

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
    text: "Back on your computer, plug in the stick, and prepare it for ws-001: its profile, its unlocking, its disk. | It writes a folder on the stick, with `corporate.config` and the files the installation needs. | The stick now holds secrets: keep it with you. The installer removes them when it's done.",
    say: "Back on your computer, plug in the stick, and prepare it for W S zero zero one: its profile, its unlocking, its disk. | It writes a folder on the stick, with corporate dot config and the files the installation needs. | The stick now holds secrets: keep it with you. The installer removes them when it's done.",
    visual: term("me", [
      { cmd: "mos-fleet prepare ws-001 --profile office --unlock tang --disk-serial S6PNNF0R123456X", beat: 0, delay: 3, typed: 30,
        out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-001", "   ws-001: profile office, unlock tang, disk S6PNNF0R123456X", "Boot the computer from this stick and choose Install: it offers the organization install.", "The stick now holds the repository token and the enroll secret: keep it with you.", "After the installation: mos-fleet add ws-001"] },
    ], { cwd: "~/fleet", fontSize: 24 }) },
  { id: "c5-install", chapter: ch.c5,
    text: "Connect the new computer to the office network with a cable, since Tang needs it. Boot it from the stick and open Install: it finds `corporate.config`, and offers the organization install. | Choose the language, the keyboard and the time zone. The organization has already decided the name, the disk and the unlocking. | Install now, and type YES. First it checks that it can reach every server: if one fails, nothing has been erased yet. | It sets up the unlocking, and encrypts the recovery key for the admins. | Then it downloads the managed system, already built, from the cache. | At the end, it writes the computer's own files back on the stick.",
    say: "Connect the new computer to the office network with a cable, since Tang needs it. Boot it from the stick and open Install: it finds corporate dot config, and offers the organization install. | Choose the language, the keyboard and the time zone. The organization has already decided the name, the disk and the unlocking. | Install now, and type YES. First it checks that it can reach every server: if one fails, nothing has been erased yet. | It sets up the unlocking, and encrypts the recovery key for the admins. | Then it downloads the managed system, already built, from the cache. | At the end, it writes the computer's own files back on the stick.",
    visual: () => <Installer host="ws-001" unlock="tang" at={{ form: 1, install: 2, checks: 2, unlock: 3, download: 4, done: 5 }} /> },
  { id: "c5-install-net", chapter: ch.c5,
    text: "On the map: the new computer checks every service, | binds its disk to Tang, | and downloads its system from the cache.",
    visual: net({ show: ["admin"], add: [{ id: "ws1", beat: 0 }], flows: [
      ...(["idm", "git", "cache", "fleet", "tang"] as const).map((s, i) => ({ from: "ws1" as const, to: s, label: "ok?", beat: 0, delay: 0.6 + i * 0.35, dur: 1.8 })),
      { from: "ws1", to: "tang", label: "bind", beat: 1, delay: 0.2 }, { from: "tang", to: "ws1", label: "bound", beat: 1, delay: 2.4, color: C.tealHi },
      { from: "cache", to: "ws1", label: "system", beat: 2, dur: 2.6, repeat: 2, every: 1 },
    ], hi: [{ id: "tang", beat: 1, for: 4 }, { id: "cache", beat: 2 }] }) },
  { id: "c5-add", chapter: ch.c5,
    text: "Restart it. It starts in managed mode, and fleet admins and the office group can already log in. | Back on your computer, with the stick, `mos-fleet add` takes it into the fleet: it copies the computer's files into the repository, checks them, commits, and pushes. | Within minutes the server builds it, and the computer takes its full configuration. `mos-fleet status` shows it.",
    say: "Restart it. It starts in managed mode, and fleet admins and the office group can already log in. | Back on your computer, with the stick, mos fleet add takes it into the fleet: it copies the computer's files into the repository, checks them, commits, and pushes. | Within minutes the server builds it, and the computer takes its full configuration. Mos fleet status shows it.",
    visual: term("me", [
      { cmd: "mos-fleet add ws-001", beat: 1, delay: 0.3, out: ["   checking that it builds (evaluating)…", "   pushed: ws-001: added to the fleet", "   its folder is removed from the stick", "The server builds it within minutes; then ws-001 takes its configuration (mos-fleet status ws-001)."] },
      { cmd: "mos-fleet status ws-001", beat: 2, delay: 1.5, out: ["ws-001     build: {g}ok 3f2a1c9{/}     Fleet: {g}online{/}, seen 2026-10-12T14:03   NixOS 26.05"] },
    ], { cwd: "~/fleet" }) },
  { id: "c5-add-net", chapter: ch.c5,
    text: "Follow the information. Your push reaches the repository. | The server builds the new computer's system, and puts it in the cache. | The computer notices the change, downloads it and switches to it, | and reports to Fleet.",
    visual: net({ show: ["admin", "ws1"], flows: [
      { from: "admin", to: "git", label: "hosts/ws-001", beat: 0, delay: 1, dur: 2.6 },
      { from: "git", to: "cache", label: "build", beat: 1, dur: 2 },
      { from: "ws1", to: "git", label: "new?", beat: 2 }, { from: "cache", to: "ws1", label: "system", beat: 2, delay: 2.2, dur: 2.4 },
      { from: "ws1", to: "fleet", label: "online", beat: 3, color: C.blue },
    ], hi: [{ id: "git", beat: 0, delay: 3, for: 3 }, { id: "cache", beat: 1, for: 4 }, { id: "ws1", beat: 2, delay: 4.6 }, { id: "fleet", beat: 3, delay: 2 }],
      tags: [{ id: "ws1", text: "managed ✓", beat: 2, delay: 4.6 }] }) },
  { id: "c5-more", chapter: ch.c5,
    text: "Two more computers, the same way. A laptop, ws-002, that unlocks with the TPM and a PIN; | and a desktop, ws-003, with a security key. | Prepare the stick, install, add.",
    say: "Two more computers, the same way. A laptop, W S zero zero two, that unlocks with the T P M and a PIN; | and a desktop, W S zero zero three, with a security key. | Prepare the stick, install, add.",
    visual: term("me", [
      { cmd: "mos-fleet prepare ws-002 --profile office --unlock tpm-pin", beat: 0, delay: 2, typed: 30, out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-002"] },
      { cmd: "mos-fleet prepare ws-003 --profile office --unlock fido2", beat: 1, delay: 0.5, typed: 30, out: ["Ready: /run/usb-vault/data/meccanicos/fleet/ws-003"] },
      { noPrompt: true, beat: 2, out: ["", "{d}# … install each one from the stick, then:{/}"] },
      { cmd: "mos-fleet add ws-002 && mos-fleet add ws-003", beat: 2, delay: 1.5, typed: 30, out: ["   pushed: ws-002: added to the fleet", "   pushed: ws-003: added to the fleet"] },
    ], { cwd: "~/fleet" }) },
  { id: "c5-pin", chapter: ch.c5,
    text: "For the laptop, the installer's form also asks for the disk PIN, | typed at every power-on.",
    visual: () => <Installer host="ws-002" unlock="tpm-pin" at={{ form: 0 }} /> },
  { id: "c5-three", chapter: ch.c5,
    text: "The fleet now has three computers. | `mos-fleet status` shows them all: each one's build, what Fleet sees, and its version.",
    say: "The fleet now has three computers. | Mos fleet status shows them all: each one's build, what Fleet sees, and its version.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: net({ show: ["admin", "ws1"], add: [{ id: "ws2", beat: 0, delay: 0.3 }, { id: "ws3", beat: 0, delay: 1 }],
          flows: [{ from: "ws2", to: "fleet", label: "online", beat: 0, delay: 1.2, color: C.blue }, { from: "ws3", to: "fleet", label: "online", beat: 0, delay: 1.8, color: C.blue }] }) },
        { beat: 1, render: term("me", [{ cmd: "mos-fleet status", beat: 1, delay: 0.3, out: [
          "{B}== Computers{/}",
          "   ws-001               build: {g}ok 3f2a1c9{/}       Fleet: {g}online{/}  NixOS 26.05",
          "   ws-002               build: {g}ok 3f2a1c9{/}       Fleet: {g}online{/}  NixOS 26.05",
          "   ws-003               build: {g}ok 3f2a1c9{/}       Fleet: {g}online{/}  NixOS 26.05"] }], { cwd: "~/fleet" }) },
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
    text: "Commit, and push. | The server builds the office computers' new systems. | Each computer notices within minutes, | downloads its new system from the cache, and switches to it. | And `git log` shows who changed what, and when.",
    say: "Commit, and push. | The server builds the office computers' new systems. | Each computer notices within minutes, | downloads its new system from the cache, and switches to it. | And git log shows who changed what, and when.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "git commit -am \"office: gimp\" && git push", beat: 0, delay: 0.3, typed: 30, out: ["[main 8e2b6a0] office: gimp", "   4c1d2e7..8e2b6a0  main -> main"] }], { cwd: "~/fleet" }) },
        { beat: 1, render: net({ show: ALL, flows: [
          { from: "admin", to: "git", label: "push", beat: 1, dur: 1.6 },
          { from: "git", to: "cache", label: "build", beat: 1, delay: 1.6, dur: 2 },
          { from: "ws1", to: "git", label: "new?", beat: 2 }, { from: "ws2", to: "git", label: "new?", beat: 2, delay: 0.5 }, { from: "ws3", to: "git", label: "new?", beat: 2, delay: 1 },
          { from: "cache", to: "ws1", label: "gimp", beat: 3, dur: 2.4 }, { from: "cache", to: "ws2", label: "gimp", beat: 3, delay: 0.4, dur: 2.4 }, { from: "cache", to: "ws3", label: "gimp", beat: 3, delay: 0.8, dur: 2.4 },
        ], hi: [{ id: "cache", beat: 1 }],
          tags: [{ id: "ws1", text: "updated ✓", beat: 3, delay: 2.4 }, { id: "ws2", text: "updated ✓", beat: 3, delay: 2.8 }, { id: "ws3", text: "updated ✓", beat: 3, delay: 3.2 }] }) },
        { beat: 4, render: term("me", [{ cmd: "git log --oneline -3", beat: 4, delay: 0.3, out: ["{a}8e2b6a0{/} office: gimp  {d}(Mario Rossi, 2 minutes ago){/}", "{a}c0f9d41{/} ws-001: added to the fleet  {d}(Mario Rossi, 1 hour ago){/}", "{a}4c1d2e7{/} office: software  {d}(Mario Rossi, 2 hours ago){/}"] }], { cwd: "~/fleet" }) },
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
    text: "People. Commands like these run on the server: typed on your computer, they go there over SSH. A new person, in the office group: | they open the link to set a password or a passkey, and can log in at every office computer. | Someone leaves: remove them. Computers forget them when their cache expires.",
    say: "People. Commands like these run on the server: typed on your computer, they go there over S S H. A new person, in the office group: | they open the link to set a password or a passkey, and can log in at every office computer. | Someone leaves: remove them. Computers forget them when their cache expires.",
    visual: term("me", [
      { cmd: "mos-fleet person add lbianchi \"Lucia Bianchi\" --group office", beat: 0, delay: 5.5, typed: 28, out: ["lbianchi created, in office.", `{a}https://idm.${DOMAIN}/ui/reset?token=Pq7c-28Ld-4kYv{/}`] },
      { cmd: "mos-fleet person password lbianchi", beat: 1, delay: 0.5, out: ["New password: ••••••••••"] },
      { cmd: "mos-fleet person remove gverdi", beat: 2, delay: 1, out: ["gverdi removed (computers forget them when their cache expires)."] },
    ]) },
  { id: "c6-login", chapter: ch.c6,
    text: "When Lucia logs in at a computer, it asks Kanidm, | and remembers the answer, for when it's offline.",
    say: "When Lucia logs in at a computer, it asks Kani D M, | and remembers the answer, for when it's offline.",
    visual: net({ show: ALL, flows: [{ from: "ws2", to: "idm", label: "lbianchi?", beat: 0, delay: 0.5 }, { from: "idm", to: "ws2", label: "ok", beat: 0, delay: 2.8, color: C.green }],
      hi: [{ id: "idm", beat: 0, delay: 0.5, for: 4 }], tags: [{ id: "ws2", text: "lbianchi ✓ (cached)", beat: 1 }] }) },
  { id: "c6-upgrade", chapter: ch.c6,
    text: "A new MeccanicOS for everyone is one command. | But you can try it on a few computers first: in their `fleet.toml`, put them on the testing branch, then upgrade with `--testing`. | When they're fine, upgrade everyone.",
    say: "A new MeccanicOS for everyone is one command. | But you can try it on a few computers first: in their fleet dot toml, put them on the testing branch, then upgrade with dash dash testing. | When they're fine, upgrade everyone.",
    visual: term("me", [
      { cmd: "mos-fleet upgrade --testing", beat: 1, delay: 5, out: ["   checking that every computer still evaluates…", "Pushed to the testing branch: computers whose fleet.toml says branch = \"testing\" take it."] },
      { cmd: "mos-fleet upgrade", beat: 2, delay: 0.5, out: ["   checking that every computer still evaluates…", "Pushed: every computer takes it within minutes (kernel changes: at the next restart)."] },
    ], { cwd: "~/fleet" }) },
  { id: "c6-upgrade-net", chapter: ch.c6,
    text: "The server fetches the new MeccanicOS, and builds every computer. | The testing computer takes it first. | Then everyone else. A new kernel takes effect at the next restart.",
    visual: net({ show: ["admin", "ws1", "ws2", "ws3", "net"], flows: [
      { from: "net", to: "git", label: "MeccanicOS", beat: 0, delay: 0.3, dur: 2.6 }, { from: "git", to: "cache", label: "build", beat: 0, delay: 3, dur: 1.8 },
      { from: "cache", to: "ws3", label: "new", beat: 1, delay: 0.2, dur: 2.4, color: C.sand },
      { from: "cache", to: "ws1", label: "new", beat: 2, dur: 2.4 }, { from: "cache", to: "ws2", label: "new", beat: 2, delay: 0.4, dur: 2.4 },
    ], tags: [{ id: "ws3", text: "testing ✓", beat: 1, delay: 2.6, color: C.sand }, { id: "ws1", text: "updated ✓", beat: 2, delay: 2.4 }, { id: "ws2", text: "updated ✓", beat: 2, delay: 2.8 }] }) },
  { id: "c6-retire", chapter: ch.c6,
    text: "A computer leaves the company: retire it. It stops getting updates, and its recovery key moves to the retired folder. Delete it in Fleet's web page too.",
    visual: term("me", [
      { cmd: "mos-fleet retire ws-003", beat: 0, delay: 1.5, out: ["   pushed: ws-003: retired", "ws-003 no longer gets updates. Its recovery key stays in retired/ws-003 until its", "disk is wiped; delete it in Fleet's web page too."] },
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
        { beat: 1, render: term("me", [{ cmd: "mos-fleet recover ws-001", beat: 1, delay: 0.3, out: ["Recovery key for ws-001 (type it at the disk prompt):", "", `    {a}${RECOVERY}{/}`] }], { cwd: "~/fleet" }) },
        { beat: 2, render: vaults([{ method: "recovery", x: 660, y: 200, beat: 2, delay: 0.8, title: "ws-001", note: "the recovery key, typed" }]) },
      ]} />
    ) },
  { id: "c7-config", chapter: ch.c7,
    text: "A computer doesn't take its configuration. `mos-fleet status` says whether its build failed, and why. | On the computer itself, comin's log says whether it can reach the repository.",
    say: "A computer doesn't take its configuration. Mos fleet status says whether its build failed, and why. | On the computer itself, come in's log says whether it can reach the repository.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "mos-fleet status ws-002", beat: 0, delay: 3, out: ["ws-002     build: {r}FAILED 9d1e0c2{/}   Fleet: {g}online{/}   NixOS 26.05", "", "error: undefined variable 'gimpp'", "       at hosts/ws-002/local.nix:4:5"] }], { cwd: "~/fleet" }) },
        { beat: 1, render: term("ws2", [{ cmd: "journalctl -u comin -n 50", beat: 1, delay: 0.3, out: ["comin[912]: fetching https://git.corp.example.com/fleet/config.git", "comin[912]: {g}fetched 9d1e0c2{/}; waiting for the cache to have it"] }]) },
      ]} />
    ) },
  { id: "c7-revert", chapter: ch.c7,
    text: "A bad commit is undone with git revert, and a push. | And a computer that doesn't start after an update: pick the previous entry in its boot menu.",
    visual: () => (
      <Phases phases={[
        { beat: 0, render: term("me", [{ cmd: "git revert 9d1e0c2 && git push", beat: 0, delay: 0.4, typed: 26, out: ["[main 1a7f3b5] Revert \"ws-002: gimpp\"", "   9d1e0c2..1a7f3b5  main -> main"] }], { cwd: "~/fleet" }) },
        { beat: 1, render: board([
          { t: "box", x: 460, y: 60, w: 1000, h: 640, title: "boot menu", top: true, align: "left", color: C.amber, mono: true, size: 30,
            body: ["", "  MeccanicOS 26.05 (generation 42)", "{a}> MeccanicOS 26.05 (generation 41){/}", "  MeccanicOS 26.05 (generation 40)", "", "{d}  the previous one: as it was before{/}"], beat: 1 },
        ]) },
      ]} />
    ) },
  { id: "c7-server", chapter: ch.c7,
    text: "A service on the server is down: `mos-fleet server status` finds it, | journalctl says why, | and systemctl restarts it.",
    say: "A service on the server is down: mos fleet server status finds it, | journal control says why, | and system control restarts it.",
    visual: term("hq", [
      { cmd: "mos-fleet server status", beat: 0, delay: 3.5, out: ["{B}== Services{/}", "   {g}ok{/}   kanidm                       active", "   {r}FAIL{/} forgejo                      failed", "   {g}ok{/}   harmonia                     active"] },
      { cmd: "journalctl -b -u forgejo -n 3", beat: 1, delay: 0.2, out: ["forgejo[1204]: {r}cannot connect to mysql: connection refused{/}"] },
      { cmd: "sudo systemctl restart mysql forgejo", beat: 2, delay: 0.2 },
    ]) },
  { id: "c7-leak", chapter: ch.c7,
    text: "And if the admin kit leaks, say with a stolen, unlocked computer: make new tokens in Forgejo and a new enroll secret in Fleet, then run server init again. The guide has the details.",
    say: "And if the admin kit leaks, say with a stolen, unlocked computer: make new tokens in Forjayo and a new enroll secret in Fleet, then run server init again. The guide has the details.",
    visual: board([
      { t: "text", x: 80, y: 10, text: "The admin kit {r}leaked{/}", size: 44, at: 0.02 },
      { t: "box", x: 80, y: 130, w: 540, h: 260, title: "Forgejo", body: ["new tokens:", "fleet-reader, fleet-admin"], at: 0.25, color: C.amber },
      { t: "box", x: 690, y: 130, w: 540, h: 260, title: "Fleet", body: ["a new enroll secret"], at: 0.45, color: C.blue },
      { t: "box", x: 1300, y: 130, w: 540, h: 260, title: "the server", body: ["mos-fleet server init", "again, same options"], at: 0.65, color: C.tealHi },
      { t: "text", x: 960, y: 500, text: "then each computer's {a}/etc/secrets/meccanicos/repo.token{/}", size: 32, align: "center", w: 1600, at: 0.8 },
    ]) },

  // ---------------------------------------------------------- 8 backups
  { id: "c8-title", chapter: ch.c8, text: "Chapter eight. Backups: what you can't afford to lose.",
    visual: title(8, "Backups", "what you can't afford to lose") },
  { id: "c8-what", chapter: ch.c8,
    text: "Back up the server every night. Above all: | the fleet's keys and certificates; | Tang's keys: without them, Tang computers never unlock by themselves again; | Kanidm's people and groups, and the repository, with its database dumps. | And each admin's key, on paper too: it's the only way to read the recovery keys.",
    say: "Back up the server every night. Above all: | the fleet's keys and certificates; | Tang's keys: without them, Tang computers never unlock by themselves again; | Kani D M's people and groups, and the repository, with its database dumps. | And each admin's key, on paper too: it's the only way to read the recovery keys.",
    visual: board([
      { t: "box", x: 80, y: 20, w: 860, h: 150, title: "/var/lib/meccanicos-fleet/", body: "keys, certificates, passwords, the kit", beat: 1, mono: true, size: 34 },
      { t: "box", x: 980, y: 20, w: 860, h: 150, title: "/var/lib/tang/", body: "{r}lost: Tang computers never unlock by themselves{/}", beat: 2, mono: true, size: 34, color: C.red },
      { t: "box", x: 80, y: 220, w: 860, h: 150, title: "/var/lib/kanidm/", body: "people and groups", beat: 3, mono: true, size: 34, color: C.tealHi },
      { t: "box", x: 980, y: 220, w: 860, h: 150, title: "/var/lib/forgejo/ + /var/backup/mysql", body: "the repository, its database dumps", beat: 3, delay: 1.5, mono: true, size: 34, color: C.green },
      { t: "box", x: 80, y: 420, w: 1760, h: 170, title: "~/.config/mos-fleet/admin.key, and the paper copy", body: "{r}each admin's: the only way to read recovery keys{/}", beat: 4, mono: true, size: 36, color: C.red },
    ]) },

  // ---------------------------------------------------------------- end
  { id: "end-sheet", chapter: ch.end,
    text: "That's the whole job, on one sheet. Everything is in the admin guide, in the MeccanicOS repository. | And remember: fleets are experimental. Start with spare machines.",
    visual: () => <Sheet /> },
];

// What each command does: the callout shown the first time it is typed.
export const COMMANDS: Record<string, string> = {
  ls: "list what is in a folder",
  cd: "change directory: go to another folder",
  ping: "check that a machine answers on the network",
  tldr: "short examples of how to use a command",
  head: "show only the first lines",
  man: "the full manual of a command (q quits)",
  pwd: "print working directory: where you are",
  mkdir: "make a new folder (directory)",
  touch: "create an empty file",
  cp: "copy a file",
  mv: "move or rename a file",
  yazi: "a file manager in the terminal",
  jed: "a simple text editor in the terminal",
  cat: "print what is in a file",
  less: "read a long file page by page (q quits)",
  open: "open a file with its usual app",
  codium: "VSCodium, a full code editor",
  print: "send a file to the printer, or to a PDF",
  rm: "remove a file, for good: no undo",
  trash: "move a file to the trash: it can come back",
  "trash-list": "list what is in the trash",
  "trash-restore": "take a file back out of the trash",
  grep: "keep only the lines that contain a word",
  wc: "count lines, words and characters",
  sort: "put lines in order",
  echo: "print some text",
  chmod: "change who may read, write or run a file",
  sudo: "run one command as the administrator",
  export: "set a variable for the programs this shell starts",
  "nix-shell": "a shell with extra programs, borrowed for now",
  "g++": "the C++ compiler: source code in, program out",
  exit: "leave this shell",
  sleep: "wait, doing nothing, for some seconds",
  ps: "list the running processes",
  pgrep: "find a process's number by its name",
  btop: "a live dashboard: processes, processor, memory",
  free: "how much memory is used, and how much is free",
  kill: "stop a process, by its number",
  pkill: "stop processes, by their name",
  ip: "show the network cards and their addresses",
  "mos-config": "see and change MeccanicOS settings",
  curl: "fetch a web address",
  python3: "run Python: here, a tiny web server",
  ss: "list network connections and open ports",
  lsof: "which program has a file, or a port, open",
  mos: "list the MeccanicOS commands",
  "mos-doctor": "find and fix common problems",
  "mos-updates": "check for updates, and install them",
  lsblk: "list the disks and their partitions",
  df: "free space on each disk",
  du: "space used by files and folders",
  ncdu: "explore what fills a disk, interactively",
  udisksctl: "mount and unmount disks, no sudo needed",
};

// The commands in a command line: the first word of each part of a pipeline
// (or &&, ;), and the one after sudo. Not ./programs or options.
export const commandNames = (line: string): string[] =>
  line.split(/\s*(?:\|\||&&|\||;)\s*/).flatMap((seg) => {
    const w = seg.trim().split(/\s+/);
    const out: string[] = [];
    let i = 0;
    if (w[0] === "sudo") { out.push("sudo"); i = 1; }
    if (w[i] && /^[a-z]/.test(w[i])) out.push(w[i]);
    return out;
  });

// What each command does: the callout shown the first time it is typed.
export const COMMANDS: Record<string, string> = {
  timedatectl: "the clock: is it synchronized?",
  grep: "keep only the lines that contain a word",
  ip: "show the network cards and their addresses",
  "usb-vault stick": "open the MeccanicOS stick's own files",
  cp: "copy a file",
  "mos-fleet server init": "turn this MeccanicOS into the fleet's server",
  "mos-fleet server status": "is every part of the server running?",
  "mos-fleet server admin-key": "let an SSH key in as an admin, for a day",
  "mos-fleet server backup": "copy the repository, databases and keys",
  "mos-fleet init": "a new fleet repository, pushed to the server",
  "mos-fleet profile add": "a new kind of computer, and its group",
  "mos-fleet person add": "a new person, in the repository",
  "mos-fleet validate": "check every file, and build every computer in Nix",
  "mos-fleet push": "check, then send the commits to the server",
  "mos-fleet password set": "set someone's password (only its hash leaves)",
  jed: "a simple text editor in the terminal",
  "git commit": "record a change in the repository",
  "git push": "send your changes to the server",
  "git revert": "undo a commit, with a new commit",
  "git log": "who changed what, and when",
  lsblk: "list the disks, here with their serial numbers",
  "mos-fleet host prepare": "a new computer's settings and one-time key, on the stick",
  "mos-fleet host pending": "computers that introduced themselves",
  "mos-fleet host add": "take a new computer into the repository",
  "mos-fleet host set": "change a computer's profile or branch",
  "mos-fleet host retire": "take a computer out of the fleet",
  "mos-fleet status": "every computer: online? up to date?",
  "mos-fleet logs": "a computer's log, as it sent it",
  "mos-fleet run": "a command on computers, as root",
  "mos-fleet shell": "SSH to a computer, through the server",
  "mos-fleet upgrade": "move the fleet to the newest MeccanicOS",
  "mos-fleet recover": "print a computer's recovery key",
  "mos-fleet builds": "the server's builds, and their errors",
  "mos-fleet audit": "who did what: pushes, jobs, passwords",
  "mos-passwd": "change your own password, on every computer",
  hostname: "the computer's name",
};

// Commands with subcommands: the callout names the subcommand too.
const GROUPS: Record<string, number> = {
  "usb-vault": 1, "mos-fleet": 1, git: 1, "mos-fleet server": 1, "mos-fleet host": 1, "mos-fleet person": 1,
  "mos-fleet profile": 1, "mos-fleet password": 1,
};

// The commands in a command line: the first word of each part of a pipeline
// (or &&, ;), the one after sudo, with their subcommands. Not ./programs or options.
export const commandNames = (line: string): string[] =>
  line.split(/\s*(?:\|\||&&|\||;)\s*/).flatMap((seg) => {
    const w = seg.trim().split(/\s+/);
    let i = w[0] === "sudo" ? 1 : 0;
    if (!w[i] || !/^[a-z]/.test(w[i])) return [];
    let name = w[i];
    while (GROUPS[name] && w[i + 1] && /^[a-z]/.test(w[i + 1])) name += " " + w[++i];
    return [name];
  });

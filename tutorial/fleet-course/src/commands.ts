// What each command does: the callout shown the first time it is typed.
export const COMMANDS: Record<string, string> = {
  timedatectl: "the clock: is it synchronized?",
  grep: "keep only the lines that contain a word",
  ip: "show the network cards and their addresses",
  "mos-fleet server init": "turn this MeccanicOS into the fleet's server",
  "mos-fleet person add": "a new person (a Kanidm account)",
  "mos-fleet person password": "set someone's password for logging in to computers",
  "mos-fleet person remove": "someone leaves: remove their account",
  "mos-fleet server status": "is every service on the server running?",
  "ssh-copy-id": "let your SSH key log you in to another computer",
  "mos-fleet connect": "fetch the admin kit, clone the fleet repository",
  "mos-fleet admin-key": "your key for reading recovery keys",
  "mos-fleet profile add": "a new kind of computer, and its group",
  jed: "a simple text editor in the terminal",
  "git commit": "record a change in the repository",
  "git push": "send your changes to the server",
  "mos-fleet doctor": "check names, servers and your setup",
  lsblk: "list the disks, here with their serial numbers",
  "mos-fleet prepare": "put a computer's install files on the stick",
  "mos-fleet add": "take an installed computer into the fleet",
  "mos-fleet status": "every computer: its build, and what Fleet sees",
  "mos-fleet member add": "let a person log in on a profile's computers",
  "mos-fleet upgrade": "move the fleet to the newest MeccanicOS",
  "mos-fleet recover": "print a computer's recovery key",
  "mos-fleet retire": "take a computer out of the fleet",
  "git revert": "undo a commit, with a new commit",
  journalctl: "read a service's log",
  cat: "print what is in a file",
  systemctl: "start, stop or restart a service",
  "git log": "who changed what, and when",
};

// Commands with subcommands: the callout names the subcommand too.
const GROUPS: Record<string, number> = { "mos-fleet": 1, git: 1, "mos-fleet server": 1, "mos-fleet person": 1, "mos-fleet member": 1, "mos-fleet profile": 1 };

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

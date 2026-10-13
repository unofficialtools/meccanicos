# MeccanicOS fleet: set up the server, add computers

> **⚠ Experimental.** Fleet management is new. It is tested end to end in
> virtual machines (`nix build .#checks.x86_64-linux.fleet`), not yet in a
> real organization. Try it on spare machines first, and back up your admin
> key and the server (Part 6) from day one. [DESIGN.md](DESIGN.md) explains
> how it works and why.

This guide is for whoever runs an organization's MeccanicOS computers. It
assumes you're at ease in a bash shell. One command, `mos-fleet`, does the
work; the guide says when to run it and what to check.

## The big picture

- **The fleet repository** is the source of truth: a git repository listing
  the computers (`hosts/`), the kinds of computers (`profiles/`), the people
  (`people/`) and the groups (`groups.toml`). Changing a computer means
  changing a file there, committing and pushing.
- **The fleet server** is a MeccanicOS computer with one extra account,
  `fleet`, reached only over SSH. It keeps the repository, builds every
  computer's system from it, and stores what the computers report (facts,
  logs, what they ran) in a SQLite database. Password hashes and disk
  recovery keys go in a second database. It also runs **Tang**, which lets
  office desktops unlock their disks by themselves, only on the office network.
- **Every other computer** runs MeccanicOS in **managed mode**. Its agent
  keeps an SSH connection open to the server, identified by the computer's
  own SSH key. Through it the computer receives the system it should run
  (and switches to it within seconds of a build), its people's password
  hashes, and jobs (run a command, restart); it sends back facts and logs.
  The connection always goes from the computer to the server, so laptops
  work from anywhere the server can be reached.

No web services, no extra databases: SSH, git, Nix and SQLite.

Who may log in, and where (`groups.toml`):

- **`fleet-admins`**: every computer, with `sudo`; and the server (pushing
  the repository, all `mos-fleet` commands).
- **Other groups**: the computers of the profiles they list. `mos-fleet
  profile add office` also makes a group `office` for the `office` computers.

Every computer has a **recovery key** for its disk, encrypted so that only the
admins can read it, kept on the server.

## Before you start

You need:

- **A server**: any 64-bit PC with 8 GB of RAM or more and 100 GB+ of disk,
  on the office network, with a **fixed IP address**, and a **DNS name**
  (here `hq.corp.example.com`) that the computers can reach.
- **Your own computer**, running MeccanicOS, with an SSH key
  (`ssh-keygen -t ed25519` if `~/.ssh/id_ed25519.pub` doesn't exist).
- **A MeccanicOS USB stick**, made with `mos-usb` or Ventoy as usual. It
  carries your SSH key to the server, and each new computer's one-time key.

Replace `corp.example.com`, `Example Corp`, `hq` and `mrossi` with your own.

---

# Part 1: the server

## 1.1 Install MeccanicOS on it

Install it from the stick as usual (normal install). Name it `hq`. Pick a
disk password and **write it down and keep it in a safe**: the server can't
unlock itself unattended (it's the one running Tang).

## 1.2 Set it up

On your own computer, copy your SSH public key to the stick:

```sh
$ usb-vault stick
$ cp ~/.ssh/id_ed25519.pub /run/usb-vault/data/
```

At the server, with the stick plugged in:

```sh
$ usb-vault stick
$ mos-fleet server init --lan 10.0.0.0/24 --admin-key /run/usb-vault/data/id_ed25519.pub
```

`--lan` is your office network (repeat it for several): only computers there
can reach Tang. It asks for your password (sudo), then:

1. writes `/etc/nixos/fleet-server.toml` and rebuilds the system with the
   fleet services: the account `fleet`, Tang, the build service;
2. makes the repository (empty) and the databases, in `/var/lib/mos-fleet`;
3. lets your SSH key in, as an admin, **for 24 hours**: long enough to create
   the repository (next part), where your key then stays.

It ends by printing **the server's SSH fingerprint** (`SHA256:…`). Note it:
your computer checks it in the next step, so that it talks to this server and
no other.

Running it again is safe. `mos-fleet server admin-key FILE` lets a key in for
another 24 hours (a new admin, or one who lost theirs): it can push the
repository, so it can fix `people/` and `groups.toml`.

## 1.3 DNS

Ask for the server's name (`hq.corp.example.com`) to point to its address.

---

# Part 2: your computer, the repository

These commands run as yourself, on your own MeccanicOS computer.

## 2.1 Create the fleet repository

```sh
$ mos-fleet init --server hq.corp.example.com --fingerprint SHA256:… \
    --organization "Example Corp" --admin mrossi --full-name "Mario Rossi"
```

It checks the server's fingerprint, makes **your admin key**
(`~/.config/mos-fleet/admin.key`: recovery keys are encrypted for it), writes
the repository in `~/fleet` with you in `fleet-admins`, pins the MeccanicOS
version (`flake.lock`), and pushes it to the server.

**Back up `admin.key` now**, offline: print it (`cat`) and keep the paper in
the safe. Without at least one admin key, no recovery key can be read.

Another admin, on their computer: `mos-fleet clone hq.corp.example.com
--fingerprint SHA256:…`, then `mos-fleet admin-key` prints the public half of
their admin key; you add them with `mos-fleet person add NAME "Full Name"
--group fleet-admins --ssh-key their.pub --age-recipient age1…`.

## 2.2 Profiles, people, groups

```sh
$ cd ~/fleet
$ mos-fleet profile add office                 # profiles/office.nix, and the group office
$ jed profiles/office.nix                      # the profile's software
$ mos-fleet person add lbianchi "Laura Bianchi" --group office
$ mos-fleet validate                           # every file, and every computer evaluated by Nix
$ mos-fleet push
```

Every `mos-fleet` command that edits the repository checks the result and
commits; `--push` sends it right away, `mos-fleet push` later. Plain git works
too: edit, `git commit`, then `mos-fleet push` (it validates first).

The server refuses a push that isn't valid (a typo in a file, two people
with the same uid, a group that doesn't exist, no admin left), and never
lets `main` be rewritten: undo with a new commit (`git revert`).

`mos-fleet diff` shows what your unpushed commits change on each computer:
who may log in, whose system changes.

---

# Part 3: adding a computer

## 3.1 (Optional) the disk's serial number

If the computer has several disks, note the serial number of the one to
install on (`lsblk -o NAME,SIZE,MODEL,SERIAL` from the live stick), so the
installer can't pick the wrong one.

## 3.2 Prepare the stick

```sh
$ mos-fleet host prepare ws-001 --profile office --unlock tang
```

`--unlock` is how its disk opens at power-on: `tang` (office desktops:
automatic on the office network, with the TPM chip), `tpm-pin` (laptops: the
TPM chip and a PIN) or `fido2` (a security key). Add `--disk-serial S` from 3.1.

It writes `meccanicos/fleet/ws-001/` on the stick: the settings, the admins'
public keys (for its recovery key), and a **one-time key** that lets the new
computer introduce itself to the server, once, within 7 days.

## 3.3 Install

Boot the computer from the stick and choose **Install**: the installer finds
the folder and offers the **organization install**. Name, disk and disk
unlocking come from the stick; you choose language, keyboard and Wi-Fi.
For Tang, the computer must be on the office network (a cable).

At the end it shows the computer's **SSH key fingerprint**: note it. It also
leaves a copy of the recovery key (encrypted) in `result/` on the stick.

## 3.4 Add it to the fleet

At its first start, the computer introduces itself to the server with the
one-time key (which then stops working): its SSH key, its hardware
configuration, its encrypted recovery key. Then:

```sh
$ mos-fleet host pending                 # ws-001 … waiting for: mos-fleet host add
$ mos-fleet host add ws-001
```

It shows the fingerprint the computer sent: **compare it** with the one the
installer showed. Then it writes `hosts/ws-001/` and commits. Look at the
files there (the computer wrote its own `hardware-configuration.nix` and
`local.nix`), and push:

```sh
$ mos-fleet push
$ mos-fleet status ws-001                # building … then up to date
```

The server builds the computer's system; the computer switches to it. Until
then nobody can log in on it: its people come with that system.

## 3.5 Passwords

```sh
$ mos-fleet password set lbianchi
```

The hash is made on your computer; only the hash goes to the server, and from
there to the computers where `lbianchi` may log in. People change their own
with **`mos-passwd`** (`passwd` on managed computers): on any computer, once,
for all of them. It needs the current password; after 5 wrong ones in an hour
it waits (or an admin sets a new one).

---

# Part 4: everyday tasks

All in `~/fleet`. Changes reach the computers within a minute or so of the
push (a new kernel: at the next restart).

| Task | How |
|---|---|
| New person | `mos-fleet person add NAME "Full Name" --group office`, then `mos-fleet password set NAME` |
| Person leaves | `mos-fleet person disable NAME` (or `remove`); push |
| Let someone use a profile's computers | `mos-fleet member add office NAME` (`member remove` to undo) |
| Someone may use more profiles | `mos-fleet group edit office --add-profile lab` |
| sudo for a group | `mos-fleet group edit lab --sudo` |
| Software for a profile | edit `profiles/office.nix`, commit, push |
| Software for everyone | edit `common.nix`, commit, push |
| Software for one computer | edit `hosts/NAME/local.nix`, commit, push |
| Move a computer to another profile | `mos-fleet host set NAME --profile lab` |
| New MeccanicOS for everyone | `mos-fleet upgrade` |
| Try it on a few computers first | `mos-fleet host set NAME --branch testing` (push); `mos-fleet upgrade --testing`; when they're fine, `mos-fleet upgrade` |
| What runs where | `mos-fleet status` (`status NAME`: details) |
| A command on computers | `mos-fleet run --host NAME -- COMMAND…` or `--profile office`: as root, at once on those online, when they connect otherwise (`jobs`, `job ID`, `cancel ID`) |
| A shell on a computer | `mos-fleet shell NAME` (SSH through the server, with your own key: end to end) |
| Restart a computer | `mos-fleet reboot NAME` |
| Its logs | `mos-fleet logs NAME [--unit U] [--since 2h] [-f]` (warnings and worse, and `fleet.toml [logs] units`) |
| Who did what | `mos-fleet audit`; `git log` for the repository |
| Retire a computer | `mos-fleet host retire NAME --push` (its recovery key stays on the server) |

---

# Part 5: when something goes wrong

**A computer doesn't unlock its disk** (a Tang desktop away from the office,
a broken TPM, a lost security key). On your computer:

```sh
$ mos-fleet recover ws-001
```

prints its recovery key (it needs your admin key). Type it when the computer
asks for the disk password.

**A computer doesn't update.** `mos-fleet status ws-001`: `build failed` shows
the build's error (the computer keeps running its previous system); `update
pending (offline)` means it hasn't connected. `mos-fleet builds ws-001 --log`,
`mos-fleet deployments ws-001`.

**A change broke something.** `git revert COMMIT && mos-fleet push`. On the
computer itself, the boot menu still lists the previous systems.

**You can't reach the server** (lost SSH key, broken `people/` file): at the
server's console, `mos-fleet server admin-key FILE`, then fix the repository
and push.

**The server's services:** `mos-fleet server status` (at its console);
`journalctl -u mos-fleet-build` for builds, `journalctl -u sshd` for logins.

---

# Part 6: backups

```sh
$ mos-fleet server backup /run/usb-vault/data/fleet-backup      # at the server
```

copies the repository, both databases (consistent copies), Tang's keys and
the server's SSH keys. It holds password hashes: keep it offline, encrypted
(a USB Vault). Also keep:

| What | Where | Why |
|---|---|---|
| Admin keys | each admin's `~/.config/mos-fleet/admin.key`, on paper | without one, no recovery key can be read |
| The server's disk password | the safe | it doesn't unlock itself |
| The repository | every admin's `~/fleet` is a full copy | |

Restoring: install MeccanicOS on a new server with the same name, `mos-fleet
server init`, then put the backup back in `/var/lib/mos-fleet` (owned by
`fleet`), `/var/lib/tang` and `/etc/ssh`, and restart it.

---

# Part 7: how it stays safe

| Who | What it may do |
|---|---|
| An admin's SSH key (`fleet-admins`, in `people/`) | push the repository; every `mos-fleet` command; `shell` into computers (with their own key, end to end) |
| A computer's SSH key (`hosts/NAME/host.toml`) | its own session: report, receive its own system, its people's hashes, its jobs. Not another computer's system, nothing else |
| A one-time key (from `host prepare`) | introduce that one computer, once, within 7 days |
| A key at the console (`server admin-key`) | push the repository, for 24 hours |
| Anyone else | nothing: the server answers no other key |

- The account `fleet` has no shell, no port forwarding, no terminal: every
  key gets one forced command (sshd's `AuthorizedKeysCommand`).
- The server's SSH key is pinned everywhere (`fleet.toml`, the stick, each
  computer), so nobody can pretend to be the server.
- Pushes are checked before they're accepted; `main` can't be rewritten; every
  push, job, password change and recovery-key read is in `mos-fleet audit`.
- Computers never send passwords: a person changing theirs proves the current
  one to the server, which keeps only hashes. Repeated wrong guesses lock it.
- Whoever controls the server controls the fleet: it decides what computers
  run. Keep it in a locked room, its disk encrypted, its backups offline.

---

# Reference

**The repository**

```
fleet.toml                organization, server (NAME[:PORT]), server_host_key,
                          [tang] url, thumbprint; [checkin] interval;
                          [logs] min_priority, units, keep_days
groups.toml               [GROUP] gid, profiles (names, or "*"), sudo, description
people/NAME.toml          name, email, uid, groups, ssh_keys, age_recipient, disabled
profiles/NAME.nix         a NixOS module: the profile's software and settings
hosts/NAME/host.toml      profile, branch ("main"), unlock, host_key, disk_serial
hosts/NAME/*.nix          hardware-configuration.nix, local.nix (from the installation)
common.nix                a NixOS module for every computer
flake.nix, flake.lock     MeccanicOS's mkFleet; the pinned MeccanicOS version
```

**Settings:** `mos-fleet`'s own (where the repository is, uid ranges, how long
one-time keys last, log retention…) are in
[`scripts/mos_fleet/defaults.toml`](../../scripts/mos_fleet/defaults.toml);
override them in `/etc/mos-fleet/config.toml` (NixOS:
`meccanicos.fleet.config`) or your `~/.config/mos-fleet/config.toml`.

**On the server:** `/var/lib/mos-fleet`: `fleet.git` (the repository),
`state.db`, `secrets.db`, `main/` (the newest valid main), `roots/` (the
built systems). Services: `mos-fleet-setup`, `mos-fleet-build` (after every
push, and every 10 minutes), `mos-fleet-prune` (daily), `tangd`.

**On a computer:** `mos-fleet-agent` (`journalctl -u mos-fleet-agent`);
`/etc/mos-fleet/client.json`, `/etc/mos-fleet/known_hosts`;
`/var/lib/mos-fleet` (password hashes, the log cursor).

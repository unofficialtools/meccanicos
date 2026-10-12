# MeccanicOS fleet: set up the server, add computers

> **⚠ Experimental.** Fleet management is new and has not been tested on real
> hardware or in a real organization yet. Try it on spare machines first, and
> keep the recovery keys (Part 6) safe from day one. See [DESIGN.md](DESIGN.md)
> for what it does and why it is built this way, and its known limits.

This guide is for whoever runs an organization's MeccanicOS computers. It
assumes you're at ease in a bash shell, and nothing more. One command,
`mos-fleet`, does the setting up; the guide says when to run it and what to
check.

## The big picture

One **server**, running MeccanicOS, hosts everything the fleet needs:

| Name | Service | What it does |
|---|---|---|
| `idm.DOMAIN` | **Kanidm** | People, groups, passwords and passkeys. Who may log in where. |
| `git.DOMAIN` | **Forgejo** | The **fleet repository**: one folder per computer, one file per profile. Changing a computer = changing a file here. |
| `cache.DOMAIN` | **Harmonia** | The server builds every computer's system and hands it out ready-made. |
| `fleet.DOMAIN` | **Fleet** (Redis) | Inventory: which computers exist, their health, their versions. |
| `tang.DOMAIN:7654` | **Tang** | Lets office desktops unlock their disks by themselves, only on the office network. |

Forgejo and Fleet share one database server, MySQL 8.4.

Every other computer runs MeccanicOS in **managed mode**. It:

- takes its configuration from the fleet repository and applies it within
  minutes (with comin), downloading the built system from the server;
- lets people log in with their organization account, also offline once
  they've logged in once;
- reports to Fleet;
- unlocks its disk with the TPM chip and a PIN (laptops), the TPM and the
  Tang server (office desktops), or a FIDO2 security key. A key is never sent
  over the network.

Every computer also has a **recovery key**, encrypted so that only the admins
can read it, stored in the fleet repository.

Who may log in, and where:

- **`fleet-admins`** (a Kanidm group): every computer, with `sudo`.
- **One group per profile**, with the profile's name (for example `office`):
  the computers of that profile.

## Before you start

You need:

- **A server**: any 64-bit PC with 8 GB of RAM or more and 100 GB+ of disk,
  on the office network, with a **fixed IP address** (ask whoever runs the
  router for a DHCP reservation).
- **A domain** the organization owns, here `corp.example.com`, and someone who
  can add **five DNS names** to it: `idm`, `git`, `cache`, `fleet`, `tang`, all
  pointing to the server.
- **Your own computer**, running MeccanicOS, on the same network.
- **A MeccanicOS USB stick**, made with `mos-usb` or Ventoy as usual. It
  carries the provisioning files to new computers.

Replace `corp.example.com`, `Example Corp` and `hq` with your own below.

---

# Part 1: the server

## 1.1 Install MeccanicOS on it

Install it from the stick as usual (normal install). Name it `hq`. Pick a
disk password and **write it down and keep it in a safe**: the server can't
unlock itself unattended (it's the one running Tang).

After the first login:

```sh
$ timedatectl | grep synchronized       # "System clock synchronized: yes"
$ ip -4 addr | grep inet                 # the fixed address
```

## 1.2 Set it up

```sh
$ mos-fleet server init --domain corp.example.com --organization "Example Corp" --lan 10.0.0.0/24
```

`--lan` is your office network (repeat it for several). Only computers there
can reach Tang. It asks for your password (sudo), then:

1. writes `/etc/nixos/fleet-server.toml` and rebuilds the system with the fleet
   services (the first time downloads about 1 GB; allow 10–30 minutes);
2. creates the organization's certificate authority and the server's
   certificate (`/var/lib/meccanicos-fleet/tls`), and makes the server trust it;
3. Kanidm: its administrators, and the group `fleet-admins`;
4. Forgejo: the repository `fleet/config`, an admin account, and a read-only
   account the computers use;
5. Fleet: its administrator and the enroll secret;
6. notes Tang's fingerprint and the cache's public key;
7. puts the first files in the fleet repository and pins the MeccanicOS version;
8. writes the **admin kit** (`/var/lib/meccanicos-fleet/kit.toml`), which your own
   computer fetches in Part 2.

It ends by printing **four passwords**: Kanidm `admin` and `idm_admin`,
Forgejo `fleet-admin` and Fleet `fleet-admin@corp.example.com`. Put them in
the company password manager. They're also in
`/var/lib/meccanicos-fleet/server-state.json`, readable only by root.

If it stops with an error, fix what it says and run the same command again:
every step is skipped when it's already done.

## 1.3 DNS

Ask for the five names (`idm`, `git`, `cache`, `fleet`, `tang` under your
domain) to point to the server's address. The server itself doesn't need
them; every other computer does.

## 1.4 Make yourself a fleet admin

```sh
$ mos-fleet person add mrossi "Mario Rossi" --group fleet-admins
$ mos-fleet person password mrossi
```

The first command prints a link: open it to set your password or passkey for
the web pages. The second sets the password for logging in to computers.

Check the server:

```sh
$ mos-fleet server status
```

Every line should say `ok`. `FAIL` on a service: `journalctl -b -u NAME`
says why.

---

# Part 2: your own computer

These commands run as yourself, on your MeccanicOS computer, not the
server.

```sh
$ mos-fleet connect you@hq
```

It copies the admin kit from the server over SSH, and clones the fleet
repository to `~/fleet`. It needs your SSH key on the server
(`ssh-copy-id you@hq`) and passwordless sudo there, which is the MeccanicOS
default.

The kit (`~/.config/mos-fleet/kit.toml`) holds the repository tokens and
the Fleet enroll secret: keep your computer's disk encrypted, as MeccanicOS
does.

```sh
$ mos-fleet admin-key
```

This makes your **admin key**, `~/.config/mos-fleet/admin.key`, and adds its
public half to `admins.txt` in the repository. Every computer installed from
now on encrypts its recovery key for all the keys in `admins.txt`.

**Back up `admin.key` now**, offline: print it (`cat`) and keep the paper in
the safe. Without at least one admin key, no recovery key can be read. Each
admin runs `connect` and `admin-key` on their own computer.

Then create a profile for each kind of computer:

```sh
$ mos-fleet profile add office
```

This adds `profiles/office.nix` to the repository and creates the Kanidm
group `office`. Edit `~/fleet/profiles/office.nix` to list the profile's
software, then `git commit -am "office: software"` and `git push`.

Check everything:

```sh
$ mos-fleet doctor
```

---

# Part 3: adding a computer

Per computer, decide three things:

| | Example | Choices |
|---|---|---|
| **Name** | `ws-001` | lowercase letters, digits, `-` |
| **Profile** | `office` | one made with `mos-fleet profile add` |
| **Disk unlock** | `tang` | `tang`: office desktop, unlocks by itself on the office network. `tpm-pin`: laptop, a PIN at power-on. `fido2`: a security key at power-on. |

## 3.1 (Optional) the disk's serial number

You can pin the installation to one disk, so that no other disk can be
erased by mistake. Boot the computer from the MeccanicOS stick, open a
terminal and run:

```sh
$ lsblk -d -o NAME,SIZE,MODEL,SERIAL
NAME     SIZE MODEL                SERIAL
nvme0n1  477G Samsung SSD 980 PRO  S6PNNF0R123456X
sda       29G USB Flash Disk       0412345678
```

The internal disk's serial is `S6PNNF0R123456X`. Without one, the installer
lets whoever installs pick the disk.

## 3.2 Prepare the stick

Plug the MeccanicOS stick into your computer:

```sh
$ mos-fleet prepare ws-001 --profile office --unlock tang --disk-serial S6PNNF0R123456X
```

It writes the folder `meccanicos/fleet/ws-001/` on the stick:
`corporate.config` and the files the installation needs. To use another
stick or folder, add `--to DIR`.

The stick now holds the repository token and the enroll secret: keep it
with you. The installer removes them from the stick when it's done.

## 3.3 Install

1. Connect the computer to the network. For `tang`, use a **network cable on
   the office network**.
2. Boot it from the stick and open **Install**. The installer finds
   `corporate.config` and offers **Organization install: ws-001 (office) for
   Example Corp**.
3. In the form, choose the language, keyboard and time zone, and Wi-Fi if
   there's no cable. For `tpm-pin`, set the **disk PIN**. The organization
   decides the name, the disk and the unlocking.
4. **Install now**, then type `YES`. First it checks it can reach every server.
   If one fails, nothing has been erased yet.
5. Unlocking:
   - `tang`: nothing to do;
   - `tpm-pin`: the PIN from the form;
   - `fido2`: plug in the security key and touch it when it blinks.
6. It downloads and installs the managed system. The very first computer
   takes longer: it compiles two small programs the server hasn't built yet.
7. At the end it writes `meccanicos/fleet/ws-001/result/` on the stick: the
   computer's own files and its recovery key, encrypted for the admins.

Reboot. The computer starts in managed mode: `fleet-admins` and the `office`
group can log in already.

## 3.4 Add it to the fleet

Back on your computer, with the stick:

```sh
$ mos-fleet add ws-001
```

It copies `result/` into the repository as `hosts/ws-001/`, checks that it
evaluates, commits, pushes, and clears the folder from the stick. Within
minutes the server builds it and the computer switches to its full
configuration (its profile and `common.nix`).

```sh
$ mos-fleet status ws-001
ws-001     build: ok 3f2a1c9     Fleet: online, seen 2026-10-12T14:03   NixOS 26.05
```

Then log in on it as a person in the `office` group.

---

# Part 4: everyday tasks

Everything that changes a computer is a change in the fleet repository
(`~/fleet`). `git log` shows who changed what, and when.

| Task | How |
|---|---|
| New person | `mos-fleet person add NAME "Full Name" --group office`, then `mos-fleet person password NAME` |
| Person leaves | `mos-fleet person remove NAME` |
| Let someone use a profile's computers | `mos-fleet member add office NAME` (`member remove` to undo) |
| A forgotten password | `mos-fleet person reset NAME` (a new setup link) |
| Software for a profile | edit `~/fleet/profiles/office.nix`, `git commit -am …`, `git push` |
| Software for everyone | edit `~/fleet/common.nix`, commit, push |
| Software for one computer | edit `~/fleet/hosts/NAME/local.nix`, commit, push |
| Move a computer to another profile | change `profile` in `~/fleet/hosts/NAME/fleet.toml`; also update its Kanidm group if needed |
| New MeccanicOS for everyone | `mos-fleet upgrade` |
| Try it on a few computers first | in their `hosts/NAME/fleet.toml`, set `branch = "testing"` under `[repo]` (commit, push); then `mos-fleet upgrade --testing`; when they're fine, `mos-fleet upgrade` |
| What runs where | `mos-fleet status`, or Fleet's web page |
| Retire a computer | `mos-fleet retire NAME`, and delete it in Fleet's web page |

Computers apply changes within minutes. A new kernel takes effect at the
next restart.

---

# Part 5: when something goes wrong

**A computer doesn't unlock its disk.** For example: a Tang desktop away
from the office, a broken TPM, or a lost security key. On your computer:

```sh
$ mos-fleet recover ws-001
```

It prints the recovery key: type it at the disk prompt.

**A computer doesn't take its configuration:**

```sh
$ mos-fleet status ws-001          # build failed? the error follows
$ journalctl -u comin -n 50        # on the computer: can it reach git.corp.example.com?
```

A bad commit is undone with `git revert COMMIT && git push`. A computer that
doesn't start after an update: pick the previous entry in its boot menu.

**A service on the server is down:** `mos-fleet server status`, then
`journalctl -b -u NAME` and `sudo systemctl restart NAME` on the server.

**The admin kit leaked** (a stolen, unlocked computer):

- In Forgejo, make new tokens for `fleet-reader` and `fleet-admin` and delete
  the old ones.
- In Fleet (Hosts > Manage enroll secret), make a new enroll secret.
- Put the new values in `/var/lib/meccanicos-fleet/server-state.json` on the
  server and run `mos-fleet server init` again with the same options.
- Each computer keeps its token in `/etc/secrets/meccanicos/repo.token`, and
  needs the new one there.

**Certificates:** the server's certificate renews itself 30 days before it
expires; the CA lasts 10 years.

---

# Part 6: backups

Back up the server every night (MeccanicOS's backup tool, or any other), in
particular these:

| What | Where | Why |
|---|---|---|
| Keys and certificates | `/var/lib/meccanicos-fleet/` | without the CA key no new certificates; without `cache.sec` computers refuse new systems. Also the passwords and the kit |
| Tang's keys | `/var/lib/tang/` | **without them, Tang computers never unlock by themselves again** (the recovery key still works) |
| People and groups | `/var/lib/kanidm/` | Kanidm also keeps daily backups there |
| The fleet repository | `/var/lib/forgejo/`, and its database dump in `/var/backup/mysql` | every admin's `~/fleet` is also a full copy |
| Fleet's inventory | its database dump in `/var/backup/mysql` | can be rebuilt (computers report again), history is lost |
| The server's own configuration | `/etc/nixos/` | |
| **Each admin's key** | `~/.config/mos-fleet/admin.key`, and the paper copy | **the only way to read recovery keys** |

---

# Appendix: what `mos-fleet` sets up, and where

For whoever wants to look under the hood, or fix things by hand.

**On the server** (module `modules/fleet-server.nix`, enabled by
`/etc/nixos/fleet-server.toml`):

- nginx terminates HTTPS for the four web names with the organization's CA.
- Kanidm runs on `127.0.0.1:8443`, Forgejo on `:3000`, Harmonia on `:5000`,
  and Fleet on `:8080` (with Redis). Forgejo and Fleet share MySQL 8.4: each
  has its own database, dumped nightly to `/var/backup/mysql`.
- Tang listens on port 7654, allowed from `--lan` and the server itself.
- `meccanicos-fleet-secrets` (at boot) creates the CA, the certificate, the
  cache key and Fleet's keys; `fleet-db-setup` creates Fleet's MySQL account.
- `fleet-build` runs every 5 minutes. It fetches the repository and builds
  each `hosts/NAME`, keeping the results for the cache. Each computer's
  result goes in `/var/lib/fleet-build/status/NAME`.
- `fleet-forgejo …` is Forgejo's command line. `fleetctl --config
  /var/lib/meccanicos-fleet/fleetctl.yml …` and `kanidm … -D idm_admin` are
  the others.

**On a managed computer** (module `modules/managed.nix`, enabled by
`/etc/nixos/fleet.toml`):

- **comin** polls the repository with `/etc/secrets/meccanicos/repo.token`.
- The **Fleet agent** (orbit, vendored from nixos-unstable) uses
  `/etc/secrets/meccanicos/fleet.secret`.
- **kanidm-unixd** provides logins and caches them for offline use.
- For `tang`, the boot stage brings up the wired network and Clevis opens
  `/etc/secrets/meccanicos/cryptroot.jwe`.
- MeccanicOS's own automatic updates are off: the repository's `flake.lock`
  decides the version.

**The fleet repository:**

```text
flake.nix          every folder in hosts/ is a computer
common.nix         every computer
profiles/NAME.nix  one per profile
hosts/NAME/        local.nix, hardware-configuration.nix, fleet.toml, ca.crt, recovery.age
retired/NAME/      retired computers (their recovery keys)
admins.txt         the admins' age public keys
```

**`corporate.config`** (written by `mos-fleet prepare`, read by the
installer):

```toml
version = 1
organization = "Example Corp"
hostname = "ws-001"
profile = "office"

[install]
disk_serial = "S6PNNF0R123456X"     # optional

[repo]
url = "https://git.corp.example.com/fleet/config.git"
branch = "main"
username = "fleet-reader"

[cache]
url = "https://cache.corp.example.com"
public_key = "cache.corp.example.com-1:…"

[fleet]
url = "https://fleet.corp.example.com"

[kanidm]
url = "https://idm.corp.example.com"

[unlock]
method = "tang"                     # tang | tpm-pin | fido2
tang_url = "http://tang.corp.example.com:7654"
tang_thumbprint = "…"
```

Next to it: `ca.crt`, `repo.token`, `fleet.secret` and `admins.txt`.

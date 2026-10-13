# MeccanicOS fleet management: design

> Experimental. How to use it: [ADMIN-GUIDE.md](ADMIN-GUIDE.md).

An organization runs many MeccanicOS computers and wants to manage them from
one place: who may log in where, what software each kind of computer has,
when everyone moves to a new MeccanicOS, what each computer is doing, and how
to open a disk whose owner lost the key.

NixOS already makes most of this a matter of files: a computer *is* its
configuration. So the design keeps everything an admin decides in **one git
repository**, and adds the least possible around it: **SSH** for every
connection, **Nix** to build each computer's system, **SQLite** for what the
computers report. No web services, no directory server, no extra databases.

(An earlier version used Kanidm, Forgejo, Harmonia, FleetDM, MySQL, Redis and
nginx. Each did its job well, but together they were a lot to run, secure,
upgrade and back up for what the fleet needs. This version replaces them.)

## 1. The jobs, and how each is done

| Job | How | Where |
|---|---|---|
| Who the computers, profiles, people and groups are | the fleet repository: TOML files and NixOS modules | `hosts/`, `profiles/`, `people/`, `groups.toml`, `fleet.toml` |
| What each computer runs | `meccanicos.lib.mkFleet`: one NixOS system per `hosts/NAME`, built by the server from the branch it follows | `flake.nix`, `mos-fleet-build` |
| Getting it there | the agent fetches exactly that system's missing store paths over SSH, then switches | `agent.py`, `server.py` (`fetch`) |
| People and their rights | declarative users (`users.mutableUsers = false`): on each computer, the people whose groups allow its profile; sudo by group | `managed.nix` |
| Passwords | hashes only, in `secrets.db`; delivered to the computers where the person may log in (`hashedPasswordFile`); `mos-passwd` changes one's own everywhere, proving the current one | `server.py`, `agent.py` |
| Inventory, health, logs | facts, journald (warnings and up, plus chosen units), deployments, in `state.db` | `agent.py`, `server.py` |
| Remote actions | jobs (run, reboot, switch, facts), delivered at once on the open session; `shell` relays SSH end to end | `server.py`, `agent.py` |
| Disk unlock and recovery | LUKS2 with Tang (+TPM), TPM+PIN or FIDO2; a systemd-cryptenroll recovery key encrypted with age for the admins, in `secrets.db` | `mos-install`, `managed.nix` |
| Enrollment | a one-time SSH key on the stick, 7 days; the computer sends its host key, hardware configuration and recovery key; an admin adds it to the repository | `host prepare`, `enroll`, `host add` |
| Audit | git history; `audit` table (pushes, jobs, passwords, recovery reads, enrollments) | `state.db` |

## 2. Architecture

```
 admin's computer                      fleet server (hq)                      managed computer
 ───────────────                      ──────────────────                     ────────────────
 ~/fleet (git)  ── git push ──▶  sshd ─ fleet.git ─ hooks: validate,        mos-fleet-agent
 mos-fleet      ── ssh fleet@ ─▶  │      refresh keys, trigger build         (its host key)
   status, logs, run, shell …     │                                              │
                                  ├─ mos-fleet-keys: which key is whom ◀─── ssh fleet@hq session
                                  ├─ mos-fleet-serve host|admin|enroll        facts, logs, results ─▶
                                  │                                        ◀─ desired system, hashes, jobs
                                  ├─ mos-fleet-build (as fleet, nix build)    ssh fleet@hq fetch
                                  │     git+file://fleet.git?ref=…#ws-001  ─▶ nix-store --export of the
                                  ├─ state.db   secrets.db                    missing paths of its system
                                  └─ Tang (port 7654, office network)    ◀─── initrd: clevis (Tang + TPM)
```

**One account, forced commands.** sshd runs `mos-fleet-keys` as its
`AuthorizedKeysCommand` for the account `fleet`. It answers from `keys.json`,
which the server writes from the newest *valid* `main` branch: each admin's
keys (people in `fleet-admins`), each computer's host key, and pending
one-time enrollment keys. The answer is an authorized_keys line with
`restrict` and a forced command naming the role and the name
(`mos-fleet-serve host ws-001`): the client can't choose who it is, and gets no
shell, terminal or forwarding. A key at the console (`server admin-key`) is
valid for a day and may only push the repository.

**The repository is only written by admins.** The pre-receive hook checks
every pushed commit with the same rules as `mos-fleet validate`
(`repo.py`), refuses deleting or rewriting `main`, and records the push. The
post-receive hook refreshes `main/`, the computer table and `keys.json`, and
touches a file a systemd path unit watches: `mos-fleet-build` starts. It
also runs every 10 minutes, and loops while new pushes arrive.

**Builds.** As the unprivileged user `fleet`, `nix build
git+file:///var/lib/mos-fleet/fleet.git?ref=BRANCH&rev=REV#nixosConfigurations.HOST…`,
for each computer from the branch its `host.toml` names (`main`, or `testing`
for canaries). The result is kept as a GC root and becomes that computer's
*desired system*. A failed build is recorded; the computer stays on the
previous one.

**Deploying.** The agent's session receives the desired system's store path.
It asks `fetch` for it: the server checks it's that computer's desired system,
lists its closure, the agent says which paths it lacks, and the server
streams them (`nix-store --export`). Nothing else on the server can be asked
for. The agent imports them (as root: no signature needed; the SSH channel
authenticates the server), sets the system profile and switches, in a
separate systemd unit so restarts can't interrupt it, then reports and
restarts itself (the new system may carry a new agent).

**The protocol.** One JSON object per line, both ways, on the session's
stdin/stdout, with size caps: `hello`, `facts`, `logs` (acknowledged by
cursor, so nothing is lost or sent twice), `deploy`, `job-done`, `passwd` from
the agent; `desired`, `passwords`, `job`, `logs-ok`, `passwd-result`, `bye`
from the server. The server's end polls SQLite every second for new jobs,
builds and password changes.

**The shell.** `mos-fleet shell ws-001` runs `ssh mrossi@ws-001` with a
ProxyCommand that opens `relay` on the server. The server queues a relay job
with a random token, the computer connects back with it, and the server joins
the two streams. SSH runs end to end: the admin authenticates to the computer
with their own key (from `people/`), and checks its host key (from
`hosts/`). The server only sees encrypted bytes.

## 3. Data

**The repository** (`repo.py` has the rules; `mkFleet` reads the same files):
`fleet.toml`, `groups.toml`, `people/*.toml`, `profiles/*.nix`,
`hosts/*/host.toml` (+ the computer's own `.nix` files), `common.nix`,
`flake.nix`/`flake.lock`. Strict: unknown keys, duplicate uids/gids/keys,
groups or profiles that don't exist, or no admin with an SSH key and an age
key: refused.

**state.db** (pydal, SQLite in WAL mode): `host` (profile, branch, last seen,
current and desired system), `revision`, `build`, `deployment`, `report`
(facts), `log`, `job`, `session`, `audit`, `enrollment`. Rebuilt by itself
from the repository and the next check-ins, except logs and history.

**secrets.db**: `password` (hashes: yescrypt or SHA-512), `recovery_key`
(age ciphertext; confirmed once `hosts/NAME` has the same host key),
`passwd_attempt`.

Both belong to `fleet`, mode 600; root's commands use them through
`runuser -u fleet` so no file becomes root's. `mos-fleet server backup` takes
consistent copies (SQLite's backup API) and a bundle of the repository.

## 4. Security

- **Authentication** is SSH keys only, both ways: computers and admins know
  the server's key from `fleet.toml` (checked against the fingerprint the
  console printed, at `init`/`clone`); the server knows theirs from the
  repository.
- **Least privilege per key**: a computer gets its own session, its own
  system's paths, its own people's hashes, its own jobs. One-time keys enroll
  one computer once. Builds run as an untrusted Nix user.
- **Passwords**: never sent by computers; a change needs the current
  password, checked on the server against the stored hash; 5 wrong ones an
  hour lock changes for that person (an admin's `password set` unlocks).
  A computer only receives the hashes of people allowed on it, and drops the
  rest.
- **Recovery keys** are age-encrypted on the new computer for the admins'
  keys; the server never sees them in clear. `recover` decrypts on the admin's
  computer.
- **What the stick carries** is a settings file, the admins' public keys and a
  one-time key: no long-lived secret. The installer pins the server's key and
  shows the new computer's fingerprint for the admin to compare at `host add`.
- **Trust**: the server decides what every computer runs; whoever controls it
  (or the repository's admins) controls the fleet. Keep it physically safe and
  its disk encrypted. `audit` and git history say who did what.

## 5. Known limits

- No web pages: no self-service password reset, no dashboards (a read-only
  page over `state.db` would be easy to add). No passkeys yet: FIDO2 logins
  (pam_u2f) and a web login are planned for later versions.
- Removing a person takes effect as each computer next connects; an offline
  laptop keeps them until then.
- Hashes in `secrets.db` and logs in `state.db` make the server a valuable
  target: its backups too.
- One server: no failover. Computers keep working without it (their last
  system, their people, their passwords); they just don't change.
- Tested end to end in VMs (`tests/fleet.nix`), not yet on real hardware with
  Tang, TPMs and FIDO2 keys.

## 6. The files

| File | What |
|---|---|
| `scripts/mos_fleet/repo.py` | the repository's rules |
| `scripts/mos_fleet/server.py` | sessions, fetch, relay, enroll, admin commands, hooks, builds |
| `scripts/mos_fleet/keys.py` | sshd's AuthorizedKeysCommand |
| `scripts/mos_fleet/agent.py` | the agent, `mos-passwd` |
| `scripts/mos_fleet/admin.py`, `console.py`, `cli.py` | `mos-fleet` |
| `scripts/mos_fleet/defaults.toml`, `settings.py` | settings, overridable |
| `modules/fleet-server.nix` | the server: account, sshd, services, Tang |
| `modules/managed.nix` | a managed computer: agent, people, disk unlock |
| `modules/fleet-config.nix` | `/etc/mos-fleet/config.toml` |
| `modules/mos-fleet-package.nix` | the commands |
| `flake.nix` (`mkFleet`) | a fleet repository's systems |
| `scripts/mos-install.py` | the organization install |
| `tests/fleet.nix`, `tests/fleet/` | the VM test |

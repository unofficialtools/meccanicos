# `mos-fleet web`: a web UI for the fleet (design)

> Status: **design, not implemented.** The fleet itself: [DESIGN.md](DESIGN.md),
> [ADMIN-GUIDE.md](ADMIN-GUIDE.md).

A browser front end to what `mos-fleet` already does: search and edit people,
groups, profiles and computers; see status, builds, deployments and logs;
run the existing actions from buttons and forms. Built with **py4web** and
**Vue 3**.

## Decisions

- **One command:** `mos-fleet web [--port 8765]`. It prints a URL with a
  one-time token and opens it in the browser.
- **Localhost only, always.** It binds to `127.0.0.1`, hard-coded: no
  `--host` option and no setting in `config.toml`. If it can't bind there, it
  stops; it never falls back to another address. From another machine, it is
  reached through SSH only:
  `ssh -L 8765:127.0.0.1:8765 my-laptop`, then the printed URL.
- **It runs where an admin's clone of the fleet repository is**, normally the
  admin's own computer, as that admin: their SSH key (and agent), their
  `~/.config/mos-fleet/admin.key`, their git identity. On the fleet server it
  would run only under a normal admin account with its own clone, never as
  the `fleet` account: **the server still never commits**.
- **No browser terminal.** A computer's page shows the `mos-fleet shell NAME`
  command to copy.
- Nothing new on the server's side but JSON output for a few commands: the
  `fleet` account keeps no shell, no forwarding.

## Security

- Bound to `127.0.0.1` only (above); the VM test checks nothing listens
  elsewhere.
- **A random token** in the printed URL, exchanged for an `HttpOnly`,
  `SameSite=Strict` cookie: other users of the same computer can't use it.
- Every API call needs the cookie **and** a custom header (`X-Mos-Fleet: 1`):
  no cross-site requests. The `Host` header must be `127.0.0.1:PORT` or
  `localhost:PORT` (no DNS rebinding). No CORS. A strict Content-Security-Policy.
- **No third-party scripts:** Vue and CodeMirror are pinned files shipped with
  the package and served locally; it works offline.
- Refuses to run as root.
- Secrets: a new password is hashed in memory (yescrypt) and only the hash
  leaves, as with `mos-fleet password set`; nothing is stored. A recovery key
  is shown only on demand, after a confirmation, and hidden again after a
  minute; it is decrypted locally with the admin key, as `mos-fleet recover`.
- Every action reaches the server through the same forced commands as the
  CLI, so `mos-fleet audit` records it the same way.

## Architecture

```
browser (Vue 3, no build step)  ⇄  py4web on 127.0.0.1  ⇄  mos_fleet library
                                                            ├─ the local clone (~/fleet): Repo, Change → validate, commit
                                                            └─ the server: ssh fleet@SERVER … --json
```

- **One library, two front ends.** The logic of `scripts/mos_fleet/admin.py`
  moves into functions that return data (`mos_fleet/ops.py`); the CLI prints
  their results, the web API returns them as JSON. They can't drift apart.
- **JSON from the server:** `status` has `--json` already; `logs`, `builds`,
  `deployments`, `jobs`, `job`, `audit` and `enroll-list` get it too.
- **Edits** go through the same `Change` transaction as the CLI: write the
  files, check the repository (`repo.py`), commit, or put everything back.
  Nothing reaches the server until **Push**.
- **Long jobs** (validate with the Nix evaluation, push, upgrade, host
  prepare) run in a background thread, one at a time, holding the
  repository's lock; the browser polls their progress.
- **Living with git and the CLI:** every edit re-reads the files. If the clone
  has uncommitted changes the UI didn't make, it shows them and refuses to
  edit (as `mos-fleet upgrade` does).
- Server answers are cached for a few seconds; logs are polled incrementally
  (by id).

## Screens

| Screen | Shows | Actions (the existing commands) |
|---|---|---|
| **Dashboard** | computers online/offline and their states, failed builds, pending enrollments, unpushed commits | **Push**, after a `diff` preview |
| **Computers** | search and filters (profile, branch, state, online), table | — |
| one computer | facts (disks, addresses, OS, kernel), current and desired revision, deployments, builds with their logs, its logs (polled; unit, priority, since) | Run a command (`run`), Reboot, Switch, Facts; profile and branch (`host set`); Retire (`host retire`); Recovery key (`recover`); the `mos-fleet shell` command to copy |
| **Add a computer** | the prepare form; computers that introduced themselves | `host prepare` (to the stick, or a folder); `host add`, with a dialog to compare the fingerprint with the installer's |
| **People** | search; where each may log in (computed), with sudo or not | add and edit (groups, SSH keys pasted or from a file, age recipient), disable, enable, remove; **Set password** (`password set`) |
| **Groups** | gid, profiles, sudo, members | `group add/edit/remove`, `member add/remove` |
| **Profiles** | each one's computers and groups | add, remove; edit the `.nix` in CodeMirror, Validate, Commit |
| **Changes** | unpushed commits, per-computer `diff`, `git log` | Validate (with Nix), Push, Upgrade (`--testing`, or everyone) |
| **Audit** | `mos-fleet audit`, filtered | — |

## API

JSON, one route per command:

```
GET    /api/hosts                         status of every computer
GET    /api/hosts/{h}                     one computer: facts, builds, deployments
GET    /api/hosts/{h}/logs?unit=&priority=&since=&after_id=
POST   /api/hosts/{h}/run | reboot | switch | facts | retire
PATCH  /api/hosts/{h}                     profile, branch, unlock (host set)
POST   /api/hosts/prepare                 host prepare
GET    /api/enrollments                   host pending
POST   /api/hosts/{h}/add                 host add
POST   /api/hosts/{h}/recover             the recovery key (decrypted locally)
GET    /api/people          POST /api/people
PATCH  /api/people/{p}      DELETE /api/people/{p}
POST   /api/people/{p}/password
GET    /api/groups          POST /api/groups
PATCH  /api/groups/{g}      DELETE /api/groups/{g}
POST   /api/groups/{g}/members            member add / remove
GET    /api/profiles        POST /api/profiles      DELETE /api/profiles/{p}
GET    /api/profiles/{p}/nix              PUT /api/profiles/{p}/nix
GET    /api/changes                       unpushed commits and their diff
POST   /api/validate | push | upgrade     long jobs: return a task id
GET    /api/tasks/{id}                    a long job's progress and output
GET    /api/audit
```

## Packaging

- **py4web is not in nixpkgs** (pydal is), nor are its own dependencies
  `ombott` and `yatl`: a small `modules/py4web.nix` builds them from PyPI,
  pinned, into `mos-fleet-package.nix`'s Python.
- Vue 3 and CodeMirror: pinned files fetched at build time with their hashes,
  served from the package.
- The app lives in `scripts/mos_fleet/web/` (py4web app: controllers,
  templates, static).

## Tests

The fleet VM test (`tests/fleet.nix`) grows a subtest: on the admin VM, start
`mos-fleet web`, then:

- nothing listens on any address but `127.0.0.1`;
- requests without the token, without the header, or with another `Host` are
  refused;
- the API lists the computers and returns `ws1`'s status and logs;
- a person added through the API is committed and, after Push, reaches `ws1`.

## Phases

1. **Read-only:** dashboard, computers, logs, people, groups, profiles,
   audit; the library refactor (`ops.py`) and the server's `--json` outputs.
2. **Edits:** people, groups, profiles (with the editor), Validate, Push,
   `diff`.
3. **Actions:** run, reboot, switch, prepare and add computers, recovery
   keys, upgrade.
4. **Later:** charts from `state.db`'s history.

Not planned: a browser terminal; listening on anything but localhost.

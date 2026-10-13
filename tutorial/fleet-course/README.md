# Running a fleet of MeccanicOS computers

A 16-minute video of [the fleet admin guide](../../docs/fleet/ADMIN-GUIDE.md),
made with [Remotion](https://www.remotion.dev) (React → video) and narrated
offline by Piper. It shares its framework with [the shell course](../shell-course/).

| | Chapter | On screen |
|---|---|---|
| | Welcome | why manage computers from one place; why NixOS makes it easier; git, SSH, Nix, SQLite |
| 1 | The big picture | the network map: Example Corp, the server hq (one SSH account, the repository, builds, two databases, Tang), three computers keeping a connection open; the repository's files; groups |
| 2 | Before you start | a server with a name, your computer with an SSH key, a stick |
| 3 | The server | your key on the stick; `mos-fleet server init`; `server status` |
| 4 | The repository | `init` (the fingerprint, your admin key, the first push), `profile add`, `person add`, `validate`, `push`; what the server refuses |
| 5 | Adding computers | LUKS and the ways to unlock it (Tang, TPM + PIN, FIDO2, recovery key); `host prepare`, the installer, the one-time key, `host add` (compare the fingerprint); three computers |
| 6 | Every day | a change flows from a commit to every computer; passwords (`password set`, `mos-passwd`); `run`, `logs`, `shell`; `upgrade --testing`; `retire` |
| 7 | When something goes wrong | `recover`, failed builds, `git revert`, the boot menu, a key at the console |
| 8 | Backups, and safety | `server backup`, the admin key on paper; one job per key; `audit` |
| | Cheat sheet | the `mos-fleet` commands |

## Make it

```sh
npm install
npm run voice      # Piper reads every scene (public/audio/), timings in src/durations.json
npm run studio     # preview in the browser, scene by scene
npm run render     # out/fleet-course.mp4
```

`npm run voice` needs `piper` and `PIPER_VOICE` (both set on MeccanicOS).
Rendering uses the system's Brave or Chromium (`remotion.config.ts`).

## Change it

Everything said and shown is in `src/script.tsx`, one entry per scene, as in
the shell course (`text`, `say`, `visual`; `|` splits the narration into
beats). Visuals specific to this video:

- `net({...})`: the network map (`src/components/Net.tsx`): which computers
  are there or appear (`show`, `add`), what lights up (`hi`), the packets
  sent between them (`flows`, e.g. `{ from: "build", to: "ws1", label: "system", beat: 1 }`)
  and labels on them (`tags`);
- `vaults([...])`: an encrypted disk and the way it unlocks
  (`src/components/Vault.tsx`: `password`, `tang`, `tpm-pin`, `fido2`,
  `recovery`; `fail: true` stays locked);
- `term(host, [...])`: a terminal on `hq`, `me` (your computer), `live`
  (a new computer started from the stick) or `ws2`; a callout says which
  computer it is, another one what each new command does (`src/commands.ts`);
- `<Installer>`: mos-install's organization mode.

The logos are the projects' own, from [simple-icons](https://simpleicons.org)
(git, NixOS, SQLite, in a lighter blue); SSH and Tang have none: they are
drawn (a terminal, a key).

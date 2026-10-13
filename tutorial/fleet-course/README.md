# Running a fleet of MeccanicOS computers

A 16-minute video of [the fleet admin guide](../../docs/fleet/ADMIN-GUIDE.md),
made with [Remotion](https://www.remotion.dev) (React → video) and narrated
offline by Piper. It shares its framework with [the shell course](../shell-course/).

| | Chapter | On screen |
|---|---|---|
| | Welcome | why manage computers from one place; why NixOS makes it easier |
| 1 | The big picture | the network map: Example Corp, `corp.example.com`, the server hq and its services, three computers; how information flows |
| 2 | Before you start | a server, a domain and five DNS names, your computer, a stick |
| 3 | The server | `mos-fleet server init`, a fleet admin, `server status` |
| 4 | Your computer | `connect`, `admin-key`, `profile add`, `doctor` |
| 5 | Adding computers | LUKS and the ways to unlock it (Tang, TPM + PIN, FIDO2, recovery key); `prepare`, the installer, `add`; three computers |
| 6 | Every day | a change flows from a commit to every computer; people; `upgrade`; `retire` |
| 7 | When something goes wrong | `recover`, failed builds, `git revert`, the boot menu, the server's services |
| 8 | Backups | what to keep |
| | Cheat sheet | every `mos-fleet` command |

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
  sent between them (`flows`, e.g. `{ from: "cache", to: "ws1", label: "system", beat: 1 }`)
  and labels on them (`tags`);
- `vaults([...])`: an encrypted disk and the way it unlocks
  (`src/components/Vault.tsx`: `password`, `tang`, `tpm-pin`, `fido2`,
  `recovery`; `fail: true` stays locked);
- `term(host, [...])`: a terminal on `hq`, `me` (your computer), `live`
  (a new computer started from the stick) or `ws2`; a callout says which
  computer it is, another one what each new command does (`src/commands.ts`);
- `<Installer>`: mos-install's organization mode.

The logos are the projects' own: Kanidm's (`public/logos/kanidm.png`, from
its repository's artwork), Fleet's (`public/logos/fleet.png`), and the
others from [simple-icons](https://simpleicons.org). Tang and comin have
none: they are drawn (a key, two arrows).

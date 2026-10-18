# Running a fleet of MeccanicOS computers

A short video (about 5 minutes) on [running a fleet](../../docs/fleet/ADMIN-GUIDE.md),
made with [Remotion](https://www.remotion.dev) (React → video) and narrated
offline by Piper. It shares its framework with [the shell course](../shell-course/).

Little talking, in four parts:

| | Part | On screen |
|---|---|---|
| | Start | the MeccanicOS logo, its tagline, the title |
| 1 | What it is | one slide: what it's for, who it's for, how it keeps the computers safe |
| 2 | What it does | animations, in plain words: the server and its computers, a change reaching every computer, passwords, a new computer, encrypted disks, undoing a mistake |
| 3 | Setting it up | the commands, on slides to read (not read aloud), each with a note: the server, each new computer, every day; then `mos-fleet` full screen (the TUI's screenshots) |
| 4 | Advanced features | a list, for experienced admins: staged rollouts, remote operations, disk encryption, troubleshooting, access model, audit and backup |

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
beats; `tail` holds a slide after the voice, to read it). Visuals specific to
this video:

- `net({...})`: the network map (`src/components/Net.tsx`), in plain words:
  which computers are there or appear (`show`, `add`), what lights up (`hi`),
  the packets sent between them (`flows`, e.g. `{ from: "build", to: "ws1", label: "new system", beat: 2 }`)
  and labels on them (`tags`);
- `vaults([...])`: an encrypted disk and the way it unlocks
  (`src/components/Vault.tsx`: `password`, `tang`, `tpm-pin`, `fido2`,
  `recovery`; `fail: true` stays locked);
- `recipe(title, rows)`: a slide of commands (`src/components/Recipe.tsx`):
  where each runs (the server, your computer, the new computer), the command
  or a step done by hand, and a note on what it does;
- `<Cover>`: the first slide, with the logo (`branding/logo`, `public/logo`
  links there);
- `<Screens>`: screenshots, one per segment: `docs/fleet/tui/*.png`
  (`public/tui` links there).

The logos are the projects' own, from [simple-icons](https://simpleicons.org)
(git, NixOS, SQLite, in a lighter blue); SSH and Tang have none: they are
drawn (a terminal, a key).

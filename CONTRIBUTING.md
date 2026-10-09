# Contributing

Thanks for helping! A few notes to keep MeccanicOS easy to build and trust.

- **Build & test before a PR**
  ```bash
  nix flake check --no-build          # evaluates everything (fast)
  shellcheck -S warning scripts/*.sh
  nix build -L .#checks.x86_64-linux.live      # VM test (needs KVM, slow)
  nix build -L .#checks.x86_64-linux.install   # VM test (needs KVM, slow)
  ```
- **Where things live:** one concern per file in `modules/`; scripts in `scripts/`;
  user-editable package list in `packages.nix`.
- **Offline first:** anything on the ISO must work without a network.
- **Licensing:** every ISO must be freely redistributable. If you add something
  unfree, check that its `meta.license` allows redistribution; if not, pick a
  free alternative.
- Code is BSD-3-Clause (see `LICENSE`).

## Releasing (maintainers)

Everything people download comes from GitHub: the README, the web page and
`scripts/get-iso.*` all point at the release tagged **`latest`**
(`releases/download/latest/…`). A release holds the ISO in parts under 2 GB
(`<iso>.part01…`), the five `mos-usb-*` programs, and `SHA256SUMS`; it is
published twice, under a dated tag (`v2026-10-09`) and again as `latest`.
The web page, meccanicos.com, is `www/`, copied there by hand.

In order (the tutorial and the translations are built into the ISO, so they
come before it):

1. **Checks:** `shellcheck -S warning scripts/*.sh`, `pyflakes scripts/*.py`,
   `tools/i18n.py check` (translations: every text, placeholders, commands
   unchanged), `nix flake check --no-build`.
2. **Tutorial** (when the tour or the desktop changed): `./start tutorial-video`
   → `tutorial/tutorial.mp4` (`www/tutorial.mp4` links to it). Commit it.
3. **ISO:** `./start iso` → `dist/meccanicos-26.05-<date>-x86_64-linux-<hash>.iso`.
4. **Screenshots** for the web page (when a tool's look changed): `./start www`
   → `www/screenshots/`. Commit them.
5. **Push** `main` (the release points at `origin/main`).
6. **Publish:** `./start release [TAG]`. It does what
   [`release.yml`](.github/workflows/release.yml) does in CI: splits the ISO
   into `dist/release/`, builds `mos-usb` for every system, writes
   `SHA256SUMS` and `dist/notes.md`, creates the release `TAG` (default
   `v<today>`; if that exists, use e.g. `v2026-10-09.2`), then deletes and
   re-creates `latest` with the same files. Needs `gh` logged in.
   (Instead, pushing a tag `v…` makes the Release workflow build and publish
   in CI; it skips a tag that already has a release.)
7. **Web page:** copy `www/` to meccanicos.com (by hand), and check that
   meccanicos.com and the `latest` downloads work.

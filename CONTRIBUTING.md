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

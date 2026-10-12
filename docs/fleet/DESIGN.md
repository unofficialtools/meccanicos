# MeccanicOS fleet management: design

> **⚠ Experimental** (October 2026). Implemented, not yet tested on real
> hardware or in a real organization. How to use it: [ADMIN-GUIDE.md](ADMIN-GUIDE.md).

**The idea:** an organization runs MeccanicOS on every computer, servers
included, and manages them from one place. MeccanicOS doesn't write its own
fleet server, key server, update protocol or user directory. It wires
together **standard, maintained tools**, all NixOS services:

- **Kanidm** for people;
- **comin** and a binary cache for configuration;
- **Tang/Clevis**, the TPM and FIDO2 for disk unlocking;
- **Fleet** for inventory.

The MeccanicOS part is the glue: two NixOS modules, an organization mode in
the installer, and the `mos-fleet` command.

## 1. The jobs, and the tool for each

| Job | Tool | MeccanicOS piece |
|---|---|---|
| People, groups, who may log in where | **Kanidm** (`services.kanidm`): passwords, passkeys, POSIX groups, offline login cache | `managed.nix` (client), `fleet-server.nix` (server), `mos-fleet person/group/member` |
| sudo and other rights | NixOS configuration in the fleet repository, keyed on Kanidm groups | `fleet-admins` everywhere with sudo; one group per profile |
| Configuration and upgrades | **comin** pulls a Git repository (Forgejo); **fleet-build** builds every computer into a **Harmonia** cache signed with a Nix key | `managed.nix`, `fleet-server.nix`, `mos-fleet profile/add/upgrade` |
| Disk unlock without typing the disk password | **TPM2 + PIN**, **Tang + TPM2** (Clevis), **FIDO2** key | the installer's organization mode |
| Disk recovery | systemd-cryptenroll's **recovery key**, encrypted with **age** for the admins, in the repository | the installer; `mos-fleet recover` |
| Inventory, health | **Fleet** (osquery/orbit), MySQL 8 + Redis | `managed.nix` (agent), `fleet-server.nix`; `mos-fleet status` |
| Audit | Git history of the repository, Fleet's activity log, Kanidm's log | |

## 2. How other systems do it

| | Enrollment / inventory | Disk keys | Config / updates | Identity |
|---|---|---|---|---|
| **Windows**: Intune + Autopilot | The vendor registers the hardware ID | BitLocker: TPM, recovery key escrowed in Entra | Policies, update rings | Entra ID |
| **macOS**: Jamf, Kandji, Intune | Apple Business Manager | FileVault recovery key escrowed | Config profiles, OS update deadlines | Entra, Okta, LDAP |
| **ChromeOS**: Google Admin | Enroll once, cloud managed | Automatic, TPM-backed | Policies, staged updates | Google accounts |
| **RHEL / Fedora**: Satellite or Foreman + IdM | Kickstart, `ipa-client-install` | **Clevis + Tang**, TPM2 | Content views, Ansible | FreeIPA |
| **Ubuntu**: Landscape | Registration key, admin approves | Nothing built in | Package updates, scripts | AD/LDAP via SSSD |
| **SUSE**: Uyuni / SUSE Manager | Bootstrap + Salt keys | Nothing built in | Salt states, patching | Varies |
| **Fleet** (open source) | Enroll secret; Linux, macOS, Windows, NixOS | LUKS escrow on Ubuntu/Fedora (NixOS planned) | Scripts, policies | Through an identity provider |
| **MeccanicOS fleet** | `corporate.config` on the stick, Fleet enroll secret | Tang+TPM / TPM+PIN / FIDO2; age-encrypted recovery key | comin + signed cache, Git as the source of truth | Kanidm |

What these systems have in common, and MeccanicOS follows:

- **The disk key never travels.** The TPM, or Tang, opens the disk. Tang's
  server and the client *derive* the key together: the server never learns
  it, so a stolen Tang server unlocks nothing. Only a recovery key is kept
  aside, for emergencies.
- **Configuration is built once and shipped built.** On NixOS that means a
  binary cache signed with a Nix key. Each computer switches to that exact
  system, with the previous one still in the boot menu.

## 3. Architecture

```
            fleet repository (Forgejo)  ──fleet-build──▶  Harmonia cache (signed)
            hosts/*, profiles/*.nix                          │
                  ▲  pull (comin)                            │  download
  ┌───────────────┴──────────────────────────────────────────┴──────┐
  │ managed MeccanicOS computer   (/etc/nixos/fleet.toml)            │
  │   comin ........... switches to nixosConfigurations.<hostname>   │
  │   orbit ........... inventory                                    │──▶ Fleet
  │   kanidm-unixd .... logins and groups, cached for offline use   │──▶ Kanidm
  │   boot stage ...... LUKS: TPM2+PIN | Tang+TPM2 | FIDO2          │──▶ Tang (LAN)
  └──────────────────────────────────────────────────────────────────┘
```

All boxes on the right run on one MeccanicOS server
(`/etc/nixos/fleet-server.toml`).

### 3.1 People: Kanidm

Kanidm has first-class NixOS support: `services.kanidm` sets up the server,
the admin client and `kanidm-unixd`, which provides PAM/NSS on each computer.

- **Offline logins:** `kanidm-unixd` caches users, groups and credentials for
  laptops away from the office, protected by the TPM when there is one.
- **Who may log in:** `pam_allowed_login_groups` = `fleet-admins`, plus the
  computer's profile group, plus `meccanicos.managed.loginGroups`.
- **Names:** `uid_attr_map = "name"`, so people are `mrossi`, not
  `mrossi@idm.corp.example.com`.
- **sudo:** Kanidm has no sudo rules. MeccanicOS gives `fleet-admins` sudo
  everywhere; anything finer goes in the repository
  (`security.sudo.extraRules`).
- **Versions:** nixpkgs carries versioned Kanidm packages because Kanidm must
  be upgraded one minor version at a time. MeccanicOS pins `kanidm_1_11`, the
  newest in its nixpkgs.
- **Not FreeIPA:** FreeIPA isn't packaged for NixOS and is only supported on
  Fedora/RHEL, but every machine here runs MeccanicOS. Giving up FreeIPA means
  giving up Kerberos (Kerberized file shares). If that's ever needed, the
  fallback is NixOS's own Kerberos server, not FreeIPA.

### 3.2 Disk unlock and recovery

| Computer | Day to day | How the installer sets it up |
|---|---|---|
| Office desktop (`tang`) | By itself, only on the office network and only in its own case | A random LUKS key, sealed with `clevis encrypt sss` to Tang **and** the TPM (`t=2`; Tang alone if there's no TPM), in `/etc/secrets/meccanicos/cryptroot.jwe`. NixOS's `boot.initrd.clevis` opens it, after the boot stage brings up the wired network. |
| Laptop (`tpm-pin`) | A PIN at power-on | `systemd-cryptenroll --tpm2-with-pin` (PCR 7) |
| Anything (`fido2`) | A security key at power-on | `systemd-cryptenroll --fido2-device` |

On every computer the installer also does two things:

- It enrolls a **recovery key** (`systemd-cryptenroll --recovery-key`) and
  encrypts it with `age` for every public key in `admins.txt`. The encrypted
  copy goes to `hosts/<name>/recovery.age`; the plain key is never written to
  any disk.
- It removes the temporary key the disk was formatted with. After that, only
  the methods above and the recovery key open the disk.

Fleet will escrow LUKS keys on NixOS too ([fleetdm/fleet#54422][54422],
planned for 5.3.0, Fleet Premium). It could replace the age-encrypted files
then, but they work without Premium and without Fleet.

### 3.3 Configuration: comin, fleet-build, Harmonia

The fleet repository is a flake: `meccanicos.lib.mkInstalled` for every folder
in `hosts/`. Each folder holds what the installer wrote into that computer's
`/etc/nixos`, so its configuration in the repository is exactly what it ran
locally, plus `common.nix` and its profile.

- **comin** (vendored as a flake input; its module is imported from its
  source) polls the repository and switches to
  `nixosConfigurations.<hostname>`. It authenticates with a read-only Forgejo
  token.
- **fleet-build** (on the server, every 5 minutes) builds every host. The
  results are kept as GC roots, so Harmonia serves them, signed with the
  server's Nix key.
- MeccanicOS's own automatic updates are off on managed computers: the
  repository's `flake.lock` pins the MeccanicOS version, and
  `mos-fleet upgrade` moves it.
- **Staged rollouts:** a computer whose `fleet.toml` says
  `branch = "testing"` follows that branch.

### 3.4 Inventory: Fleet

- **Agent:** orbit with osquery. Its NixOS module and package exist only in
  nixos-unstable, so they're vendored in `modules/vendor/` (fleet-orbit 1.55.0
  with nixpkgs' NixOS patches). Drop the copies when MeccanicOS's nixpkgs has
  them.
- **Server:** `fleet serve` as a systemd service, with MySQL 8.4 and Redis.
  Fleet supports neither PostgreSQL nor MariaDB, so NixOS's `services.mysql`
  is given `pkgs.mysql84`. Forgejo, the only other service with a database,
  supports MySQL too and uses the same server: one database server to run
  and back up.

### 3.5 The server

| Service | NixOS | Behind nginx at |
|---|---|---|
| Kanidm | `services.kanidm` | `idm.DOMAIN` |
| Forgejo | `services.forgejo` | `git.DOMAIN` |
| Harmonia | `services.harmonia` | `cache.DOMAIN` |
| Fleet + Redis | own systemd unit | `fleet.DOMAIN` |
| MySQL 8.4 (Forgejo's and Fleet's databases) | `services.mysql` | local only |
| Tang | `services.tang` | `tang.DOMAIN:7654` (direct) |

At boot, `meccanicos-fleet-secrets` creates the organization's CA, a
`*.DOMAIN` certificate (renewed 30 days before it expires), the cache signing
key and Fleet's keys, all in `/var/lib/meccanicos-fleet`.
`mos-fleet server init` does the one-time setup that can't be declared:
accounts, tokens, the repository, the enroll secret.

## 4. The glue, file by file

| File | What |
|---|---|
| `modules/managed.nix` | Managed mode: on when `/etc/nixos/fleet.toml` exists |
| `modules/fleet-server.nix` | The server: on when `/etc/nixos/fleet-server.toml` exists. Also installs `mos-fleet` everywhere |
| `modules/vendor/` | The Fleet agent's module and package, from nixos-unstable |
| `scripts/mos-install.py` | Organization install: finds `meccanicos/fleet/*/corporate.config` on the stick |
| `scripts/mos-fleet.py` | `mos-fleet`: the server's setup, people, profiles, provisioning, recovery |
| `flake.nix` | the `comin` input; it's also pinned in installed computers' `/etc/nixos` lock |

## 5. Known limits

- **Not tested yet** on real hardware, a real TPM, a real Tang server or a
  real Fleet enrollment. The modules evaluate and the managed system builds.
- **Shared credentials:** every computer uses the same read-only repository
  token and the same Fleet enroll secret. Both can be replaced (see the
  guide), but not per computer yet.
- **The very first install compiles** comin and the Fleet agent, until the
  server's cache has a built computer.
- **Laptops away from the office** need the repository, the cache and Fleet
  reachable: a VPN (WireGuard, Headscale) is the way. Tang stays LAN-only by
  design.
- **One server**, no replication: Kanidm can replicate, and a second Tang
  server is one line in the Clevis policy. Neither is set up yet.
- **To check before relying on them:**
  - Fleet Desktop on Xfce;
  - Kanidm's offline cache (how long it's honoured);
  - Tang's boot-stage network timeout away from the office.

## Sources

- Fleet on NixOS: [fleetdm/fleet#54421](https://github.com/fleetdm/fleet/pull/54421),
  LUKS escrow on NixOS: [fleetdm/fleet#54422][54422],
  [Fleet Linux management](https://fleetdm.com/linux-management)
- Fleet and MySQL 8 (no PostgreSQL, no MariaDB):
  [osquery Slack](https://chat.osquery.io/t/22710220/rotating-light-hello-this-message-is-to-prepare-you-for-flee)
- comin: [nlewo/comin](https://github.com/nlewo/comin)
- Clevis/Tang on NixOS: [`boot.initrd.clevis`](https://mynixos.com/options/boot.initrd.clevis),
  [FOSDEM 2024](https://fosdem.org/schedule/event/fosdem-2024-3044-clevis-tang-unattended-boot-of-an-encrypted-nixos-system)
- Kanidm unix integration:
  [Kanidm book: PAM and nsswitch](https://kanidm.github.io/kanidm/stable/integrations/pam_and_nsswitch.html)

[54422]: https://github.com/fleetdm/fleet/issues/54422

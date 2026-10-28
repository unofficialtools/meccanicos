# redistributable: what ships (the ISO and the installed system prebuilt into
# it) may hold unfree software only when its licence lets anyone pass it on
# (NVIDIA's driver, firmware, unrar). Anything else stops the build, instead
# of landing on a stick that can't be shared (CONTRIBUTING.md: Licensing).
# An installed computer's own rebuilds don't use this: there unfree is fine.
{ lib, ... }:
{
  nixpkgs.config.allowUnfree = lib.mkForce false;
  nixpkgs.config.allowUnfreePredicate =
    pkg:
    lib.all (l: builtins.isAttrs l && ((l.free or true) || (l.redistributable or false))) (
      lib.toList (pkg.meta.license or [ ])
    );
}

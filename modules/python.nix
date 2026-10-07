# Python 3.13 for everyday use: python3, venv + pip, and uv.
#
# This is the portable CPython build that uv itself uses
# (python-build-standalone), not Nix's Python. It runs through nix-ld
# (packages.nix) like on any other Linux, so ordinary PyPI wheels work:
#
#   python3 -m venv .venv && .venv/bin/pip install numpy     # no Nix involved
#   uv run python / uv venv / uv pip install ...             # uses it too
#
# `pip install` outside a venv falls back to ~/.local (the system copy is
# read-only).
{ pkgs, ... }:
let
  version = "3.13.14";
  release = "20260610";
  python = pkgs.runCommand "python-standalone-${version}" {
    src = pkgs.fetchurl {
      url = "https://github.com/astral-sh/python-build-standalone/releases/download/${release}/cpython-${version}%2B${release}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz";
      hash = "sha256-1gfhjoMiegUnzz9UpIvpc6dTWKaIXkvmfUsDWbbxyIA=";
    };
  } ''
    # runCommand skips the fixup phase, so the binaries stay untouched
    # (generic /lib64 loader, served by nix-ld).
    mkdir -p $out/lib/python-standalone $out/bin
    tar -xzf $src -C $out/lib/python-standalone --strip-components=1
    for b in python python3 python3.13 pip pip3 pip3.13 pydoc3 idle3 python3-config; do
      ln -s ../lib/python-standalone/bin/$b $out/bin/$b
    done
  '';
in
{
  environment.systemPackages = [ python ];
}

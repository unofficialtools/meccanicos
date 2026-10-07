# vscodium: VSCodium (VS Code without Microsoft's licence and telemetry) with
# a few extensions, installed into the user's own extensions folder the first
# time it starts, so the user can still add, update and remove extensions
# (vscode-with-extensions would make that folder read-only). Each one is
# installed once: one the user uninstalls stays uninstalled.
{ config, pkgs, ... }:
let
  ext = pkgs.vscode-extensions;
  # Shipped on the ISO (open source); installed from their .vsix, offline.
  bundled = [
    ext.mkhl.direnv # the folder's direnv environment (apps install --here) in the editor
    ext.bbenoist.nix # Nix language support
    ext.esbenp.prettier-vscode # code formatter
    ext.eamodio.gitlens # git blame and history
    ext.ritwickdey.liveserver # live-reload web server
    ext.yzhang.markdown-all-in-one # Markdown preview and shortcuts
  ];
  # From Open VSX, once online. Microsoft's Remote - SSH may only be used in
  # Microsoft's VS Code; this is its open-source counterpart for VSCodium.
  online = [ "jeanp413.open-remote-ssh" ];
  vsix = e: "${e.vscodeExtUniqueId}=${e.src}";

  codium = pkgs.writeShellScript "codium" ''
    real=${pkgs.vscodium}/bin/codium
    state="''${XDG_STATE_HOME:-$HOME/.local/state}/meccanicos/codium-extensions"
    mkdir -p "$(dirname "$state")" && touch "$state"
    pending=() ids=()
    for e in ${pkgs.lib.concatStringsSep " " (map vsix bundled)}; do
      id=''${e%%=*}
      grep -qixF "$id" "$state" && continue
      ids+=("$id")
      # --install-extension wants a .vsix name.
      pending+=(--install-extension "''${e#*=}")
    done
    if ((''${#pending[@]})); then
      "$real" "''${pending[@]}" >/dev/null 2>&1 || true
      printf '%s\n' "''${ids[@]}" >>"$state"
    fi
    for id in ${pkgs.lib.concatStringsSep " " online}; do
      grep -qixF "$id" "$state" && continue
      # In the background: offline, it is tried again next time.
      ( "$real" --install-extension "$id" >/dev/null 2>&1 && echo "$id" >>"$state" ) &
    done
    # No keyring where nothing unlocks it (the live system logs in by
    # itself), as for Brave: else "choose a password for the new keyring".
    exec "$real" ${pkgs.lib.optionalString config.meccanicos.browserBasicPasswordStore "--password-store=basic"} "$@"
  '';

  vscodium = pkgs.symlinkJoin {
    name = "vscodium-${pkgs.vscodium.version}";
    paths = [ pkgs.vscodium ];
    # Its menu entries run `codium` from PATH: this one.
    postBuild = ''
      rm $out/bin/codium
      ln -s ${codium} $out/bin/codium
    '';
    meta.mainProgram = "codium";
  };
in
{
  environment.systemPackages = [ vscodium ];
}

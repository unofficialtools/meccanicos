# The start of a command that works as the user, not as root: run with sudo it
# would use root's home, settings, desktop and sound (and leave files owned by
# root in the user's home). It asks for root itself when it needs it, so it
# stops and says so. Only when started through sudo (SUDO_USER set): services
# that run as root, and a real root login, are not affected.
#   text = notRoot "mos-config" + ''...'';
#   notRoot' "mos-logins" [ "root" "watch" ]   (these first arguments may run as root)
let
  check = name: ''
    declare -F T >/dev/null || T() { printf '%s' "$1"; }
    if [ "$(id -u)" = 0 ] && [ -n "''${SUDO_USER:-}" ] && [ "''${SUDO_USER}" != root ]; then
      echo "${name}: $(T 'run it as yourself, without sudo: it asks for root itself when it needs to.')" >&2
      echo "  $(T "(with sudo it would use root's settings and files, not yours)")" >&2
      exit 1
    fi
  '';
in
{
  notRoot = check;
  notRoot' = name: allowed: ''
    case "''${1:-}" in
      ${builtins.concatStringsSep "|" allowed}) ;;
      *)
    ${check name}
        ;;
    esac
  '';
}

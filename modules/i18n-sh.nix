# The T and Tf functions (scripts/lib/mos_i18n.sh) for a mos-* shell tool,
# put in front of its text like not-root.nix:
#   let tSh = import ./i18n-sh.nix pkgs; in
#   text = tSh "mos-backup" + ''echo "$(T 'Backup finished.')"'';
# Exported, so a script it runs with bash (scripts/*.sh) loads the same:
#   declare -F T >/dev/null || . "''${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null || { T() ...; Tf() ...; }
# (English without the lib: a script copied alone, as tests/default.nix does).
pkgs: app:
''
  export MOS_APP=${app} MOS_JQ=${pkgs.jq}/bin/jq MOS_I18N_SH=${../scripts/lib/mos_i18n.sh}
''
+ builtins.readFile ../scripts/lib/mos_i18n.sh

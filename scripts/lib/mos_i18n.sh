# mos_i18n.sh - translations for the mos-* shell tools (see mos_i18n.py:
# the same folder, files and choice of language). Sourced, or pasted in
# front of a script by modules/i18n.nix, after setting:
#   MOS_APP=mos-backup      the tool's name: its own translations win
#   MOS_JQ=/path/to/jq      (else jq from PATH; without jq: English)
# Then:
#   echo "$(T 'Backup finished.')"
#   Tf 'Saved %s to %s\n' "$file" "$dir"     (printf with a translated format)
# T prints the text in the user's language, or the English unchanged.

declare -gA MOS_T=()
mos_i18n_load() {
  local d lang key file loc=${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}
  for d in "${MECCANICOS_I18N:-}" /etc/meccanicos/i18n; do
    [ -n "$d" ] && [ -f "$d/languages.json" ] && break
    d=""
  done
  [ -n "$d" ] || return 0
  command -v "${MOS_JQ:-jq}" >/dev/null || return 0
  if [ -z "$loc" ] && [ -r /etc/locale.conf ]; then
    local line
    while IFS= read -r line; do
      if [[ $line == LANG=* ]]; then loc=${line#LANG=} loc=${loc//\"/}; fi
    done </etc/locale.conf
  fi
  case ${loc%%.*} in "" | C | POSIX) return 0 ;; esac
  local IFS=:
  for lang in ${LANGUAGE:-} $loc; do
    lang=${lang%%.*} lang=${lang%%@*}
    for key in "$lang" "${lang%%_*}"; do
      # shellcheck disable=SC2016 # jq programs, not shell
      file=$("${MOS_JQ:-jq}" -r --arg k "$key" 'if has($k) then (.[$k] // "") else "-" end' "$d/languages.json" 2>/dev/null) || return 0
      [ "$file" = - ] && continue
      [ -n "$file" ] || return 0 # English
      [ -r "$d/$file" ] || break  # missing: the next language
      local k v
      # shellcheck disable=SC2016 # a jq program, not shell
      while IFS= read -r -d '' k && IFS= read -r -d '' v; do
        MOS_T[$k]=$v
      done < <("${MOS_JQ:-jq}" -j --arg app "${MOS_APP:-}" \
        '((.["*"] // {}) + (.[$app] // {})) | to_entries[] | "\(.key)\u0000\(.value)\u0000"' "$d/$file" 2>/dev/null)
      return 0
    done
  done
}
mos_i18n_load
T() {
  if [ -n "${MOS_T[$1]+set}" ]; then printf '%s' "${MOS_T[$1]}"; else printf '%s' "$1"; fi
}
Tf() {
  local f
  f=$(T "$1")
  shift
  # shellcheck disable=SC2059 # the format is the translated text
  printf -- "$f" "$@"
}

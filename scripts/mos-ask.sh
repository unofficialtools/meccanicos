#!/usr/bin/env bash
# mos-ask - the big command bar (Super+Space / Alt+F2).
#
#   a URL or domain        -> opens in Brave            (github.com, https://…)
#   a path: / or ~ first   -> yazi there, in a terminal (~/Documents, /etc/nixos)
#   an app or program      -> starts it                 (thunar, btop, ls -la)
#   anything else          -> web search                ("convert png to jpg linux")
#
# Prefix with "?" to ask the AI (mos-ai; set up once with mos-ai-setup),
# "!" to run it as a command in a new bash shell, whose window stays until
# you press Enter.
#   mos-ask                 show the popup
#   mos-ask "some text"     act on the text without the popup
#   mos-ask --classify TXT  print what would happen (for testing)
#   mos-ask --apps          list apps in the order the popup shows them
#   mos-ask --help          this help

set -uo pipefail

ROFI_THEME="${MECCANICOS_ASK_THEME:-}"
TERMINAL_CMD=(xfce4-terminal)

trim() { local s=$1; s="${s#"${s%%[![:space:]]*}"}"; echo "${s%"${s##*[![:space:]]}"}"; }

# --- is it a URL / web address? ---------------------------------------------
FILE_EXT='txt|md|py|sh|pdf|png|jpe?g|gif|svg|nix|json|toml|ya?ml|conf|cfg|ini|log|csv|tsv|zip|tar|gz|xz|zst|7z|iso|img|mp3|mp4|mkv|webm|wav|flac|doc|docx|xls|xlsx|ppt|pptx|odt|ods|html?|css|js|ts|c|h|cpp|rs|go|java|rb|pl|lua|desktop'
is_url() {
    local t=$1
    [[ $t =~ ^(https?|ftp|file)://[^[:space:]]+$ ]] && return 0
    [[ $t =~ ^www\.[^[:space:]]+$ ]] && return 0
    [[ $t =~ ^localhost(:[0-9]+)?(/[^[:space:]]*)?$ ]] && return 0
    [[ $t =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}(:[0-9]+)?(/[^[:space:]]*)?$ ]] && return 0
    # bare domain: name.tld[/path] with an alphabetic TLD that isn't a file extension
    if [[ $t =~ ^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9-]+)*\.([A-Za-z]{2,24})(:[0-9]+)?(/[^[:space:]]*)?$ ]]; then
        local tld=${BASH_REMATCH[3],,}
        [[ $tld =~ ^($FILE_EXT)$ ]] && return 1
        [[ -e $t ]] && return 1   # an existing local file, not a website
        return 0
    fi
    return 1
}

# --- desktop applications ---------------------------------------------------
# Yours first, then the system's (where MeccanicOS renames and hides entries), then
# the rest: the session also lists packages' own folders (e.g. exo's), whose
# untouched copies would otherwise bring back what the system hides.
app_dirs() {
    local IFS=: d seen=:
    for d in ${XDG_DATA_HOME:-$HOME/.local/share} /run/current-system/sw/share ${XDG_DATA_DIRS:-}; do
        [[ $seen == *":$d:"* ]] && continue
        seen+="$d:"
        [[ -d $d/applications ]] && echo "$d/applications"
    done
}
# Prints "<desktop-file>\t<Terminal>" for the app whose Name or Exec binary
# matches $1 (case-insensitive). With "alias" as $2, also the program a
# terminal launcher runs (xfce4-terminal ... -x PROG), and either one without
# "mos-": "read" and "btop" start their launchers, whose
# windows close when the program ends. An exact match wins over an alias.
find_app() {
    local want=${1,,} alias=${2:-} f name exec bin prog term found=""
    while read -r d; do
        for f in "$d"/*.desktop; do
            [[ -f $f ]] || continue
            name=$(grep -m1 '^Name=' "$f" | cut -d= -f2-)
            exec=$(grep -m1 '^Exec=' "$f" | cut -d= -f2-)
            grep -q '^NoDisplay=true' "$f" && continue
            bin=${exec%% *}
            bin=${bin##*/}
            term=$(grep -m1 '^Terminal=' "$f" | cut -d= -f2-)
            if [[ ${name,,} == "$want" || ${bin,,} == "$want" ]]; then
                printf '%s\t%s\n' "$f" "${term:-false}"
                return 0
            fi
            [[ -n $alias && -z $found ]] || continue
            prog=""
            if [[ $exec == *" -x "* ]]; then
                prog=${exec#* -x }
                prog=${prog%% *}
                prog=${prog##*/}
            fi
            bin=${bin,,} prog=${prog,,}
            if [[ $want == "${bin#mos-}" || -n $prog && ($want == "$prog" || $want == "${prog#mos-}") ]]; then
                found=$(printf '%s\t%s' "$f" "${term:-false}")
            fi
        done
    done < <(app_dirs)
    [[ -n $found ]] && printf '%s\n' "$found"
}

# A command line (not plain English): first word is a program, and every
# further word looks like an argument (-flag, path, file.ext, number, a=b, |, >).
looks_like_command() {
    local -a w
    read -r -a w <<<"$1"
    command -v -- "${w[0]}" >/dev/null 2>&1 || return 1
    local a
    for a in "${w[@]:1}"; do
        [[ $a =~ ^- || $a == *[/.=~\$\|\>\<\*\&\;:]* || $a =~ ^[0-9]+$ || $a == '"'* || $a == "'"* ]] || return 1
    done
    return 0
}

classify() {
    local t
    t=$(trim "$1")
    [[ -z $t ]] && { echo "none"; return; }
    # shellcheck disable=SC2088 # a typed "~" is matched as text
    case $t in
        \?*) echo "ask	$(trim "${t#\?}")"; return ;;
        !*) echo "shell	$(trim "${t#!}")"; return ;;
        / | /* | "~" | "~/"*)
            local path=$t
            [[ $path == "~"* ]] && path=$HOME${path#\~}
            # An existing file or folder: yazi on it. Anything else goes on as text.
            if [[ -e $path ]]; then echo "path	$path"; return; fi ;;
    esac
    if is_url "$t"; then
        if [[ ! $t =~ ^[a-z]+:// ]]; then
            if [[ $t =~ ^(localhost|[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+) ]]; then t="http://$t"; else t="https://$t"; fi
        fi
        echo "url	$t"; return
    fi
    local app
    if app=$(find_app "$t" alias); then
        if [[ ${app#*$'\t'} == true ]]; then
            # terminal app (btop, mc…): run its Exec line in our terminal
            local ex
            ex=$(grep -m1 '^Exec=' "${app%%$'\t'*}" | cut -d= -f2- | sed 's/ *%[a-zA-Z]//g')
            echo "run	$ex"
        else
            echo "app	$app"
        fi
        return
    fi
    if looks_like_command "$t"; then
        local first=${t%% *}
        # GUI program with a desktop entry -> start it directly; else in a terminal
        if app=$(find_app "$first") && [[ ${app#*$'\t'} != true ]]; then
            echo "gui	$t"
        else
            echo "run	$t"
        fi
        return
    fi
    echo "search	$t"
}

urlencode() {
    local LC_ALL=C s=$1 out="" c i
    for ((i = 0; i < ${#s}; i++)); do
        c=${s:i:1}
        case $c in
            [a-zA-Z0-9.~_-]) out+=$c ;;
            " ") out+="+" ;;
            *) printf -v c '%%%02X' "'$c"; out+=$c ;;
        esac
    done
    printf '%s' "$out"
}

USAGE_FILE="${XDG_CACHE_HOME:-$HOME/.cache}/mos-ask/usage"

# Count launches so frequently used apps float to the top of the list.
bump_usage() {
    mkdir -p "${USAGE_FILE%/*}"
    local tmp
    tmp=$(mktemp)
    awk -F'\t' -v k="$1" 'BEGIN{OFS="\t"} $1==k{$2++; f=1} {print} END{if(!f) print k, 1}' \
        "$USAGE_FILE" 2>/dev/null >"$tmp" || printf '%s\t1\n' "$1" >"$tmp"
    mv "$tmp" "$USAGE_FILE"
}

# Visible desktop applications: "Name<TAB>Icon", one per app, deduplicated.
list_apps() {
    local files=() d f
    # Only real files: a folder without .desktop files (e.g. a fresh
    # ~/.local/share/applications) would otherwise pass the literal
    # "*.desktop" to awk, which then fails and the popup shows no apps.
    while read -r d; do
        for f in "$d"/*.desktop; do [[ -f $f ]] && files+=("$f"); done
    done < <(app_dirs)
    ((${#files[@]})) || return 0
    # A file name met again in a later folder is the same app, replaced by the
    # first one (a copy in ~/.local/share/applications wins over the system's).
    awk '
        function flush() { if (n != "" && !hide && typ == "Application" && !seen[n]++) print n "\t" ic }
        FNR == 1 { flush(); n = ""; ic = ""; hide = 0; typ = ""; sect = 0
                   id = FILENAME; sub(/.*\//, "", id); if (ids[id]++) hide = 1 }
        /^\[/ { sect = ($0 == "[Desktop Entry]") }
        sect && /^Name=/ && n == "" { n = substr($0, 6) }
        sect && /^Icon=/ && ic == "" { ic = substr($0, 6) }
        sect && /^Type=/ { typ = substr($0, 6) }
        sect && /^(NoDisplay|Hidden)=true/ { hide = 1 }
        END { flush() }
    ' "${files[@]}" 2>/dev/null
}

# Apps sorted by how often they were launched, then alphabetically.
ranked_apps() {
    awk -F'\t' 'FILENAME==ARGV[1] {u[$1]=$2; next} {printf "%08d\t%s\t%s\n", 99999999-(u[$1]+0), $1, $2}' \
        <(cat "$USAGE_FILE" 2>/dev/null) <(list_apps) | sort -t$'\t' -k1,1 -k2,2f | cut -f2-
}

# A command in its own terminal window. The window stays open after a quick
# command (ls, df…) or one that failed, so you can read what it printed, and
# closes by itself after a program you used for a while (btop, yazi…).
# shellcheck disable=SC2016
RUN_IN_TERMINAL='t=$SECONDS; sh -c "$1"; s=$?
if ((s != 0 || SECONDS - t < 10)); then
    ((s)) && printf "\n(exit status %s)" "$s"
    printf "\nPress any key to close."
    read -rsn1
fi'

act() {
    local kind rest
    IFS=$'\t' read -r kind rest <<<"$(classify "$1")"
    case $kind in
        none) ;;
        url) setsid -f brave "$rest" >/dev/null 2>&1 ;;
        app)
            local file=${rest%%$'\t'*}
            bump_usage "$(grep -m1 '^Name=' "$file" | cut -d= -f2-)"
            setsid -f gtk-launch "$(basename "$file" .desktop)" >/dev/null 2>&1 ||
                setsid -f gio launch "$file" >/dev/null 2>&1 ;;
        gui) setsid -f sh -c "$rest" >/dev/null 2>&1 ;;
        run) setsid -f "${TERMINAL_CMD[@]}" --title "$rest" -x bash -c "$RUN_IN_TERMINAL" run "$rest" >/dev/null 2>&1 ;;
        # "!command": in an interactive bash (your aliases), then Enter closes it.
        shell)
            # shellcheck disable=SC2016 # $1 and $? belong to the inner bash
            setsid -f "${TERMINAL_CMD[@]}" --title "$rest" -x bash -c \
                'bash -ic "$1"; s=$?; ((s)) && printf "\n(exit status %s)" "$s"; printf "\nPress Enter to close."; read -r' \
                shell "$rest" >/dev/null 2>&1 ;;
        # A folder opens in yazi; a file shows in yazi, in its folder.
        path) setsid -f "${TERMINAL_CMD[@]}" --title "$rest" -x yazi "$rest" >/dev/null 2>&1 ;;
        search) setsid -f brave "https://duckduckgo.com/?q=$(urlencode "$rest")" >/dev/null 2>&1 ;;
        # "?question" answers it; a lone "?" starts a chat.
        ask) if [[ -n $rest ]]; then
                 setsid -f "${TERMINAL_CMD[@]}" --title "AI" --hold -x mos-ai "$rest" >/dev/null 2>&1
             else
                 setsid -f "${TERMINAL_CMD[@]}" --title "AI Chat" --hold -x mos-ai >/dev/null 2>&1
             fi ;;
    esac
}

# Matching apps appear as you type (most used first). If nothing matches,
# Enter uses your text: website, command or web search. Ctrl+Enter always uses
# exactly what you typed, even when an app matches.
popup() {
    local args=(-dpi 0 -dmenu -p "❯" -i -show-icons -no-fixed-num-lines -no-sort
        -mesg "Enter: open   ·   Ctrl+Enter: use exactly what I typed   ·   / or ~ a folder   ·   !… run a command   ·   shortcuts: every key")
    [[ -n $ROFI_THEME ]] && args+=(-theme "$ROFI_THEME")
    ranked_apps | while IFS=$'\t' read -r name icon; do
        printf '%s\0icon\x1f%s\n' "$name" "${icon:-application-x-executable}"
    done | rofi "${args[@]}"
}

case ${1:-} in
    -h | --help) sed -n '/^# mos-ask - /,/^$/p' "$0" | sed '$d; s/^# \{0,1\}//' ;;
    --classify) classify "${2:-}" ;;
    --apps) ranked_apps ;;
    "") text=$(popup) && act "$text" ;;
    *) act "$*" ;;
esac

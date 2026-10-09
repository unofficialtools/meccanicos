#!/usr/bin/env bash
# mos-open (also `open`): open files, folders and URLs with the right app,
# like macOS `open`. Used by the shell, fzf (Ctrl-O), yazi (Enter, Ctrl-O)
# and mc (Enter).
#
# Rules: ~/.config/meccanicos/open.conf (yours, checked first; `open --config`
# creates it), then /etc/meccanicos/open.conf. One rule per line:
#
#   PATTERNS   COMMAND
#
# PATTERNS is a comma-separated list. A pattern with a "/" is a MIME type
# (as `file --mime-type` reports it; globs allowed: image/*), one ending in
# ":" is a URL scheme (https:), anything else is a file-name glob, matched
# ignoring case (*.csv). The first matching rule wins.
# COMMAND is a shell command: %f is the file (or URL), %d its folder; without
# %f the file is added at the end. Prefix "term:" for a terminal program (runs
# in this terminal, or in a new terminal window when started from the desktop).

set -uo pipefail
# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }

SYS_CONF=${MECCANICOS_OPEN_SYSTEM_CONF:-/etc/meccanicos/open.conf}
USER_CONF=${XDG_CONFIG_HOME:-$HOME/.config}/meccanicos/open.conf

usage() {
    local help
    help=$(T 'Usage: open [options] FILE|FOLDER|URL...

  (no option)  open with the app chosen by the rules in open.conf
  -a APP       open with APP (a command, e.g. -a eog)
  -e           open in the graphical text editor (VSCodium)
  -t           open in the terminal text editor ($EDITOR)
  -R           show it in the file manager instead of opening it
  -W           wait until the app exits
  -n           only print the command that would run
  -l, --list   show which app opens which files, and the keys in yazi, mc, fzf
  --config     create/edit your own rules (~/.config/meccanicos/open.conf)
  -h, --help   this help

Examples: open .   open report.pdf   open -a eog photo.jpg   open https://nixos.org')
    printf '%s\n' "$help"
}

die() {
    echo "open: $*" >&2
    exit 1
}
usage_error() { # wrong usage: exit 2
    echo "open: $* (open --help)" >&2
    exit 2
}

have_display() { [[ -n ${DISPLAY:-}${WAYLAND_DISPLAY:-} ]]; }

# Run a command line: detached for desktop apps (like macOS), in place for
# terminal programs or with -W.
run() {
    local cmd=$1 term=$2
    if ((dry)); then
        echo "${term:+term: }$cmd"
        return 0
    fi
    if [[ -n $term ]]; then
        if [[ -t 0 && -t 1 ]]; then
            bash -c "$cmd"
        elif have_display; then
            setsid -f xfce4-terminal -x bash -c "$cmd" >/dev/null 2>&1 </dev/null
        else
            die "$(Tf 'no terminal or display to run: %s' "$cmd")"
        fi
    elif ((wait)); then
        bash -c "$cmd"
    else
        have_display || die "$(T 'no graphical display (try -t for the terminal editor)')"
        setsid -f bash -c "$cmd" >/dev/null 2>&1 </dev/null
    fi
}

# Fill %f / %d into COMMAND (or append the file).
expand() {
    local cmd=$1 target=$2 qf qd
    qf=$(printf '%q' "$target")
    qd=$(printf '%q' "$(dirname -- "$target")")
    if [[ $cmd == *%f* ]]; then
        cmd=${cmd//%f/$qf}
    else
        cmd+=" $qf"
    fi
    printf '%s' "${cmd//%d/$qd}"
}

# Print "COMMAND" of the first rule matching TARGET (MIME, name, scheme).
match_rule() {
    local target=$1 mime=$2 scheme=$3 conf line pats cmd pat name
    name=$(basename -- "$target")
    name=${name,,}
    shopt -s nocasematch
    for conf in "$USER_CONF" "$SYS_CONF"; do
        [[ -r $conf ]] || continue
        while IFS= read -r line || [[ -n $line ]]; do
            line=${line#"${line%%[![:space:]]*}"}
            [[ -z $line || $line == \#* ]] && continue
            pats=${line%%[[:space:]]*}
            cmd=${line#"$pats"}
            cmd=${cmd#"${cmd%%[![:space:]]*}"}
            IFS=, read -ra list <<<"$pats"
            for pat in "${list[@]}"; do
                if [[ $pat == *: ]]; then
                    [[ -n $scheme && $scheme: == "$pat" ]] && { printf '%s' "$cmd"; return 0; }
                elif [[ $pat == */* ]]; then
                    # shellcheck disable=SC2053 # glob match on purpose
                    [[ -n $mime && $mime == $pat ]] && { printf '%s' "$cmd"; return 0; }
                elif [[ -z $scheme ]]; then
                    # shellcheck disable=SC2053
                    [[ $name == $pat ]] && { printf '%s' "$cmd"; return 0; }
                fi
            done
        done <"$conf"
    done
    return 1
}

open_one() {
    local target=$1 scheme="" mime="" cmd term=""
    if [[ $target =~ ^([A-Za-z][A-Za-z0-9+.-]*):(//)? && ! -e $target ]]; then
        scheme=${BASH_REMATCH[1],,}
    else
        [[ -e $target ]] || die "$(Tf '%s: no such file or folder' "$target")"
        target=$(realpath -- "$target")
    fi

    if [[ -n $reveal ]]; then
        [[ -z $scheme ]] || die "$(T '-R needs a file or folder')"
        if ((dry)); then Tf 'show %s in the file manager\n' "$target"; return 0; fi
        have_display || die "$(T 'no graphical display')"
        # Thunar implements FileManager1: opens the folder with the item selected.
        dbus-send --session --type=method_call --dest=org.freedesktop.FileManager1 \
            /org/freedesktop/FileManager1 org.freedesktop.FileManager1.ShowItems \
            array:string:"file://$target" string:"" 2>/dev/null ||
            setsid -f thunar "$(dirname -- "$target")" >/dev/null 2>&1 </dev/null
        return 0
    fi

    if [[ -n $app ]]; then
        cmd=$app
    elif ((gui_editor)); then
        cmd="codium"
    elif ((term_editor)); then
        cmd="term:${EDITOR:-vi}"
    else
        [[ -z $scheme ]] && mime=$(file --brief --mime-type --dereference -- "$target" 2>/dev/null)
        cmd=$(match_rule "$target" "$mime" "$scheme") || cmd="xdg-open"
        # No desktop (SSH, console): text goes to the terminal editor.
        if ! have_display && [[ $cmd != term:* && $mime == text/* ]]; then
            cmd="term:${EDITOR:-vi}"
        fi
    fi
    if [[ $cmd == term:* ]]; then
        term=1
        cmd=${cmd#term:}
        cmd=${cmd#"${cmd%%[![:space:]]*}"}
    fi
    run "$(expand "$cmd" "$target")" "$term"
}

# --list: what opens with what (your rules first), and the keys in each app.
list_rules() {
    local conf line pats cmd label="" exts p app
    echo "$(T 'What open uses (first match wins):')"
    for conf in "$USER_CONF" "$SYS_CONF"; do
        [[ -r $conf ]] || continue
        echo
        if [[ $conf == "$USER_CONF" ]]; then Tf '  Your rules (%s)\n' "$conf"; else Tf '  System rules (%s)\n' "$conf"; fi
        while IFS= read -r line || [[ -n $line ]]; do
            line=${line#"${line%%[![:space:]]*}"}
            if [[ $line == '#:'* ]]; then
                label=${line#'#:'}
                label=${label# }
                continue
            fi
            [[ -z $line || $line == \#* ]] && continue
            pats=${line%%[[:space:]]*}
            cmd=${line#"$pats"}
            cmd=${cmd#"${cmd%%[![:space:]]*}"}
            # Extensions, URL schemes and MIME families (image/*); the label
            # covers the long specific MIME types.
            exts=""
            IFS=, read -ra list <<<"$pats"
            for p in "${list[@]}"; do
                if [[ $p == */* ]]; then
                    [[ $p == */\* ]] && exts+="$p "
                elif [[ $p != "*" ]]; then
                    exts+="${p#\*.} "
                fi
            done
            # The app: the command's first word ("in terminal" for term: rules).
            if [[ $cmd == term:* ]]; then
                cmd=${cmd#term:}
                cmd=${cmd#"${cmd%%[![:space:]]*}"}
                app=$(Tf '%s (in the terminal)' "${cmd%% *}")
            else
                app=${cmd%% *}
            fi
            printf '    %-20s %-38s %s\n' "${label:-${exts% }}" "${exts% }" "$app"
            label=""
        done <"$conf"
    done
    local keys
    keys=$(T 'Keys that open the file under the cursor with open:
    yazi     Enter or Ctrl+O (a folder: go into it); O offers VSCodium, Jed
             (terminal editor), "Print…" and "show in file manager";
             e drags the selected files out, i takes files dropped on it
    mc       Enter (archives: browse inside; F3 views, F4 edits in Jed)
    fzf      Ctrl+O in any file list (Ctrl+T, Alt+C, ...); Enter just picks
    shell    open FILE   -e VSCodium   -t Jed   -R file manager   -a APP
Text, folders and archive listings stay in this terminal (from the desktop: a
terminal window); everything else opens in a window.
Double-click in Thunar or on the desktop also goes through open (Thunar keeps
folders); right-click > "Open in Browser" shows anything in Brave.')
    printf '\n%s\n' "$keys"
}

edit_config() {
    if [[ ! -e $USER_CONF ]]; then
        mkdir -p "$(dirname -- "$USER_CONF")"
        {
            T '# Your own open rules: checked before the system rules below (all
# commented out). Uncomment and change a line, or add new ones.
# Test with: open -n FILE'
            echo
            echo
            sed -e 's/^\([^#[:space:]]\)/# \1/' "$SYS_CONF"
        } >"$USER_CONF"
    fi
    "${EDITOR:-vi}" "$USER_CONF"
}

app="" reveal="" gui_editor=0 term_editor=0 wait=0 dry=0
while (($#)); do
    case $1 in
    -a)
        [[ $# -ge 2 ]] || usage_error "$(T '-a needs an app')"
        app=$2
        shift 2
        ;;
    -e) gui_editor=1; shift ;;
    -t) term_editor=1; shift ;;
    -R) reveal=1; shift ;;
    -W) wait=1; shift ;;
    -n) dry=1; shift ;;
    -l | --list) list_rules; exit 0 ;;
    --config) edit_config; exit ;;
    -h | --help) usage; exit 0 ;;
    --) shift; break ;;
    -*) usage_error "$(Tf 'unknown option %s' "$1")" ;;
    *) break ;;
    esac
done
(($#)) || usage_error "$(T 'missing FILE')"

status=0
for t in "$@"; do
    (open_one "$t") || status=1
done
exit "$status"

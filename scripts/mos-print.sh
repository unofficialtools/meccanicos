#!/usr/bin/env bash
# mos-print (also `print`): print files from the terminal. A menu asks
# where: one of the printers, or "Save as PDF" (not offered when every file is
# already a PDF). Used by the shell and yazi (O → Print).
#
# PDFs, pictures, plain text and PostScript go straight to the printer; office
# documents (pandoc: Word, OpenDocument, RTF, CSV), web pages (Brave), Markdown
# (pandoc) are made into a PDF first. Spreadsheets and slides: printed from
# OnlyOffice (Ctrl+P), which lays them out as they look. "Save as PDF" writes NAME.pdf next to the file; code and other
# text become a PDF with page numbers (typst).

set -uo pipefail
# Translations (scripts/lib/mos_i18n.sh); without them, English.
# shellcheck source=/dev/null disable=SC2059
declare -F T >/dev/null || . "${MOS_I18N_SH:-$(dirname "$0")/lib/mos_i18n.sh}" 2>/dev/null ||
  { T() { printf '%s' "$1"; } && Tf() { local f=$1 && shift && printf -- "$f" "$@"; }; }

usage() {
    local help
    help=$(T 'Usage: print [options] FILE...

  (no option)   choose a printer or "Save as PDF" from a menu, then print
  -d PRINTER    print on PRINTER without the menu
  --pdf         save as PDF (NAME.pdf next to the file) without the menu
  -n COPIES     number of copies
  -l, --list    list the printers (the default one is marked)
  -h, --help    this help

Printers are found on the network by themselves; add others in Print
Settings (command bar: "Print Settings"). `lpstat -o` shows the queue,
`cancel -a` empties it.')
    printf '%s\n' "$help"
}

die() {
    echo "print: $*" >&2
    exit 1
}
usage_error() { # wrong usage: exit 2
    echo "print: $* (print --help)" >&2
    exit 2
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mime_of() { file --brief --mime-type --dereference -- "$1" 2>/dev/null; }

is_pdf() { [[ $(mime_of "$1") == application/pdf ]]; }

# What kind of file: pdf, direct (CUPS prints it as is), office, web,
# markdown, text, or other.
kind_of() {
    local f=$1 name mime
    name=$(basename -- "$f")
    name=${name,,}
    mime=$(mime_of "$f")
    case $name in
    *.pdf) echo pdf; return ;;
    *.doc | *.docx | *.odt | *.rtf | *.xls | *.xlsx | *.ods | *.csv | *.tsv | *.ppt | *.pptx | *.odp) echo office; return ;;
    *.html | *.htm | *.xhtml | *.svg) echo web; return ;;
    *.md | *.markdown) echo markdown; return ;;
    *.ps | *.eps) echo direct; return ;;
    esac
    case $mime in
    application/pdf) echo pdf ;;
    image/svg+xml) echo web ;;
    image/*) echo direct ;;
    text/* | application/json | application/xml | application/x-yaml | application/toml | application/javascript | application/x-shellscript) echo text ;;
    *) echo other ;;
    esac
}

# Make a PDF of FILE at OUT (code and text get page numbers via typst).
to_pdf() {
    local f=$1 out=$2 kind
    kind=$(kind_of "$f")
    case $kind in
    pdf) cp -- "$f" "$out" ;;
    office)
        local from
        case ${f,,} in
        *.docx) from=docx ;; *.odt) from=odt ;; *.rtf) from=rtf ;; *.csv) from=csv ;; *.tsv) from=tsv ;;
        *) die "$(Tf '%s: open it in OnlyOffice and print from there (Ctrl+P)' "$f")" ;;
        esac
        (cd "$(dirname -- "$f")" && pandoc -f "$from" "$f" -o "$out" --pdf-engine=typst \
            -V mainfont="Libertinus Serif" -V codefont="DejaVu Sans Mono") >/dev/null 2>&1
        ;;
    web)
        brave --headless --disable-gpu --no-pdf-header-footer --print-to-pdf="$out" "file://$f" >/dev/null 2>&1
        ;;
    markdown)
        # Fonts named: pandoc's typst template fails with an empty font list.
        (cd "$(dirname -- "$f")" && pandoc "$f" -o "$out" --pdf-engine=typst \
            -V mainfont="Libertinus Serif" -V codefont="DejaVu Sans Mono") >/dev/null 2>&1
        ;;
    text)
        local ext=${f##*.}
        [[ $ext == "$f" || $ext == */* ]] && ext=""
        cat >"$TMP/text.typ" <<'EOF'
#set page(paper: "a4", margin: 1.5cm, footer: context align(center, text(8pt, counter(page).display("1 / 1", both: true))))
#set text(size: 9pt)
#raw(read(sys.inputs.file), block: true, lang: if sys.inputs.lang == "" { none } else { sys.inputs.lang })
EOF
        typst compile --root / --input file="$f" --input lang="${ext,,}" "$TMP/text.typ" "$out" >/dev/null 2>&1
        ;;
    direct)
        case $(mime_of "$f") in
        image/*) magick "$f" "$out" >/dev/null 2>&1 ;;
        *) ps2pdf "$f" "$out" >/dev/null 2>&1 ;;
        esac
        ;;
    *) die "$(Tf "%s: don't know how to make a PDF of this (%s)" "$f" "$(mime_of "$f")")" ;;
    esac
    [[ -s $out ]] || die "$(Tf '%s: could not convert it to PDF' "$f")"
}

# NAME.pdf next to FILE, or NAME-2.pdf, NAME-3.pdf, ... if taken.
pdf_name() {
    local f=$1 base out n=2
    base=${f%.*}
    [[ $base == "$f" || -z $(basename -- "$base") ]] && base=$f
    out=$base.pdf
    while [[ -e $out ]]; do
        out=$base-$n.pdf
        n=$((n + 1))
    done
    printf '%s' "$out"
}

save_pdf() {
    local f=$1 out
    is_pdf "$f" && { Tf '%s is already a PDF\n' "$f"; return 0; }
    out=$(pdf_name "$f")
    to_pdf "$f" "$out" && Tf 'Saved %s\n' "$out"
}

print_on() {
    local f=$1 printer=$2 kind send=$1 job
    kind=$(kind_of "$f")
    case $kind in
    pdf | direct | text) ;;
    other) die "$(Tf "%s: can't print this kind of file (%s)" "$f" "$(mime_of "$f")")" ;;
    *)
        send="$TMP/$(basename -- "$f").pdf"
        to_pdf "$f" "$send" || return 1
        ;;
    esac
    job=$(lp -d "$printer" -n "$copies" -t "$(basename -- "$f")" "$send" 2>&1) || die "$f: $job"
    echo "$(basename -- "$f") → $printer  ($job)"
}

# "name<TAB>label" for each printer, the default one first.
printers() {
    local def p state
    def=$(lpstat -d 2>/dev/null | sed -n 's/^system default destination: //p')
    while read -r p; do
        [[ -n $p ]] || continue
        state=$(lpstat -p "$p" 2>/dev/null | head -n1)
        case $state in
        *disabled*) state="  $(T '(paused)')" ;;
        *) state="" ;;
        esac
        if [[ $p == "$def" ]]; then
            printf '0\t%s\t%s%s\n' "$p" "$(Tf 'Printer: %s  (default)' "$p")" "$state"
        else
            printf '1\t%s\t%s%s\n' "$p" "$(Tf 'Printer: %s' "$p")" "$state"
        fi
    done < <(lpstat -e 2>/dev/null) | sort -s -k1,1n | cut -f2-
}

menu() {
    local all_pdf=$1 entries choice
    entries=$(
        printers
        ((all_pdf)) || printf '%s\t%s\n' "@pdf" "$(T 'Save as PDF (next to the file)')"
        printf '%s\t%s\n' "@setup" "$(T 'Add a printer… (Printers)')"
    )
    choice=$(printf '%s\n' "$entries" | fzf --height=~12 --layout=reverse --border \
        --with-nth=2 --delimiter='\t' --no-sort --prompt="$(Tf 'Print %s to ❯ ' "$label")") || exit 130
    printf '%s' "${choice%%$'\t'*}"
}

dest="" copies=1
while (($#)); do
    case $1 in
    -d)
        [[ $# -ge 2 ]] || usage_error "$(T '-d needs a printer')"
        dest=$2
        shift 2
        ;;
    --pdf) dest=@pdf; shift ;;
    -n)
        [[ $# -ge 2 && $2 =~ ^[1-9][0-9]*$ ]] || usage_error "$(T '-n needs a number of copies')"
        copies=$2
        shift 2
        ;;
    -l | --list)
        out=$(printers | cut -f2)
        if [[ -n $out ]]; then echo "$out"; else echo "$(T 'No printers (add one in Print Settings).')"; fi
        exit 0
        ;;
    -h | --help) usage; exit 0 ;;
    --) shift; break ;;
    -*) usage_error "$(Tf 'unknown option %s' "$1")" ;;
    *) break ;;
    esac
done
(($#)) || usage_error "$(T 'missing FILE')"

files=() all_pdf=1
for f in "$@"; do
    [[ -f $f ]] || die "$(Tf '%s: no such file' "$f")"
    f=$(realpath -- "$f")
    files+=("$f")
    is_pdf "$f" || all_pdf=0
done
if ((${#files[@]} == 1)); then label=$(basename -- "${files[0]}"); else label=$(Tf '%s files' "${#files[@]}"); fi

if [[ -z $dest ]]; then
    [[ -t 0 && -t 1 ]] || die "$(T 'no terminal for the menu (use -d PRINTER or --pdf)')"
    dest=$(menu "$all_pdf") || exit
    # "Add a printer…": the Printers screen, here, then the menu again.
    while [[ $dest == @setup ]]; do
        mos-printers
        dest=$(menu "$all_pdf") || exit
    done
fi

status=0
for f in "${files[@]}"; do
    if [[ $dest == @pdf ]]; then
        (save_pdf "$f") || status=1
    else
        (print_on "$f" "$dest") || status=1
    fi
done
exit "$status"

#!/usr/bin/env python3
"""i18n - the texts of the mos-* tools and their translations (i18n/).

  tools/i18n.py extract    every T("...") text into i18n/strings.json (with
                           the tools and lines that use it), for translators
  tools/i18n.py check      problems: T() of an f-string, a translation whose
                           placeholders ({name}, %s) differ from the English,
                           translations of texts no tool uses; and how much
                           of each language is translated (exit 1 on problems)
  tools/i18n.py todo xx.json [N]
                           the texts xx.json lacks (the first N), as JSON:
                           [{"text", "apps", "where"}] to translate
  tools/i18n.py merge xx.json DONE.json
                           add {"English": "translation", ...} from DONE.json
                           to xx.json's "*" (a new file if needed), then tidy
  tools/i18n.py tidy       rewrite the translation files the one way (and drop
                           the texts no tool uses any more): UTF-8
                           with the real characters (not \\u escapes), "*"
                           first, then the tools, each sorted, one text a line

Where texts are found: T(...) and N_(...) in scripts/**/*.py (and the
module docstring where T(__doc__) is); T and Tf with a
quoted word in scripts/*.sh and in the shell inside modules/*.nix.
"""

import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N = os.path.join(ROOT, "i18n")
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?:![rsa])?(?::[^{}]*)?\}|%(?:\d+\$)?[-+#0]*\d*(?:\.\d+)?[sdifxXuc%]")
# printf escapes in shell texts (a backslash and a letter): translations keep them.
ESCAPE = re.compile(r"\\[nt]")
# What must come through a translation unchanged, so the commands are the same
# in every language: options (-x, --xyz), mos-* names, `quoted` commands, the
# command lines of the help (an indented line that starts with a command, up
# to the gap before its description), what follows "usage:", short mentions
# like "(apps list)", and the METAVARS those use (NAME, FILE, ...), plus YES.
OPTION = re.compile(r"(?<![\w-])--?[A-Za-z][\w-]*|\bmos(?:-[\w-]+)?\b|`[^`\n]+`")
COMMANDS = r"(?:mos(?:-[\w-]+)?|apps|usb-vault|say|open|print|sudo|nix|gopass)"
COMMAND_LINE = re.compile(r"^[ \t]+(" + COMMANDS + r"(?:[ \t]\S+)*?)(?=[ \t]{2,}|$)", re.M)
USAGE = re.compile(r"\busage:[ \t]*(\S.*?)(?=[ \t]{2,}|\\n|$)", re.M | re.I)
MENTION = re.compile(r"\((" + COMMANDS + r"(?:[ \t][-\w|.]+){0,2})\)")
CAPS = re.compile(r"\b[A-Z][A-Z0-9_]{1,}\b")


SYNTAX = re.compile(r"\[.*\]|<.*>|--?[A-Za-z][\w-]*(=\S*)?|[A-Z][A-Z0-9_]*(\.\.\.|…)?|\.\.\.|…|\||[a-z][\w-]*(\|[a-z][\w-]*)+|\d+")


def syntax(line):
    """A command line's command part: the command, a subcommand, then options,
    [optional] parts, METAVARS and a|b choices, up to the first plain word
    (the start of a description written after a single space)."""
    words = line.split()
    keep = words[:1]
    for i, w in enumerate(words[1:], 1):
        sub = i == 1 and words[0] not in ("open", "print", "say") and re.fullmatch(r"[a-z][a-z-]*", w)
        if SYNTAX.fullmatch(w) or sub:
            keep.append(w)
        else:
            break
    return " ".join(keep) if len(keep) > 1 else ""


def command_lines(en):
    found = [syntax(m.strip()) for rx in (COMMAND_LINE, USAGE, MENTION) for m in rx.findall(en)]
    return [f for f in found if f]


# "apps update" is the command when it ends the text or a clause, or options or
# ARGUMENTS follow; not in "your apps update with the system".
AS_COMMAND = r"(?=$|[.,;:)!?'`\"]|\s+(?:-|\[|[A-Z]{2}|\{))"


def vocabulary(texts):
    """From the command lines: the CAPITAL words they use (NAME, FILE, ...,
    and YES), and each command's subcommands ("apps manage", ...)."""
    caps, subs = {"YES"}, set()
    for t in texts:
        for line in command_lines(t):
            caps.update(CAPS.findall(line))
            words = line.split()
            if words[0] not in ("open", "print", "say") and re.fullmatch(r"[a-z][a-z-]*", words[1]):
                subs.add(f"{words[0]} {words[1]}")
    return caps, subs


def verbatim(en, vocab):
    """The parts of an English text a translation must keep as they are."""
    caps, subs = vocab
    return (OPTION.findall(en) + command_lines(en) + [w for w in CAPS.findall(en) if w in caps]
            + [p for p in subs if re.search(r"(?<![\w-])" + re.escape(p) + AS_COMMAND, en)])


# A shell T/Tf argument: 'single quoted' or "double quoted" (no $, ` or \ but \" \\ \n).
SH_CALL = re.compile(r"""(?<![\w$-])(Tf?)\s+(?:'([^']*)'|"((?:[^"\\$`]|\\["\\n])*)")""")


def rel(p):
    return os.path.relpath(p, ROOT)


def python_texts(path, problems):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src, path)
    app = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "translator"
                and node.args and isinstance(node.args[0], ast.Constant)):
            app = node.args[0].value or "*"
    doc_call = any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "T" and n.args
                   and getattr(n.args[0], "id", None) == "__doc__" for n in ast.walk(tree))
    if doc_call and ast.get_docstring(tree, clean=False):
        yield ast.get_docstring(tree, clean=False), app or "*", f"{rel(path)}:1"
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("T", "N_") and node.args):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            yield arg.value, app or "*", f"{rel(path)}:{node.lineno}"
        elif isinstance(arg, ast.JoinedStr):
            problems.append(f"{rel(path)}:{node.lineno}: T(f\"...\"): use T(\"... {{name}}\").format(name=...)")


def shell_texts(path, apps, unescape_nix):
    src = open(path, encoding="utf-8").read()
    for m in SH_CALL.finditer(src):
        text = m.group(2) if m.group(2) is not None else re.sub(r'\\(["\\])', r"\1", m.group(3))
        if unescape_nix:
            text = text.replace("''$", "$").replace("'''", "''")
        line = src.count("\n", 0, m.start()) + 1
        for app in apps:
            yield text, app, f"{rel(path)}:{line}"


def sh_app(path):
    name = os.path.basename(path)[:-3]
    return {"usb-vault": "mos-vault"}.get(name, name)


def collect(problems):
    texts = {}  # text -> {"apps": set, "where": list}

    def add(text, app, where):
        if not text.strip():
            return
        e = texts.setdefault(text, {"apps": set(), "where": []})
        e["apps"].add(app)
        e["where"].append(where)

    for p in sorted(glob.glob(os.path.join(ROOT, "scripts", "**", "*.py"), recursive=True)):
        for t in python_texts(p, problems):
            add(*t)
    for p in sorted(glob.glob(os.path.join(ROOT, "scripts", "*.sh"))):
        for t in shell_texts(p, [sh_app(p)], False):
            add(*t)
    for p in sorted(glob.glob(os.path.join(ROOT, "modules", "*.nix"))):
        src = open(p, encoding="utf-8").read()
        apps = sorted(set(re.findall(r'(?:tSh|MOS_APP=)\s*"?(mos-[a-z0-9-]+)', src))) or ["*"]
        for t in shell_texts(p, apps, True):
            add(*t)
    return texts


def languages():
    return sorted(f for f in os.listdir(I18N) if f.endswith(".json") and f not in ("languages.json", "strings.json"))


def tidy(path, texts=None):
    """Sorted, real characters; with texts, translations of texts no tool uses go."""
    tables = json.load(open(path, encoding="utf-8"))
    if texts is not None:
        tables = {app: {k: v for k, v in t.items() if k in texts} for app, t in tables.items()}
    order = sorted(tables, key=lambda app: (app != "*", app))
    out = {app: dict(sorted(tables[app].items(), key=lambda kv: (kv[0].lower(), kv[0]))) for app in order}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    problems = []
    texts = collect(problems)
    if argv[0] == "todo" and len(argv) in (2, 3):
        path = os.path.join(I18N, argv[1])
        have = json.load(open(path, encoding="utf-8")).get("*", {}) if os.path.exists(path) else {}
        todo = [{"text": t, "apps": sorted(e["apps"]), "where": e["where"][:2]}
                for t, e in sorted(texts.items()) if t not in have]
        json.dump(todo[: int(argv[2])] if len(argv) == 3 else todo, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    if argv[0] == "merge" and len(argv) == 3:
        path = os.path.join(I18N, argv[1])
        tables = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"*": {}}
        done = json.load(open(argv[2], encoding="utf-8"))
        tables.setdefault("*", {}).update({k: v for k, v in done.items() if k in texts})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(tables, f, ensure_ascii=False)
        tidy(path)
        print(f"{argv[1]}: {len(tables['*'])}/{len(texts)} texts translated; {len([k for k in done if k not in texts])} unknown texts skipped")
        return 0
    if argv[0] == "tidy":
        for name in languages():
            tidy(os.path.join(I18N, name), texts)
        return 0
    if argv[0] == "extract":
        out = [{"text": t, "apps": sorted(e["apps"]), "where": e["where"][:3]} for t, e in sorted(texts.items())]
        with open(os.path.join(I18N, "strings.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"{len(out)} texts -> i18n/strings.json")
    elif argv[0] == "check":
        vocab = vocabulary(texts)
        for name in languages():
            tables = json.load(open(os.path.join(I18N, name), encoding="utf-8"))
            done = 0
            for app, table in tables.items():
                for en, tr in table.items():
                    where = f"i18n/{name} [{app}] {en[:50]!r}"
                    if en not in texts:
                        problems.append(f"{where}: no tool uses this text")
                        continue
                    if app != "*" and app not in texts[en]["apps"]:
                        problems.append(f"{where}: {app} does not use this text")
                    if not isinstance(tr, str):
                        problems.append(f"{where}: not a string")
                    elif sorted(PLACEHOLDER.findall(en)) != sorted(PLACEHOLDER.findall(tr)):
                        problems.append(f"{where}: placeholders {PLACEHOLDER.findall(en)} -> {PLACEHOLDER.findall(tr)}")
                    elif [v for v in verbatim(en, vocab) if v not in tr]:
                        problems.append(f"{where}: must stay as in English: {[v for v in verbatim(en, vocab) if v not in tr]}")
                    elif ESCAPE.findall(en) != ESCAPE.findall(tr):
                        problems.append(f"{where}: escapes {ESCAPE.findall(en)} -> {ESCAPE.findall(tr)} (keep the \\n of shell texts)")
            shared = tables.get("*", {})
            done = sum(1 for t in texts if t in shared)
            print(f"{name}: {done}/{len(texts)} texts translated")
    else:
        print(f"i18n: unknown command {argv[0]} (tools/i18n.py --help)", file=sys.stderr)
        return 2
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""mos_i18n - translations for the mos-* tools.

Every text a tool shows is written in American English and wrapped in T():

    from mos_i18n import translator
    T = translator("mos-apps")          # the tool's name: its own translations win
    print(T("Installed {name}.").format(name=attr))
    print(T(__doc__))                   # the help: the module docstring

T() returns the text in the user's language, or the English unchanged when
there is no translation for that language or for that text. Placeholders are
named ({name}) and go through .format() after T(), so translators can move them.

The translations live in one folder, shared by every tool:
  /etc/meccanicos/i18n (MECCANICOS_I18N overrides it; next to scripts/ in the repo)
    languages.json   which file serves which language: {"pt_BR": "pt.json", "gl": "pt.json", "en": null}
    es.json, ...     {"*": {"English": "translation"}, "mos-apps": {"English": "only in mos-apps"}}

The language is the first of $LANGUAGE (a colon-separated list), $LC_ALL,
$LC_MESSAGES, $LANG (then LANG in /etc/locale.conf) that languages.json knows,
tried as "pt_BR" then "pt"; a C or POSIX locale means English, as with gettext.
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_tables = None


def folder():
    for d in (os.environ.get("MECCANICOS_I18N"), "/etc/meccanicos/i18n",
              os.path.join(_HERE, "..", "..", "i18n")):
        if d and os.path.isfile(os.path.join(d, "languages.json")):
            return d
    return None


def wanted():
    """The user's languages, most preferred first, e.g. ["pt_BR", "en"]."""
    env = os.environ
    locale = env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG")
    if not locale:
        try:
            with open("/etc/locale.conf") as f:
                for line in f:
                    if line.startswith("LANG="):
                        locale = line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    if not locale or locale.split(".")[0] in ("C", "POSIX"):
        return []
    langs = [l for l in env.get("LANGUAGE", "").split(":") if l] + [locale]
    return [l.split(".")[0].split("@")[0] for l in langs]


def load():
    """The translation file's tables, {} for English (or nothing found)."""
    global _tables
    if _tables is not None:
        return _tables
    _tables = {}
    d = folder()
    if not d:
        return _tables
    try:
        with open(os.path.join(d, "languages.json"), encoding="utf-8") as f:
            languages = json.load(f)
    except (OSError, ValueError):
        return _tables
    for lang in wanted():
        for key in (lang, lang.split("_")[0]):
            if key not in languages:
                continue
            if not languages[key]:
                return _tables  # English
            try:
                with open(os.path.join(d, languages[key]), encoding="utf-8") as f:
                    _tables = json.load(f)
                return _tables
            except (OSError, ValueError):
                break  # that file is missing or broken: the next language
    return _tables


def N_(text):
    """Marks a text for translation where it is written (a table of labels);
    T() translates it where it is shown: T(label)."""
    return text


def translator(app):
    """T(text) for this app: its own translation, else the shared one, else text."""
    def T(text):
        tables = load()
        own = tables.get(app)
        if own and text in own:
            return own[text]
        return tables.get("*", {}).get(text, text)
    return T

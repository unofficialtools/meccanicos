# Translations of the mos-* tools

Every text a mos-* tool shows is written in American English and wrapped in
`T(...)`; at start the tool picks the user's language and `T` returns the
translation, or the English when there is none.

| File | What |
|---|---|
| `languages.json` | locale → translation file, e.g. `"pt_BR": "pt.json"`, `"gl": "pt.json"`, `"en": null` (English). Tried as `pt_BR`, then `pt`; a language not listed is English. |
| `es.json`, `pt.json`, … | `{"*": {"English": "translation", …}, "mos-apps": {"English": "only in mos-apps", …}}`: `"*"` serves every tool, a tool's own section wins for that tool. |
| `strings.json` | every text and the tools that use it (`tools/i18n.py extract`): what to translate. |

Installed in `/etc/meccanicos/i18n` (`MECCANICOS_I18N` overrides it). The
language is the first of `$LANGUAGE` (a colon-separated list), `$LC_ALL`,
`$LC_MESSAGES`, `$LANG` (then `/etc/locale.conf`) that `languages.json`
knows; a `C` or `POSIX` locale is English.

## In a tool

Python (`scripts/lib/mos_i18n.py`):

```python
from mos_i18n import translator, N_
T = translator("mos-apps")
print(T("Installed {name}.").format(name=attr))   # never T(f"...")
LABELS = [N_("Install"), N_("Remove")]             # marked here, translated where shown: T(label)
print(T(__doc__))                                  # the help (the module docstring)
```

Shell (`scripts/lib/mos_i18n.sh`; Nix wrappers start with `tSh "mos-backup"`
from `modules/i18n-sh.nix`, scripts run with bash load it themselves):

```bash
echo "$(T 'Backup finished.')"
Tf 'Saved %s to %s\n' "$file" "$dir"     # printf with a translated format
```

`T`'s argument is always a literal, so `tools/i18n.py` can find it.
Placeholders (`{name}`, `%s`) must stay in the translation, in any order
for `{name}`.

## Translating

```bash
tools/i18n.py extract     # i18n/strings.json: the texts, and where they are used
tools/i18n.py check       # placeholders, texts no tool uses, how much is translated
tools/i18n.py tidy        # rewrite the files the one way (below)
```

The files are plain UTF-8 JSON, meant to be edited by hand: the real
characters (`"Sí"`, `"保存"`), never `\u` escapes; `"*"` first, then a
section per tool; one `"English": "translation"` per line, sorted.

Not translated, in any language: app and product names and the technical
words people search for or type (Word Processor, Spreadsheet, Browser, web,
shell, terminal, USB, Wi-Fi, SSH, …), commands, options, file names, keys.

To add a language: a new `xx.json`, and its locales in `languages.json`.
A text missing from a file is shown in English.

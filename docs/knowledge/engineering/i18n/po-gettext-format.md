# po-gettext-format

**Issue:** Using GNU gettext PO/POT files for localizing applications
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Gettext is widely used in Python/Django, PHP/WordPress, and C. PO files store source strings alongside translations; POT files are templates.

## Pattern / Solution
POT file:
```po
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"

#: src/views/home.py:42
#, python-format
msgid "Hello, %(name)s!"
msgstr ""

msgid "One item"
msgid_plural "%(count)d items"
msgstr[0] ""
msgstr[1] ""
```
Commands:
```bash
xgettext -d myapp -o locale/myapp.pot src/**/*.py
msginit --locale=fr_FR --input=myapp.pot --output=locale/fr_FR/LC_MESSAGES/myapp.po
msgmerge --update locale/fr_FR/LC_MESSAGES/myapp.po locale/myapp.pot
msgfmt locale/fr_FR/LC_MESSAGES/myapp.po -o locale/fr_FR/LC_MESSAGES/myapp.mo
```

## Gotchas
- `.mo` (binary) is what gettext reads at runtime -- always compile after edits
- `#, fuzzy` marks indicate stale translations; they are NOT used unless `--use-fuzzy` flag is passed
- Plural rules are defined by the `Plural-Forms` header -- wrong formula causes wrong plural selection

## Related
- `xliff-format-handling.md`
- `plural-rules-cldr.md`

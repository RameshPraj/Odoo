# Nepali (ne_NP) translations for this Odoo 19 instance

Odoo 19 ships **no** Nepali translations. It has no `ne_NP` entry in
`odoo/addons/base/data/res.lang.csv`, so Nepali never appears in
Settings → Translations → Languages. The 62 `i18n/ne.po` files that do exist in
the tree are empty Transifex stubs from Odoo 11 (2017) — `account/i18n/ne.po`
has 2,413 source strings and **zero** translations.

This directory adds the language and a hand-written Nepali translation of the
high-traffic UI.

## Files

| Path | Purpose |
|---|---|
| `translations.py` | The English → Nepali dictionary. **This is the only file you edit.** |
| `apply.py` | Creates/activates `ne_NP`, builds `.po` files, deploys and imports them. |
| `verify.py` | Reports how much Nepali actually resolves, through both paths. |
| `po/` | Generated `.po` files, kept as the backup copy of what was deployed. |

## Usage

```powershell
# translate every installed module that ships a .pot
venv\Scripts\python.exe l10n_ne\apply.py

# just some modules
venv\Scripts\python.exe l10n_ne\apply.py --modules web,base,account

# build .po files without deploying or importing
venv\Scripts\python.exe l10n_ne\apply.py --dry-run

# check the result (run after restarting the server)
venv\Scripts\python.exe l10n_ne\verify.py
```

**Restart the server after applying** — code translations are cached per
process, so a running server will not pick up changes.

Then set a user's language: avatar → Preferences → Language → *Nepali / नेपाली*.

## To extend coverage

Add entries to `TRANSLATIONS` in `translations.py` and re-run `apply.py`.
Keys must match the `msgid` in the module's `.pot` **exactly** — case, spacing
and punctuation included — or they are silently skipped. To find real msgids:

```powershell
Select-String -Path odoo\addons\account\i18n\account.pot -Pattern '^msgid "Invoice' -Context 2,0
```

Newly installed modules are picked up automatically on the next run, since
`apply.py` enumerates installed modules from `ir.module.module`.

## How translation actually works in Odoo 19 (the important part)

There are **two independent stores**, and you must write to both:

**1. Code translations** — every Python `_()` and JavaScript `_t()` string, i.e.
all buttons, dialogs and client-side labels. These are read from `.po` files
**on disk**, never from the database:

```
odoo/tools/translate.py
  CodeTranslations._get_code_translations()  ->  get_po_paths(module, lang)
  get_po_paths() searches, in order:
      <module>/i18n/<base_lang>.po
      <module>/i18n_extra/<base_lang>.po
      <module>/i18n/<lang>.po
      <module>/i18n_extra/<lang>.po
  later entries win (translations.update(...))
```

So `apply.py` writes `<module>/i18n_extra/ne.po`, which overrides the empty
stub in `<module>/i18n/ne.po`. `i18n_extra` is Odoo's own override slot —
`account_edi_proxy_client` already ships one.

**2. Model translations** — field labels, menu names, view text, model
descriptions. These live in `jsonb` columns in the database, keyed by language.
`TranslationImporter.save()` writes *only* these; it returns early otherwise
(`odoo/tools/translate.py:1615`).

Consequence: importing a `.po` through the **Import Translation** wizard in the
UI cannot translate a single button — it only ever reaches store 2. That is why
`apply.py` does both.

## Caveats

- **`i18n_extra/` directories live inside the Odoo source tree.** Unavoidable:
  code translations are resolved by module path, so `web`'s strings must sit
  under a directory named `web`. They survive `-u <module>`, but a fresh
  extract of the Odoo tarball wipes them — re-run `apply.py` after that.
  The `po/` directory here is the backup.
- **Coverage is partial by design.** The dictionary targets the most-repeated
  chrome (toolbars, dialogs, common field labels). The long tail — settings
  help text, rarely-seen views, report bodies — stays English.
- `res.lang` for `ne_NP` is created **without an external ID** on purpose. An
  xmlid under the `base.` prefix would look like stale module data and could be
  removed by `-u base`.
- `res.lang.format()` raises `UserError: The language ... is not installed`
  until the language is active, so number grouping only applies after
  activation.

## Locale settings used

| Field | Value | Note |
|---|---|---|
| `code` | `ne_NP` | |
| `iso_code` / `url_code` | `ne` | `.po` filename, and `/ne/` in URLs |
| `date_format` | `%d/%m/%Y` | |
| `time_format` | `%H:%M:%S` | 24-hour |
| `week_start` | `7` | Sunday |
| `grouping` | `[3,2,0]` | lakh/crore — 1,23,45,678.90 |

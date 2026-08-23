# -*- coding: utf-8 -*-
"""Build and install Nepali (ne_NP) translations for this Odoo instance.

Usage (from anywhere):
    venv\\Scripts\\python.exe l10n_ne\\apply.py
    venv\\Scripts\\python.exe l10n_ne\\apply.py --modules web,base,account
    venv\\Scripts\\python.exe l10n_ne\\apply.py --db otherdb --dry-run

What it does
------------
1. Ensures a ne_NP record exists in res.lang and is active.
2. For every installed module that ships an i18n/<module>.pot, fills in msgstr
   from translations.py and writes l10n_ne/po/<module>_ne.po.
3. Copies each result to <addons>/<module>/i18n_extra/ne.po.
4. Imports the same files into the database.

Why both steps 3 and 4
----------------------
Odoo 19 resolves translations from two independent stores:

  * CODE translations -- every Python _() and JS _t() string -- are read from
    .po files ON DISK by odoo.tools.translate.CodeTranslations, never from the
    database. get_po_paths() searches <module>/i18n/ then <module>/i18n_extra/,
    and later wins, so i18n_extra is the safe override slot.
  * MODEL translations -- field labels, menu names, view text -- live in jsonb
    columns in the database. TranslationImporter.save() writes only these.

Skipping step 3 leaves every button in English; skipping step 4 leaves every
field label in English. Both are required.

Caveat: i18n_extra/ directories live inside the Odoo source tree because code
translations are resolved by module path. They survive `-u <module>`, but a
fresh extract of the Odoo tarball wipes them -- rerun this script after that.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ODOO_ROOT = os.path.dirname(HERE)
ADDONS = os.path.join(ODOO_ROOT, "odoo", "addons")
PO_DIR = os.path.join(HERE, "po")
CONF = os.path.join(ODOO_ROOT, "odoo.conf")

for p in (ODOO_ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import polib  # noqa: E402
from odoo import SUPERUSER_ID, api  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402
from odoo.tools import config  # noqa: E402
from odoo.tools.translate import TranslationImporter  # noqa: E402
from translations import TRANSLATIONS  # noqa: E402

LANG_CODE = "ne_NP"
LANG_VALS = {
    "name": "Nepali / नेपाली",
    "code": LANG_CODE,
    "iso_code": "ne",
    "url_code": "ne",
    "direction": "ltr",
    "date_format": "%d/%m/%Y",
    "time_format": "%H:%M:%S",
    "week_start": "7",       # Sunday
    "grouping": "[3,2,0]",   # lakh / crore
    "decimal_point": ".",
    "thousands_sep": ",",
}

PO_METADATA = {
    "Project-Id-Version": "Odoo Server 19.0",
    "Report-Msgid-Bugs-To": "",
    "Language-Team": "Nepali",
    "Language": "ne",
    "MIME-Version": "1.0",
    "Content-Type": "text/plain; charset=UTF-8",
    "Content-Transfer-Encoding": "8bit",
    "Plural-Forms": "nplurals=2; plural=(n != 1);",
}


def build_po(module):
    """Fill msgstr on the module's .pot; return (path, hits) or None."""
    pot_path = os.path.join(ADDONS, module, "i18n", f"{module}.pot")
    if not os.path.exists(pot_path):
        return None

    pot = polib.pofile(pot_path, encoding="utf-8")
    po = polib.POFile(encoding="utf-8")
    po.metadata = dict(PO_METADATA, **{"Project-Id-Version": f"Odoo Server 19.0 ({module})"})

    for entry in pot:
        ne = TRANSLATIONS.get(entry.msgid)
        if not ne:
            continue
        po.append(polib.POEntry(
            msgid=entry.msgid,
            msgstr=ne,
            occurrences=entry.occurrences,
            comment=entry.comment,          # keeps '#. odoo-javascript' / '#. odoo-python'
            tcomment=entry.tcomment,
            flags=[f for f in entry.flags if f != "fuzzy"],
        ))

    if not po:
        return None
    os.makedirs(PO_DIR, exist_ok=True)
    out = os.path.join(PO_DIR, f"{module}_ne.po")
    po.save(out)
    return out, len(po)


def main():
    ap = argparse.ArgumentParser(description="Install Nepali translations")
    ap.add_argument("--db", default=None, help="database (default: db_name from odoo.conf)")
    ap.add_argument("--modules", default=None,
                    help="comma-separated modules (default: every installed module with a .pot)")
    ap.add_argument("--dry-run", action="store_true", help="build .po files but do not deploy or import")
    args = ap.parse_args()

    config.parse_config(["-c", CONF] + (["-d", args.db] if args.db else []))
    # config['db_name'] is a list in Odoo 19 (it accepts a comma-separated set)
    db = args.db or (config["db_name"] or [None])[0]
    if not db:
        sys.exit("no database: pass --db or set db_name in odoo.conf")

    registry = Registry(db)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})

        # -- 1. language record -------------------------------------------
        Lang = env["res.lang"].with_context(active_test=False)
        lang = Lang.search([("code", "=", LANG_CODE)], limit=1)
        if not lang:
            lang = Lang.create(dict(LANG_VALS, active=True))
            print(f"created res.lang {LANG_CODE} (id={lang.id})")
        elif not lang.active:
            lang.active = True
            print(f"activated res.lang {LANG_CODE}")
        else:
            print(f"res.lang {LANG_CODE} already active")

        # -- 2. which modules ---------------------------------------------
        if args.modules:
            modules = [m.strip() for m in args.modules.split(",") if m.strip()]
        else:
            modules = env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")
        modules = sorted(modules)
        print(f"scanning {len(modules)} module(s) for .pot templates")

        # -- 3. build ------------------------------------------------------
        built = {}
        for mod in modules:
            res = build_po(mod)
            if res:
                built[mod] = res
        if not built:
            sys.exit("no module produced any translation -- nothing to do")

        print()
        print(f"{'module':<22} {'strings':>7}")
        total = 0
        for mod, (_path, hits) in sorted(built.items()):
            print(f"{mod:<22} {hits:>7}")
            total += hits
        print(f"{'TOTAL':<22} {total:>7}")

        if args.dry_run:
            print("\n--dry-run: built .po files only, nothing deployed or imported")
            return

        # -- 4. deploy to i18n_extra (code translations) -------------------
        print()
        for mod, (path, _hits) in sorted(built.items()):
            target_dir = os.path.join(ADDONS, mod, "i18n_extra")
            os.makedirs(target_dir, exist_ok=True)
            shutil.copyfile(path, os.path.join(target_dir, "ne.po"))
        print(f"deployed {len(built)} file(s) to <module>/i18n_extra/ne.po")

        # -- 5. import into the database (model translations) --------------
        # IMPORTANT: TranslationImporter.load_file() opens through Odoo's
        # sandboxed file_open(), which only resolves paths inside the addons
        # tree -- and it swallows the resulting FileNotFoundError:
        #
        #   with suppress(FileNotFoundError), file_open(filepath, ...) as f:
        #
        # Passing an absolute path to l10n_ne/po/ therefore imports NOTHING,
        # silently. Load the copies deployed in step 4 instead, addressed
        # module-relative so file_open can resolve them.
        importer = TranslationImporter(cr)
        loaded = 0
        for mod in sorted(built):
            rel = f"{mod}/i18n_extra/ne.po"
            before = len(importer.model_translations)
            importer.load_file(rel, LANG_CODE, module=mod)
            if len(importer.model_translations) > before or importer.model_translations:
                loaded += 1
        if not importer.model_translations and not importer.model_terms_translations:
            sys.exit("ERROR: importer collected nothing -- check that the i18n_extra "
                     "files exist and that ne_NP is active")
        importer.save(overwrite=True)
        cr.commit()
        print(f"imported model translations into the database from {loaded} file(s)")

        print()
        print("Done. Restart the server, then set a user's language to "
              "'Nepali / नेपाली' in Preferences.")
        print("Code translations are cached per process -- a restart is required.")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Report how much Nepali is actually resolving, through both translation paths.

    venv\\Scripts\\python.exe l10n_ne\\verify.py
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ODOO_ROOT = os.path.dirname(HERE)
CONF = os.path.join(ODOO_ROOT, "odoo.conf")

if ODOO_ROOT not in sys.path:
    sys.path.insert(0, ODOO_ROOT)

from odoo import api, SUPERUSER_ID  # noqa: E402
from odoo.modules.registry import Registry  # noqa: E402
from odoo.tools import config  # noqa: E402
from odoo.tools.translate import code_translations  # noqa: E402

LANG = "ne_NP"
SAMPLE = ["Save", "Discard", "New", "Delete", "Search", "Filters",
          "Actions", "Add", "Export", "Send message", "Log note"]

ap = argparse.ArgumentParser()
ap.add_argument("--db", default=None)
args = ap.parse_args()

config.parse_config(["-c", CONF] + (["-d", args.db] if args.db else []))
# config['db_name'] is a list in Odoo 19 (it accepts a comma-separated set)
db = args.db or (config["db_name"] or [None])[0]
registry = Registry(db)

with registry.cursor() as cr:
    env = api.Environment(cr, SUPERUSER_ID, {})

    lang = env["res.lang"].with_context(active_test=False).search([("code", "=", LANG)], limit=1)
    if not lang:
        sys.exit(f"{LANG} does not exist -- run apply.py first")
    print(f"{LANG}: {lang.name}   active={lang.active}")

    installed = env["ir.module.module"].search([("state", "=", "installed")]).mapped("name")

    print()
    print("=== CODE TRANSLATIONS (read from <module>/i18n_extra/ne.po on disk) ===")
    print(f"{'module':<22} {'javascript':>10} {'python':>7}")
    tj = tp = 0
    for mod in sorted(installed):
        js = len(code_translations.get_web_translations(mod, LANG)["messages"])
        py = len(code_translations.get_python_translations(mod, LANG))
        if js or py:
            print(f"{mod:<22} {js:>10} {py:>7}")
            tj += js
            tp += py
    print(f"{'TOTAL':<22} {tj:>10} {tp:>7}")

    web = {m["id"]: m["string"] for m in code_translations.get_web_translations("web", LANG)["messages"]}
    mail = {m["id"]: m["string"] for m in code_translations.get_web_translations("mail", LANG)["messages"]}
    both = {**web, **mail}
    print()
    print("  sample:")
    for k in SAMPLE:
        print(f"    {k:<14} -> {both.get(k, '<not translated>')}")

    print()
    print("=== MODEL TRANSLATIONS (jsonb columns in the database) ===")
    checks = [
        ("ir_model_fields", "field_description", "field labels"),
        ("ir_ui_menu", "name", "menu items"),
        ("ir_model", "name", "model names"),
        ("ir_act_window", "name", "window actions"),
    ]
    for table, col, label in checks:
        try:
            cr.execute(f"SELECT count(*) FROM {table} WHERE {col}->>%s IS NOT NULL", (LANG,))
            print(f"  {label:<16} {cr.fetchone()[0]:>6}")
        except Exception as exc:  # noqa: BLE001
            cr.rollback()
            print(f"  {label:<16} n/a ({exc.__class__.__name__})")

    print()
    print("  sample field labels:")
    cr.execute("""SELECT field_description->>'en_US', field_description->>%s
                  FROM ir_model_fields WHERE field_description->>%s IS NOT NULL
                  ORDER BY random() LIMIT 8""", (LANG, LANG))
    for en, ne in cr.fetchall():
        print(f"    {en!r} -> {ne!r}")

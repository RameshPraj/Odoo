# -*- coding: utf-8 -*-
"""Guards for the Nepal localization scaffold.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d <db> \\
        --test-enable --test-tags /l10n_np --stop-after-init

The XML well-formedness test exists because this module already shipped a broken
comment once: a double hyphen inside <!-- --> is illegal XML, and because Odoo
merges module XML it can break far more than the offending module.
"""
import csv
import glob
import os

from lxml import etree
from odoo.tests import TransactionCase, tagged

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(MODULE_DIR, "data", "template")


@tagged("-at_install", "post_install")
class TestNPScaffold(TransactionCase):

    def test_xml_is_well_formed(self):
        """Every XML file must parse. A stray '--' in a comment breaks the bundle."""
        files = glob.glob(os.path.join(MODULE_DIR, "**", "*.xml"), recursive=True)
        self.assertTrue(files, "no XML files found")
        for path in files:
            with self.subTest(file=os.path.basename(path)):
                try:
                    etree.parse(path)
                except etree.XMLSyntaxError as exc:
                    self.fail(f"{os.path.basename(path)} is not well-formed: {exc}")

    def test_template_registered(self):
        """The 'np' chart template must be discoverable."""
        mapping = self.env["account.chart.template"]._get_chart_template_mapping()
        self.assertIn("np", mapping, "Nepal chart template is not registered")
        self.assertEqual(mapping["np"]["country_code"], "NP")

    def test_wired_accounts_exist_in_csv(self):
        """Every account id referenced by template_np.py must exist in the CSV.

        A mismatch fails installation with a missing-xmlid error, so catch it here.
        """
        csv_path = os.path.join(TEMPLATE_DIR, "account.account-np.csv")
        with open(csv_path, encoding="utf-8") as fh:
            ids = {row["id"] for row in csv.DictReader(fh)}

        Template = self.env["account.chart.template"]
        wired = set()
        for method in ("_get_np_template_data", "_get_np_res_company", "_get_np_account_account"):
            data = getattr(Template, method)()
            # flatten one or two levels of dict into candidate string values
            stack = [data]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    stack.extend(cur.values())
                elif isinstance(cur, str) and cur.startswith("l10n_np_"):
                    wired.add(cur)

        missing = wired - ids
        self.assertFalse(
            missing,
            f"template_np.py references account ids absent from the CSV: {sorted(missing)}",
        )

    def test_provinces_loaded(self):
        """Nepal has 7 provinces; base ships none."""
        states = self.env["res.country.state"].search([("country_id.code", "=", "NP")])
        self.assertEqual(len(states), 7, f"expected 7 provinces, found {len(states)}")
        self.assertEqual(
            sorted(states.mapped("code")),
            ["P1", "P2", "P3", "P4", "P5", "P6", "P7"],
        )

    def test_vat_rate_is_thirteen_percent(self):
        """Documents the standard-rate assumption so a change is deliberate."""
        csv_path = os.path.join(TEMPLATE_DIR, "account.tax-np.csv")
        with open(csv_path, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["id"]]
        standard = [r for r in rows if r["id"] in ("VAT_S_NP_13", "VAT_P_NP_13")]
        self.assertEqual(len(standard), 2, "expected a sale and a purchase standard-rate tax")
        for row in standard:
            self.assertEqual(row["amount"], "13", "Nepal standard VAT assumed to be 13%")

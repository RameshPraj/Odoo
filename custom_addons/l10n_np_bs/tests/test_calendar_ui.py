# -*- coding: utf-8 -*-
"""Tests for the Nepali (Bikram Sambat) calendar module.

    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d odoo19 \\
        --test-enable --test-tags /l10n_np_bs --stop-after-init

Three layers, cheapest first:

  TestBSAssets      pure Python. Parses every XML file in the module. This is
                    the one that matters most: Odoo merges all modules' asset
                    templates into a single document, so one malformed file
                    blanks the entire backend with no console error. That is
                    exactly the bug this module shipped once.
  TestBSConversion  pure Python. AD <-> BS correctness.
  TestBSCalendarUI  headless Chrome. Confirms the page actually renders.

The browser test needs:
  * pip install websocket-client
  * pre-built asset bundles (a cold build is ~150s on Windows and would eat
    the browser timeout)
  * onboarding tours disabled -- an active tour clicks through to another app
    mid-test and the action never renders
"""
import datetime
import glob
import os

from lxml import etree

from odoo.tests import HttpCase, TransactionCase, tagged

MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@tagged("-at_install", "post_install")
class TestBSAssets(TransactionCase):

    def test_all_xml_is_well_formed(self):
        """Every XML file must parse.

        A stray '--' inside a comment is illegal XML and invalidates the whole
        merged asset bundle, taking down web.WebClient itself.
        """
        files = glob.glob(os.path.join(MODULE_DIR, "**", "*.xml"), recursive=True)
        self.assertTrue(files, "no XML files found -- is MODULE_DIR wrong?")
        for path in files:
            with self.subTest(file=os.path.relpath(path, MODULE_DIR)):
                try:
                    etree.parse(path)
                except etree.XMLSyntaxError as exc:
                    self.fail(f"{os.path.relpath(path, MODULE_DIR)} is not well-formed: {exc}")

    def test_assets_are_declared(self):
        """Every asset listed in the manifest must exist on disk."""
        module = self.env["ir.module.module"].search([("name", "=", "l10n_np_bs")])
        self.assertEqual(module.state, "installed")
        paths = self.env["ir.asset"]._get_asset_paths("web.assets_backend", {})
        ours = [str(p[0]) for p in paths if "l10n_np_bs" in str(p[0])]
        self.assertTrue(ours, "module contributes nothing to web.assets_backend")
        for rel in ours:
            disk = os.path.join(os.path.dirname(MODULE_DIR), rel.lstrip("/").replace("/", os.sep))
            self.assertTrue(os.path.exists(disk), f"declared asset missing on disk: {rel}")


@tagged("-at_install", "post_install")
class TestBSConversion(TransactionCase):

    def setUp(self):
        super().setUp()
        from odoo.addons.l10n_np_bs.tools import bs  # noqa: PLC0415
        self.bs = bs

    def test_known_dates(self):
        cases = [
            (datetime.date(2026, 9, 9), (2083, 5, 24)),
            (datetime.date(2026, 4, 14), (2083, 1, 1)),    # Nepali new year
            (datetime.date(2000, 1, 1), (2056, 9, 17)),
        ]
        for ad, expected in cases:
            with self.subTest(ad=ad):
                self.assertEqual(self.bs.ad_to_bs(ad), expected)
                self.assertEqual(self.bs.bs_to_ad(*expected), ad)

    def test_round_trip(self):
        d = datetime.date(1960, 1, 1)
        step = datetime.timedelta(days=97)
        while d < datetime.date(2040, 1, 1):
            self.assertEqual(self.bs.bs_to_ad(*self.bs.ad_to_bs(d)), d, f"round trip failed for {d}")
            d += step

    def test_devanagari_formatting(self):
        out = self.bs.format_bs(datetime.date(2026, 9, 9), np_digits=True, month_names=True)
        self.assertEqual(out, "२०८३-भदौ-२४")
        self.assertEqual(self.bs.parse_bs("२०८३-०५-२४"), datetime.date(2026, 9, 9))

    def test_out_of_range_raises(self):
        from odoo.exceptions import UserError  # noqa: PLC0415
        with self.assertRaises(UserError):
            self.bs.ad_to_bs(datetime.date(1850, 1, 1))


@tagged("-at_install", "post_install")
class TestBSCalendarUI(HttpCase):

    def test_calendar_renders(self):
        action = self.env.ref("l10n_np_bs.action_bs_calendar")
        self.browser_js(
            f"/odoo/action-{action.id}",
            """
            (async () => {
                for (let i = 0; i < 100; i++) {
                    const cells = document.querySelectorAll(
                        '.o_bs_cal_cell:not(.o_bs_cal_blank)').length;
                    if (document.querySelector('.o_bs_cal_grid') && cells > 20) {
                        console.log('test successful');
                        return;
                    }
                    await new Promise((r) => setTimeout(r, 200));
                }
                const root = document.querySelector('.o_bs_calendar_action');
                console.error(
                    'calendar did not render' +
                    ' :: root=' + !!root +
                    ' :: grid=' + !!document.querySelector('.o_bs_cal_grid') +
                    ' :: cells=' + document.querySelectorAll('.o_bs_cal_cell').length +
                    ' :: body=' + document.body.innerHTML.slice(0, 400)
                );
            })();
            """,
            ready="document.readyState === 'complete'",
            login="admin",
            timeout=240,
        )

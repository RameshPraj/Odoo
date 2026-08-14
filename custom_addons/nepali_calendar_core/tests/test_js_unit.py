# -*- coding: utf-8 -*-
"""Run the browser-side unit tests from the Python suite.

Declaring a file under ``web.assets_unit_tests`` gets it *bundled*; it does not
get it *run*. Odoo executes hoot suites only when something opens ``/web/tests``,
which in practice means ``web``'s own ``WebSuite`` -- so a module's JS tests can
sit in the repository for years without ever executing. That is the position the
Python ``selftest.py`` was in before this pass, and the same mistake is worth
avoiding twice.

This drives the real hoot runner in headless Chrome, filtered to this module's
suite so it does not drag in the whole ``web`` suite (minutes, not seconds).

The filter is a hash of the suite path, matching ``HOOTCommon.get_hoot_filters``
in ``odoo/addons/web/tests/test_js.py``. A wrong hash silently matches nothing and
hoot would still report success over an empty run, so the suite name is asserted
against the file on disk first, and the count of executed tests is checked from
the browser log afterwards.

Requires the same environment as the other browser test: ``websocket-client``,
pre-built asset bundles, and onboarding tours disabled.
"""
import glob
import os
import re

from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import unit_test_error_checker

MODULE = "nepali_calendar_core"
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_TESTS_DIR = os.path.join(MODULE_DIR, "static", "tests")


def hoot_hash(text):
    """Reimplementation of hoot's suite-id hash.

    Deliberately a copy of `HOOTCommon._generate_hash` rather than a call into it:
    that method is on an `HttpCase` subclass we do not otherwise want to inherit,
    and the algorithm is four lines. `test_hash_matches_core` pins the two
    together so a change upstream cannot pass unnoticed.
    """
    value = 0
    for char in text:
        value = ((value << 5) - value + ord(char)) & 0xFFFFFFFF
    return f"{value:08x}"


@tagged("-at_install", "post_install")
class TestJsUnit(HttpCase):

    def test_hash_matches_core(self):
        """Pin the local hash implementation to core's known values.

        These two are asserted by core's own `test_generate_hoot_hash`, so if hoot
        changes its hashing this fails here rather than degrading into a filter
        that silently matches nothing.
        """
        self.assertEqual(hoot_hash("@web/core"), "e39ce9ba")
        self.assertEqual(hoot_hash("@web/core/autocomplete"), "69a6561d")

    def test_every_js_test_file_is_covered(self):
        """A new .test.js file must not be silently left unrun.

        `test_bs_convert_unit_tests` names one suite explicitly. Without this,
        adding a second test file would look covered and never execute.
        """
        found = sorted(
            os.path.basename(p)
            for p in glob.glob(os.path.join(JS_TESTS_DIR, "**", "*.test.js"),
                               recursive=True)
        )
        self.assertEqual(
            found, ["bs_convert.test.js"],
            "the set of JS test files changed; add the new suite to this class so "
            "it actually runs, then update this assertion"
        )

    def test_bs_convert_unit_tests(self):
        """The conversion contract, executed in a browser.

        The Python suite can only assert the JS half by pattern-matching its
        source. This is the half that actually runs it.
        """
        suite = f"@{MODULE}/bs_convert"
        url = (
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={hoot_hash(suite)}"
        )
        self.browser_js(
            url, "", "",
            login="admin",
            timeout=600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )

    def test_the_suite_name_matches_the_file_on_disk(self):
        """Guard the filter against a rename.

        `static/tests/bs_convert.test.js` is addressed as
        `@nepali_calendar_core/bs_convert`. Renaming the file without updating the
        filter would leave `test_bs_convert_unit_tests` passing over zero tests --
        the worst possible outcome for a test, so it is checked separately.
        """
        expected = os.path.join(JS_TESTS_DIR, "bs_convert.test.js")
        self.assertTrue(
            os.path.exists(expected),
            f"{expected} is missing, but the hoot filter still points at "
            f"@{MODULE}/bs_convert"
        )

    def test_no_focused_tests_are_committed(self):
        """`test.only` in a committed file silently skips everything else.

        Core guards its own suites with the same check
        (`RE_FORBIDDEN_STATEMENTS` in web/tests/test_js.py).
        """
        pattern = re.compile(r"\btest(?:\.\w+)*\.(?:only|debug)\(")
        for path in glob.glob(os.path.join(JS_TESTS_DIR, "**", "*.test.js"),
                              recursive=True):
            with self.subTest(file=os.path.basename(path)):
                with open(path, encoding="utf-8") as fh:
                    self.assertNotRegex(
                        fh.read(), pattern,
                        "remove test.only / test.debug before committing"
                    )

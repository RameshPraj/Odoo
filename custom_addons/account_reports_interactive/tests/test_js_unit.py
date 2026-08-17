# -*- coding: utf-8 -*-
"""Run this module's browser-side unit tests from the Python suite.

Declaring a file under ``web.assets_unit_tests`` bundles it; it does not run it.
Odoo executes hoot suites only when something opens ``/web/tests``, so a module's
JS tests can sit in the repository for years without ever executing. The pattern
here is the one already proven in ``nepali_calendar_core/tests/test_js_unit.py``;
see that file for the reasoning behind the suite-id hash.

Requires ``websocket-client``, pre-built asset bundles, and Chrome.
"""
import glob
import os
import re

from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import unit_test_error_checker

MODULE = "account_reports_interactive"
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_TESTS_DIR = os.path.join(MODULE_DIR, "static", "tests")

#: Suite names, i.e. `static/tests/<name>.test.js` addressed as `@<module>/<name>`.
SUITES = [
    "report_interactive",
]


def hoot_hash(text):
    """Reimplementation of hoot's suite-id hash. See nepali_calendar_core."""
    value = 0
    for char in text:
        value = ((value << 5) - value + ord(char)) & 0xFFFFFFFF
    return f"{value:08x}"


@tagged("-at_install", "post_install")
class TestJsUnit(HttpCase):

    def test_hash_matches_core(self):
        """Pinned to values core's own test asserts, so a wrong filter cannot
        silently match nothing and still report success."""
        self.assertEqual(hoot_hash("@web/core"), "e39ce9ba")
        self.assertEqual(hoot_hash("@web/core/autocomplete"), "69a6561d")

    def test_every_js_test_file_is_run(self):
        on_disk = sorted(
            os.path.relpath(p, JS_TESTS_DIR).replace(os.sep, "/")[: -len(".test.js")]
            for p in glob.glob(os.path.join(JS_TESTS_DIR, "**", "*.test.js"),
                               recursive=True)
        )
        self.assertEqual(
            on_disk, sorted(SUITES),
            "the set of JS test files no longer matches SUITES; add the new suite "
            "there so it actually runs")

    def test_no_focused_tests_are_committed(self):
        pattern = re.compile(r"\btest(?:\.\w+)*\.(?:only|debug)\(")
        for path in glob.glob(os.path.join(JS_TESTS_DIR, "**", "*.test.js"),
                              recursive=True):
            with open(path, encoding="utf-8") as handle:
                self.assertIsNone(
                    pattern.search(handle.read()),
                    f"{os.path.basename(path)} contains a focused test, which "
                    f"would skip every other test in the run")

    def test_js_unit_tests(self):
        """The suites, executed in a browser."""
        ids = "".join(f"&id={hoot_hash(f'@{MODULE}/{s}')}" for s in SUITES)
        url = "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000" + ids
        self.browser_js(
            url, "", "",
            login="admin",
            timeout=900,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )

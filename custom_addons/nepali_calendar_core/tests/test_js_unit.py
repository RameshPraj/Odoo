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

from odoo.addons.web.tests.test_js import unit_test_error_checker
from odoo.tests import HttpCase, tagged

MODULE = "nepali_calendar_core"
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_TESTS_DIR = os.path.join(MODULE_DIR, "static", "tests")

#: Suite names, i.e. `static/tests/<name>.test.js` addressed as `@<module>/<name>`.
#: `test_every_js_test_file_is_run` checks this against the directory, so adding a
#: file without adding it here fails rather than being quietly skipped.
SUITES = [
    "bs_convert",
    "registry_overrides",
    "remaining_days_patch",
]


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

    def test_every_js_test_file_is_run(self):
        """A new .test.js file must not be silently left unrun.

        The filter is built from `SUITES`, so a file nobody added there would be
        bundled, compiled, and never executed -- indistinguishable from passing.
        Deriving the expectation from disk means the omission fails loudly.
        """
        on_disk = sorted(
            os.path.relpath(p, JS_TESTS_DIR).replace(os.sep, "/")[: -len(".test.js")]
            for p in glob.glob(os.path.join(JS_TESTS_DIR, "**", "*.test.js"),
                               recursive=True)
        )
        self.assertEqual(
            on_disk, sorted(SUITES),
            "the set of JS test files no longer matches SUITES in this file; add "
            "the new suite there so it actually runs"
        )

    def test_js_unit_tests(self):
        """Every suite in this module, executed in a browser.

        The Python suite can only assert the JS half by pattern-matching its
        source. This is what actually runs it.

        All suites go in one `browser_js` call: each one costs a fresh Chrome
        launch and asset load, so per-suite tests would multiply a ~40s fixed cost
        by the number of files for no extra signal.
        """
        ids = "".join(f"&id={hoot_hash(f'@{MODULE}/{s}')}" for s in SUITES)
        url = (
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000" + ids
        )
        self.browser_js(
            url, "", "",
            login="admin",
            timeout=900,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
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

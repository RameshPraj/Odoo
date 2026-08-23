# -*- coding: utf-8 -*-
"""The Python dependency must stay pinned in requirements.txt.

`external_dependencies` in a manifest is checked by **Odoo**, at module load. It
is not read by pip and never installs anything. So a dependency declared only
there is a dependency that a fresh environment does not get: Odoo refuses the
module, and everything depending on it follows. That is what happened here --
`nepali_datetime` was declared, never pinned, and the suite could not be installed
from a clean checkout at all.

Two failure modes, both covered below:

1. **The line goes missing.** `requirements.txt` is Odoo's own file, carried in
   with the 19.0 baseline. Re-vendoring it from a newer Odoo release overwrites
   our addition, and nothing would notice until a deploy failed. So the pin is
   asserted, not trusted.

2. **The pin drifts from what is installed.** The month-length table *is* the
   algorithm -- BS months run 29-32 days with no formula -- and we call the
   private `nepali_datetime._days_in_month`. A version other than the tested one
   can change dates or break fiscal-year generation at runtime. The 46,022-day
   cross-check catches wrong dates, but only for the version actually present, so
   the pin and the installed version must agree.

Deliberately a pure-Python check on the file, with no network access and no pip
invocation: it must be cheap enough to run in every suite.
"""
import os
import re

import nepali_datetime
from odoo.tests import TransactionCase, tagged

#: Repo root. tests/ -> nepali_calendar_core/ -> custom_addons/ -> root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
REQUIREMENTS = os.path.join(REPO_ROOT, "requirements.txt")

#: pip name (hyphen) vs import name (underscore) -- a routine trip hazard.
PIP_NAME = "nepali-datetime"


def _pinned_version():
    """The version pinned in requirements.txt, or None.

    Ignores comments, and tolerates an environment marker (`; python_version …`)
    so adding one later does not break this.
    """
    with open(REQUIREMENTS, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            spec = line.split(";", 1)[0].strip()
            match = re.fullmatch(
                re.escape(PIP_NAME) + r"==([0-9][0-9A-Za-z.\-_]*)", spec,
                flags=re.IGNORECASE)
            if match:
                return match.group(1)
    return None


@tagged("-at_install", "post_install")
class TestRequirementsPin(TransactionCase):

    def test_requirements_file_exists(self):
        self.assertTrue(
            os.path.exists(REQUIREMENTS),
            f"requirements.txt not found at {REQUIREMENTS}; if the repository "
            f"layout moved, fix REPO_ROOT here rather than deleting this test"
        )

    def test_the_dependency_is_pinned(self):
        pinned = _pinned_version()
        self.assertIsNotNone(
            pinned,
            f"{PIP_NAME} is not pinned in requirements.txt. It is declared in "
            f"this module's `external_dependencies`, but pip never reads that, so "
            f"a fresh environment cannot install the Nepal suite. If "
            f"requirements.txt was just re-vendored from upstream Odoo, "
            f"re-append the project-additions block at the end of the file."
        )

    def test_the_pin_is_exact(self):
        """`>=` is not good enough here.

        We depend on a *data table* and on a private symbol, so a minor release
        can silently change what dates this system produces.
        """
        with open(REQUIREMENTS, encoding="utf-8") as fh:
            body = fh.read()
        loose = re.findall(
            re.escape(PIP_NAME) + r"\s*(>=|>|~=|!=|<)", body, flags=re.IGNORECASE)
        self.assertFalse(
            loose,
            f"{PIP_NAME} must be pinned with `==`, not {loose}: the month-length "
            f"table is the algorithm, and we call a private symbol"
        )

    def test_the_pin_matches_the_installed_version(self):
        pinned = _pinned_version()
        self.assertIsNotNone(pinned, "not pinned; see test_the_dependency_is_pinned")
        installed = getattr(nepali_datetime, "__version__", None)
        if not installed:
            # The package has not always exposed __version__; fall back to the
            # installed distribution metadata rather than skipping silently.
            from importlib.metadata import version  # noqa: PLC0415
            installed = version(PIP_NAME)
        self.assertEqual(
            pinned, installed,
            f"requirements.txt pins {PIP_NAME}=={pinned} but {installed} is "
            f"installed. The 46,022-day conversion check only validates the "
            f"version actually present, so the two must agree or the suite is "
            f"green against something the deployment will not get."
        )

    def test_the_private_symbol_we_rely_on_still_exists(self):
        """`month_length()` calls `nepali_datetime._days_in_month`.

        A private symbol can vanish in any release without notice. This is the
        cheapest possible early warning, and it names the risk explicitly rather
        than leaving it as a comment nobody reads.
        """
        self.assertTrue(
            callable(getattr(nepali_datetime, "_days_in_month", None)),
            "nepali_datetime._days_in_month is gone. tools/bs.py:month_length "
            "depends on it; fiscal-year generation breaks without it."
        )

    def test_the_manifest_still_declares_it(self):
        """Belt and braces: Odoo's own check must stay in place too.

        The pin gets it installed; `external_dependencies` is what produces a
        clear error instead of an ImportError when it is not.
        """
        module = self.env["ir.module.module"].search(
            [("name", "=", "nepali_calendar_core")], limit=1)
        self.assertTrue(module, "nepali_calendar_core is not in ir.module.module")

        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "__manifest__.py")
        import ast  # noqa: PLC0415
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = ast.literal_eval(fh.read())
        self.assertIn(
            "nepali_datetime",
            manifest.get("external_dependencies", {}).get("python", []),
            "the manifest no longer declares the dependency, so a missing package "
            "surfaces as an ImportError mid-request instead of a clear refusal to "
            "install"
        )

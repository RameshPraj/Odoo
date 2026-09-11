# -*- coding: utf-8 -*-
r"""The due-instalment test does not depend on when it is run (TST-6).

    venv\Scripts\python.exe -m odoo -c odoo.conf -d <db> \
        --test-enable --test-tags /l10n_np_loan --stop-after-init

``test_post_due_posts_only_what_has_fallen_due`` starts a loan at
``fields.Date.context_today`` and then backdates two instalments so that exactly
two have fallen due. It used to express those backdates as the literals
``2026-01-01`` and ``2026-02-01``, which are backdates only while the clock is
past February 2026 — so the test would have begun failing on its own, with no
code change, at the turn of the year.

Rewriting it to use offsets from ``today`` fixes that, but a rewrite is a claim
about behaviour under a clock the suite never actually runs at. This runs it at
one: **2025-06-01, a date at which the old literals were in the future** and the
original test would have found nothing due and failed.

Only that one scenario is re-run, rather than the whole loan suite. Running
everything under a shifted clock was the verification used while making the
change and it passed for all 27 cases, but keeping it would double the module's
test count permanently to re-assert things that never read the clock.
"""
from odoo.tests import tagged
from odoo.tests.common import freeze_time

from .test_loan import TestLoan


@tagged("-at_install", "post_install")
class TestPostDueIsClockIndependent(TestLoan):
    """The scenario, replayed under an earlier clock.

    Note the method below is defined here rather than inherited. Odoo collects
    only test methods found in a class's own ``__dict__``
    (``odoo/tests/loader.py:29-33``), so a subclass that adds no methods of its
    own contributes **zero** tests and the run still reports success. The first
    attempt at this file did exactly that: it ran nothing, reported green, and
    was only caught by noticing the test count had not moved. The alternative is
    the ``allow_inherited_tests_method`` opt-in on the same lines, which re-runs
    the entire parent class.
    """

    freeze_time = freeze_time("2025-06-01")

    def test_post_due_under_an_earlier_clock(self):
        self.test_post_due_posts_only_what_has_fallen_due()

# -*- coding: utf-8 -*-
"""Headless-Chrome checks for the Nepali Calendar client action.

Run:
    venv\\Scripts\\python.exe -m odoo -c odoo.conf -d odoo19 \\
        --test-enable --test-tags /l10n_np_bs --stop-after-init

Note: pre-build the asset bundles first, otherwise a cold build (~150s on
Windows) eats the browser timeout. Also make sure onboarding tours are off --
an active tour clicks its way to another app and the action never renders.
"""
from odoo.tests import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestBSCalendarUI(HttpCase):

    def _open(self, xmlid, probe_js):
        action = self.env.ref(xmlid)
        self.browser_js(
            f"/odoo/action-{action.id}",
            probe_js,
            # Deliberately weak: we want the probe to run and describe the DOM
            # even when the web client did not render, rather than time out.
            ready="document.readyState === 'complete'",
            login="admin",
            timeout=240,
        )

    def test_00_dump_dom(self):
        """Report what actually lands in the DOM. Always fails, by design."""
        self._open("l10n_np_bs.action_bs_calendar", """
            setTimeout(() => {
                const q = (s) => document.querySelector(s);
                console.error(
                    'DOMDUMP' +
                    ' url=' + location.href +
                    ' | title=' + document.title +
                    ' | o_action_manager=' + !!q('.o_action_manager') +
                    ' | o_web_client=' + !!q('.o_web_client') +
                    ' | o_main_navbar=' + !!q('.o_main_navbar') +
                    ' | bs_root=' + !!q('.o_bs_calendar_action') +
                    ' | bs_grid=' + !!q('.o_bs_cal_grid') +
                    ' | cells=' + document.querySelectorAll('.o_bs_cal_cell').length +
                    ' | BODY=' + document.body.innerHTML.slice(0, 600)
                );
            }, 8000);
        """)

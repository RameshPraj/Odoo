# -*- coding: utf-8 -*-
"""Pin the authentication on the xlsx report routes (SEC-8).

`report_xlsx/controllers/main.py:27,52` overrides two of Odoo's report endpoints
with a **bare** `@route()`:

    @route()
    def report_routes(self, reportname, docids=None, converter=None, **data):

Odoo requires the decorator on an overriding controller method but allows its
arguments to be omitted, in which case the routing is merged from the parent
(`odoo/http.py:933`, `merged_routing.update(submethod.original_routing)`). So the
bare form does not *choose* an authentication level — it inherits whatever the
core route happens to declare, silently and for ever.

Today that is `auth='user'` on both (`web/controllers/report.py:26,92`), so this
is not an open door. It is an unstated dependency: if a future Odoo release
relaxed either endpoint, an AGPL module three layers down would follow it without
a diff, a warning, or a line in anyone's release notes. Restating the value is
what turns that into a decision.

Only `auth` is passed. The rest of the routing -- the URL paths, `type='http'`,
`website=True`, `readonly=True` -- is deliberately left to merge from the parent,
so this pins the security-relevant setting without freezing route definitions
that legitimately belong upstream.

**What this file deliberately does not do.** SEC-8 also records that
`report_download` returns `_serialize_exception(e)` to the client
(`report_xlsx/controllers/main.py:100-104`), whose `debug` key is
`traceback.format_exc()` -- server paths and code structure, html-escaped so not
XSS but disclosure nonetheless. Fixing that means changing the body of the
`except`, and the body is not separable: every local fix requires copying the
method into this module. `report_xlsx` is **AGPL-3** and this module is
**LGPL-3**, so that copy would place AGPL code inside an LGPL-declared module --
the precise licence mixing LIC-1 exists to track. Trading a low-severity escaped
disclosure for that is a bad bargain, so it is left, recorded, and belongs
upstream as an OCA patch instead.
"""
from odoo.addons.report_xlsx.controllers.main import ReportController
from odoo.http import route


class ReportController(ReportController):

    @route(auth="user")
    def report_routes(self, reportname, docids=None, converter=None, **data):
        return super().report_routes(reportname, docids, converter, **data)

    @route(auth="user")
    def report_download(self, data, context=None, token=None, readonly=True):
        return super().report_download(data, context, token=token, readonly=readonly)

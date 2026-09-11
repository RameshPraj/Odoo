# Copyright 2016 ACSONE SA/NV (<http://acsone.eu>)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
{
    "name": "Date Range",
    "summary": "Manage all kind of date range",
    # 19.0.1.1.0 is a LOCAL deviation from vendored upstream, recorded in
    # VENDORED.md: the three test classes were tagged post_install (TST-8).
    # Bumped so the change is visible to Odoo's version comparison, per UPG-2.
    "version": "19.0.1.1.0",
    "category": "Uncategorized",
    "website": "https://github.com/OCA/server-ux",
    "author": "ACSONE SA/NV, Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "installable": True,
    "depends": ["web"],
    "data": [
        "data/ir_cron_data.xml",
        "security/ir.model.access.csv",
        "security/date_range_security.xml",
        "views/date_range_view.xml",
        "wizard/date_range_generator.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "date_range/static/src/js/*",
        ],
    },
    "development_status": "Mature",
    "maintainers": ["lmignon"],
}

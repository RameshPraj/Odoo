# Part of Odoo. See LICENSE file for full copyright and licensing details.
# `wizard` first: models/bs_accounting_dates.py extends account.lock.dates, which
# is defined in wizard/, and an extension cannot precede its model.
from . import wizard
from . import models

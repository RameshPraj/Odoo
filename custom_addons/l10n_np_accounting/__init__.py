# Part of Odoo. See LICENSE file for full copyright and licensing details.
# `wizard` first. This comment used to say "models/ extends account.lock.dates,
# which is defined in wizard/, and an extension cannot precede its model". That
# is no longer true: nothing in models/ extends that wizard today, and the model
# is now l10n_np.account.lock.dates (UPG-4). The order is kept because it is the
# safe one for a module whose models/ may come to extend something in wizard/,
# not because a specific extension currently depends on it.
from . import wizard
from . import models

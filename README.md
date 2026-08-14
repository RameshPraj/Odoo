# Odoo

[![Build Status](https://runbot.odoo.com/runbot/badge/flat/1/master.svg)](https://runbot.odoo.com/runbot)
[![Tech Doc](https://img.shields.io/badge/master-docs-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/documentation/master)
[![Help](https://img.shields.io/badge/master-help-875A7B.svg?style=flat&colorA=8F8F8F)](https://www.odoo.com/forum/help-1)
[![Nightly Builds](https://img.shields.io/badge/master-nightly-875A7B.svg?style=flat&colorA=8F8F8F)](https://nightly.odoo.com/)

Odoo is a suite of web based open source business apps.

The main Odoo Apps include an [Open Source CRM](https://www.odoo.com/page/crm),
[Website Builder](https://www.odoo.com/app/website),
[eCommerce](https://www.odoo.com/app/ecommerce),
[Warehouse Management](https://www.odoo.com/app/inventory),
[Project Management](https://www.odoo.com/app/project),
[Billing &amp; Accounting](https://www.odoo.com/app/accounting),
[Point of Sale](https://www.odoo.com/app/point-of-sale-shop),
[Human Resources](https://www.odoo.com/app/employees),
[Marketing](https://www.odoo.com/app/social-marketing),
[Manufacturing](https://www.odoo.com/app/manufacturing),
[...](https://www.odoo.com/)

Odoo Apps can be used as stand-alone applications, but they also integrate seamlessly so you get
a full-featured [Open Source ERP](https://www.odoo.com) when you install several Apps.

## This checkout

Odoo 19 Community plus a Nepal localisation suite in [`custom_addons/`](custom_addons) — chart of
accounts and VAT, Bikram Sambat as a platform-wide calendar, Shrawan–Ashar fiscal years, TDS, the IRD
VAT return, loans, and financial statements. Configuration lives in `odoo.conf` (untracked; copy
`odoo.conf.example`).

### Running the server

```powershell
.\run-odoo.ps1 start          # background, waits until genuinely healthy
.\run-odoo.ps1 status         # RUNNING / STOPPED / DEGRADED, with detail
.\run-odoo.ps1 logs-follow
.\run-odoo.ps1 doctor         # read-only diagnostic; changes nothing
.\run-odoo.ps1 stop
```
```bash
./run-odoo.sh start           # same verbs, same exit codes
./run-odoo.sh doctor
./run-odoo.sh stop
```

`help` lists every command. Anything that modifies a database requires naming it explicitly — there is
no default and no "all databases" mode:

```powershell
.\run-odoo.ps1 test    -Db odoo19                        # all custom module suites
.\run-odoo.ps1 upgrade l10n_np_accounting -Db odoo19
```

These scripts are a developer/operator convenience layer, **not** a service manager. In production the
service is systemd — see [`deploy/README.md`](deploy/README.md) — and `run-odoo.sh` refuses to start
when it can see that unit is active.

* [`docs/operations/ODOO_SERVICE_MANAGEMENT.md`](docs/operations/ODOO_SERVICE_MANAGEMENT.md) —
  commands, configuration, safety rules, exit codes
* [`docs/operations/TROUBLESHOOTING.md`](docs/operations/TROUBLESHOOTING.md) — symptom-first fixes
* [`docs/project-review/`](docs/project-review) — the repository audit and its backlog

## Getting started with Odoo

For a standard installation please follow the [Setup instructions](https://www.odoo.com/documentation/master/administration/install/install.html)
from the documentation.

To learn the software, we recommend the [Odoo eLearning](https://www.odoo.com/slides),
or [Scale-up, the business game](https://www.odoo.com/page/scale-up-business-game).
Developers can start with [the developer tutorials](https://www.odoo.com/documentation/master/developer/howtos.html).

## Security

If you believe you have found a security issue, check our [Responsible Disclosure page](https://www.odoo.com/security-report)
for details and get in touch with us via email.

#!/usr/bin/env sh
# Run the custom-module Odoo test suite against the dedicated local staging DB.
# This script is meant to run inside the odoo-staging Podman machine.

set -eu

modules='account_asset_management,account_budget_oca,account_financial_report,account_financial_statements,account_fiscal_year,account_reports_interactive,date_range,l10n_np,l10n_np_accounting,l10n_np_bs,l10n_np_fiscal_year,l10n_np_loan,l10n_np_pos,l10n_np_tds,l10n_np_vat_return,local_ui_tweaks,nepali_calendar_core,report_xlsx,report_xlsx_helper'
tags='/account_asset_management,/account_budget_oca,/account_financial_report,/account_financial_statements,/account_fiscal_year,/account_reports_interactive,/date_range,/l10n_np,/l10n_np_accounting,/l10n_np_bs,/l10n_np_fiscal_year,/l10n_np_loan,/l10n_np_pos,/l10n_np_tds,/l10n_np_vat_return,/local_ui_tweaks,/nepali_calendar_core,/report_xlsx,/report_xlsx_helper'

restart_staging() {
    podman start odoo-staging >/dev/null 2>&1 || true
}
trap restart_staging EXIT

podman stop odoo-staging >/dev/null
podman run --rm --name odoo-staging-tests \
    --network odoo-staging-net \
    --secret odoo-staging-config,target=/etc/odoo/odoo.conf,uid=10001,gid=10001,mode=0440 \
    --volume odoo-staging-filestore:/var/lib/odoo:U \
    localhost/odoo19-np:staging \
    --config=/etc/odoo/odoo.conf \
    --database=odoo_staging \
    --update="$modules" \
    --test-enable \
    --test-tags="$tags" \
    --stop-after-init

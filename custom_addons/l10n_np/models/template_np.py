# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Chart template wiring for Nepal.

The @template decorator is the extension point documented in
odoo/addons/account/models/chart_template.py -- no subclassing, no framework
code. Each method returns data that account.chart.template._load() instantiates
when a company adopts this chart.

Every account reference below MUST exist in
data/template/account.account-np.csv or installation fails with a missing-xmlid
error. That coupling is the reason the skeleton chart cannot simply be emptied.
"""
from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('np')
    def _get_np_template_data(self):
        return {
            'property_account_receivable_id': 'l10n_np_100201',
            'property_account_payable_id': 'l10n_np_200101',
            'code_digits': '6',
        }

    @template('np', 'res.company')
    def _get_np_res_company(self):
        return {
            self.env.company.id: {
                'account_fiscal_country_id': 'base.np',
                'bank_account_code_prefix': '1001',
                'cash_account_code_prefix': '1001',
                'account_default_pos_receivable_account_id': 'l10n_np_100202',
                'account_journal_suspense_account_id': 'l10n_np_100102',
                'default_cash_difference_income_account_id': 'l10n_np_400302',
                'default_cash_difference_expense_account_id': 'l10n_np_500909',
                'income_currency_exchange_account_id': 'l10n_np_400301',
                'expense_currency_exchange_account_id': 'l10n_np_500903',
                'transfer_account_id': 'l10n_np_100101',
                'account_journal_early_pay_discount_loss_account_id': 'l10n_np_501107',
                'account_journal_early_pay_discount_gain_account_id': 'l10n_np_400304',
                'account_sale_tax_id': 'VAT_S_NP_13',
                'account_purchase_tax_id': 'VAT_P_NP_13',
                'income_account_id': 'l10n_np_400100',
                'expense_account_id': 'l10n_np_500200',
                'account_stock_journal_id': 'inventory_valuation',
                'account_stock_valuation_id': 'l10n_np_100502',
            },
        }

    @template('np', 'account.journal')
    def _get_np_account_journal(self):
        return {
            'tax_adjustment': {
                'name': 'Tax Adjustments',
                'code': 'TA',
                'type': 'general',
                'show_on_dashboard': True,
            },
        }

    @template('np', 'account.account')
    def _get_np_account_account(self):
        return {
            'l10n_np_100502': {
                'account_stock_variation_id': 'l10n_np_500905',
            },
        }

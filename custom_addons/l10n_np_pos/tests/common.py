# -*- coding: utf-8 -*-
"""Deterministic Point of Sale fixtures which do not depend on demo data."""


def create_pos_config(env, name):
    company = env.company
    sale_journal = env["account.journal"].search([
        ("company_id", "=", company.id),
        ("type", "=", "sale"),
    ], limit=1)
    assert sale_journal, "the test company has no sales journal"
    return env["pos.config"].create({
        "name": name,
        "company_id": company.id,
        "journal_id": sale_journal.id,
        "invoice_journal_id": sale_journal.id,
    })

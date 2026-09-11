# -*- coding: utf-8 -*-
"""Give the existing TDS certificate sequence an owner (ACC-6).

The module shipped one `ir.sequence` with `company_id = False`. Because
`next_by_code` matches `company_id in (False, env.company.id)`, every company on
the database drew from that single row, so a certificate issued by one company
advanced the numbering of all of them.

The data file now scopes the record to the main company, but `noupdate="1"` means
that change does not reach a database where the record already exists -- which is
the correct behaviour for a sequence, since re-applying it would reset
`number_next` and reissue numbers that may already have been printed. So the
conversion happens here instead.

**Converted in place, never replaced.** Creating a fresh company-scoped sequence
and leaving the global one behind would restart numbering at 1 and hand out
certificate numbers a real deployment had already issued. Only `company_id` is
written; `number_next` is left exactly as it stands.

Companies other than the main one are deliberately not given a sequence here.
`_certificate_sequence()` creates one on first use, which keeps the "one series
per issuer" rule true for companies created after this migration as well -- a
migration cannot cover those, so it should not pretend to.
"""
import logging

_logger = logging.getLogger(__name__)

SEQUENCE_CODE = "l10n_np.tds.certificate"


def migrate(cr, version):
    if not version:
        return

    cr.execute(
        """
        SELECT s.id, c.id
          FROM ir_sequence s
         CROSS JOIN LATERAL (
               SELECT id FROM res_company ORDER BY id LIMIT 1
         ) AS c
         WHERE s.code = %s AND s.company_id IS NULL
        """,
        [SEQUENCE_CODE],
    )
    rows = cr.fetchall()
    if not rows:
        _logger.info("ACC-6: no company-less TDS certificate sequence to convert.")
        return

    for sequence_id, company_id in rows:
        cr.execute(
            "UPDATE ir_sequence SET company_id = %s WHERE id = %s",
            [company_id, sequence_id],
        )
        # No counter is named here on purpose. With implementation='standard'
        # the live counter is a PostgreSQL sequence (`ir_sequence_<id>`) and the
        # `number_next` COLUMN is stale -- on this database it read 1 while the
        # real next value was 320. Quoting the column would have put a wrong
        # number in the log of a statutory-numbering migration, which is the one
        # place a wrong number should not appear. The counter is untouched
        # because only `company_id` is written.
        _logger.info(
            "ACC-6: TDS certificate sequence %s assigned to company %s. Only "
            "company_id was written, so the existing counter is preserved and "
            "no certificate number can be reissued.",
            sequence_id, company_id,
        )

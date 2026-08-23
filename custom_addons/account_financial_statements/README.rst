==============================
Account Financial Statements
==============================

Balance Sheet, Profit & Loss and Cash Flow, rendered on screen and to PDF from one
QWeb template each.

Every figure is a link
======================

Each line carries ``res-model``, ``res-id`` and ``view-type`` attributes, so Odoo's
own report drill-down turns it into a link to the journal items behind it. Those
attributes are inert in a PDF, which is why one template serves both screen and
paper rather than two diverging ones.

Each statement is registered twice as an ``ir.actions.report`` sharing one
``report_name`` -- once ``qweb-html`` and once ``qweb-pdf`` -- which is what makes
core's Print button work.

An anomaly panel flags the things that make a statement wrong rather than ugly:
a sheet that does not balance, accounts with no type, and entries outside the
period.

Known gaps
==========

**ACC-2**: prior-year unallocated earnings are not carried, so the Balance Sheet
stops balancing after the first fiscal year. That needs an accountant's decision,
not a code change.

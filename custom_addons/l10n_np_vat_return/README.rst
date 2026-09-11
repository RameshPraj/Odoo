==========================
Nepal VAT Return (IRD)
==========================

A VAT return driven by a **versioned, configurable form definition** rather than a
hard-coded layout.

No form ships with this module
==============================

That is deliberate, and the most important thing to understand before using it.
The IRD return layout, its box numbers, and which tax tags feed each box must be
supplied by an accountant. Inventing them would produce a plausible-looking and
wrong filing, so the tables ship empty.

::

    l10n_np.vat.return.form    one version of the statutory form
      └── l10n_np.vat.return.box    one box, over tax tags or a formula

Forms are versioned with in-force dates: when the IRD revises the form, add a new
version. Returns already filed keep rendering against the version that applied at
the time, which is a legal requirement for reprints.

Box amounts come from tax tags on journal items, so every figure traces to the
ledger and can be drilled into during an audit.

The formula grammar
===================

A formula box may use other box codes, numbers and ``+ - * / ( )``. Nothing else:
the expression is parsed and walked, not ``eval``-ed, and exponentiation is
rejected structurally (audit finding **SEC-3** -- ``9**9**9`` used to be accepted
and would occupy the worker indefinitely).

Known gaps
==========

The IRD box layout itself is **SME-gated** and absent from this repository, so a
computed return is not yet a usable filing.

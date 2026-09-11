# -*- coding: utf-8 -*-
"""IRD VAT return for Nepal, driven by a versioned form definition.

DESIGN INTENT — READ BEFORE EDITING
-----------------------------------
No form definition ships with this module. The IRD return layout, its box numbers
and which tax tags feed each box must be supplied by an accountant; inventing
them would produce a plausible-looking but wrong filing.

The form is therefore data:

    l10n_np.vat.return.form   one version of the statutory form
      └── l10n_np.vat.return.box   one box, with a formula over tax tags

Forms are VERSIONED with an effective-from date. When the IRD changes the form, a
new version is added; returns already filed keep rendering against the version
that was in force, which is a legal requirement for reprints.

Box amounts are computed from tax tags on posted journal items, so every figure
traces back to the ledger and can be drilled into during an audit.
"""
import ast
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class VatReturnForm(models.Model):
    _name = 'l10n_np.vat.return.form'
    _description = 'Nepal VAT Return Form (version)'
    _order = 'date_from desc'

    name = fields.Char(required=True, help="e.g. 'IRD VAT Return 2082 revision'.")
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True)  # SCH-1: the SEC-2 record rule filters on it
    date_from = fields.Date(
        string='In force from', required=True,
        help="First date this version of the form applies to.")
    date_to = fields.Date(string='In force to')
    active = fields.Boolean(default=True)
    box_ids = fields.One2many('l10n_np.vat.return.box', 'form_id')
    note = fields.Text(help="Source of the layout, e.g. IRD circular reference.")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(_("'In force to' precedes 'In force from'."))

    @api.model
    def _form_for_date(self, date, company=None):
        company = company or self.env.company
        form = self.search([
            ('company_id', '=', company.id),
            ('date_from', '<=', date),
            '|', ('date_to', '=', False), ('date_to', '>=', date),
        ], limit=1)
        if not form:
            raise UserError(_(
                "No VAT return form is configured for %(date)s.\n\n"
                "An authorised user must define it under Accounting > "
                "Configuration > VAT Return Forms, mapping each IRD box to the "
                "tax tags that feed it. The layout is deliberately not shipped "
                "with this module because it is set by the IRD.",
                date=date))
        return form


class VatReturnBox(models.Model):
    _name = 'l10n_np.vat.return.box'
    _description = 'Nepal VAT Return Box'
    _order = 'sequence, code'

    form_id = fields.Many2one(
        'l10n_np.vat.return.form', required=True, ondelete='cascade',
        index=True)  # SCH-1: traversed for every one2many read
    # Stored so the multi-company record rule can filter on it (SEC-2). A box has
    # no company of its own -- it belongs to whichever company owns the form
    # version. Mirrors l10n_np.loan.line and l10n_np.tds.certificate.line.
    company_id = fields.Many2one(related='form_id.company_id', store=True,
                                 index=True)  # SCH-1
    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, help="IRD box number or code.")
    label_en = fields.Char(string='Label (English)', required=True)
    label_ne = fields.Char(string='Label (Nepali)')
    box_type = fields.Selection(
        [('tags', 'Sum of tax tags'),
         ('formula', 'Formula over other boxes'),
         ('heading', 'Heading only')],
        required=True, default='tags')
    tag_ids = fields.Many2many(
        'account.account.tag', string='Tax tags',
        domain="[('applicability', '=', 'taxes')]",
        help="Journal-item tax tags summed into this box.")
    formula = fields.Char(
        help="Simple expression over other box codes, e.g. '11 - 21'. "
             "Only box codes, numbers and + - * / are allowed.")
    sign = fields.Selection(
        [('1', 'As recorded'), ('-1', 'Reverse sign')],
        default='1', required=True,
        help="Tax tags on sales carry credit balances. Reverse the sign where the "
             "form expects a positive figure.")

    @api.constrains('box_type', 'tag_ids', 'formula')
    def _check_definition(self):
        for box in self:
            if box.box_type == 'tags' and not box.tag_ids:
                raise ValidationError(_(
                    "Box %s is a tag box but has no tax tags.", box.code))
            if box.box_type == 'formula' and not box.formula:
                raise ValidationError(_(
                    "Box %s is a formula box but has no formula.", box.code))


class VatReturn(models.Model):
    _name = 'l10n_np.vat.return'
    _description = 'Nepal VAT Return'
    _order = 'date_to desc'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, copy=False)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True)  # SCH-1: the SEC-2 record rule filters on it
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    form_id = fields.Many2one(
        'l10n_np.vat.return.form', string='Form version', readonly=True,
        help="Frozen when the return is computed, so a reprint uses the form that "
             "was in force at the time.")
    state = fields.Selection(
        [('draft', 'Draft'), ('computed', 'Computed'), ('filed', 'Filed')],
        default='draft', tracking=True)
    line_ids = fields.One2many('l10n_np.vat.return.line', 'return_id', readonly=True)
    target_move = fields.Selection(
        [('posted', 'Posted entries only'), ('all', 'Posted and draft')],
        default='posted', required=True)

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise ValidationError(_("The period end precedes its start."))

    # ------------------------------------------------------------------
    def _tag_balance(self, tags, sign):
        """Sum journal-item balances carrying any of ``tags`` in the period."""
        self.ensure_one()
        if not tags:
            return 0.0
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('tax_tag_ids', 'in', tags.ids),
        ]
        domain.append(('parent_state', '=', 'posted') if self.target_move == 'posted'
                      else ('parent_state', 'in', ('posted', 'draft')))
        groups = self.env['account.move.line']._read_group(
            domain, groupby=[], aggregates=['balance:sum'])
        total = (groups[0][0] or 0.0) if groups else 0.0
        return total * int(sign)

    def action_compute(self):
        for ret in self:
            # A filed return is a submitted statutory document. Recomputing one in
            # place would change a filed figure with no trace, and `action_compute`
            # checked nothing -- so this was reachable by any user who could edit a
            # return at all. Resetting to draft first is deliberate friction, and it
            # is visible in the state field afterwards. Found while fixing SEC-6,
            # which is about the same document being rewritten by the wrong hands.
            if ret.state == 'filed':
                raise UserError(_(
                    "%s has been filed. Reset it to draft before recomputing, so "
                    "that the change to a filed return is visible.", ret.name))
            form = self.env['l10n_np.vat.return.form']._form_for_date(
                ret.date_to, ret.company_id)
            ret.line_ids.unlink()
            ret.form_id = form

            values = {}
            # tag boxes first, so formula boxes can reference them
            for box in form.box_ids.filtered(lambda b: b.box_type == 'tags'):
                values[box.code] = ret._tag_balance(box.tag_ids, box.sign)
            for box in form.box_ids.filtered(lambda b: b.box_type == 'formula'):
                values[box.code] = ret._eval_formula(box, values)

            for box in form.box_ids:
                ret.env['l10n_np.vat.return.line'].create({
                    'return_id': ret.id,
                    'box_id': box.id,
                    'sequence': box.sequence,
                    'code': box.code,
                    'label_en': box.label_en,
                    'label_ne': box.label_ne,
                    'amount': 0.0 if box.box_type == 'heading' else values.get(box.code, 0.0),
                    'is_heading': box.box_type == 'heading',
                })
            ret.state = 'computed'
        return True

    #: The only AST node types a box formula may contain. Exponentiation is absent
    #: on purpose and cannot be re-admitted by a regex slip: see _eval_formula.
    _FORMULA_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div)
    _FORMULA_UNARYOPS = (ast.UAdd, ast.USub)

    def _eval_formula(self, box, values):
        r"""Evaluate a box formula over other box codes. Never `eval`.

        The grammar is deliberately tiny: box codes, numbers, `+ - * / ( )`.

        **SEC-3.** This used to substitute the codes, check the result against
        `re.fullmatch(r"[0-9eE+\-*/(). ]*")` and hand it to `eval`. Because `*`
        appears once in that character class, `**` matched it -- a character class
        cannot express "one star but not two". `9**9**9` passed the check and then
        occupied the worker computing a number with hundreds of millions of digits.
        With `workers = 0` that is the entire server, and `limit_time_real = 0` on
        this host means nothing reclaims it. RCE was already blocked and tested;
        this was the denial of service beside it.

        Now the substituted expression is parsed and walked, and evaluation is done
        by this method rather than by Python. `ast.Pow` simply is not in
        `_FORMULA_BINOPS`, so `**` is rejected structurally -- there is no pattern
        to get wrong. Formulas come from an accountant configuring boxes, so this
        is not a hostile input in normal use; it is one keystroke away from
        wedging the server, which is enough.
        """
        expr = (box.formula or '').strip()
        if not expr:
            return 0.0

        if values:
            # Substituted in one pass, longest code first, and only where the code
            # is not part of a longer number. The old sequential str.replace could
            # match digits inside a float it had already substituted -- with a box
            # coded '0', an earlier '200.0' became '2<subst>0.0'.
            pattern = re.compile(
                r'(?<![\d.])(?:{})(?![\d.])'.format('|'.join(
                    re.escape(code) for code in sorted(values, key=len, reverse=True))))
            expr = pattern.sub(lambda m: repr(float(values[m.group(0)])), expr)

        def fail(detail):
            return UserError(_(
                "Box %(code)s has a formula that could not be resolved: %(f)s\n\n"
                "Use only other box codes, numbers and + - * / ( ). %(detail)s",
                code=box.code, f=box.formula, detail=detail))

        try:
            tree = ast.parse(expr, mode='eval')
        except SyntaxError as exc:
            raise fail(_("It is not a valid expression.")) from exc

        def evaluate(node):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                    raise fail(_("Only numbers are allowed."))
                return float(node.value)
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, self._FORMULA_UNARYOPS):
                operand = evaluate(node.operand)
                return operand if isinstance(node.op, ast.UAdd) else -operand
            if isinstance(node, ast.BinOp) and isinstance(node.op, self._FORMULA_BINOPS):
                left, right = evaluate(node.left), evaluate(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                if right == 0.0:
                    raise fail(_("It divides by zero."))
                return left / right
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                raise fail(_("Exponentiation is not allowed."))
            if isinstance(node, ast.Name):
                # An unresolved box code reaches here as a bare name.
                raise fail(_("%s is not a known box code.", node.id))
            raise fail(_("%s is not allowed.", type(node).__name__))

        return evaluate(tree.body)
    def action_file(self):
        for ret in self:
            if ret.state != 'computed':
                raise UserError(_("Compute the return before filing it."))
        self.write({'state': 'filed'})

    def action_draft(self):
        self.write({'state': 'draft'})


class VatReturnLine(models.Model):
    _name = 'l10n_np.vat.return.line'
    _description = 'Nepal VAT Return Line'
    _order = 'sequence, code'

    return_id = fields.Many2one(
        'l10n_np.vat.return', required=True, ondelete='cascade',
        index=True)  # SCH-1: traversed for every one2many read
    # As on l10n_np.vat.return.box: stored purely so the record rule has a column
    # to filter on (SEC-2). A line's company is the filed return's company.
    company_id = fields.Many2one(related='return_id.company_id', store=True,
                                 index=True)  # SCH-1
    box_id = fields.Many2one('l10n_np.vat.return.box', readonly=True,
                             index=True)  # SCH-1
    currency_id = fields.Many2one(related='return_id.currency_id')
    sequence = fields.Integer()
    code = fields.Char()
    label_en = fields.Char()
    label_ne = fields.Char()
    amount = fields.Monetary()
    is_heading = fields.Boolean()

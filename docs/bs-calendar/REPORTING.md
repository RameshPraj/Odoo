# Reporting

> **Built.** `models/ir_qweb_fields.py` implements the design below: both
> `value_to_html` overrides, the `bs_report_output` company setting with `ad` / `bs` / `both`, a
> per-field `t-options="{'calendar': 'ad'}"` escape hatch, and `format_date_bs` as a new template
> name. Asserted in `tests/test_timezone_and_reports.py`, including that two readers with opposite
> personal calendars are handed the identical document.
>
> One correction to what follows: the plan asserted that core supplies a `format_date` in the QWeb
> environment which we must be careful not to shadow. It does not — `mail.render.mixin` and the EDI
> modules each inject their own into their own values dict. So there is nothing to shadow; the
> requirement is simply that we never claim the name, which is now tested.

## State before this pass: no BS in any report, anywhere

Stated as a measured absence:

- **No** `format_date` / `format_datetime` override in `custom_addons`.
- **No** `ir.actions.report` record in any `l10n_np*` module.
- **No** QWeb report template in any `l10n_np*` module.
- **No** `ir.qweb` / `ir.qweb.field.date` extension.
- `bs.format_bs()` exists and has **zero callers**.

So every printed PDF, every xlsx export, and the TDS certificate and VAT return outputs render
Gregorian. BS is screen-only. This is a green field.

## The seam: `ir.qweb.field.*`

Override `value_to_html` on both converters. This is an **officially documented** extension point —
`ir_qweb.py:686-687`: *"to customize `t-field` rendering, subclass `ir.qweb.field` and create new
models called `ir.qweb.field.{widget}`"* — dispatched dynamically at `:2761-2762`, with core
precedent in `html_editor/models/ir_qweb_fields.py`.

```
ir.qweb.field.date      → value_to_html   (ir_qweb_fields.py:272-274)
ir.qweb.field.datetime  → value_to_html   (ir_qweb_fields.py:294-332)
```

**Both must be overridden, because they do not share an implementation.** An asymmetry worth
knowing: `.date` delegates to `tools.format_date`, while `.datetime` calls **Babel directly**
(`:328-332`) after `context_timestamp`. Overriding only `tools.format_date` would leave every
`t-field` on a Datetime rendering Gregorian — a confusing half-state.

This single seam covers `t-field` and `t-out t-options-widget` output across **reports, website and
portal** — the majority of business-document dates.

## What we deliberately do NOT do

**Monkeypatching `tools.misc.format_date`.** There are **218 call sites** across ~130 files, none
funnelled through a chokepoint. Worse, roughly fifteen of them build **legal e-invoicing payloads** —
`account_edi_ubl_cii/models/account_edi_xml_cii_facturx.py`,
`l10n_es_edi_tbai/models/l10n_es_edi_tbai_document.py` and similar. Those must stay Gregorian; a BS
date in a UBL/CII document is a malformed legal artefact.

Patching is also unreliable there: `mail_render_mixin.py:26-41` and `ir_qweb_fields.py:17` bind the
function with `from … import`, so patching the module attribute after import does not reach them.

Instead: the `ir.qweb.field.*` override above, plus an explicit `format_date_bs(env, value)` helper
for the specific human-facing call sites we choose to convert.

**A further gap to know about:** plain `ir.actions.report` QWeb has **no `format_date` in its render
context at all** (`ir_qweb.py:1294-1329`, `ir_actions_report.py:1125-1142`). Only `MailRenderMixin`
injects it (`mail_render_mixin.py:311-333`). So a report template cannot call `format_date(...)`
unless it goes through the mail renderer — which is why `t-field` is the right vehicle.

## Mail templates

Add a BS-aware helper into `MailRenderMixin._render_eval_context()` (`:311-333`) via `super()`-and-
update — **as a new key**, e.g. `format_date_bs`.

**Do not shadow the existing `format_date` key.** That would silently change every existing mail
template, including the invoice and EDI ones.

## Output format — configurable, resolved centrally

Per the brief, three modes, chosen by a company setting and applied by the central formatter — never
hard-coded per report:

| Mode | Output |
|---|---|
| `ad` | `2026-08-14` |
| `bs` | `2083-04-29 BS` |
| `both` | `2083-04-29 BS (2026-08-14 AD)` |

`both` is the sensible default for statutory documents: the BS date is what a Nepali reader expects,
and the AD date keeps the document reconcilable against banking and audit records. Numerals follow
the same `bs_digits` company setting used on screen, so a document and the screen agree.

## Exports stay Gregorian — a hard rule

**The single most dangerous coupling in this project:**

`Datetime.convert_to_export` (`fields_temporal.py:287-289`) internally calls
`convert_to_display_name` (`:291-294`).

So overriding `convert_to_display_name` "just for display" **silently corrupts every CSV and XLSX
export and breaks re-import round-trips.** Neither may be touched.

Export must remain Gregorian ISO for round-trip fidelity. If BS export is genuinely wanted, add a
**separate** computed Char column that users can select in the export dialog — additive, and it
cannot break anything.

Import is likewise safe *provided* `res.lang.date_format` is never changed:
`base_import.py:700` sniffs incoming CSV dates using the user's `res.lang.date_format` **first**, so
a BS pattern there would make the importer try to parse Gregorian files as BS. The architecture
already rules out the lang-variant approach for other reasons; this is a second reason.

## xlsx

The vendored `report_xlsx_helper` carries its own cell-format dictionaries
(`report_xlsx_format.py:26-28,50-52`) which are xlsx number formats, unrelated to BS. Native xlsx
date cells are written from `date`/`datetime` objects and would need to become **strings** to carry
BS — losing sortability and Excel date arithmetic.

**Recommendation: leave xlsx Gregorian.** A BS column can be added alongside where a report needs it.
Backlogged rather than done, deliberately.

## Backlog

| ID | Item | Priority | Effort |
|---|---|---|---|
| BSR-1 | Override `ir.qweb.field.date` and `.datetime` `value_to_html` | P1 | S |
| BSR-2 | `format_date_bs` helper + company output-mode setting (`ad`/`bs`/`both`) | P1 | S |
| BSR-3 | Add `format_date_bs` to `MailRenderMixin` eval context as a **new** key | P2 | S |
| BSR-4 | Convert the TDS certificate and VAT return outputs to BS/both | P1 | M |
| BSR-5 | Decide per-document defaults with the SME (invoice, statement, certificate) | P2 | S |
| BSR-6 | Optional BS column for xlsx exports | P3 | M |

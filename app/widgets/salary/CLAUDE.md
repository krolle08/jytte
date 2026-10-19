# salary widget

Net pay per person, computed from each one's skattekort. Powers
`/salary` and hands `/budget` a derived income row.

No network, no credential, no AI. The inputs are eleven numbers you
type once; everything else is arithmetic.

## Files

| File | What |
|---|---|
| `calc.py` | the payroll arithmetic. Pure, no DB, no imports from the app |
| `db_salary.py` | `salary_profiles` storage, parsers, formatters, `person_row()` |
| `routes.py` | the HTMX form: `/card`, `/form`, `/save` |
| `fetch.py` | widget state: every person, computed |
| `../../templates/_sal_card.html` | one person, figures or form |
| `../../templates/jy_salary.html` | the page, which just loops the partial |

## Why the skattekort and not a tax model

Your `traekprocent` already encodes kommuneskat, kirkeskat, bundskat,
beskaeftigelsesfradrag and your personfradrag. SKAT computed it from
your forskudsopgoerelse. Recomputing all of that here would mean
reproducing SKAT's work, getting it slightly wrong, and maintaining a
rates table every January, to arrive at a number already printed on
the card.

The limitation that buys, stated on the page rather than hidden: the
calculation is **exact at the current income and says nothing about
what a raise would cost**. From 2026 that matters more than it used
to, because the old top bracket is now three (mellemskat, topskat,
top-topskat) and a card issued mid-year keeps withholding at the rate
it was issued for. Closing that gap needs a second, small bracket
model, and it does not belong in this widget.

## Three things that must not change quietly

1. **AM-bidrag rounds half-up to whole kroner. A-skat rounds DOWN.**
   Both derived from a real Danloen payslip, not assumed. Using one
   rule for both throws the net out by a krone or two every month.
2. **A profile needs gross AND traekprocent.** `REQUIRED` in
   `db_salary.py`. Gross alone used to count as configured, which
   rendered a salary with zero A-skat. `derived_income_entries()`
   reads the same flag, so a half-filled profile cannot feed the
   budget a wrong income either.
3. **Money is oere and rates are basis points, both INTEGER.** 36% is
   `3600`, 10,18% is `1018`. No float enters a salary figure at any
   point, which is project rule 1 applied to payroll.

## Route shape is load-bearing

Widget routers mount under `/widgets/<name>/` and are included in
`app/main.py` **before** the generic `POST /widgets/{name}/refresh`,
`/state` and `/error`. A save route written `POST /{person}` matches
`/widgets/salary/refresh` and silently steals all three. That is why
every path here ends in a verb, and why
`test_save_route_path_cannot_shadow_the_generic_widget_endpoints`
exists.

## The viewport rule

`_sal_card.html` renders both the figures and the form, and every
endpoint returns it. The page swaps it `outerHTML` on `#sal-<slug>`,
so opening the form on one person does not repaint the other and
nothing scrolls. A bad input re-renders the form with what was typed
still in it; returning 400 would leave the form untouched and silent,
which reads as a broken Save button.

## Editing the profile

`/salary` -> **Udfyld** or **Redigér** on a person's card. The two
figures under "Fra forskudsopgoerelsen" come from skat.dk; the rest
come off a payslip. A blank field means zero. Nothing here is guessed:
with no traekprocent the card says what is missing rather than
printing a net salary that is too high.

## Tests

```bash
docker compose exec jytte python -m pytest tests/test_salary_calc.py tests/test_salary_form.py -q
```

`test_salary_calc.py` is a characterization test: a real payslip is the
oracle, and if the engine stops reproducing it the engine is wrong.
`test_salary_form.py` covers parsing, the round trip back into an
input, and two couplings that would otherwise break in silence -
`calc_inputs()` against `calc.compute`'s signature, and the form's
field list against `FIELDS`.

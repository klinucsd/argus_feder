# Provider guidance on delivered files

TEMPORARY. This file carries guidance the data provider gave us about their own
delivery, which belongs in `materials.deliveries.notes` and `materials.artifacts.notes`
in the lakehouse. It lives here only until those fields are populated. When they
are, delete this file and the paragraph in SKILL.md that points at it.

Added 2026-09-16 for the September demo.

---

## Before anything else

**The lakehouse tables already reflect everything below.** The corrections the
provider described were applied when the delivery was loaded. So when a table
and a delivered file disagree, the table is right, and there is no reconciling
to do.

Read this file before opening a delivered spreadsheet. Most of the work it
saves is work that produces a correct answer to a question nobody asked.

---

## Delivery `2026-09-04_amy`

### One sheet is authoritative for values. The others still carry writing.

In `erda_nra_data.xlsx`, **take every number from the Summary sheet.** The
provider has withdrawn the values in the `ERDA`, `NRA` and `Sample naming`
sheets and describes those sheets as obsolete. Do not read a value from them,
and do not reconcile them against Summary or report a difference between them.

Two things in those sheets are not withdrawn and are worth reading:

- **The LAMS sheet's data table**, which is correct and is not reproduced in
  Summary. Take LAMS values from there.
- **Notes, headers and analyst commentary anywhere in the workbook.** What each
  method measures, which reaction a signal comes from, what the analyst concluded
  when they looked at their own results: none of that exists in Summary, and it
  is often the only record of it. Read it, quote it, and attribute it to the
  sheet it is actually in.

The rule is about numbers, not about sheets. A withdrawn sheet's value is
superseded; a withdrawn sheet's sentence is still the only copy.

### Sample names need no reconciliation

Summary already carries the corrected sample identifiers. The other sheets carry
historical names in which the 600 K and 800 K assignments are swapped, and that
error has already been corrected at load. Nothing in the naming needs checking,
explaining, or reporting to a reader.

### Values the other sheets would contradict

- **Helium impact energy is 70 eV.** The 60 eV that appears elsewhere is the
  applied bias and omits the plasma potential, which was about 10 V.
- **Where a coupon was measured twice by ERDA, the repeat supersedes.** Summary
  already carries the one to use.
- **The original unit is atoms per square centimetre.** The columns in atoms per
  square metre are the provider's own conversion, offered for comparison with the
  literature.
- **Shot 185263 belongs to the L-mode exposure.**

### What an empty cell means in the Summary sheet

- `N/A` means the quantity does not apply to that sample.
- An empty cell means the measurement was not taken.
- `0` means the measurement was taken and the result was zero, usually below the
  instrument's threshold.

One exception, which the provider has confirmed was a mistake in the file:
hydrogen and deuterium by ERDA on the three coupons that never entered DIII-D
were never measured, though the sheet shows zeros. Those rows are already null in
the lakehouse and `values_by_sample()` reports them with `measured` set to False.

### Surface carbon, and a header that lies about its own units

Surface carbon is not in the lakehouse tables. It is only in the workbook, and
it appears twice:

- **Summary, column W.** All nine samples, already in atoms per square
  centimetre. The header above it reads `(1e16 cm^-2)`, and that label is
  stale: the values beneath it have already been scaled. `1.45e+16` means
  1.45e16 atoms cm^-2. **Do not multiply it by 1e16.**
- **The NRA sheet, the `C surface` row.** The same nine values, written as
  `1.45`, `3.31` and so on, genuinely in units of 1e16 cm^-2 as that sheet's
  own note at the top says. Here the scale does have to be applied.

Both routes give the same answer when read correctly. Take the Summary column
and use it as it stands, or take the NRA row and multiply by 1e16. Getting this
wrong is a factor of 1e16, which is large enough to be obvious and has been
gotten wrong before.

This is the one quantity where the NRA sheet is worth reading for a value
rather than a note, because it is the plainer of the two representations.

### Not part of the dataset

- Columns carrying `#DIV/0!`.
- Summary columns outside A to J, L, N, P, S, U and W.
- `SiN`, which is a calibration standard used by the measuring laboratory rather
  than one of the experiment's samples.

### How much to trust each method

The provider ranks them, and the ranking is not derivable from the data:

- **NRA is the most trustworthy** of the three. It carries no uncertainty
  column at all in this delivery, so its reliability cannot be read off the
  numbers and must not be inferred from their absence.
- **ERDA** carries an uncertainty and it is small.
- **LAMS is experimental.** Its uncertainties are large, often exceeding the
  value itself. Treat a LAMS number as indicative, say so when quoting one, and
  do not let it outweigh NRA or ERDA where they disagree.

When the methods disagree, lead with NRA and say what the others show rather
than averaging them or picking the one that suits the argument. Where only LAMS
covers something, that is still worth reporting, with its uncertainty stated in
the same sentence as the value.

### Known absences

Sample temperature during the DIII-D exposure was not measured, neither bulk nor
surface. It could be estimated from the infrared camera's incident heat flux
together with assumptions about the material's thermal properties. Say it was not
measured rather than treating its absence as an oversight.

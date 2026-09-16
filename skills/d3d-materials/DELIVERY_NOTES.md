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

### The workbook has one authoritative sheet

In `erda_nra_data.xlsx`, use the **Summary** sheet. The `ERDA`, `NRA` and
`Sample naming` sheets are superseded: the provider has withdrawn the values in
them and describes them as obsolete. Do not read them, and do not reconcile them
against Summary.

One exception. The **LAMS** worksheet's data table is correct, and its contents
are not reproduced in Summary, so read that sheet when you need LAMS values.

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

### Not part of the dataset

- Columns carrying `#DIV/0!`.
- Summary columns outside A to J, L, N, P, S, U and W.
- `SiN`, which is a calibration standard used by the measuring laboratory rather
  than one of the experiment's samples.

### Known absences

Sample temperature during the DIII-D exposure was not measured, neither bulk nor
surface. It could be estimated from the infrared camera's incident heat flux
together with assumptions about the material's thermal properties. Say it was not
measured rather than treating its absence as an oversight.

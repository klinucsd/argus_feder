---
name: d3d-relational-db
description: "DIII-D signal catalog and shot-metadata database (d3drdb), as a trimmed plasma-shots-only local copy. REQUIRED for any question about what a DIII-D signal, tag or pointname MEANS -- including questions phrased as explanation rather than data, such as 'what is FS02UPDA', 'what does EFIT01::BT0VAC mean in plain English', 'what does this signal measure', 'what are its units'. Those are catalog lookups, not general knowledge: DIII-D tag names are not self-describing and answering from the name has produced wrong meanings, so call explain_signal(tag) and quote what it returns. Also REQUIRED for per-shot scalars (elongation, plasma current, pulse length, neutron yield, peak beta_N, disruption time) -- call report_shot_summary(shot, fields) and quote it -- and for which shots exist in a range, plasma-shot filtering, and which MDSplus tree and path a signal lives in. Catalog and metadata only, NOT the raw time series: for a waveform use d3d-shot-fetcher / d3d-filterscopes / toksearch-mds."
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: DeepTok
  version: "1.0"
---

# d3d-relational-db -- DIII-D Relational Database (d3drdb)

## What this is, and what it is NOT

d3drdb is DIII-D's shot-metadata database (shot list, physics summary scalars,
signal catalog). This skill queries a **trimmed, local, read-only copy** --
plasma-type shots only, 5 tables, no legacy/unusable data. It is NOT a live
connection to GA's real d3drdb server, and it is NOT the raw signal data --
d3drdb tells you a shot's characterization and what signals exist; to fetch an
actual waveform, use `d3d-shot-fetcher`, `d3d-filterscopes`, or `toksearch-mds`.

## No fdp wrapper needed

This is a local SQLite file -- no network access, no Pelican, no `fdp`. Run
scripts with plain `python script.py`.

## Importing the helper

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-relational-db"))
from d3d_relational_db import (query_d3drdb, plasma_shots_in_range, shot_summary,
                               search_signal_catalog, report_shot_summary, explain_signal)
```

## Convenience functions (prefer these over writing raw SQL)

```python
plasma_shots_in_range(190000, 195000)   # -> [190000, 190001, ...] list of shot numbers
shot_summary(165340)                     # -> dict of SUMMARIES columns for one shot, or None
search_signal_catalog("kappa")           # -> [{"Name", "Tree", "Full_Path", "Description", "Units"}, ...]
query_d3drdb(sql, params=())             # -> list[dict], for anything else

report_shot_summary(144921, ["gas", "neutrons"])   # -> ANSWER TEXT to quote verbatim
explain_signal(r"\FS02UPDA")                        # -> ANSWER TEXT to quote verbatim
```

## Answer summary questions with `report_shot_summary()`, and quote it

**When the question asks for per-shot scalars, call `report_shot_summary(shot,
fields)` and quote the string it returns.** It reads each field straight from
the row and formats it, so there is nothing left to restate:

```
Shot 144921 (values read directly from d3drdb SUMMARIES):
  gas: D2
  neutrons: 3.98594e+15
  betanmax: 3.1168
  t_betanmax: 3.905
```

An unknown field name comes back as `NOT A COLUMN in SUMMARIES` and a missing
shot as `no SUMMARIES row in d3drdb`, so neither can be mistaken for a
measurement that happens to be absent.

**Why this is a rule and not a suggestion.** An answer to exactly this question
ran the right query on the right columns for shot 144921 -- `s.get("neutrons")`,
`s.get("betanmax")`, `s.get("t_betanmax")` -- and then wrote different numbers
into its report: `1.094e+16` instead of `3.98594e+15`, `2.317` instead of
`3.1168`, `3.206 s` instead of `3.905 s`. Wrong by 2.7x, by 34%, and by 0.7 s.
The one field that came out right was `gas`, the only one that is a string.
Nothing in the answer looked wrong; three plausible scalars in a fluent
sentence give a reader nothing to check against.

## Answer "what does this tag mean" with `explain_signal()`, never from the name

**Tag names are not self-describing. Resolve them through the catalog.**
`explain_signal(tag)` returns the answer text and says plainly when the catalog
has no entry -- an undocumented signal is not one whose meaning can be guessed.

Verified, and the reason this rule exists:

```
\FS02UPDA -- from the d3drdb signal catalog:
  Name        : FS02UPDA
  Tree        : SPECTROSCOPY
  Full_Path   : \SPECTROSCOPY::TOP.FILTERSCOPE.PMT22:PHOTON_FLUX
```

An answer once glossed this as "UPDA indicates an *updated/processed* version".
It is a **raw** channel -- `PHOTON_FLUX` off PMT22. In this naming scheme `UP`
is a viewing location and the trailing letters are the species, which the
catalog shows directly: `FS04C3` and `FS04UPC3` are the same carbon-III
measurement from two locations, exactly as `FS02DA` and `FS02UPDA` are for
D-alpha. Read from the name, "UP" disappears into a plausible English word.

**The same name usually exists in several trees, and the description is often
attached to only one of them.** `explain_signal()` labels the rows, so quote
the labels as it gives them:

```
\EFIT01::BT0VAC -- from the d3drdb signal catalog:
  REQUESTED TREE (EFIT01):
    Full_Path   : \EFIT01::TOP.RESULTS.AEQDSK:BT0VAC
    Description : NOT DOCUMENTED for this tree
  SAME NAME IN OTHER TREES -- a different signal record, not the one asked about:
    Tree        : EFIT
    Description : vacuum toroidal field at magnetic axis
    Units       : T
  The EFIT01 row carries no description. If you offer the EFIT description as
  the likely meaning, say that it comes from a DIFFERENT tree and is
  unconfirmed for EFIT01.
```

An answer to this exact question stated "vacuum toroidal magnetic field at the
magnetic axis" for `\EFIT01::BT0VAC` as catalog fact. That text belongs to the
`EFIT` row; `EFIT01` says "Unassigned Signal". It is very likely the same
quantity -- and that is an inference, which the reader is entitled to see
marked as one. `BT0VAC` also exists in `EFIT02` and `EFIT03`, equally
undocumented.

Note the catalog stores the placeholder string `"Unassigned Signal."` for
undocumented entries. `explain_signal()` reports those as `NOT DOCUMENTED for
this tree`; do not quote the placeholder as though it described the signal.

## Trap: do NOT filter on `PLASMA_SHOT`

`SHOTS.PLASMA_SHOT` looks like the plasma filter and is not. It is NULL for
90,416 of 90,418 rows, and the two populated values are the **string** `'1'`,
not the integer 1. `WHERE PLASMA_SHOT = 1` therefore returns 2 rows and looks
like a catastrophic archive, which has already misled one analysis.

There is nothing to filter: **every row in this file is already a plasma
shot**. Count them with a plain `SELECT COUNT(*) FROM SHOTS WHERE SHOT BETWEEN
? AND ?`, or use `plasma_shots_in_range(lo, hi)`.

```python
plasma_shots_in_range(190000, 195000)      # correct -- 3,507 shots
query_d3drdb("SELECT COUNT(*) n FROM SHOTS WHERE SHOT BETWEEN 190000 AND 195000")
# [{'n': 3507}]   correct

# WRONG -- returns 2, because PLASMA_SHOT is unpopulated
query_d3drdb("SELECT COUNT(*) n FROM SHOTS WHERE PLASMA_SHOT = 1")
```

## Tables (only these 5 exist in this file)

- **SHOTS** -- one row per shot, 17 columns. Core: `SHOT` (int, primary key),
  `BRIEF` (short text description of the shot), `SHOT_TYPE`, `SHOT_OK`
  (quality flag). Also present: `RUN` (run/session date, e.g. `'20160128'`),
  `ENTERED` (timestamp the record was entered), `USERNAME` (who entered it),
  `CHIEF_OPERATOR`/`CHIEF_OPERATOR_ID`, `QUALITY_COMMENT`, `PLASMA_SHOT`
  (**a trap -- see below**),
  `TOTAL_UNCOMPRESSED_SIZE`/`TOTAL_COMPRESSED_SIZE` (archive size),
  `INIT_TIME`/`STORE_TIME`/`ANALYSIS_TIME`, `DBKEY`. Several of these
  (`CHIEF_OPERATOR`, `INIT_TIME`, `STORE_TIME`) are frequently NULL in this
  data -- check for `None` before relying on them. Already filtered to
  plasma-type shots only.
- **SHOTS_TYPE** -- `shot`, `shot_type` (always `'plasma'` in this file), `source`.
- **SUMMARIES** -- one row per shot, **82 columns** of physics/operational
  scalars. `shot_summary()` already returns ALL of them (plain `SELECT *`) --
  the groups below exist so you know what's available and can choose to use
  it, not because the code restricts anything.

  - *Timing*: `time_of_shot` (when the shot occurred, ISO timestamp -- ~74%
    of rows populated), `ready_time`, `updated` (row last-modified,
    bookkeeping not physics).
  - *Shape/geometry*: `a` (minor radius), `r` (major radius), `rsurf`,
    `kappa` (elongation), `delta_u`/`delta_l` (upper/lower triangularity),
    `zmaxis` (magnetic axis vertical position), `topology` (e.g.
    limited/diverted, single/double-null).
  - *Current*: `ip` (plasma current), `ipmax`/`t_ipmax`, `ipsign`,
    `ip_flat`/`t_ip_flat`/`ip_flat_duration`/`ip_flat_sdev` (flattop current
    and its quality), `fbs` (bootstrap current fraction), `lock_time`
    (locked-mode onset).
  - *Field*: `btor` (toroidal field), `btormax`, `btorsign`.
  - *Heating/power*: `poh` (ohmic), `pbeam`/`t_pbeam` (neutral beam),
    `pech`/`t_pech` (ECH), `bm_eng`/`ech_eng` (injected beam/ECH energy),
    `prad` (radiated power), `plhmax`/`t_plhmax` (power near the L-H
    transition).
  - *Density/temperature*: `nemax_co2`/`t_nemax_co2` (peak density, CO2
    interferometer), `nemax_thomson` (peak density, Thomson scattering),
    `temax_ece` (peak Te, ECE), `temax_thomson` (peak Te, Thomson),
    `DENSITY_AVG`, `wtotmax`/`t_wtotmax` (peak stored energy),
    `betanmax`/`t_betanmax`.
  - *Disruption/fault*: `t_disrupt`, `t_forced_disrupt`, `ffault`/`t_ffault`
    (fault code and time -- **`ffault` is fixed-width and BLANK-padded
    (`'       '`) for "no fault," not NULL; check `TRIM(ffault) != ''`, not
    just `IS NOT NULL`, or you'll count "no fault" shots as having fault
    data**) -- see the CRITICAL note below before using ANY of these as a
    disruption label.
  - *Impurities/radiation*: `zeff` (effective charge -- **empty in this
    snapshot, 0 of 90,418 rows populated; the column exists but has no usable
    data here, say so rather than querying it as if it will return a value**),
    `gamma_n`/`t_gamma_n`, `neutrons` (neutron yield, a fusion-reaction-rate
    proxy -- well populated, ~53% of rows),
    `FE23_AVG`/`FE16_AVG`/`NI26_AVG`/`NI17_AVG`/`MO32_AVG` and their `_MAX`
    counterparts (impurity spectral-line intensities -- iron/nickel/
    molybdenum charge states, common wall/divertor material tracers).
  - *Gas/wall conditioning*: `gas`/`gas_amount` (fuel species and amount --
    **`gas` values are fixed-width, e.g. `'D2        '`; `TRIM()` before
    comparing or displaying**), `gas_imp`/`gas_imp_amount` (impurity gas),
    `glow_time` (glow-discharge wall-cleaning duration before the shot),
    `daysvent`/`shotsvent` (time/shots since the vessel was last vented -- a
    wall-conditioning proxy), `t_efit` (EFIT reference time).
  - *Engineering -- meaning NOT independently verified, don't present a
    confident interpretation without checking further*: `pfw`/`t_fw`,
    `portdsp`, `t_78`, `lpi`, `dpi`, `patch_panel`,
    `low_dv_out_baf_cryo`/`upp_dv_out_baf_cryo`/`upp_dv_pf_baf_cryo`. Names
    suggest cryopump/baffle status and diagnostic patch-panel configuration
    (divertor engineering bookkeeping), but the exact definitions haven't
    been confirmed against GA documentation.

- **SIGNAL_NAMES** -- signal catalog. `Name`, `Tree`, `Full_Path` (the real
  MDSplus node path), `Group_Id`. **`Tree` is NOT always a directly-openable
  MDSplus tree name -- verified 2026-08-01, see `d3d-shot-fetcher`'s "the
  `d3d` master tree" section.** For signals under branches like IONS,
  TRANSPORT, SPECTROSCOPY (as a `d3d`-tree branch, distinct from the
  standalone `spectroscopy` tree), `Tree` holds the BRANCH name (e.g.
  `'IONS'`), which is not a real tree and will fail if passed straight to
  `MdsSignal(name, tree=row['Tree'])`. Only `efit01` and a small set of other
  subsystems have their own genuine standalone top-level tree. When in doubt,
  fetch with `MdsSignal('\\' + row['Name'], 'd3d')` (the master tree) instead
  of trusting `Tree` literally -- see the fetch-skill for the verified
  pattern and a worked example. **`Full_Path` can also be stale** (verified
  same date, same `ZEFF` entry: the catalog's `Full_Path` names a node that
  no longer exists, even though the tag itself still resolves fine to a
  different real node) -- treat `Full_Path` as a hint for humans/debugging,
  never quote it in a final answer as "the signal's path" without confirming
  via the fetched node's own `.getFullPath()`.
- **SIGNAL_INFO** -- descriptions, joined to SIGNAL_NAMES on `Group_Id`.
  `Description`, `Units`, `Diagnostic`. Sparse -- most signals have
  `Group_Id=0` ("unassigned") and no SIGNAL_INFO row; a miss here does not mean
  the signal doesn't exist in MDSplus, only that d3drdb has no catalog entry.

## CRITICAL: SUMMARIES gives ONE scalar per shot, not a time series

This applies to EVERY numeric column in SUMMARIES, not just the well-known
ones. `SUMMARIES.kappa` (and similarly `ip`, `betanmax`, `nemax_thomson`,
etc.) is a single representative number per shot -- e.g. shot 165340's
`SUMMARIES.kappa` is `1.834`, while the *actual* `\kappa` MDSplus signal for
that shot ranges `1.436-1.945` across the discharge. **Do not treat a
SUMMARIES scalar as the full time-resolved signal.** If a request wants
elongation "versus time," fetch the real MDSplus signal (`d3d-shot-fetcher`);
if it just wants "what was the elongation for this shot" as one number,
`SUMMARIES.kappa` is the right (and much cheaper) answer. Several columns
carry a paired `t_*` column (e.g. `betanmax`/`t_betanmax`) giving the TIME at
which that peak/representative value occurred -- report both if asked "when."

## CRITICAL: do NOT use SUMMARIES.t_disrupt (or similar) as a disruption label

`SUMMARIES` has a `t_disrupt` column that LOOKS like a disruption time, but its
provenance/reliability has not been verified, and the two tables that WERE
d3drdb's dedicated disruption label tables (`DISRUPTIONS`, `disruption_warning`)
are legacy and are deliberately excluded from this file (per GA, do not use).
Do not answer a disruption question from `SUMMARIES.t_disrupt`. Authoritative
disruption labels come from a separate labels store (populated by running
`disruption-py` / GA's disruption packages) -- not yet available as of this
skill's writing. If asked about disruptions and no labels-skill exists yet,
say so rather than inferring an answer from this field.

## Data scope -- read this before answering coverage questions

This file is a **snapshot** (not live) filtered to **plasma-type shots only**
(non-plasma test/calibration shots are excluded by design, not missing data).
It does not cover every shot in the full d3drdb, and it may lag the real,
live database. State this if asked how current/complete the data is.

## Verified example queries

```python
# Which plasma shots exist in a range (was: d3drdb <=> Pelican availability, Q7)
shots = plasma_shots_in_range(190000, 195000)   # 3,507 shots

# Physics characterization for one shot -- returns ALL 82 SUMMARIES columns,
# not just the well-known ones. Shown here truncated to a few of interest
# (verified against the real data -- note gas/zeff/neutrons are NULL for this
# particular shot; coverage varies column by column, always check for None):
s = shot_summary(165340)
# {'shot': 165340, 'time_of_shot': '2016-01-28T10:46:13', 'kappa': 1.83382,
#  'ip': 1194570.0, 'pulse_length': 6.55144, 't_disrupt': None,
#  'gas': None, 'zeff': None, 'neutrons': None, ...}   # see column reference above for the rest

# What does a signal name mean, and where does it live in MDSplus?
search_signal_catalog("kappa")
# [{'Name': 'KAPPA', 'Tree': 'EFIT', 'Full_Path': '\\D3D::TOP.MHD.EFIT.EFIT.RESULTS.AEQDSK:KAPPA',
#   'Description': 'elongation at plasma boundary', 'Units': '(dimensionless)'}, ...]

# Anything else via raw SQL (read-only; tables listed above only)
query_d3drdb("SELECT SHOT, BRIEF FROM SHOTS WHERE SHOT = ?", (165340,))
```

## Keep internal names out of the final answer

`d3drdb`, `SUMMARIES`, `SHOTS`, table/column names -- these are OUR internal
implementation details. A domain scientist doesn't know or care what d3drdb is.
It's fine (good, even) for the tool-call trace (scripts, `execute` output) to
show them -- that's the transparent "how was this computed" record. But the
FINAL prose answer to the user should describe the source in domain terms:
say "DIII-D shot records" or "the shot summary data," not "d3drdb's SUMMARIES
table." Same for column names -- say "elongation," not "the kappa column."

## Verify your own summary before presenting it

Before stating a count or an "X out of Y" claim, count the rows in the table
you are actually about to display and confirm it matches. If a query returned
18 rows, the table you print must have 18 rows and the text must say 18 --
not silently drop one while still claiming the original total. This has
happened before: correct code, correct data, but the final written table was
missing a row the summary text didn't notice. Do the arithmetic on what you are
about to show, not on what you expected to compute.

**Range compression is a second way to get this wrong even when the count is
right.** If you summarize a shot list as ranges (e.g. `190044-190117`) instead
of listing every shot, the ranges must decode back to EXACTLY the stated count
-- not just look plausible. A real shot list has gaps (missing shot numbers
that were never plasma shots at all), and collapsing a gapped list into one
range silently erases those gaps, overstating the count. Before presenting
compressed ranges, sum `(hi - lo + 1)` for each range and confirm the total
equals your stated count. If it doesn't, or if you are not certain a span is
truly gap-free, list the shots individually instead of compressing them.

## If the file is missing

`query_d3drdb()` raises `FileNotFoundError` with the exact folders it
searched and the fix. It checks several folders (NRP persistent storage,
`~/feder_data`, plain `~`, and on Colab plain `/content/` -- upload via the
file browser, no Drive mount needed or supported) and, in each one, either
filename (`d3drdb.sqlite` or `d3drdb_demo.sqlite`) -- both work everywhere,
so don't rename the file to "fix" a not-found error, just place it in one of
the listed folders. Surface the raised error message to the user rather than
guessing an answer.

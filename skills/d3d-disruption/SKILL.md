---
name: d3d-disruption
description: "Query the stored DIII-D disruption index built from disruption-py output: which shots disrupted and when, the 63 physics parameters sampled through each shot as a time series (plasma current, q95, betas, radiated power, n=1 mode amplitude, stored energy), and what each parameter MEANS and its units. Use for questions about disruptions, disruption timing, disruption precursors, pre-disruption plasma state, or the meaning and units of a disruption-warning parameter. This is DERIVED time-series data carrying its own annotation layer, not a raw diagnostic waveform and not the shot catalog."
license: Apache-2.0
compatibility: standard library only (sqlite3); runs in the image, on Colab, or locally
metadata:
  version: "1.0"
---

# d3d-disruption -- DIII-D disruption index

## First: this index is a SLICE, not a sample of DIII-D

Every count in this database describes the shots that were ingested, and
nothing else. The current slice is 20 shots, deliberately balanced 10 disrupted
/ 10 not.

That means **any question phrased as a rate, fraction, or frequency across
DIII-D cannot be answered from this file**, and the correct response is to say
so. `disruption_rate()` exists purely to return that refusal rather than leave
it to be inferred:

```
PopulationClaimUnsupported: This index holds 20 shots, 10 of them disrupted --
deliberately balanced, not drawn at random from DIII-D. Any rate computed from
it (10/20) describes the slice and says nothing about how often DIII-D
disrupts. For an archive-wide rate you need the d3drdb disruptions table over a
defined shot population, not this file.
```

Call `index_info()` before quoting any count, and quote its `coverage_note`
alongside the number.

## What this skill is for

| question | this skill? |
|---|---|
| Which shots disrupted, and at what time? | yes |
| What was Ip / q95 / Wmhd doing before the disruption? | yes |
| What does `n1rms` mean, and in what units? | yes |
| Which parameters are unreliable? | yes |
| The raw D-alpha or BES waveform for a shot | no -- `d3d-shot-fetcher` |
| Per-shot summary scalars, or what an MDSplus tag means | no -- `d3d-relational-db` |
| ELM times, ELMy phases | no -- `d3d-elm-index` |

## Setup

The database is not shipped in the image. `locate_disruption_db()` searches
`$DISRUPTION_DB_PATH`, then:

```
~/work/_User-Persistent-Storage_CephBlock_/feder/   (NRP persistent, survives pod restarts)
~/feder_data/
~/
/content/                                          (Colab upload target)
```

for `disruption.sqlite` or `disruption_index.sqlite`. If it is missing the
error names every path searched.

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-disruption"))
from d3d_disruption import (
    index_info, parameters, parameter_info, unusable_parameters,
    shots, is_indexed, shot_summary,
    fetch_samples, disruption_label, label_disagreements,
    disruption_rate,
    ShotNotInIndex, UnusableParameter, PopulationClaimUnsupported,
)
```

## The parameter dictionary is the point of this skill

The source files carry **no semantic metadata at all** -- 0 of 65 variables in
the NetCDF have `units`, `long_name`, `standard_name` or `description`. That
layer exists only in the dataset's HTML writeup, and this index is where it
became queryable. If asked what a parameter means or what its units are, look
it up; do not infer it from the name.

```python
parameter_info("wmhd")
```

```
{'name': 'wmhd', 'long_name': 'Stored magnetic energy', 'units': 'J',
 'method': 'get_efit_parameters', 'method_desc': 'equilibrium reconstruction',
 'fill_pct': 84.6, 'authoritative': 0, 'usable': 1, 'caveat': None}
```

**Units convention.** An explicit unit string; `'1'` for a dimensionless
quantity; `NULL` **only** when the unit is genuinely unknown. In the current
slice: 37 explicit, 26 dimensionless, 0 unknown. So `units IS NULL` is a real
gap, not "this quantity has no units" -- do not report a dimensionless
parameter as having unknown units.

`parameters(method="get_efit_parameters")` lists a whole physics group. The 14
groups correspond to the disruption-py method that produced each column.

## Three parameters return wrong numbers -- the code blocks them

These are upstream disruption-py defects, documented by the dataset's authors
and verified against the data. They do not fail; they return plausible values,
which is why `fetch_samples()` raises rather than warns.

| parameter | defect |
|---|---|
| `time_domain` | constant 1.0 for every row -- flat-top detection tests `\|ip_prog\| >= 100e3` but `ip_prog` is in MA (order 1), so it never fires |
| `ip_error` | numerically identical to `ip` (2.1e-6 relative) -- `ip_prog` is in MA but used unscaled, so the subtraction is a no-op |
| `dipprog_dt` | in MA/s while `dipprog_dt_rt` is in A/s, differing by ~5e5 -- use `dipprog_dt_rt` |

```python
fetch_samples(194128, ["ip_error"])
```

```
UnusableParameter: 'ip_error' is flagged unusable: Numerically identical to ip
(median |ip_error - ip| = 1.7 A against a median |ip| of 788 kA, 2.1e-6
relative). ip_prog is in MA but is used unscaled, so the subtraction is a no-op.
It returns plausible numbers, which is why this raises rather than warns. Pass
allow_unusable=True only if you intend to demonstrate the defect itself.
```

`fetch_samples()` with `columns=None` returns the 60 usable parameters and
excludes these three automatically. `unusable_parameters()` lists them with
reasons.

## Two disruption labels that disagree -- use the authoritative one

- `time_until_disrupt` -- from the **human-curated** `disruptions` table in
  d3drdb. **This is the label.**
- `current_quench_time` -- disruption-py's own estimate from the Ip decay.

They disagree on 3 of the 20 shots. `disruption_label()` returns the curated
one; the derived one requires `derived=True`, so the class balance cannot shift
silently from 10/20 to 13/20.

```python
disruption_label(194128)
# {'shot': 194128, 'disrupted': True, 't_disrupt': 5.6267,
#  'source': 'time_until_disrupt (d3drdb, curated)'}

[r["shot"] for r in label_disagreements()]
# [198244, 198643, 199062]
```

## A shot that is absent is not a shot that did not disrupt

```python
shot_summary(999999)
```

```
ShotNotInIndex: shot 999999 is not in this index. It has not been run through
disruption-py here -- which is NOT evidence that it did not disrupt. Use
shots() to see what is covered.
```

Never convert this into "no disruption". Use `is_indexed(shot)` to test
coverage first when that distinction matters.

## Worked example: plasma state approaching a disruption

Verified output, run against the current slice.

```python
s = shot_summary(194128)
# {'shot': 194128, 'disrupted': 1, 't_disrupt': 5.6267, 'n_rows': 269,
#  't_min': 0.1, 't_max': 5.6267, ...}

rows = fetch_samples(194128, ["ip", "q95", "wmhd"], time_until_disrupt_max=0.05)
len(rows)      # 26
rows[0]        # {'shot': 194128, 'time': 5.577, 'ip': 474544.06,
               #  'q95': 4.217, 'wmhd': 119044.33}
```

`fetch_samples()` is deliberately scoped to **one shot**. The samples table
reaches roughly 17 million rows at full archive coverage, so there is no
call that selects across all shots at once; iterate over `shots()` instead.

## Comparing disrupted and non-disrupted populations

Legitimate within the slice, provided the answer says it is the slice:

```python
dis = [r["shot"] for r in shots(disrupted=True)]     # 10 shots
non = [r["shot"] for r in shots(disrupted=False)]    # 10 shots
```

State the denominator every time (see [[d3d-elm-index]]'s equivalent rule): the
answer is "of the 10 disrupted shots in this index", never "of disrupted DIII-D
shots".

## Provenance

`index_info()` returns the producing code, pinned to a commit, straight from
the NetCDF global attributes:

```
package     disruption_py          version   0.15.0.dev0
commit_sha  9987784e78ef97...      tokamak   D3D
produced_by sammuli                produced_on omega06.gat.com
produced_at 2026-08-19T07:36:50
```

Quote the version and commit when reporting a result -- the parameters and
their defects are properties of that revision.

## Interface stability

This skill is expected to move to the FEDER lakehouse (Iceberg-based) once it
exists. All SQL sits behind one private `_query()` in `d3d_disruption.py`; the
public function names, arguments, return shapes and exception types are the
contract and do not change with the backend. Written answers that quote these
functions stay valid across that migration.

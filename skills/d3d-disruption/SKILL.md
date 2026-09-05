---
name: d3d-disruption
description: "Query the stored DIII-D disruption index built from disruption-py output: which shots disrupted and when, the 63 physics parameters sampled through each shot as a time series (plasma current, q95, betas, radiated power, n=1 mode amplitude, stored energy), and what each parameter MEANS and its units. Use for questions about disruptions, disruption timing, disruption precursors, pre-disruption plasma state, or the meaning and units of a disruption-warning parameter. This is DERIVED time-series data carrying its own annotation layer, not a raw diagnostic waveform and not the shot catalog."
license: Apache-2.0
compatibility: standard library only; runs in the image, on Colab, or locally
metadata:
  version: "1.0"
---

# d3d-disruption -- DIII-D disruption index

## First: this index is a SLICE, not a sample of DIII-D

Every count in this database describes the shots that were ingested, and
nothing else. The slice is constructed -- shots were chosen to cover a range of
behaviour, and the disrupted/non-disrupted split is deliberate, not natural.

That means **any question phrased as a rate, fraction, or frequency across
DIII-D cannot be answered from this file**, and the correct response is to say
so. `disruption_rate()` exists purely to return that refusal rather than leave
it to be inferred; its message carries the live counts, so quote the message:

```python
disruption_rate()
# PopulationClaimUnsupported: ... deliberately balanced, not drawn at random
# from DIII-D ... For an archive-wide rate you need the d3drdb disruptions
# table over a defined shot population, not this file.
```

**Never write a coverage number as a literal.** `index_info()` returns
`n_shots`, `n_rows`, `n_disrupted`, `shot_min`, `shot_max` and a
`coverage_note`; call it and quote what it returns, alongside the note. The
slice grows as more shots are ingested, so a number written into an answer --
or into this file -- is wrong from the next ingest onward.

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

The index is served over HTTP by the FEDER lakehouse. There is nothing to
download, nothing to place in a folder, and no copy to keep in step -- just
import and query. It does need outbound network; if the service is unreachable
the helper says so in those terms.

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

The source files carry **no semantic metadata at all** -- not one variable in
the NetCDF has `units`, `long_name`, `standard_name` or `description`. That
layer exists only in the dataset's HTML writeup, and this index is where it
became queryable. If asked what a parameter means or what its units are, look
it up; do not infer it from the name.

```python
parameter_info("wmhd")
```

```
{'name': ..., 'long_name': ..., 'units': ..., 'method': ...,
 'method_desc': ..., 'fill_pct': ..., 'authoritative': ..., 'usable': ...,
 'caveat': ...}
```

**Units convention.** An explicit unit string; `'1'` for a dimensionless
quantity; `NULL` **only** when the unit is genuinely unknown. So `units IS
NULL` is a real gap, not "this quantity has no units" -- report a dimensionless
parameter as dimensionless, never as unknown.

**`caveat` is the field that matters.** A column can be marked usable and still
be wrong in a way the `units` field does not admit. Read `caveat` before
quoting a column's values or naming it as a substitute for another, and pass on
what it says.

`parameters(method=...)` lists a whole physics group; the groups correspond to
the disruption-py method that produced each column. `parameters()` with no
argument gives every column and its `usable` flag -- use it rather than a
remembered count.

## Some parameters return wrong numbers -- the code blocks them

These are upstream disruption-py defects: they do not fail, they return
plausible values, which is why `fetch_samples()` raises rather than warns.
**Which columns are blocked is a property of the disruption-py revision that
produced the index, so read the list rather than recalling it:**

```python
unusable_parameters()      # name, long_name and the reason for each
fetch_samples(shot, ["<a blocked column>"])
# UnusableParameter: '<name>' is flagged unusable: <reason>. It returns
# plausible numbers, which is why this raises rather than warns. Pass
# allow_unusable=True only if you intend to demonstrate the defect itself.
```

The defects in the current revision share one root cause worth understanding,
because it explains the shape of the errors: `ip_prog` is stored in MA and used
as if it were A. That single mismatch makes a difference-of-currents column
collapse to a copy of `ip`, puts a derivative six orders of magnitude off, and
holds a threshold test permanently false so a phase flag never leaves its first
value. When a column looks like one of those symptoms, check its `caveat`
before using it.

`fetch_samples()` with `columns=None` returns the usable parameters and
excludes the blocked ones automatically.

## A blocked column does not imply its `_rt` twin is the fix

Several columns come in a plain and a real-time (`_rt`) form. **The `_rt` twin
is a different measurement path, not a known-good version of its partner.** One
of them is currently the reverse: a column that is marked usable, declares
amperes, and carries a constant gain that leaves its magnitude larger than the
plasma current itself. Its `caveat` says so; nothing else does.

So: **recommend only a substitution the dictionary names.** Call
`parameter_info(candidate)` and read `caveat` before naming any column as a
replacement for another. When neither form is sound, derive the quantity from
columns that are -- a current-tracking error, for instance, is a difference the
index already holds the terms for:

```python
rows = fetch_samples(shot, ["ip_rt", "ip_prog_rt"])
err = [r["ip_rt"] - r["ip_prog_rt"] for r in rows]     # A
```

Deriving is preferable to quoting a column whose caveat you have not read.

## Two disruption labels that disagree -- use the authoritative one

- `time_until_disrupt` -- from the **human-curated** `disruptions` table in
  d3drdb. **This is the label.**
- `current_quench_time` -- disruption-py's own estimate from the Ip decay.

They disagree on a minority of shots. `disruption_label()` returns the curated
one; the derived one requires `derived=True`, so the disrupted count cannot
shift silently between the two definitions.

```python
disruption_label(shot)
# {'shot': ..., 'disrupted': ..., 't_disrupt': ...,
#  'source': 'time_until_disrupt (d3drdb, curated)'}

label_disagreements()      # the shots where the two definitions differ,
                           # with both labels -- call it, do not recall it
```

When an answer turns on how many shots disrupted, say which definition it used.

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

## The index stops AT the disruption, and the cadence changes near it

The last sample of a disrupted shot sits at `t_disrupt` exactly -- no shot in
the slice carries a sample after its disruption time. The thermal quench and
the current quench both happen after that instant, on a millisecond scale, so
neither is in this data.

**Both quenches are named events with millisecond timescales, and both are
outside this data.** The thermal quench dumps the stored energy in roughly
0.1-1 ms; the current quench follows and collapses `I_p` in roughly 1-10 ms.
Anything spread over tens or hundreds of milliseconds is neither one, however
large the fractional change -- a stored-energy decay over a ~100 ms window runs
two orders of magnitude slower than a thermal quench.

Describe a pre-disruption window as the approach to the disruption -- confinement
degrading, stored energy falling, `q95` rising as `I_p` decays -- and reserve
both quench terms for the interval after the last sample. ("Energy quench" is
not a term in either sense.)

`q95` rising means the plasma is moving **away** from the low-q kink/tearing
boundary, not toward it. The disruptive limit is `q95` approaching 2 from
above; a rise late in a shot is the arithmetic consequence of `I_p` falling at
fixed field and shape, and is a symptom of the current decay rather than a
driver of instability.

When you report that a signal is getting noisier or more oscillatory, compute
it -- detrended standard deviation or median `|step|` over each half -- rather
than reading it off the trace. Two traps make the eye unreliable here: the
sample cadence changes mid-window (below), so a sparse early region and a dense
late region are not visually comparable; and a single outlier moves
peak-to-peak without moving the distribution, so the two measures can disagree
in sign on the same data.

**The cadence is not uniform.** Disrupted shots run at a coarse rate through
the bulk of the discharge and switch to a much finer one for a short interval
before the disruption, so a fixed-duration window mixes both and its sample
count follows neither rate. Derive the spacing from the returned `time` values
rather than assuming one:

```python
t = [r["time"] for r in fetch_samples(shot, ["ip"], time_until_disrupt_max=0.2)]
dt = [round(b - a, 4) for a, b in zip(t, t[1:])]
sorted(set(dt))          # the rates actually present in this window
```

## Columns are not filled uniformly -- count coverage per shot, per window

Measured columns like `ip` are filled on essentially every row. Columns derived
from the equilibrium reconstruction (the `get_efit_parameters` group -- `q95`,
`wmhd`, `beta_n`, `li`, `q0`, `kappa`) are filled only where EFIT converged,
and those gaps are **not spread evenly**: they concentrate at the end of a
shot, which is exactly the interval a pre-disruption question asks about. Some
shots keep almost no EFIT samples at all.

`parameter_info(name)["fill_pct"]` gives the index-wide fill for a column. It
does not tell you about the shot or window in front of you -- count that
directly, before plotting or aggregating:

```python
rows = fetch_samples(shot, ["ip", "q95", "wmhd"], time_until_disrupt_max=0.2)
have = {c: sum(r[c] is not None for r in rows) for c in ("ip", "q95", "wmhd")}
# len(rows) is the window; have[c] is how much of it column c actually covers
```

Report the two numbers when they differ, and when a column has no samples in
the window, say so rather than plotting an empty panel.

`None` is not `nan`: it arrives as a Python object, so `np.nanmedian` on the
raw list raises `TypeError: '<' not supported between instances of 'NoneType'`.
Use `pd.to_numeric(series, errors="coerce")`, or filter, before aggregating.

## Worked example: plasma state approaching a disruption

Pick the shot from the index rather than hard-coding one -- the covered shots
change as the slice grows.

```python
shot = shots(disrupted=True)[0]["shot"]

shot_summary(shot)
# {'shot': ..., 'disrupted': ..., 't_disrupt': ..., 'n_rows': ...,
#  't_min': ..., 't_max': ...}

rows = fetch_samples(shot, ["ip", "q95", "wmhd"], time_until_disrupt_max=0.05)
rows[0]
# {'shot': ..., 'time': ..., 'ip': ..., 'q95': ..., 'wmhd': ...}
```

`time_until_disrupt_max` is measured back from `t_disrupt`, so it applies only
to disrupted shots; for the rest, window against `t_max` from `shot_summary()`.

`fetch_samples()` is deliberately scoped to **one shot**. The samples table
reaches roughly 17 million rows at full archive coverage, so there is no
call that selects across all shots at once; iterate over `shots()` instead.

## Comparing disrupted and non-disrupted populations

Legitimate within the slice, provided the answer says it is the slice:

```python
dis = [r["shot"] for r in shots(disrupted=True)]
non = [r["shot"] for r in shots(disrupted=False)]
# report len(dis) and len(non) from these calls -- the split is not fixed
```

State the denominator every time (see [[d3d-elm-index]]'s equivalent rule): the
answer is "of the N disrupted shots in this index", with N taken from the call,
never "of disrupted DIII-D shots".

## Provenance

`index_info()` returns the producing code, pinned to a commit, straight from
the source file's global attributes:

```python
index_info()
# package, version, commit_sha, source, tokamak, produced_by, produced_on,
# produced_at, source_file, ingested_at, plus the coverage fields above
```

Quote the version and commit **from that call** when reporting a result -- the
parameter list and the defects are properties of that revision, and a
re-ingest from a newer disruption-py changes both.

## Interface stability

This skill is expected to move to the FEDER lakehouse (Iceberg-based) once it
exists. All SQL sits behind one private `_query()` in `d3d_disruption.py`; the
public function names, arguments, return shapes and exception types are the
contract and do not change with the backend. Written answers that quote these
functions stay valid across that migration.

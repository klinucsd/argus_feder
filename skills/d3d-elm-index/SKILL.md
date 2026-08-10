---
name: d3d-elm-index
description: "Query stored ELM (Edge Localized Mode) labels for DIII-D shots and the filterscope signal-availability metadata collected alongside them. Use for: when a shot was ELMy, individual ELM burst times, ELM frequency/period, finding shots by ELM behaviour, which detector produced a label and with what parameters, comparing two detection methods, and which filterscope channels a shot has at what sampling rate. This is DERIVED LABEL data, NOT the raw waveform -- for the D-alpha trace itself use d3d-filterscopes or d3d-shot-fetcher; for shot metadata (kappa, Ip, pulse length, signal catalog) use d3d-relational-db."
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: DeepTok
  version: "1.0"
---

# d3d-elm-index -- stored ELM labels and filterscope availability

## What this is

A local SQLite index of ELM labels produced by running detection code over
DIII-D shots, plus a record of what filterscope data each shot actually had.

Three kinds of stored fact, and anything derivable from them is in scope:

1. **ELM labels** -- when a shot was ELMy (phases) and when individual ELMs
   fired (bursts), in milliseconds.
2. **Detector provenance** -- which method, version and parameters produced
   each label, so results from different methods can be compared instead of
   silently mixed.
3. **Signal availability** -- which filterscope channels a shot has, at what
   sampling rate, and the reason when a channel is missing.

This is not a fixed list of supported questions. Compose the functions below,
and use `query_elm_index(sql)` with `schema()` for anything they do not cover.

## What this is NOT

- **Not the raw waveform.** To fetch and plot a D-alpha trace, use
  `d3d-filterscopes` or `d3d-shot-fetcher`.
- **Not shot metadata.** For kappa, Ip, beam power, pulse length or the signal
  catalog, use `d3d-relational-db`. To combine the two, see "Joining to
  d3drdb" below.
- **Not a live detector.** These are labels from a past run. Producing new
  labels is a separate offline job.

## No fdp wrapper needed

Local SQLite -- no network, no Pelican, no `fdp`. Run scripts with plain
`python script.py`. The command must be BARE `python script.py`, with no
`cd ... &&`, no pipes and no redirection, so it runs in-kernel.

## Importing

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-elm-index"))
from d3d_elm_index import (
    elm_index_info, schema, runs, query_elm_index,
    is_indexed, shot_status, elm_windows, elm_bursts, was_elmy_at,
    elm_statistics, find_shots,
    signal_availability, shots_with_signals, coverage_summary,
    compare_runs, fetch_estimate, locate_elm_db, ShotNotIndexed,
    # ground truth and cross-method comparison -- rules 9, 9b, 10
    label_sets, regime_windows, regime_at, compare_on_shot, plot_comparison,
    shots_with_multiple_sources, firing_rate_by_regime, events_by_regime,
    regime_summary,
)
```

## The eleven rules, in one place

Read the rule that applies before answering. Each is spelled out below.

1. **Absence is not evidence of absence** -- a shot not in the index was not
   analysed; that is not "no ELMs".
2. **Never compare counts across granularity** -- an `interval` row is an ELMy
   phase, a `burst` row is one ELM.
3. **Check coverage before quoting a proportion** -- the index is a non-uniform
   subset, not a census.
4. **Report a detector's parameters, never guess its algorithm** -- the code is
   not in this image.
5. **A label is an assertion by its producer, not a guarantee** -- a `labeled`
   status means D-alpha transients were detected, and a regime class means a
   labeller called the phase that. Never report a fraction of shots that "are
   ELMy", and never write "no ELMs occurred here by definition".
6. **Check `signal_snr`** -- it is dB and can be negative; the detector picks
   the best available channel, not a good one.
7. **Every time is milliseconds** -- 0-6000 is 6 seconds.
8. **When the index falls short, offer a fetch with a cost, and put the offer
   last** -- give the real numbers, end the answer with the offer so the reply
   is the next thing, and wait. Closing on "this cannot be determined" is wrong
   whenever the measurement is one question away.
9. **The index holds ground truth as well as detector output** -- never present
   a hand-labelled run as a detector result, or vice versa. Call
   `label_sets()`.
9b. **Detection is other people's work: report stored labels, and when a shot
   has none, say so and offer to run a named existing detector.** Writing new
   detection code is out of scope.
10. **Never compare an ELM-event run against a regime-window run** -- same
    granularity, different kind of statement. And clip to the comparable
    window: ground-truth runs cover only the slice a person labelled.

Rules 9 and 10 are spelled out first because they concern the most recently
added data and are the easiest to get silently wrong; rules 1-8 follow.

## Before those: how to talk to the person asking

The user does not work on this system. They are a fusion scientist asking
about DIII-D. Two habits matter.

**Never make them supply a shot number they have no way to know.** "Find a
shot where several methods can be compared" is a normal question and it has an
answer -- `shots_with_multiple_sources()`. Never answer a question of that
shape with "which shot?".

```python
X.shots_with_multiple_sources(min_sources=4)
# [{'shot': 163518, 'n_sources': 4,
#   'methods': ['human_elm_events', 'human_regime', 'omfit_elm', 'slope_outlier'],
#   'ground_truth': ['human_elm_events', 'human_regime'], 'has_expert_labels': True}]
X.shots_with_multiple_sources(min_sources=3)          # 23 shots
X.shots_with_multiple_sources(min_sources=2, require_ground_truth=True)   # 342 shots
```

**Never use our internal vocabulary in an answer.** These are implementation
words. Translate:

**Name each method by its `display_name`**, which every run declares and
`label_sets()` returns. Use that one string everywhere in an answer -- prose,
tables and figure labels -- so the same thing is not called two names:

```python
{r['method']: r['display_name'] for r in X.label_sets()['runs']}
# {'slope_outlier': 'GA mode_classifier detector',
#  'human_regime': 'Expert regime labels',
#  'human_elm_events': 'Expert ELM events',
#  'omfit_elm': 'OMFIT ELM detector'}
```

For the rest, translate:

| do not say | say |
|---|---|
| "the ELM index" / "the database" | "DIII-D shot data" -- or just answer |
| "run 4" | "the labels hand-made by a DIII-D expert" |
| "granularity burst / interval" | "individual ELMs" / "ELMy phases" |
| "none_found vs no_data" | "the detector ran and found nothing" vs "the data isn't there" |

Name a run_id only when the person asks how something was produced, or when
two runs would otherwise be ambiguous. Provenance still matters -- say which
detector and which settings produced a number -- but say it in words a
scientist uses.

## Rule 9: the index holds ground truth, not just detector output

Some runs are hand-labelled by a domain expert. They are the yardstick, not
another opinion. `label_sets()` says which is which:

```python
X.label_sets()["runs"]
# run 1  slope_outlier     interval  elm_events      10840 shots  detector      [default]
# run 2  slope_outlier     burst     elm_events      10840 shots  detector      [default]
# run 3  human_regime      interval  regime_windows    397 shots  GROUND TRUTH
# run 4  human_elm_events  burst     elm_events         23 shots  GROUND TRUTH
# run 5  omfit_elm         burst     elm_events         23 shots  detector
```

Ground-truth runs are **scoped**: they cover only the shots and time windows a
person actually labelled. Outside that scope they assert nothing -- absence is
Rule 1 again, more sharply.

Runs 1 and 2 are the blessed defaults. There is no implicit fallback: a query
with no `run_id` uses the blessed run or raises. It never silently picks the
newest, which would have quietly narrowed every answer to 23 shots once these
comparison runs were added.

## Rule 9b: answer ELM counts from stored labels, never from new detection code

**When asked how many ELMs a shot had:**

1. Look up its stored labels. If a method has labelled it, report that count and
   name the method that produced it.
2. If no method has labelled it, say exactly that -- the shot has not been
   analysed, so the count is unknown -- and offer to run one of the detectors
   already in the system, or to fetch the D-alpha trace so a person can look.
   Give the cost, and wait to be asked (Rule 8).

**The number in an answer always comes from a named detector or a named person.**
Deciding what counts as an ELM is the physics work this system deliberately does
not do: it records, compares and serves other people's labels. A count produced
by code written on the spot has no provenance, cannot be compared with anything
else in the index, and will not reproduce.

This is not hypothetical. Asked for the ELM count on an unanalysed shot, an
agent fetched the raw trace unprompted, wrote a threshold detector, measured it
over-counting by roughly six times, and still reported its number. Both halves
were wrong: the fetch was not offered first, and the count had no provenance.

If a question needs detection that does not exist yet, the honest answer names
what is missing and stops there.

## Rule 10: kind, not just granularity -- and clip the window

A run's `granularity` says how finely it cuts time. It does **not** say what
the labels mean:

| kind | a row asserts | example run |
|---|---|---|
| `elm_events` | "an ELM occurred at t" | 1, 2, 4, 5 |
| `regime_windows` | "the plasma was in QH-mode from t1 to t2" | 3 |

Runs 1 and 3 are both `interval`. Differencing them yields a number that looks
fine and means nothing. Use `compare_on_shot()`, which refuses across kinds and
clips to the intersection of the runs' analysis windows -- one graded window in
the answer key is 17 ms, so an unclipped whole-shot run would appear to have
hundreds of "extra" events it never claimed were in that window.

```python
X.compare_on_shot(154749)
# comparable_window_ms: [2548.0, 3362.0]
# run 1  slope_outlier     detector          1 events  labeled   (interval: ELMy phases)
# run 2  slope_outlier     detector         14 events  labeled
# run 4  human_elm_events  ground truth     15 events  labeled
# run 5  omfit_elm         detector         14 events  labeled

X.compare_on_shot(180445)      # a no-plasma control shot
# run 2  slope_outlier     detector       372 events  labeled
# run 4  human_elm_events  ground truth     0 events  none_found
# run 5  omfit_elm         detector         0 events  error
# warning: ... Zero-because-it-crashed is not zero-because-it-found-nothing;
#          do not read it as agreement with a ground truth of 0.
```

**Report a crashed detector's zero as a failure, never as agreement.**

Regime context, when the shot has it:

**To report how long a shot spent in each regime, call `regime_summary(shot)`.**
Adding the raw window durations double-counts the nested intervals -- on shot
163518 that turns 3516 ms of quiescent time into 3830.

```python
X.regime_summary(163518)
# {'by_regime_ms': {'WPQH': 2235.0, 'QH': 1281.0, 'ELMy H': 361.0},
#  'elmy_ms': 361.0, 'quiescent_ms': 3516.0, 'labelled_ms': 3877.0,
#  'unlabelled_ms': 2123.0,
#  'elmy_percent_of_labelled': 9.3, 'elmy_percent_of_discharge': 6.0,
#  'unlabelled_note': 'asserts nothing -- NOT L-mode; ...'}
```

**Unlabelled time is not L-mode.** The source's `MODE_INFO` line
`"L", LMODE background (not labeled)` means L-mode was never marked -- not that
unmarked time is L-mode. Ramp-up, ramp-down and anything the labeller skipped
land in the same gap. Report it as "no regime was marked here", and give both
percentages when quoting a fraction, since "6% of the discharge" and "9.3% of
the labelled time" are different claims.

```python
X.regime_windows(163518)[:2]
# [{'start_ms': 0.0, 'end_ms': 8.0, 'regime': 'ELMy H',
#   'means': 'ELMing H-mode -- the plasma IS producing ELMs'},
#  {'start_ms': 1100.0, 'end_ms': 1820.0, 'regime': 'QH',
#   'means': 'Quiescent H-mode -- good confinement, no ELMs, edge oscillates instead'}]
X.regime_at(163518, 3000)
# {'start_ms': 2480.0, 'end_ms': 5000.0, 'regime': 'WPQH', 'means': 'Wide-Pedestal Quiescent H-mode'}
```

### What these return

```python
X.compare_on_shot(163518).keys()
# ['shot', 'comparable_window_ms', 'event_level', 'regime_context',
#  'note', 'granularity_warning']
```

**The per-run list is `event_level`, not `runs`.** Each item has: `run_id`,
`method`, `granularity`, `source` ('ground truth' | 'detector'),
`n_events_in_window`, `status`, `error`. `regime_context`, `note` and
`granularity_warning` appear only when they apply, so reach them with `.get()`.

```python
X.regime_at(163518, 3000)
# {'start_ms': 2480.0, 'end_ms': 5000.0, 'regime': 'WPQH',
#  'means': 'Wide-Pedestal Quiescent H-mode'}

X.regime_at(163518, 900)          # a gap between labelled windows
# {'regime': None, 'means': 'no hand-labelled regime covers this time ...'}
```

**`regime_at()` always returns a dict, and `['regime']` is `None` in the gaps**
between labelled windows -- most shot time is unlabelled background. Coalesce
before formatting: `(w['regime'] or 'unlabelled')`.

Regime windows OVERLAP: narrow ELMy H intervals are nested inside broad
QH/WPQH spans, marking ELMy stretches within an otherwise quiescent phase.
`regime_at()` returns the most specific (narrowest) window covering the time,
which is what makes "n in quiescent" counts correct -- resolving overlaps the
other way inflated shot 163518 from 44 quiescent bursts to 75.

### Counting a detector's events by regime

**For one shot, call `events_by_regime(shot)`; across shots, call
`firing_rate_by_regime()`.** Both assign an event to the regime containing its
**midpoint**, which is also what `plot_comparison()` prints in its row labels,
so a figure and the sentence beside it cannot disagree.

```python
X.events_by_regime(163518)
# {'shot': 163518, 'detector': 'GA mode_classifier detector', 'n_events': 91,
#  'by_regime': {'WPQH': 37, 'ELMy H': 36, 'QH': 7},
#  'n_quiescent': 44, 'n_elmy': 36, 'n_outside_any_labelled_regime': 11,
#  'assignment': 'each event assigned by its midpoint'}
```

Events straddle regime boundaries, so the convention matters: counting shot
163518 by start time gives 44 -> 46. Use these functions rather than binning by
hand, and the whole answer stays on one convention.

### Population scale: does a detector fire when it should?

**To answer "how often does this detector fire during quiescent periods" across
many shots, call `firing_rate_by_regime()`.** One shot is an anecdote; this is
the whole overlap between a detector and the expert's regime labels.

```python
X.firing_rate_by_regime()["elmy_vs_quiescent"]
# {'elmy_events_per_second': 34.23, 'quiescent_events_per_second': 3.96, 'ratio': 8.6}
```

```
slope_outlier vs human_regime over 320 shots
  ELMy H   317 shots   253.1 s   8664 events   34.23 /s
  WPQH     136 shots   197.9 s   1377 events    6.96 /s
  BBQH      84 shots    73.4 s    391 events    5.33 /s
  QH       262 shots   317.4 s    566 events    1.78 /s
```

It resolves overlapping regime windows to the narrowest and uses each regime's
exclusive duration, which hand-written versions get wrong in both directions.
Report the ratio with its caveat: a non-zero quiescent rate is not
automatically wrong, since quiescent phases can contain real ELMs.

### Plotting a comparison

**When asked to show, plot or visualise how methods differ, call
`plot_comparison(shot)` and present its figure as the answer.**

```python
ax = X.plot_comparison(163518)          # returns a matplotlib Axes
```

It is already the complete comparison figure: each method on its own track,
every event coloured by the regime it falls in, the quiescent count per method
in the row label, a crashed detector marked as crashed, duplicate runs hidden,
and granularities kept apart. A figure assembled by hand has to get all of
that right; one attempt shaded the band labelled "ELMs expected" across the
quiescent stretch, asserting the opposite of its own conclusion.

**To change the size, pass `figsize` to the call:**

```python
X.plot_comparison(163518, figsize=(14, None))   # wider, height stays automatic
X.plot_comparison(163518, figsize=(14, 6))      # both fixed
```

The figure sets its own height from the number of label sets, roughly 0.6 inch
per row, and scales its type with the width so it stays legible at whatever
size the notebook renders it. Resizing it afterwards with
`fig.set_size_inches()` leaves the rows at their data coordinates and the type
at its original size, so the result is blank space between rows and text too
small to read.

The default 9.5 inches is tuned for a notebook cell. Go wider only when the
time axis is genuinely crowded.

**To show whether a detector fires during quiescent periods on a given shot,
call `plot_comparison(shot)`** -- the hand-labelled regime background and the
per-row "n in quiescent" count answer that question directly, for any shot with
regime labels, whether or not a second detector or expert ELM list exists.

**To add a view the function does not provide, pass `ax=` and draw onto the
same axes**, so the answer carries one figure rather than two that can
disagree about the same shot.

Pass `dalpha={'times':..., 'data':...}` from d3d-filterscopes to overlay the
waveform the detectors looked at; without it the tracks still render, since
this skill must not require the network. `run_ids=` chooses which sets appear.

### Reporting how often a method failed

**Read `n_failed` from `label_sets()`** -- it counts shots with status
`error`. A count of zero-event shots would merge a crash with an honest "ran
and found nothing", which are different claims about the machine:

Each row of `label_sets()['runs']` carries: `run_id`, `method`, `granularity`,
`kind`, `source`, `is_ground_truth`, `shots`, `status_counts`, `n_failed`,
`n_ran_and_found_nothing`, `is_default`, `notes`.

```python
{r['method']: (r['n_failed'], r['n_ran_and_found_nothing'])
 for r in X.label_sets()['runs']}
# {'slope_outlier': (313, 119), 'human_regime': (0, 0),
#  'human_elm_events': (0, 6), 'omfit_elm': (4, 4)}
# omfit_elm: 4 crashed, 4 ran and found nothing -- NOT '8 failures'.
```

## Rule 1: absence is not evidence of absence

This is the single most important thing about this index and the easiest error
to make.

The index covers **a subset of the archive that grows over time**. A shot that
is not in it has *not been analysed*. That is completely different from a shot
that was analysed and found to have no ELMs.

Functions raise `ShotNotIndexed` rather than returning an empty list, so this
cannot be missed by accident:

```python
elm_windows(999)
# ShotNotIndexed: shot 999 is not in the ELM index -- it has not been analysed.
```

**`shot_status(N)` returns a LIST -- one row per run, not a single verdict.**
A shot has a status per method, and they differ: a detector can crash on the
same shot where an expert found nothing.

```python
X.shot_status(163518)          # 5 rows, one per run
# [{'run_id': 1, 'method': 'slope_outlier', 'granularity': 'interval',
#   'status': 'labeled', 'n_labels': 6, ...},
#  {'run_id': 2, 'method': 'slope_outlier', 'granularity': 'burst',
#   'status': 'labeled', 'n_labels': 91, ...}, ...]
# row keys: run_id, method, granularity, status, signal_used, signal_snr,
#           t_start, t_end, n_labels, error
```

Report "shot N has no ELMs" only for a run whose row says `none_found`, and say
which method it was.

The same distinction applies within an analysed shot. `elm_run_shots.status`:

| status | meaning |
|---|---|
| `labeled` | analysed, ELMs found |
| `none_found` | analysed, genuinely no ELMs |
| `no_data` | the signal could not be fetched (reason in `error`) |
| `error` | data returned but unusable by this detector (reason in `error`) |

## Rule 2: never compare across granularity

The same detector produces two different products depending on one parameter:

- **`interval`** -- one row per continuous **ELMy phase** (many ELMs).
- **`burst`** -- one row per **individual ELM**.

An interval count and a burst count are not comparable. For shot 149058 the
same detector gives 2 interval rows and 82 burst rows. Use `elm_windows()` for
phases and `elm_bursts()` for individual ELMs; `compare_runs()` refuses to
difference two runs of differing granularity and returns a warning instead.

## Rule 3: check what is in the index before quoting a proportion

Call `elm_index_info()` first. It returns coverage, status counts, the label
classes actually present, and caveats. Two traps it exposes:

- The indexed shots are **not a uniform sample**. The index is built in batches
  with different sampling strategies -- an even stride, a validation set, and
  contiguous blocks -- so percentages over the whole index are skewed. The
  caveat returned by `elm_index_info()` is **computed from the data**, so it
  describes the current composition rather than a fixed description that goes
  stale. Use `coverage_summary()` to see the distribution, and restrict to a
  known-unbiased shot list for an archive-representative figure.
- `label_classes` pools the classes of EVERY run, so it now mixes a detector's
  ELM classes, the expert's regime classes and the answer key's type codes.
  Read a class back to the run that produced it -- `QH` appearing in the list
  means the human regime labeller emits it, not that a detector claims QH.
  `label_sets()` gives the per-run breakdown.

Real output (the index grows, so read the live values rather than these):

```python
info = elm_index_info()
# shots_indexed: 10917
# shot_range: (55102, 207788)
# status_counts: {'labeled': 9629, 'no_data': 856, 'error': 317, 'none_found': 127}
# labels: {'run 1 (interval)': 26234, 'run 2 (burst)': 1318684,
#          'run 3 (interval)': 2333, 'run 4 (burst)': 326, 'run 5 (burst)': 3637}
# label_classes: ['BBQH', 'ELM', 'ELMy H', 'QH', 'WPQH',
#                  'type1', 'type2', 'type3', 'type4', 'type5']   # pooled across runs
# channels_tracked: ['fs03da', 'fs04', 'fs04da', 'fs05da']
# low_snr_labeled_shots: 658
```

## Rule 4: report a detector's PARAMETERS, never guess its ALGORITHM

`parameters` tells you `pos_deriv_thresh = 2.7` and
`lowpass_cutoff_freq = 2000.0`. It does **not** tell you what that threshold is
normalised against, how the baseline is estimated, or in what order the steps
run. The algorithm lives in the source repository, which is **not installed in
this image** -- you cannot read it from here.

So when asked what a detector *does*: give the method name, version, commit,
repo and the full parameter set, and say the internals must be read from that
repo. Do **not** reconstruct the mechanism from parameter names.

Two plausible inventions have already reached a reviewer this way:

| invented | actual |
|---|---|
| thresholds are "MAD-normalised" | the reference detector fits a **gamma** distribution; MAD appears nowhere in it |
| the code is "legacy Python 2" | it is **Python 3**; the compatibility patch was for a pandas 2 / toksearch 2.x API change |

Both were stated confidently and both were wrong. "The parameters are X; the
algorithm is documented at <repo>@<commit>" is the complete, correct answer.

## Rule 5: a label is an assertion by its producer, not a guarantee

Every label in this index -- detector or human -- records that someone or
something **asserted** a state over an interval. It does not guarantee the
physics held throughout, and it does not exclude what the producer did not look
for. Write "the expert marked this phase quiescent", never "no ELMs occurred
here by definition".

The evidence is in the data itself: narrow ELMy intervals are labelled *inside*
broad quiescent spans on the same shot, and one hand-labelled case is described
as "QH mode broken by ELM clusters". A regime class names the dominant
behaviour a labeller saw, not an impossibility proof. The same applies to
`none_found`: it means the detector ran and found nothing, not that the
discharge was quiet.

### `labeled` does not mean the discharge was ELMy

This is the most important limitation of the label set, and the one most likely
to produce a confident wrong answer.

`status = 'labeled'` means **the detector found D-alpha transients**. It does
not mean the discharge was in ELMy H-mode. The detector almost never declines:
`none_found` is a small fraction of a percent of analysed shots.

Validation confirms this is over-labelling, not physics. Run against discharges
that domain experts hand-labelled as QH-mode -- a regime that by definition has
no ELMs -- the detector labelled **every single one**. QH-mode carries edge
harmonic oscillations and real D-alpha activity, and a slope threshold responds
to it.

**Therefore, the correct answer to "what fraction of DIII-D shots are ELMy?"
is that this index cannot answer it.** Not "98.8% of analysed shots", not any
figure with caveats attached. The label is not an ELMy/not-ELMy classification,
so no denominator rescues it. Say so plainly, and say why: the detector labels
essentially everything with a usable D-alpha trace.

The same applies to any question of the form "how many / what proportion of
shots are ELMy", "is shot N an ELMy discharge", or "find me the non-ELMy
shots".

**Magnitude carries the signal; the binary does not.** Burst count and total
ELMy duration separate regimes far better than the presence of a label -- QH
discharges score markedly lower on both than the index at large, though the
distributions overlap and no clean threshold exists. When a question is really
about ELM behaviour, use `elm_statistics()` and compare magnitudes rather than
counting labelled shots.

## Working examples (all verified against the real index)

### One shot: everything known about it

```python
elm_statistics(149058)
# {'shot': 149058, 'n_windows': 2, 'n_bursts': 82,
#  'elmy_duration_ms': 3595.04, 'first_elm_ms': 65.46, 'last_elm_ms': 5121.84,
#  'frequency_hz': 22.81, 'mean_period_ms': 43.84, 'mean_burst_ms': 5.41,
#  'signal_used': 'fs04da', 'status': 'labeled'}
```

`frequency_hz` is bursts divided by ELMy duration -- the rate *while ELMing*,
not averaged over the whole discharge.

### ELMy phases, and individual ELMs inside a time window

```python
elm_windows(149058)
# [{'start_time': 65.46, 'end_time': 97.02, 'duration_ms': 31.56,
#   'label': 'ELMy H', 'confidence': None, 'run_id': 1}, ...]   # 2 rows

elm_bursts(149058, 2000, 2200)
# [{'start_time': 2017.86, 'end_time': 2025.30, 'duration_ms': 7.44,
#   'label': 'ELMy H'}, ...]                                    # 4 rows
```

### Point query: was the plasma ELMy at this instant?

```python
was_elmy_at(149058, 3000)
# {'start_time': 1558.36, 'end_time': 5121.84, 'label': 'ELMy H'}
was_elmy_at(149058, 200)
# None
```

`None` means no ELMy phase covers that time. It does **not** mean L-mode -- the
quiet period could be ELM-suppressed H-mode or QH-mode, which this detector
does not distinguish.

### Finding shots by ELM behaviour

`find_shots()` takes any combination of criteria, ANDed together:

```python
find_shots(min_elmy_ms=4000, limit=3)
# [{'shot': 142183, 'status': 'labeled', 'signal_used': 'fs04da',
#   'signal_snr': 25.04, 'n_windows': 2, 'elmy_ms': 5084.2, 'n_bursts': 245}, ...]

find_shots(shot_min=200000, signal_used='fs03da')     # by channel and era
find_shots(min_bursts=300)                            # heavily ELMing shots
find_shots(status='error')                            # data-quality triage
```

Available criteria: `shot_min`, `shot_max`, `status`, `signal_used`,
`min_windows`, `min_elmy_ms`, `max_elmy_ms`, `min_bursts`, `label`, `limit`.

### Which channel produced the label, and why it matters

The detector ranks candidate channels by signal-to-noise **per shot**, so the
diagnostic varies within one run. Always report `signal_used` when comparing
shots -- a difference between two shots may come from the channel, not the
plasma.

```python
query_elm_index("""SELECT signal_used, COUNT(*) n FROM elm_run_shots
                   WHERE run_id = 1 AND signal_used IS NOT NULL
                   GROUP BY 1 ORDER BY n DESC""")
# [{'signal_used': 'fs04da', 'n': 430}, {'signal_used': 'fs03da', 'n': 95},
#  {'signal_used': 'fs05da', 'n': 38}]
```

Note this aggregate is skewed by the index's non-uniform sampling (Rule 3), and
the preferred channel also drifts with shot era.

## Rule 6: check `signal_snr` before trusting a shot's labels

`signal_snr` is in **dB and can be negative**. The detector picks the *best
available* channel, not a *good* one, and labels the shot regardless. In the
current index **20 labelled shots have negative SNR** -- noise exceeding
signal (`elm_index_info()['low_snr_labeled_shots']`):

```python
query_elm_index("""SELECT shot, ROUND(signal_snr,1) snr, signal_used, n_labels
                   FROM elm_run_shots WHERE run_id = 1 AND signal_snr < 0
                   ORDER BY signal_snr LIMIT 3""")
# [{'shot': 192179, 'snr': -10.5, 'signal_used': 'fs04da', 'n_labels': 7},
#  {'shot': 188421, 'snr': -9.3,  'signal_used': 'fs05da', 'n_labels': 1},
#  {'shot': 183857, 'snr': -8.2,  'signal_used': 'fs05da', 'n_labels': 2}]
```

Shot 188421 has 443 burst labels from a -9.3 dB channel. Those labels exist,
but presenting them as a confident measurement would be wrong. Flag low SNR
when reporting per-shot results, and consider excluding `signal_snr < 0` from
aggregate statistics.

`signal_snr` can also be `inf` (a channel with no measurable noise); guard
against it in arithmetic.

## Rule 7: every time in this index is in MILLISECONDS

`start_time`, `end_time`, `t_start`, `t_end`, `elmy_duration_ms`,
`first_elm_ms` -- all milliseconds. A full discharge runs 0 to ~6000, which is
**6 seconds, not 6000 seconds**. Labelling those as seconds is a 1000x error
and it has actually happened in review. Derived rates are Hz, and `rate_khz` is
kHz.

When you print a time, put `ms` in the column header.

## Rule 8: when the index falls short, OFFER a fetch -- do not just say "unknown"

The index is a cache over a much larger archive. When a question needs a shot
it does not cover, "not indexed" is a true but unhelpful answer. The raw data
usually **is** reachable from Pelican.

The required behaviour, in order:

1. Say what the index knows.
2. **Run `fetch_estimate()` and put its numbers in your answer** -- the actual
   gigabytes and minutes, written out.
3. Ask whether to proceed, and wait.

Step 2 is the one that gets skipped. "I can run a fetch estimate, just say the
word" is **not** an acceptable answer: it offers to do arithmetic instead of
doing it, and leaves the user unable to decide. Nor is a large number a reason
to withhold it -- "completing this range means ~108 GB and about 80 minutes"
is exactly what lets someone say "no, do a narrower slice". Silence about the
cost is worse than a big number.

Do not fetch unprompted -- fetching is slow and metered, and the user may not
want it. But always price it.

**Put the offer last.** When an answer contains both limitations and an offer,
the offer is the final thing written, after any closing summary. A question
that asks what the data cannot do invites a summary of limits, and an offer
placed above that summary is buried: the reader's last impression is a dead
end. "X cannot be determined from these labels" as a closing line is wrong
whenever the measurement is one question away -- close instead with what you
can do about it, and stop there so the reply is the next thing.

Use `fetch_estimate()` so the numbers are measured, not guessed:

```python
fetch_estimate(186000)
# {'requested': 1, 'already_indexed': [], 'would_fetch': [186000],
#  'megabytes': 31.0, 'seconds': 1.4, 'seconds_8_workers': 0.9,
#  'megabytes_note': '31.0 MB/shot crosses the wire; only 9.6 MB/shot is
#                     decoded and used',
#  'likely_no_data': [], 'can_answer_by_fetching': [...], ...}

fetch_estimate(range(200000, 200020))
# 20 shots -> 620.0 MB, ~28 s serial (~18 s with 8 workers)
```

It also flags shots below the filterscope coverage boundary (shot 130882) as
`likely_no_data` — cheap misses at ~0.65 s and no payload — so a wide old range
is not over-quoted.

**Quote `megabytes` as the transfer cost, not the array size.** Reading four
channels pulls whole tree files, so ~31 MB crosses the wire per shot while only
~9.6 MB is decoded. Using the array figure understates transfer threefold.

**Be precise about what a fetch would and would not settle**, because the two
differ here:

| Fetching CAN answer | Fetching CANNOT answer |
|---|---|
| which channels exist for the shot | ELM labels from GA's detector |
| sampling rate and time coverage | when the shot was ELMy |
| the raw D-alpha trace (plot it, count peaks) | anything requiring the stored label set |

GA's `mode_classifier` is **not installed in this image**, so new ELM labels
cannot be produced here. Offering to "detect the ELMs" for an un-indexed shot
would be a promise the environment cannot keep. Fetching the trace and plotting
it, so the user can see the ELM spikes, is honest and often enough.

A good response to "how many ELMs in shot 186000?" therefore looks like:

> Shot 186000 has not been analysed, so the index has no count -- and that is
> not evidence it had none. I can fetch its D-alpha filterscope data (~9.6 MB,
> about 1.4 s) to confirm the channels exist and show you the trace, but I
> cannot produce ELM labels here: GA's detector is not installed in this image.
> Shall I fetch it?

**This applies to ranges too, not just single shots.** "Which shots in
190000-195000 have channel X" is answered over the shots the index has checked,
and the rest are unknown. Say how many shots the range actually contains (query
d3drdb -- do not count shot numbers), how many were checked, and what completing
it would cost:

```python
from d3d_relational_db import plasma_shots_in_range
rng = plasma_shots_in_range(190000, 195000)     # 3507 real shots, not 5001 numbers
est = fetch_estimate(rng)
# would_fetch 3487 shots -> ~33.5 GB, ~4952 s
```

When the estimate is large, still give it -- "completing this range means ~33 GB
and about 80 minutes" lets the user decide, and a narrower sub-range is often
the sensible counter-offer. Silence about the cost is worse than a big number.

The shot number above is only an illustration. **Always check the actual index
with `is_indexed()` before saying a shot is or is not covered** -- this document
is not a list of which shots are indexed, and it goes stale as the index grows.

To actually perform the fetch once the user says yes, use `d3d-filterscopes`.

### RMP suppression: what to offer

No run in this index labels RMP suppression, so when a question turns on it,
Rule 8 applies: say what the labels do cover, then make the offer, and put it
last. For example:

> No expert marked RMP suppression for this shot. I can fetch the twelve I-coil
> currents -- about 2.3 seconds -- and show you when they were energised.
> Shall I?

DIII-D's twelve non-axisymmetric (I-)coils are **PTDATA pointnames**, fetched
with `PtDataSignal` through `d3d-shot-fetcher`:

```
IU30  IU90  IU150  IU210  IU270  IU330
IL30  IL90  IL150  IL210  IL270  IL330
```

Measured cost, shot 158115: **all twelve in 2.3 s, 125.7 MB decoded; one coil
in 0.2 s, 10.5 MB.** About 1.3 million samples per coil, in amps, on a
millisecond time base.

Two things to state when reporting what comes back:

**The current is the measurement; "suppression" is an interpretation.** Report
the coil currents and their time intervals. Deciding how many amps counts as
energised is a judgement for the facility, not one to make here — see Rule 9b,
which applies to regimes exactly as it applies to ELM counts. A threshold taken
relative to each shot's own maximum is demonstrably wrong: it marks a QH-mode
discharge, peaking at 1,537 A, as energised almost throughout, while a genuine
RMP case peaks near 4,300 A.

**These coils are in PTDATA, not in the MDSplus `operations` tree.** Querying
that tree returns `TreeNODATA` for most shots, which reads as "the archive does
not have it" and is wrong. We reported RMP as blocked on that basis for weeks.

### Signal availability, independent of any detector

```python
signal_availability(shot=149058)
# 4 rows, e.g. {'shot': 149058, 'signal': 'fs04da', 'present': 1,
#   'n_samples': 300000, 't_start': 0.02, 't_end': 6000.0,   # <- MILLISECONDS
#   'rate_khz': 50.0, 'units': 'ph/cm2/sr/s', 'error': None}
#
# t_start/t_end are ms: this channel spans 0.02 ms to 6000 ms = 6 seconds.
# `units` describes the DATA (photon flux), not the time axis.

signal_availability(present=0, limit=2)
# {'shot': 55102, 'signal': 'fs03da', 'present': 0, ..., 'error': 'TreeFOPENR'}
```

`present=1` is not the same as *usable*: a channel can be present as a single
sample at t=0, or at 0.5-1 kHz which is far too slow to resolve ELMs. Check
`n_samples` and `rate_khz`, not just `present`.

**`rate_khz` is measured, not nominal, so bin it with care.** Values arrive in
near-duplicate pairs -- 50.0 *and* 49.951, 100.0 *and* 99.902, 10.0 *and*
9.996 -- because the rate is derived from the median sample spacing. Two
consequences:

- Grouping by the exact value fragments every nominal rate into two rows.
- Rounding to the nearest integer merges 0.5 kHz into the 1 kHz bin, because
  SQLite rounds 0.5 up.

Bin with an explicit tolerance instead, and **never present a rounded bin
alongside its own constituents** -- a table listing both "~1 kHz: 256" and
"0.5 kHz: 198" double-counts the 198. This has already reached a reviewer.

```python
shots_with_signals(['fs04da', 'fs03da'], 190000, 195000)
# {'have': [190067, 190300, ...],      # 20 shots
#  'missing': [],
#  'not_indexed_note': '20 shots in this range have been checked. Any shot in
#   the range not listed in either group has never been fetched, and its
#   availability is unknown -- not absent.'}
```

Always pass on that note when answering a range question -- the honest answer
distinguishes "checked and absent" from "never checked".

### Where in the archive the index has data

```python
coverage_summary()
# [{'bucket': 50000, 'shots_indexed': 13, 'usable': 0, 'labeled': 0},
#  ...
#  {'bucket': 130000, 'shots_indexed': 34, 'usable': 30, 'labeled': 30}, ...]
```

### Detector provenance and method comparison

```python
runs()
# run_id, method, method_version, granularity, parameters (JSON),
# source_repo, source_commit, signal_candidates, created_at, is_default, notes

cmp = compare_runs(1, 2, shot=149058)
# cmp['comparable'] -> False
# cmp['granularity_warning'] -> "run 1 is 'interval' and run 2 is 'burst' --
#     these are different products. Counts are not comparable..."
# cmp['per_shot'] -> [{'shot': 149058, 'n_a': 2, 'n_b': 82}]
```

To read a run's parameters, parse the JSON:

```python
import json
json.loads(runs()[0]["parameters"])["elm_merge_time"]   # 200.0
```

## Anything else: raw SQL

```python
schema()   # prints every table, column and row count

query_elm_index("""
    SELECT s.shot, s.signal_used, COUNT(l.label_id) n
    FROM elm_run_shots s LEFT JOIN elm_labels l
      ON l.run_id = s.run_id AND l.shot = s.shot
    WHERE s.run_id = 1 AND s.status = 'labeled'
    GROUP BY s.shot HAVING n > 3 ORDER BY n DESC LIMIT 5
""")
```

Tables: `elm_runs`, `elm_run_shots`, `elm_labels`, `signal_availability`, and
the view `elm_labels_current` (labels from the default run only).

**SQL trap:** `elm_run_shots` has one row per (run, shot). Joining
`elm_labels` to it without constraining `run_id` on *both* sides counts every
label once per run and silently doubles the totals.

## Joining to d3drdb

Physics context lives in the other database. Attach it rather than
re-implementing lookups -- and prefer the `d3d-relational-db` skill for
anything that is purely a d3drdb question.

```python
import sqlite3
from d3d_elm_index import locate_elm_db
import sys, os
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-relational-db"))
from d3d_relational_db import locate_d3drdb

con = sqlite3.connect(f"file:{locate_elm_db()}?mode=ro", uri=True)
con.execute(f"ATTACH DATABASE 'file:{locate_d3drdb()}?mode=ro' AS d3d")
rows = con.execute("""
    SELECT l.shot, COUNT(*) n_windows,
           ROUND(SUM(l.end_time - l.start_time)) elmy_ms,
           ROUND(m.ipmax/1e6, 2) ip_MA, ROUND(m.kappa, 2) kappa
    FROM elm_labels_current l
    JOIN d3d.SUMMARIES m ON m.shot = l.shot
    GROUP BY l.shot ORDER BY elmy_ms DESC LIMIT 5
""").fetchall()
```

`d3d.SUMMARIES` also has `t_ip_flat` and `ip_flat_duration` (flattop timing),
which lets an ELM window be placed within the discharge phase.

If `locate_d3drdb()` returns None the d3drdb file is not installed; answer the
ELM-only part and say the physics join is unavailable rather than guessing.

## Reporting rules

1. State how many shots the answer is based on, and that the index is a
   subset. "234 of the indexed shots" -- never "234 DIII-D shots". Take the
   total from `elm_index_info()`, which changes as the index grows.
2. Give `signal_used` when the answer depends on which diagnostic was read.
3. Give the granularity and, for interval results, the merge time -- the
   parameters change what a row means.
4. Never present a derived rate without its basis (bursts over what duration).
5. If a question needs a label class no run produces, say so and name what is
   available -- `label_sets()` shows which run emits which classes. Substituting
   a different class, or reading one run's class as another's, is the error.
6. Label every time column `ms` (Rule 7).
7. **Quote numbers from query output, not from memory.** When giving a worked
   example or a "sample row", copy it from what the script actually printed. A
   plausible-looking value written from recollection is the failure mode that
   survives review, because everything around it is correct.
8. When a question is about a shot RANGE, get the population size by querying
   d3drdb rather than assuming -- the count of shot *numbers* in the interval
   is not the count of shots that exist.

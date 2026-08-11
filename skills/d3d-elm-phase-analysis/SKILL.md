---
name: d3d-elm-phase-analysis
description: "Use stored ELM event times to filter or phase-sort a DIII-D diagnostic that is not synchronised with the ELMs, so measurements taken at different points in the ELM cycle are not averaged together. Use for: ELM-synchronised or conditionally averaged profiles, selecting pre-ELM or recovered-pedestal samples, relating Thomson/CER/ECE/bolometry samples to the ELM cycle, and deciding which ELM label set an analysis should be built on. Composes d3d-elm-index (event times, phase) with d3d-shot-fetcher (the diagnostic itself)."
---

# d3d-elm-phase-analysis -- ELM-relative analysis of another diagnostic

## The problem this solves

ELMs recur at tens of hertz and are not scheduled. Diagnostics sample on their
own clocks, unrelated to when an ELM happens, so **every measurement lands at an
arbitrary point in the ELM cycle** -- some mid-crash, some in a fully recovered
pedestal -- and averaging them together smears out the very structure being
studied.

**This is a synchronisation problem, not a slowness problem, and saying
otherwise is wrong.** On shot 169908 the ELM rate is 27.5 Hz (36 ms period)
while Thomson runs at about 233 Hz (4.29 ms): the diagnostic is roughly 8.5
times *faster* than the ELMs. What makes the analysis necessary is that it is
unsynchronised, and that 8.5 samples per cycle -- about one during the crash --
is far too coarse to characterise a cycle from any single instance. Samples must
be pooled across many cycles, and pooling requires each sample's phase.

The regime where this matters is a diagnostic comparable to or somewhat faster
than the ELM rate, but not fast enough to resolve one cycle alone. At 100 kHz
you would watch a single ELM directly and need none of this; at 5 Hz you would
still phase-sort, over far more cycles.

The fix is to sort measurements by where they fall in the cycle and keep only
the part you want. That needs the time of every ELM, which is what the stored
event index provides without re-running a detector.

## The five rules, in one place

1. **Build on a detector run for coverage; validate it against hand labels.**
   Keying an analysis on hand labels restricts it to 23 shots.
2. **Validate event times by millisecond offset**, not by whether one set's
   events fall inside the other's intervals.
3. **The phase window is the user's choice** -- state it, report the fraction
   kept, and show the unfiltered result alongside.
4. **Scan every channel and report where the effect appears.** A channel showing
   no effect is a channel the ELM does not reach, not a failed method. Compare
   the result to another quantity only if that quantity was fetched -- an
   unfetched equilibrium is not evidence.
5. **Do not average across a change of confinement regime.**

Then hand back the judgements: this skill selects and sorts measurements, it does
not decide what counts as a recovered pedestal or whether a result is
significant.

## Rule 1: choose the label set for coverage, then validate it

**Build the analysis on a detector run, because it covers the whole index. Use
hand-labelled events to check the detector's timing first, on the shots where
both exist.**

This is the mistake to avoid, and it is easy to make: hand-made labels look like
the better choice because they are more accurate. They are also scarce and
scoped. On shot 154749:

| label set | events | covers |
|---|---|---|
| hand-labelled | 15 | 2548-3362 ms -- **8%** of the Thomson record |
| detector run | 125 | 619-5424 ms |

and across the index, an analysis keyed on hand labels runs on **23 shots**
against **10,840** for the detector run. Keying the analysis on ground truth
silently restricts it to a couple of dozen discharges -- it produces a result
for one shot that cannot be repeated on the archive.

So: `elm_phase_at(shot, times)` with the default burst run for the work, and a
separate validation step for confidence.

## Rule 2: validate event times in milliseconds, not by containment

**Compare the two sets by the time offset between matched events, in ms, against
the inter-ELM period.** Do not test whether one set's events fall *inside* the
other's intervals -- that depends on how wide the detector draws a burst and
flips on sub-millisecond differences.

Verified, expert event midpoints against detector-derived phase:

```
shot 154749   detector mean burst 2.98 ms   offset median  +0.45 ms   14/15 within 5% of an ELM end
shot 169908   detector mean burst 4.44 ms   offset median  -3.82 ms   22/22
```

Both are agreement to a few milliseconds against inter-ELM periods of tens to
hundreds -- good enough to phase-sort on. Yet a containment test calls 154749
`0/15` and 169908 `21/22`, purely because the bursts are drawn differently.
Report the offset.

On 154749 one expert event sits at phase 0.70 rather than near 0: that is the
one the detector missed, and it is the kind of thing this check exists to find.

## Rule 3: the phase window is the user's choice, so show both

**Report the phase range used, and show the unfiltered result beside the
filtered one.** A filtered average presented alone hides the choice that
produced it.

```python
from d3d_elm_index import elm_phase_at, select_by_elm_phase

sel = select_by_elm_phase(shot, thomson_times, phase_range=(0.5, 1.0))
# {'n_kept': 104, 'n_times': 185, 'fraction_kept': 0.5622,
#  'n_dropped': {'in_elm': 9, 'outside_phase': 72, 'not_covered': 0}}
```

`(0.5, 1.0)` keeps the later half of the inter-ELM period, a common stand-in for
a recovered pedestal. It is a stand-in, not a definition. Say which range was
used, say what fraction of the data survived, and let the reader see the
difference the filter made.

Where two events sit very close together, the inter-ELM period between them is
short and phase still sweeps 0 to 1, so a sample can score as "recovered" with
no time to recover. `min_ms_since_elm=` rejects those.

## Rule 4: scan every channel; report where the effect appears

**Compute the filtered/unfiltered ratio for every channel and report the
profile.** Where that ratio departs from 1 tells you which channels the ELM
actually affects. That is a measurement, and it removes the need to know where
the pedestal sits before starting.

The reason this matters: DIII-D's core Thomson system is a vertical view at
fixed major radius with channels spread in height, and which channel sits at the
pedestal depends on where the separatrix is -- which comes from an equilibrium
reconstruction this skill does not do. Choosing a channel by eye and reporting
one number stakes the whole result on a guess. Scanning does not.

A channel showing no effect is not a null result; it is a channel the ELM does
not reach. Verified on shot 169908, mean pedestal density over samples in phase
0.5-1.0 divided by the mean over all samples:

```
 ch   z (m)     all   recovered   mid-ELM   ratio
  0   0.826  3.49e18    1.67e18   5.17e18   0.48     far edge: filtering halves it
  4   0.777  3.13e18    2.11e18   5.90e18   0.68
  8   0.744  6.56e18    5.57e18   1.14e19   0.85
 12   0.719  1.20e19    1.13e19   1.55e19   0.95     effect nearly gone
 16+  <0.694    ~2.4e19    ~2.5e19   ~2.5e19   ~1.02  core: no effect at all
```

Mid-ELM density is **three times higher** than recovered at the far edge --
ELMs expelling particles outward, which is the signature the workflow exists to
isolate. Pick a single channel near the middle of that gradient and the effect
reads as zero, which looks like the method failing when it is the channel being
wrong.

So: report the ratio profile across channels, say which channels show the
effect, and leave the pedestal's exact location to an equilibrium. The scan is
the result; the pedestal position is a separate question.

**Compare a result to another quantity only if that quantity was actually
fetched.** The channel where the ratio crosses 1 is an observation about where
the ELM reaches; it is not a separatrix position, and saying it "agrees with the
equilibrium" is a claim about data. Fetch the equilibrium and show the number,
or describe the crossover on its own terms. This has already happened once: an
otherwise careful answer stated the crossover "is consistent with the separatrix
location from EFIT for this discharge" having made no EFIT call at all. A single
unsupported sentence in a careful answer is more likely to be believed, not
less.

Verified reachable, shot 169908:

| node | tree | shape |
|---|---|---|
| `\electrons::top.ts.blessed.core.density` | `electrons` | 45 channels x 2408 times, m^-3 |
| `\electrons::top.ts.blessed.core.temp` | `electrons` | 45 x 2408, eV |
| `\electrons::top.ts.blessed.core.r` | `electrons` | 45, m |
| `\electrons::top.ts.blessed.core.z` | `electrons` | 45, m |
| `\electrons::top.ts.blessed.tangential.density` | `electrons` | 9 x 421, m^-3 |

Shorter aliases for the same core data work too and are what an agent tends to
reach for: `\TSNE_CORE` (45 x 2408), `\TSTIME_CORE`, `\TSZ_CORE`, all in the
`electrons` tree.

2408 samples over about 10.5 s is roughly 230 Hz -- which is exactly why phase
filtering is needed. Fetch these with `d3d-shot-fetcher`; the time base is in
**milliseconds**, matching the event index.

## Rule 5: do not average across a change of regime

**Check what confinement regime the window sits in before averaging over it.**
A stretch that straddles an ELMy phase and a quiescent one is two different
plasmas, and an average over both describes neither. `regime_windows(shot)` and
`regime_summary(shot)` give the hand-labelled regimes where they exist.

The same caution applies to the detector's own reliability: it fires during
quiescent phases at about 4 events per second against 34 in ELMy phases, so
phase computed inside a quiescent stretch is built on events that may not be
ELMs at all.

## The workflow

1. **Find a candidate** -- a shot with a long, steady stretch of ELMs and enough
   events to average over. A query over stored event times, not a detector run.
2. **Validate the event times** on that shot if hand labels exist (Rule 2).
3. **Fetch the diagnostic** (Rule 4). Price it and offer before fetching.
4. **Compute phase** for every sample: `elm_phase_at(shot, times)`.
5. **Filter** with a stated range: `select_by_elm_phase(...)` (Rule 3), and
   compute the ratio across channels rather than at one (Rule 4).
6. **Present filtered and unfiltered together**, and name what the analysis does
   not establish.

## What this skill does not do

It selects and sorts measurements. It does not fit pedestal profiles, choose
what counts as a recovered pedestal, or decide whether a result is physically
significant -- those are the user's judgements, and an answer should hand them
back rather than make them silently.

It also does not detect ELMs. Event times come from a named detector or a named
person, recorded in the index with provenance; see `d3d-elm-index`.

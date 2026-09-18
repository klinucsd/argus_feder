---
name: cmod-disruption
description: "Query the stored Alcator C-Mod disruption index built from MIT's disruption-py output: which C-Mod shots disrupted and when, the physics parameters sampled through each shot as a time series, the discharge phase (ramp-up, flat-top, ramp-down) at each moment, and what each parameter means and its units. USE ONLY for Alcator C-Mod / CMOD / MIT shots. For DIII-D disruptions use the DIII-D disruption index instead: the two devices publish different parameter sets, and two identically named columns differ in units by a factor of a million."
license: Apache-2.0
compatibility: standard library only; runs in the image, on Colab, or locally
metadata:
  version: "1.0"
---

# cmod-disruption -- Alcator C-Mod disruption index

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/cmod-disruption"))
import cmod_disruption as cmod
```

## First: this index is a selection, not a sample of C-Mod

The index holds the shots the provider published disruption times for. The
C-Mod origin holds more shots than that, and how these were chosen is not
recorded here.

So a rate, fraction or frequency computed over this index describes the
selection and says nothing about how often C-Mod disrupted. `disruption_rate()`
raises rather than returning a number. That refusal is the correct answer, not
an obstacle to route around.

Call `index_info()` before quoting any count. It returns the size of the
selection and the provenance of the file it came from, so a "how many" answer
can say what it is counting.

A shot that is absent is absent. `shot_summary()` and `fetch_samples()` raise
`ShotNotInIndex` rather than returning nothing, because "no rows for shot X"
must never be read as "shot X did not disrupt".

## This is C-Mod. The DIII-D index is a different thing.

Both devices publish a disruption index from the same package, and they are not
interchangeable:

- **The parameter sets only partly overlap.** Each device publishes parameters
  the other does not, because the machines have different heating systems and
  different real-time diagnostics. `parameters()` lists what exists here.
  `parameter_info(name)` raises for a name this device does not have rather
  than returning nothing.
- **Nothing joins a C-Mod shot to the rest of this lakehouse.** There is no
  C-Mod shot catalogue, no summaries and no ELM labels here. A question that
  needs the plasma conditions around a C-Mod shot cannot be answered from this
  lakehouse, and saying so is the answer.
- **Shot numbering differs.** C-Mod shot numbers are not in the same range as
  DIII-D's, so a number alone tells you which device it belongs to. Never pass
  a shot from one index to the other.

**The trap worth knowing before you write a sentence with two numbers in it.**
Some parameters carry the same name on both devices while being recorded in
different units, differing by a large power of ten. The name matches, the value
looks plausible, and the comparison is silently wrong. Call
`cross_device_note()` for the current list, and read it before putting a C-Mod
number and a DIII-D number in the same table, ratio or sentence.

`fetch_samples()` enforces this: requesting one of those parameters raises
`CrossDeviceUnitMismatch` unless you pass `cross_device=True`, which is you
stating you have accounted for the difference.

## Signing a quantity by the current direction

This machine ran the plasma current in both directions. A quantity whose sign
follows the current is not comparable between shots until it is multiplied by
that direction, and loop voltage is the usual case.

```python
cmod.ip_direction(shot_list=None)                          # +1 or -1 per shot
cmod.fetch_samples(shot, columns=[...], sign_by_ip=[...])  # applies it for you
```

**Let the skill apply it rather than doing the multiplication by hand.** Getting
it the wrong way round mirrors the result about zero: every magnitude still
looks right, every count is unchanged, and the conclusion is inverted. There is
nothing in the numbers to catch it.

The check that does catch it is physical. A tokamak's transformer drives current
against the plasma's resistance, so **signed loop voltage is positive for an
ordinary discharge**. <!-- lint-ok: true of any tokamak and any delivery, not a fact about this index -->
If a signed median comes out negative, the sign has been applied backwards; do
not report it. State the signed median you got, so a reader can see the check
was made.

## Discharge phase: what this index can answer

This index carries a working discharge-phase column, so these are answerable:

```python
cmod.phase_windows(shot)        # when ramp-up, flat-top and ramp-down began and ended
cmod.phase_at_disruption(shot)  # which phase the shot was in when it disrupted
cmod.flattop_entry()            # per shot: flat-top entry, plus disruption or censoring time
```

`flattop_entry()` returns the pair a hazard model needs, with `censored` set
for shots that did not disrupt. Shots that never reached flat-top come back
with `t_flattop` of None rather than being dropped, because never reaching
flat-top is a result rather than a gap.

Phase data is not guaranteed for every shot. `phase_windows()` returns an empty
list for an indexed shot that has none, which is different from raising for a
shot that is not indexed at all. Check rather than assume, particularly for the
oldest shots.

## The rest of the API

```python
cmod.index_info()                     # size of the selection, and where the file came from
cmod.parameters(usable_only=False)    # every parameter with meaning, units, IMAS path
cmod.parameter_info(name)             # one parameter, including any cross-device caveat
cmod.cross_device_note()              # parameters whose units differ from DIII-D's
cmod.d3d_equivalent(name=None)        # the DIII-D parameter this one corresponds to

cmod.shots(disrupted=None)            # shots in the index, optionally filtered
cmod.is_indexed(shot)                 # False means unknown, not "did not disrupt"
cmod.shot_summary(shot)               # label, disruption time, sample coverage
cmod.disruption_label(shot)           # one shot's label
cmod.disruption_labels(shot_list)     # a GROUP of shots in one request
cmod.label_disagreements()            # where the per-shot label and per-sample indicator differ

cmod.ip_direction(shot_list=None)      # +1 or -1 per shot, for signing
cmod.fetch_samples(shot, columns=None, cross_device=False, sign_by_ip=())
cmod.window_before_disruption(shots, ms, columns, sign_by_ip)  # windowed in SQL
```

Pass a **group** of shots to `disruption_labels()` rather than looping one at a
time: each call is an HTTP round trip.

`d3d_equivalent()` answers "what is this called on the other device". Its
`mapping_source` says how the correspondence was established, which matters
because they are not equally strong: some names are shared outright, some were
matched against both descriptions, and some were confirmed by the package's own
maintainers. A parameter with no equivalent is specific to this device, usually
because the two machines differ in hardware. That is an answer, not a gap, and
should be reported as one.

A correspondence is about the quantity, not the units. Two parameters can map to
each other and still be recorded on different scales, so check
`cross_device_note()` as well before comparing values.

Where a parameter carries an IMAS path, `parameters()` returns it. That path is
the device-neutral identity of the quantity and is the right thing to quote when
a question is about what a parameter means rather than what this device called
it.

## Quoting a statistic over part of the data

Sampling here is uneven and tightens sharply near a disruption, so a statistic
over a sub-window moves fast as the window changes. A median over the final
2 ms and a median over the final 1.5 ms are not close to each other.

**State the bounds and the sample count with the number, every time.** Write
"median 4.2 V over the final 2 ms, 143 samples", not "median 4.2 V near the
quench". A reader cannot check the second, and neither can you a week later.

**The count is the half that catches mistakes.** A bound can look right while
the data behind it is wrong, and then only the count shows it: a 2 ms window on
this index should hold about 143 samples, so a statistic quoting 106 is being
computed on a subset that lost rows somewhere. Quote the count and that is
visible. Omit it and it is not.

This is not the same as sourcing the number. A figure can be computed correctly,
appear in a tool result, and still be unreproducible because the window it came
from was described loosely. Both are needed: where it came from, and over what.

The same applies to any subset, not just time: a set of shots, a phase, one
current direction. Name the selection and its size in the same sentence as the
value.

## Windowing near the disruption

Use `window_before_disruption(shots, ms, ...)` rather than fetching whole shots
and slicing them in Python. The comparison against the window edge then happens
in the database, on the stored values.

**Do not round when writing intermediate data to a file.** A sample sitting on a
window edge is stored as 0.00199997 seconds, inside a 2 ms window. Written with
six decimal places it becomes exactly 0.002, and the same test now puts it
outside. Rows vanish at the boundary, every surviving number stays consistent
with every other, and a median can move by a factor of two with nothing to show
for it.

If an intermediate file is genuinely needed, write full precision (`repr`, or
`%.17g`), and check the row count survives the round trip before computing
anything from it.

## What a disagreement means

`label_disagreements()` compares the per-shot label against the per-sample
indicator from the same file. Where they differ, that is a finding about the
pipeline that produced them, not about the shot. Report it as such, and do not
pick whichever of the two supports the rest of the answer.

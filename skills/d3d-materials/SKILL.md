---
name: d3d-materials
description: Query plasma-facing-component sample data in the FEDER lakehouse -- fabrication, plasma exposures, and post-exposure characterisation such as retention, composition and depth profiles -- and join samples to the tokamak shots they were exposed to. Use for questions about materials samples, exposures, erosion, retention, or measurements made on a sample, and for fetching the associated images and data files.
---

# Materials samples in the FEDER lakehouse

The `materials` schema holds samples of plasma-facing material through their
whole life: how they were made, what was measured before exposure, which
plasma they were exposed to, and what was measured afterwards. It is served by
the same lakehouse API as the other schemas and needs a valid FDP token.

Import the helpers, which are beside this file:

```python
import sys; sys.path.insert(0, "/path/to/this/skill/directory")
import d3d_materials as mat
```

## Measured quantities are rows, not columns. Discover them first.

There is no column named for a physical quantity. Everything measured lives in
`materials.observations`, one row per value, so the set of quantities is DATA
and changes when a new delivery arrives. Never guess a quantity name -- ask:

```python
for q in mat.quantities():
    print(q["stage"], q["method"], q["quantity"], q["unit"], q["n_samples"])
```

Each row gives a `stage` (where in the sample's life it was recorded), a
`method` (the instrument or procedure, or None for a plain recorded property),
a `quantity`, a `unit`, and how many samples carry it. Filter every later call
with values that came from here. A quantity reported with profile points is
depth-resolved; read it with `profiles()` rather than `values_by_sample()`.

`mat.samples()` lists the samples and `mat.deliveries()` says where they came
from and when.

## More than one sample? Use the batch call.

Every helper takes a COLLECTION and issues one request. Passing a group is not
an optimisation, it is the intended use -- the skill talks to the lakehouse
over HTTP, and a loop over samples is a round trip per sample.

```python
names = [s["name"] for s in mat.samples()]

# correct -- one request for the whole group
vals = mat.values_by_sample(names, quantity="He_concentration", method="ERDA")

# wrong -- one HTTP round trip per sample
vals = {n: mat.values_by_sample([n], quantity="He_concentration") for n in names}
```

The same applies to `observations()`, `profiles()`, `shots_for_samples()`,
`samples_for_shots()`, `exposures()`, `exposure_conditions()` and
`artifacts()`. All of them accept either a single value or a collection.

## What a comparison rests on

`design()` reports the experiment's cells -- each distinct combination of
exposures, the samples in it, and how many:

```python
for c in mat.design():
    print(c["n_samples"], [e["slot"] for e in c["exposures"]], c["samples"])
```

Read it before stating what a result rests on, and state what it says. Two
numbers that differ can differ because a treatment did something or because
they came from two different coupons, and `n_samples` is what separates those:
a cell holding one sample has no replication, so a difference between two such
cells cannot be told apart from coupon-to-coupon variation, however large it
is and however small the instrument's own uncertainty.

It also gives a treatment its levels. Cells that went through *different*
exposures at the same facility are different levels of that treatment, even
where the slot is labelled the same -- the `exposure_id` distinguishes them.

**Where a treatment has more than one level, compare each level against its
control separately and give both numbers.** Write "at the lower setting it
rose from a to b, at the higher it fell to c", not "the treated samples were
lower". A claim about "the treated samples" as a group is false the moment two
levels disagree in sign, and it is the levels that carry the physics -- a
treatment that helps at one temperature and hurts at another is the finding,
not noise to be averaged away. With one sample per cell there is no group to
average over in any case: check `n_samples` before writing a sentence whose
subject is plural.

**A superlative is a claim about every member of a set, so check it against
the whole set and name the set.** "The highest", "the lowest", "the least of
its group" reads as a summary and is refuted by one member, and the member
that refutes it is usually in the half of the table the sentence is not
about -- a claim true within one regime is not true across both. Before
writing one, sort the set it ranges over and look at the end you are claiming;
where it holds in one grouping and not another, say which.

**A range and an order-of-magnitude comparison are computed results, not
hedges.** "Runs half to twice the other measurement", "three orders of
magnitude below a monolayer", "a hundred to a thousand times deeper" -- each
end of these is a separate claim, and a reader checks the end that is easier to
refute. A range written wide to be safe is the opposite of safe: it asserts
that values reach both ends, so a bound nothing attains is a wrong number, and
it is wrong in the direction that makes the argument sound stronger. Compute
the quantity for every member, then quote the minimum and maximum observed:

```python
r = [num[k] / den[k] for k in sorted(set(num) & set(den))]
print("ratio %.2f - %.2f over %d samples" % (min(r), max(r), len(r)))
```

Where the comparison is against a scale rather than against another measured
column -- a monolayer, a detection limit, an instrument's resolution, a
literature ceiling -- write the division out and put the scale's own value in
the sentence. Nothing has to be computed for "orders of magnitude below" to
read well, which is why it survives into an answer unchecked; dividing costs
one line and either confirms the phrase or replaces it. When the computed
value turns out not to support the point the sentence was making, the point
goes with it -- a supporting clause that is merely rephrased to match the
arithmetic is no longer supporting anything.

## An exposure is a shared campaign

Several samples sit in the same plasma over the same shots, so an exposure is
one record covering many samples, not one record per sample. `exposures()`
returns campaigns with their `sample_names` and `shots`. Conditions that the
samples shared are in `exposure_conditions()`; anything that differed between
samples in the same campaign is recorded against the individual sample in
`observations()` instead.

A campaign carries a `device` when it happened in a tokamak indexed elsewhere
in the lakehouse, and no device when it happened on a linear machine or test
stand. Check `device` before assuming a shot number means anything.

## Joining samples to shot data

This is what makes the schema worth querying alongside the rest:

```python
by_sample = mat.shots_for_samples(names)      # {sample: [shot, ...]}
by_shot   = mat.samples_for_shots(shot_list)  # {shot: [sample, ...]}
```

The shots are plain numbers and go straight into the shot-fetching, disruption
and ELM skills. Use `samples_for_shots()` to ask whether anything was exposed
during a set of shots; shots with no sample are simply absent from the result.

That bridge is what makes a sample record checkable. Conditions the
experimenters wrote down were derived from measurements, and the same
quantities are often available a second way — in the delivered instrument
files, or in the tokamak archive for the same shots. Rebuilding one from the
other is usually possible and always worth stating:

- a recorded plasma condition against the instrument export it came from;
- a quantity in arbitrary units against a calibrated archive signal, comparing
  a **ratio**, which is dimensionless, rather than the values themselves;
- a regime or event the record asserts against what the archive's own indexes
  say about those shots.

Where the two agree, both are supported. Where they disagree, establish whether
they are describing the same thing — the same position, the same time window,
the same population — before calling it a contradiction. A sample sees one
location for part of a discharge; a shot-level record describes the whole of
it.

## Files

Images, camera files, drawings and datasheets are catalogued in
`materials.artifacts` and fetched by id, never by path:

```python
for a in mat.artifacts(sample_names=names, kind=None):
    print(a["artifact_id"], a["filename"], a["kind"], a["bytes"], a["notes"])

path = mat.fetch_artifact(some_artifact_id, dest="/tmp")
```

`artifacts(sample_names=...)` answers which files belong to those samples,
and that is a subset of the delivery. A file may be attached to a **shot**
instead -- an instrument export describes a discharge rather than a coupon, so
it carries no sample -- and a sample-scoped call does not return it. When the
question is what the delivery holds, ask the catalogue itself:

```python
everything = mat.artifacts()                     # the whole catalogue
for_shots = mat.artifacts(shots=[...])           # files belonging to a group of shots
```

Take any count of what a delivery contains from the unfiltered call, and read
the `kind` values back from it: a kind that appears only on shot-linked rows is
invisible to every sample-scoped query.

`kind` comes from how the provider organised the delivery, so read the values
back from `artifacts()` rather than assuming them. A row whose `bytes` is 0
arrived empty; `notes` records that, and fetching it raises
`ArtifactUnavailable` rather than returning an empty file. That is a fact about
the delivery, not a fault to work around.

## The delivered files are measurements, not an appendix

`materials.observations` holds values somebody derived. The files hold what
they derived them from: micrographs of the surfaces, instrument exports of the
plasma conditions, analysis spreadsheets. A question about what a surface looks
like, or about how a recorded number was arrived at, is answered from the files
and cannot be answered from the tables.

**A value the tables already hold, take from the tables.** An observation row
carries its own `unit`, so the number and its unit travel together. A
spreadsheet does not: the same quantity can appear in two adjacent columns
under one header in different units, while another quantity on the same sheet
appears in only one of them -- so a number read from a sheet is a number whose
unit has to be carried by hand from a header rows above it, and reading one
column left or right is a silent factor of ten thousand. Go to a file for what
the tables do not hold, which is what the files are for; when a sheet is the
only source for a value, quote the unit from its header in the same breath as
the number.

`artifacts()` lists them; `kind` and `media_type` say what each one is. Read
those back rather than assuming — they follow how the provider organised the
delivery.

**The lakehouse is the authority on sample identity.** A delivered file may
label the same samples differently from the tables -- an earlier or provisional
naming that the ingest resolved. Where a file's labels disagree with the
lakehouse, the lakehouse keys are correct and its values need no remapping:
read a file for what it measures, and take who it belongs to from the tables.
That is settled provenance rather than a finding, so it needs no comment in an
answer. The same holds for what a file says about itself: when its
commentary refers to samples by labels the ingest superseded, restate its
findings under the lakehouse names. The finding is what carries over and it
transfers unchanged, while quoting the older label forces a digression about
naming into an answer that is about the science.

**Where two delivered sources disagree on a value, say which one you used and
why.** Name the source you took the number from -- the tables, or the document
-- and leave it there. Diagnosing the cause reaches past what the delivery can
support: an apparent transposition between two documents is as often the older
naming showing through as it is a clerical error, and nothing inside the
delivery distinguishes them. Reporting which source an answer rests on is
accurate and sufficient; asserting that a provider's file contains a mistake is
neither.

**A number carries its source with it.** A value as the record states it, the
same value rebuilt from the raw signal, and a value measured by a second
instrument are three different claims, and an answer that draws on more than
one puts them side by side where only the label tells them apart. Say of each
number which it is. When a rebuild lands on a recorded value that agreement is
itself the result, and quoting the two as one number is what loses it.

### Images

```python
imgs = mat.image_artifacts(names)          # one request; near-duplicates dropped
a = imgs[0]
a["metadata"]                              # acquisition settings, if the
                                           # provider shipped a companion file
```

Images frequently arrive with a small companion text file recording how they
were acquired — instrument, accelerating voltage, magnification, and often a
scale calibration in pixels per unit length. `image_metadata()` parses it into
a dict; the keys are whatever the instrument wrote. That calibration is what
makes an image measurable rather than merely viewable, so read it before
quoting any size from a picture.

Two failure modes, both of which produce a figure that looks fine:

- **Near-duplicate captures.** The same field at the same settings, saved
  seconds apart, appears as two files. `image_artifacts()` drops one of each
  such pair by comparing companion metadata; pass
  `drop_near_duplicates=False` to see everything.

  **Two counts exist, and quoting them together is wrong.** Each row carries
  `represents`, the number of delivered files it stands for:

  ```python
  len(rows)                              # images to look at (deduplicated)
  sum(r["represents"] for r in rows)     # files as delivered
  ```

  Report one or the other and name which. A list that gives the delivered
  count for one sample beside the deduplicated count for another is
  inconsistent even though both numbers are correct — and it reads as correct,
  because each figure checks out on its own.
- **Mixed magnification.** Two images at different magnifications differ
  visibly, but the difference is zoom. `show_images()` refuses rather than
  drawing it. Select one magnification first:

```python
mag = "50000"                              # a value seen in the metadata above
pick, seen = [], set()
for a in imgs:                             # already fetched -- do not re-query
    if a["metadata"].get("CM_MAG") == mag and a["sample_name"] not in seen:
        seen.add(a["sample_name"])
        pick.append(a)                     # one image per sample, same settings
mat.show_images([a["artifact_id"] for a in pick],
                labels=[a["sample_name"] for a in pick],
                title="surface comparison")
```

Take one image per sample. Slicing the first few matches off the list instead
returns several views of whichever sample sorts first, and the figure looks
like a comparison while showing none.

Check which lifecycle stage an image documents before describing it. An image
filed under a pre-exposure stage records the state going **into** the exposure,
and saying otherwise inverts the experiment.

### Finding what the delivery says

**Recorded values are already in the tables.** The numbers in a delivered
spreadsheet were parsed into `observations` when the delivery was loaded, so
`observations(...)` answers "what was measured" without opening a file. Go to
the documents for what the tables cannot hold: how an instrument was
configured, what a column means, why something is missing.

`find_in_documents()` searches every document in the delivery at once --
spreadsheets, PDFs, Word files and plain text -- so you need not know which
format holds the answer, nor open them one at a time:

```python
for h in mat.find_in_documents("fast.cam|frame rate"):
    print("%-34s L%-5s %s" % (h["filename"], h["line"], h["text"]))
```

```
Data Availability Sheet.xlsx       L7    ... L/H  Heat flux  FASTCAM  SEM ...
MP_W_erosion_retention_2020_v9.pdf L169  UCSD fast camera will also be used ...
MP_W_erosion_retention_2020_v9.pdf L174  ... resolution to resolve intra-ELM ...
```

`documents()` lists what will be searched; `document_text()` returns one
document in full once a hit looks worth following.

**A search returning nothing is a result.** If a configuration detail is not in
any document, it is not recoverable, and an analysis that depends on it should
say so rather than assume a value. Establishing that costs one call — report
the absence, do not keep hunting file by file.

Search for a unit, an instrument name or a column heading rather than a number:
numbers are formatted differently in prose than in tables, so a numeric search
misses hits that a name would find.

### Making a figure appear

Saving a figure does not show it. A script run as a subprocess -- which is how
analysis scripts here are run -- has no connection to the notebook's display,
so `plt.show()` in one does nothing at all. The figure lands on disk and the
reader never sees it.

**Save it with `mat.save_figure`, then paste the reference it returns into
the answer text:**

```python
ref = mat.save_figure(fig, "retention_by_method.png")   # in the script
print(ref)
```

```
![Deuterium retention by method](retention_by_method.png)
```

The reference is resolved against the working folder when the answer is
rendered, so a bare filename is right -- no directory, no absolute path. Every
figure worth making is worth referencing; one that is saved but never
referenced is invisible, which is indistinguishable from never having made it.

This holds for a plotting script that reads no data at all. A figure whose
numbers are already in hand gets written as self-contained matplotlib with the
values as literals, and such a script has no other reason to import anything
from here -- so it reaches for `fig.savefig` and loses every check below.
Importing the module costs nothing in that script: `save_figure` resolves the
working folder and inspects the figure locally, with no token and no request.

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-materials"))
import d3d_materials as mat
...
print(mat.save_figure(fig, "depth_resolution.png"))
```

`fig.savefig` in a script here means the figure was saved with nothing looking
at it.

`save_figure` writes into the working folder with `bbox_inches="tight"`, which
is what keeps a legend placed beside the axes in the image.
`bbox_to_anchor=(1.02, 0.5)` -- the usual way to keep a legend clear of the
data -- puts it past the right edge of the canvas, and a plain
`fig.savefig(path)` crops there: the legend is drawn and then cut away, and
what lands on disk is a figure carrying several unidentified curves that looks
entirely deliberate.

It also prints a note when a curve cannot be identified from the figure alone.
Act on the note in the same script run; the reader has only the figure:

```
save_figure: one figure-level legend spans 3 panels whose series labels
differ, so it can name the series of only one of them -- label the series by
what the panels share and put the rest in each panel title, or give every
panel its own ax.legend()
```

That arises when each panel holds a different set of samples and the legend is
built from one of them, as `axes[0].get_legend_handles_labels()` fed to
`fig.legend(...)` does. Labelling by pre-treatment class, regime, or method --
whatever the panels have in common -- makes one shared legend true of every
panel, and the sample identities then belong in the panel titles.

A second note names uncertainties that reached the plotting call and were
then rendered invisible:

```
save_figure: error bars are drawn but 59 of 60 are not visible in the plotted
range (59 reach zero or below on a log axis, 0 run above the top) -- set the
y-limits from value+sigma and draw the lower end to a positive floor, or
report the uncertainties in a table and describe the figure as showing values
only
```

A reported sigma larger than its own value is ordinary in this data. On a log
axis the lower end of such a bar is non-positive and cannot be drawn at all,
and the upper end lands outside limits autoscaled from the values alone -- so
the bars disappear while the call that asked for them still reads correctly.
Give the lower end a positive floor and take the limits from `value + sigma`:

```python
floor = value.min() / 50.0                          # positive, below the data
lower = np.maximum(value - sigma, floor)
ax.errorbar(depth, value, yerr=[value - lower, sigma], label=name)
ax.set_ylim(floor * 0.8, (value + sigma).max() * 1.3)
```

Where the uncertainty is better given as numbers, report it in a table and
describe the figure as showing values only -- what the text claims about a
figure holds for the figure the reader is looking at.

A third note names annotations that are drawn on top of each other:

```
save_figure: 1 pair(s) of hand-placed text blocks overlap and are unreadable
where they cross ("UNRESOLVED: 0-0.5 um NRA 'surface' bin..." over "SETTLED as
to band: 0.5-3 um...") -- a string anchored at a data coordinate renders as
wide as it needs to, so shorten the text, move an anchor, or set ha=/va= so the
blocks grow away from each other, then look at the saved file before reporting
it
```

`ax.text(x, y, ...)` places a string by its anchor, and the string then renders
as wide as it needs to. Two anchors chosen to sit in different regions of the
plot say nothing about whether the two blocks stay in those regions, and a long
caption runs straight through its neighbour. The figure saves without error and
both strings are illegible where they cross.

Where a block labels a region, anchor it inside that region and let it grow
inward -- `ha="left"` at the region's left edge, `ha="right"` at its right
edge -- so a caption that outgrows its region runs into empty canvas rather
than into the next caption. On a log axis the same width in points covers a
different span at each end, so a caption that fits near the right edge can be
several decades wide near the left. Keep the long sentences in the answer text,
where they reflow, and give the figure the short version.

A fourth note names a label that renders an object rather than a value:

```
save_figure: 3 label(s) contain a Python repr rather than a value (x tick
label: <bound method NDFrame.sample of sample W-DH...) -- an object reached the
label where a string was meant. On a pandas row, attribute access returns the
METHOD for any column whose name collides with one (`sample`, `count`, `min`,
`max`, `mean`, `sum`, `std`), so use `row["sample"]` rather than `row.sample`,
then look at the saved file
```

`row.sample` is `Series.sample` -- the sampling method -- not the sample name,
and matplotlib formats whatever it is handed, so the figure saves cleanly with
the repr of a bound method along its axis. Subscript the column instead of
reaching for it as an attribute whenever the column name could be a method:
`row["sample"]` is never ambiguous.

Only code running directly in the notebook kernel can use `plt.show()` or
`display(...)`. When in doubt, save and reference -- that works either way.

Fetched files land in the working folder by default, which is the only place
readable from here. Pass `dest=` only to choose a subfolder of it.

A file already present is not fetched again: an artifact is immutable, so a
complete local copy is the artifact. Re-running an analysis costs nothing, and
the same file used by five scripts is transferred once.

### Instrument data files

```python
preamble, columns, rows = mat.read_data_file(artifact_id)
```

Returns the free-text preamble, the column names as written, and a float array.
The layout is discovered, not assumed, so a new provider's export reads the
same way.

**Read the preamble.** It routinely records what the numbers are and what units
they are in, and neither is recoverable from the numbers. Column names
generally carry their own units — use them rather than guessing, and convert
explicitly when comparing against a value recorded in the database, which may
be in different ones.

**Check for a grid before filtering row by row.** Many instrument exports are a
raster written long: an outer variable held constant while an inner one sweeps,
repeated. Hand the parsed rows to `as_grid()`, which detects that from the data
and reshapes it:

```python
preamble, columns, rows = mat.read_data_file(artifact_id)
g = mat.as_grid(rows, columns)
if g:
    q = g["values"]["q (W cm^-2)"]        # shape (n_outer, n_inner)
    t = g["axes"]["Time (ms)"]            # the outer axis
    R = g["axes"]["R (cm)"]               # the inner axis
    window = q[(t >= t0) & (t <= t1)]     # a slice, not a scan
```

It returns None when the rows are not a grid, so it is safe to try.

This matters more than it looks. Selecting rows with `rows[:, 0] == value`
scans the whole file, so doing it once per distinct value is quadratic in the
file's size -- minutes of work, per file, to recover a structure the header
usually states outright. Reshaped, the same questions are array slices and take
milliseconds. **If a loop is about to run once per timestep, stop and reshape
instead.** The cost is invisible while it happens: output is buffered, so a
script doing this looks hung rather than slow.

**An average over a whole file usually answers a different question from the
one a recorded value answers.** Instrument exports are resolved in time and
often in space. A sample occupies one position and is exposed during part of a
discharge, so a recorded condition describes that position and that interval,
not the whole array over the whole shot. Averaging everything can be wrong by a
large factor while looking entirely reasonable. Find the restriction first — the
exposure record and the file preamble say where and when — then average:

```python
import numpy as np
i_t = columns.index("time(msec)")           # names as the provider wrote them
t   = rows[:, i_t]
sel = (t >= t_start) & (t <= t_end)         # the exposure window
# ... and restrict in space to where the sample actually sat
```

When a rebuilt value is compared against a recorded one, state the window and
the restriction used. Agreement means little if the reader cannot see what was
averaged.

## Raw SQL

The schema is queryable directly for anything the helpers do not cover. Always
schema-qualify: the lakehouse resolves an unqualified name against `d3d`
first, where `shots` is the full plasma catalogue, so a bare `FROM samples`
asks a different question.

```sql
SELECT s.name, o.method, o.quantity, o.value_num, o.unit
  FROM materials.observations o
  JOIN materials.samples s USING (sample_key)
 WHERE o.quantity = %s
```

Tables: `deliveries`, `samples`, `exposures`, `exposure_samples`,
`exposure_params`, `exposure_shots`, `observations`, `artifacts`.

The database is PostgreSQL. Write `STRING_AGG(x, ',')` not `GROUP_CONCAT`, do
not reference a SELECT alias in `WHERE` or `HAVING`, and expect column names
back in lowercase.

One query per sample is one round trip per sample here too. If the question is
about a group, the query should mention the group -- use `IN` or a join, not a
loop.

Run it with `query` from the lakehouse client, which sits in this same
directory. A group goes in as one parameter behind one parenthesised
placeholder, and the client expands it into one placeholder per element:

```python
import d3d_lakehouse as lh

rows = lh.query("SELECT s.name, o.quantity, o.value_num "
                "FROM materials.observations o "
                "JOIN materials.samples s USING (sample_key) "
                "WHERE s.name IN (?) AND o.method = ?",
                (["W-DH", "W-DL"], "LAMS"))
```

`?` and `%s` both work as the placeholder token. The expansion needs the
parentheses and one placeholder per parameter: `IN (?)` with a list is
expanded, while `IN ?`, `IN %s` without parentheses, or `= ANY(%s)` are passed
through as written and the service rejects them.

## What the values mean

Values are reported as the provider gave them, with their own units and, where
supplied, a standard deviation in `value_std`. A quantity may be measured by
more than one method with different units and different depth sensitivity;
`quantity` alone does not identify a comparable number, so carry `method` and
`unit` through any comparison. A qualifier, when present, records a
distinction the provider made within one quantity, such as a depth band.

A sample with no row for a quantity was not measured for it. That is not a
zero, and a missing row must never be reported as one.

**A row can also be present and carry no value, and that is the same
statement.** `values_by_sample()` sets `measured` to False on such an entry
and leaves `value_num` as None; `observations()` shows it as a row whose
`value_num` and `value_text` are both empty. It means the delivery names the
measurement and reports no result for it -- the provider listed the
measurement and then did not make it, or withdrew it. Write "not measured"
for that sample and method, and leave it out of any ratio, mean or total.

Read None as the absence of a number, not as the number zero. The distinction
is the whole content of a reference sample: a coupon that reads a measured
zero is evidence that the species arrived during the exposure, while a coupon
that was never measured is evidence of nothing, and a sentence that turns the
second into the first states as established the very thing it was supposed to
demonstrate. Check `measured` before writing a number into a sentence:

```python
v = mat.values_by_sample(names, quantity=q, method=m)
for n in names:
    e = v.get(n)
    if e is None:
        print(n, "no row -- not measured")
    elif not e["measured"]:
        print(n, "row present, no value -- not measured")
    else:
        print(n, e["value_num"], e["unit"])
```

**A number belongs to the method that produced it.** Where the method you
asked for reports nothing, report that method as not measured and name the
other method separately with its own value. Substituting a second method's
number under the first method's name states a measurement that was never
made, and it is the reader who knows the instruments who will catch it.

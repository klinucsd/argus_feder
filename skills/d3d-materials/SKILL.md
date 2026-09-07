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

`artifacts()` lists them; `kind` and `media_type` say what each one is. Read
those back rather than assuming — they follow how the provider organised the
delivery.

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
- **Mixed magnification.** Two images at different magnifications differ
  visibly, but the difference is zoom. `show_images()` refuses rather than
  drawing it. Select one magnification first:

```python
mag = "50000"                              # a value seen in the metadata above
pick, seen = [], set()
for a in imgs:                             # already fetched -- do not re-query
    if a["metadata"].get("CM_MAG") == mag and a["sample"] not in seen:
        seen.add(a["sample"])
        pick.append(a)                     # one image per sample, same settings
mat.show_images([a["artifact_id"] for a in pick],
                labels=[a["sample"] for a in pick],
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

**Save it into the working folder, then reference it from the final answer:**

```python
fig.savefig("retention_by_method.png", bbox_inches="tight")   # in the script
```

then, in the answer text itself:

```
![Deuterium retention by method](retention_by_method.png)
```

The reference is resolved against the working folder when the answer is
rendered, so a bare filename is right -- no directory, no absolute path. Every
figure worth making is worth referencing; one that is saved but never
referenced is invisible, which is indistinguishable from never having made it.

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

## What the values mean

Values are reported as the provider gave them, with their own units and, where
supplied, a standard deviation in `value_std`. A quantity may be measured by
more than one method with different units and different depth sensitivity;
`quantity` alone does not identify a comparable number, so carry `method` and
`unit` through any comparison. A qualifier, when present, records a
distinction the provider made within one quantity, such as a depth band.

A sample with no row for a quantity was not measured for it. That is not a
zero, and a missing row must never be reported as one.

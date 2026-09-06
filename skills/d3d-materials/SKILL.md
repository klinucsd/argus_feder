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

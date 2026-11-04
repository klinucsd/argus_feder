---
name: cmf-provenance
description: Read pipeline provenance from a CMF metadata server -- which code, parameters, inputs and software environment produced a result, what each pipeline run recorded about itself, and how its output files descend from one another. Use when asked how a result was produced or whether it can be reproduced, which data snapshot or parameter values an analysis used, why two results differ, what prior analyses exist, or where a file came from. It does not hold the data files themselves, and it does not describe how datasets entered the lakehouse.
---

# Pipeline provenance in CMF

CMF is a metadata server. It records what a computational pipeline did: the
stages it ran, the code and parameter values each stage used, the artifacts it
produced, and how those artifacts descend from one another.

Import the helpers, which are beside this file:

```python
import sys; sys.path.insert(0, "/path/to/this/skill/directory")
import cmf_client as cmf
```

Credentials come from `KEYCLOAK_USERNAME` and `KEYCLOAK_PASSWORD`, in the
environment or in a `.env` beside the notebook. The helpers find them; no setup
cell is needed.

## Start by asking what is there

Never assume a pipeline name, a stage name or a property name. Every one of them
is chosen by whoever pushed the pipeline, and a name that exists today may not
exist tomorrow.

```python
cmf.pipelines()          # every pipeline this user may see
cmf.overview()           # all of them summarised in one call: stages, counts,
                         # artifact types, and which property names each uses
```

`overview()` is the right opening move for any question of the form "what work
exists" or "has anyone already done X". It answers for the whole server in one
call. Do not loop over pipelines calling single-field accessors -- each call is
an HTTP round trip.

For one pipeline, take it whole:

```python
p = cmf.pipeline(name)   # stages, executions, artifacts and lineage together
```

## What the records contain

`cmf.executions(name)` returns one entry per stage run:

```python
{"id": ..., "stage": ..., "uuid": ...,
 "git_repo": ..., "git_start_commit": ..., "git_end_commit": ...,
 "properties": {...}}
```

**`properties` is provider-chosen.** The keys are whatever that pipeline
recorded -- a script path, an input data snapshot, signal identifiers, numeric
thresholds, a time window, a fit expression. Read the keys that are present;
never write code or prose that assumes a particular key exists. `overview()`
reports the property names each pipeline actually uses, so look there first and
report what you find rather than what you expected.

`cmf.artifacts(name)` returns one entry per artifact, with a `type`:

- **`Metrics`** carries numbers in `properties` -- these are what a stage chose
  to record about its own run.
- **`Dataset`** and **`Environment`** carry a `hash` and a `location`, and
  **not** their contents.

`cmf.metrics(name)` returns just the recorded numbers, keyed by artifact name.

## Three questions this answers well

**Why do two results differ?** Line up the parameters and look for the one that
is not the same.

```python
rows = cmf.parameters_table()        # one row per stage, across pipelines
```

Differences in an input snapshot, a time window, a threshold, or the identifier
of the signal used are the usual causes. A signal recorded under two different
naming schemes is the subtlest of these: the same physical quantity fetched two
ways is a real difference in provenance even when both are correct.

**Where did this file come from?** Match its hash.

```python
cmf.find_by_hash(digest)             # searches every visible pipeline
```

**Can this be reproduced?** The repository, the commit and the environment
artifact are recorded per stage. Report the identifiers; do not claim the
reproduction is possible without checking that the repository and the artifact
store are reachable from where the reader sits. Usually they are not.

## What CMF does not tell you

State these plainly rather than filling the gap:

- **It records what ran, never whether the result is right.** A recorded fit
  coefficient or correlation is a number a script produced on the inputs it was
  given. It is not an established result, and quoting it as a physical finding
  is the most likely way this metadata gets misused.
- **It holds references, not data.** An artifact gives you a hash and a
  location. If the location is not reachable from here, the honest answer is
  that the artifact exists, here is its hash and what produced it, and the
  contents cannot be fetched.
- **Absence is not evidence.** Nothing in CMF means nobody pushed. It does not
  mean nothing was run. Say the first, never the second.
- **Nothing can be retracted.** The server is append-only: no update and no way
  to delete metadata. A pipeline name, once used, is permanent -- so a name that
  looks like a test may still be the only record of real work.
- **It is not the lakehouse.** CMF answers "what did a pipeline run produce".
  How a dataset entered the lakehouse is recorded in the lakehouse's own ingest
  tables, which are the origin for that question, not a fallback. If a question
  is about how data got into the archive, this skill is the wrong source.

## Lineage has more than one view

`cmf.lineage(name)` returns every view the server offers, keyed by name. The
views do not always agree: one can come back empty while another renders the
same pipeline correctly. Read the artifacts first, use whichever view answers,
and report an empty view as a gap in that view rather than as a pipeline without
lineage.

Lineage links artifacts to executions by **name**. Do not join on an artifact
id; the event records may not carry one.

## Authorisation is per user

The server decides what a caller may read from the role in that caller's own
token. Two consequences:

- A refusal is an **answer**, not a malfunction. The helpers raise
  `CMFForbidden`; report that this user is not authorised for that pipeline, and
  do not retry or work around it.
- Every discovery answer is scoped to the asking user. "The pipelines" always
  means "the pipelines you can see", so phrase it that way. Before reporting
  that the server holds little, call `cmf.whoami()` -- a short list may reflect a
  narrow role rather than an empty server.

```python
cmf.whoami()   # username, realm, the roles the token carries, seconds remaining
```

Tokens are short-lived and the helpers re-authenticate as needed. A session long
enough to outlive the refresh window will need the credentials again; if that
happens, say so rather than reporting the data as unavailable.

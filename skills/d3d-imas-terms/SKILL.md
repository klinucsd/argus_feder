---
name: d3d-imas-terms
description: "Translate between IMAS standard names and DIII-D signal names. USE FOR ANY request mentioning IMAS, IDS, an IMAS path (e.g. equilibrium.time_slice.global_quantities.ip, core_profiles, magnetics.ip.data), 'what is X called in IMAS', 'IMAS name for', 'standard name', or the reverse (which IMAS quantity a DIII-D signal like \\ipmhd or CPASMA corresponds to). Lookup only -- it resolves names, it does not fetch data."
license: Apache-2.0
compatibility: Pure JSON lookup -- no toksearch, no MDSplus, no network. Works in-kernel anywhere including Colab.
metadata:
  author: DeepTok
  version: "1.0"
---

# IMAS <-> DIII-D terminology lookup

IMAS is the device-neutral standard vocabulary for fusion data
(`equilibrium.time_slice.global_quantities.ip`). DIII-D stores the same
quantities under its own historical names (`\EFIT01::TOP.MEASUREMENTS.CPASMA`).
This skill translates between them.

**This skill resolves NAMES ONLY. It does not fetch data.** To fetch, take the
`mds_path` and `tree` it returns and hand them to `d3d-shot-fetcher`.

## Start from this script -- verified, and its real output is below

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-imas-terms"))
from d3d_imas_terms import imas_to_d3d, d3d_to_imas, search, table_info

# 1. IMAS name -> DIII-D signal. Array indices in the input are fine.
r = imas_to_d3d("equilibrium.time_slice[0].global_quantities.ip", shot=165920)
print(f"IMAS  {r['imas_path']}")
print(f"  DIII-D   {r['mds_path']}   (tree {r['tree']})")
print(f"  verified {r['verified']} on shots {r['verified_on_shots']}")
if r.get("cocos_warning"):
    print(f"  CAUTION  {r['cocos_warning']}")

# 2. The other direction.
print("\nDIII-D CPASMA is used by:")
for h in d3d_to_imas("CPASMA")[:3]:
    print(f"  {h['imas_path']}")

# 3. Free-text search when the exact IMAS path isn't known.
print("\nsearch('elongation'):")
for h in search("elongation", limit=3):
    print(f"  {h['imas_path']:52} -> {h['mds_path']}")

# 4. Not in the table -> None. Say so; never invent a mapping.
print("\nunknown:", imas_to_d3d("equilibrium.made_up_field"))

i = table_info()
print(f"\ntable: {i['summary']['imas_fields_verified']} verified of "
      f"{i['summary']['imas_fields']} fields, upstream {i['upstream_commit'][:8]}")
```

Actual output (run in-kernel with plain `python /abs/path/script.py` -- this
skill needs no `fdp`, it touches no data):

```
IMAS  equilibrium.time_slice.global_quantities.ip
  DIII-D   \EFIT01::TOP.MEASUREMENTS.CPASMA   (tree EFIT01)
  verified True on shots [91388, 156199, 165920, 168442, 181681, 198189]
  CAUTION  Sign convention differs: apply the TOR COCOS transform. Serving the raw DIII-D value under this IMAS name can be sign-flipped.

DIII-D CPASMA is used by:
  equilibrium._cpasma
  equilibrium._cpasma_cocos
  equilibrium.time_slice.constraints.ip.reconstructed

search('elongation'):
  equilibrium.time_slice.boundary_separatrix.elongation -> \EFIT01::TOP.RESULTS.AEQDSK.KAPPA

unknown: None

table: 258 verified of 294 fields, upstream 8873703c
```

## Rules

**1. Never invent a mapping.** If `imas_to_d3d()` returns `None`, the field is
not in the table -- say exactly that. IMAS and DIII-D names are unrelated
vocabularies; a DIII-D name cannot be guessed from an IMAS name or vice versa.
Offer `search()` results instead.

**1b. When the requested name is absent, do NOT claim a near-match is the same
quantity.** Offering related rows is helpful; asserting equivalence is not.
Verified 2026-08-03 on a real run: asked for `\ipmhd`, the answer correctly
reported it absent, then stated `\ipmhd` and `CPASMA` "return identical values
for the same shot." They do not. On shot 165340:

| expression | resolves to | samples | min |
|---|---|---|---|
| `\ipmhd` | `\EFIT01::TOP.RESULTS.AEQDSK:IPMHD` | 311 | 2.9202e5 |
| `\EFIT01::TOP.MEASUREMENTS.CPASMA` | `…MEASUREMENTS:CPASMA` | 315 | 2.718e5 |

Different nodes, different lengths, different values -- one is the EFIT
*measurement constraint*, the other the *fitted output*. (Confusingly there are
two CPASMA nodes: `RESULTS.GEQDSK.CPASMA` does match `\ipmhd` exactly, while
`MEASUREMENTS.CPASMA` -- the one this table maps -- does not.) Say "the table
maps X, which is a related but distinct signal", never "they are the same".

**2. Always surface the COCOS caution when present.** 22 fields carry a
`cocos_transform`. DIII-D and IMAS use different sign/orientation conventions,
so presenting a raw DIII-D value under the IMAS name can give a
**sign-flipped** number -- correct magnitude, correct units, wrong sign, and
nothing catches it automatically. If the row has `cocos_warning`, state it in
the answer; do not bury it.

**3. Report verification status, don't imply certainty.** Each row records
whether it was confirmed by actually fetching it and on which shots. Say
"verified on shots …" rather than presenting every row as equally certain.
Rows with `verified: false` carry a `caution` field -- repeat it.

**4. Mappings are time-scoped.** Availability changes across DIII-D's history:
diagnostics were added and retired, and sampling rates changed by up to 100x
for the same signal. Pass `shot=` when the user mentions one, and report
`verified_for_shot`. A mapping verified on recent shots may not hold for a
1990s shot.

**5. Rows with `parameterized: true` are templates, not names.** They need a
channel or system argument (`required_parameters` lists which). Don't present
`\ECE::TOP.TECE.TECE{01-NUMCH}` as if it were a fetchable signal.

**6. Coverage is partial -- 294 of 566 IMAS fields.** Don't imply the table is
the complete IMAS standard. If something is absent, that means it is absent
from *this table*, not that it doesn't exist in IMAS.

## Functions

- `imas_to_d3d(imas_path, shot=None, verified_only=True)` -> row dict or `None`.
  Array indices in the input are stripped, so `time_slice[0]` matches
  `time_slice`.
- `d3d_to_imas(signal, tree=None)` -> list of IMAS fields backed by that DIII-D
  signal. Matches a full path, a PTDATA pointname, or a trailing fragment
  (`CPASMA` works as well as `\EFIT01::TOP.MEASUREMENTS.CPASMA`).
- `search(term, limit=20)` -> free-text across IMAS paths, DIII-D paths and
  summaries. Use when the exact IMAS path isn't known.
- `list_ids(verified_only=False)` -> which IMAS systems are covered, and how many
  fields each.
- `cocos_fields()` -> every field whose sign convention differs.
- `table_info()` -> provenance and coverage. Cite this rather than guessing how
  current or complete the table is.

## Row fields

| field | meaning |
|---|---|
| `mds_path`, `tree` | the DIII-D signal, ready to hand to `d3d-shot-fetcher` |
| `ptdata_pointname` | set when the source is PTDATA rather than an MDSplus tree |
| `cocos_transform` | sign/orientation conversion required (see rule 2) |
| `unit_transform` | inline unit conversion, e.g. `/1000.` for ms -> s |
| `verified`, `verified_on_shots` | whether a real fetch succeeded, and where |
| `confidence` | `documented` > `literal` > `derived` > `template` |
| `resolved_via` | the internal chain, when the field has no direct path |
| `parameterized`, `required_parameters` | needs a channel/system argument |

## Provenance

Extracted from GA's [`imas_composer`](https://github.com/GA-FDP/imas_composer)
(Apache-2.0); the underlying correspondence descends from the OMAS DIII-D
machine mappings. The extractor and verification harness live in
`feder/imas_d3d_mapping/`. Re-run them against a newer upstream checkout to
refresh the table.

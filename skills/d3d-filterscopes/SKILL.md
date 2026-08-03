---
name: d3d-filterscopes
description: DIII-D D-alpha filterscope signals and pointnames (D-alpha / Dalpha / D_alpha / Dα) in the spectroscopy tree. USE FOR ANY request about filterscope pointnames, D-alpha channels, or ELM (Edge Localized Mode) light — e.g. list/enumerate the D-alpha filterscope pointnames for a shot and resolve each to its MDSplus node path, or fetch the raw ~50 kHz photon-flux traces. Prefer this over the general shot-fetcher skill for filterscope/D-alpha/ELM questions.
license: Apache-2.0
compatibility: Designed for deepagents CLI with fdp-d3d
metadata:
  author: DeepTok
  version: "1.0"
---

# DIII-D D-alpha Filterscope Skill

Use this skill whenever a request asks about D-alpha (Dalpha, D_alpha, Dα)
filterscope signals or pointnames, or about the light traces used to detect ELMs.

## The canonical answer (read this first)

The D-alpha filterscope signals live in the **`spectroscopy`** tree. There are TWO
different structures in that tree, and only one is the raw signal:

- CORRECT — the raw D-alpha filterscope light traces are the tags ending in `DA`:
  `\FS00DA`, `\FS04DA`, `\FS04UPDA`, `\FS01DWDA`, `\ELM1MIDDA`, ... Each resolves to
  a node `\SPECTROSCOPY::TOP.FILTERSCOPE.PMT<nn>:PHOTON_FLUX` — usage SIGNAL,
  ~400,000 samples per shot at ~50 kHz, units `ph/cm2/sr/s`. These carry the ELM
  bursts. The tag `\fs04` is the same node as `\FS04DA` (both map to PMT42).
- WRONG — do NOT report the `PHD.D_ALPHA`, `PHD.D_ALPHA_ELM`, `PHD.D_ALPHA_FAST`,
  or `PHDM.D_ALPHA` subtrees as "the D-alpha filterscope pointnames." Those are
  small derived/summary nodes (e.g. `\SPECTROSCOPY::TOP.PHD.D_ALPHA:FS04` has
  length ~280, not the ~400k-sample raw trace). They are not the signal you fetch
  for ELM work, and some of their stored pointnames are mislabeled (e.g. the
  `D_ALPHA_ELM` members carry `PHD..C3` = carbon-III names, not D-alpha).

So: "D-alpha filterscope pointnames" == the `*DA` tags resolving to
`FILTERSCOPE.PMT<nn>:PHOTON_FLUX`.

## How to enumerate the D-alpha pointnames for a shot

The D-alpha filterscope pointnames are the tags ending in `DA`. Use this
ready-made function — it filters `findTags` to `*DA`, resolves each to its node
path, and labels which are the raw photon-flux traces. Do NOT walk the PMT
structure nodes by hand: that returns ALL spectral lines (C-II, C-III, He,
broadband, ...), not just D-alpha, and is the common wrong answer.

```python
def list_dalpha_pointnames(shot, tree="spectroscopy"):
    """D-alpha filterscope pointnames for a shot -> MDSplus node paths.

    Returns a list of {"tag", "node_path", "kind"} where kind is one of
    photon_flux | photo_el_sig | midplane | elm | obsolete | other | unresolved.
    The raw ~50 kHz D-alpha traces used for ELM detection are the 'photon_flux'
    rows (the \\FS##DA tags -> FILTERSCOPE.PMT##:PHOTON_FLUX).
    findTags returns bytes -- decode them.
    """
    from MDSplus import Tree
    t = Tree(tree, shot)
    tags = sorted({x.decode() if isinstance(x, bytes) else str(x)
                   for x in t.findTags("*")})
    rows = []
    for tag in tags:
        if not tag.upper().endswith("DA"):
            continue
        try:
            fp = t.getNode(tag).getFullPath()
        except Exception:
            rows.append({"tag": tag, "node_path": None, "kind": "unresolved"}); continue
        up = fp.upper()
        if   "PHOTON_FLUX"  in up: kind = "photon_flux"
        elif "PHOTO_EL_SIG" in up: kind = "photo_el_sig"
        elif "MIDPLANEFS"   in up: kind = "midplane"
        elif "D_ALPHA_ELM"  in up or "PHDM" in up: kind = "elm"
        elif "OBSOLETE"     in up: kind = "obsolete"
        else:                      kind = "other"
        rows.append({"tag": tag, "node_path": fp, "kind": kind})
    return rows

# Usage (run under the fdp wrapper):
rows = list_dalpha_pointnames(165920)
flux = [r for r in rows if r["kind"] == "photon_flux"]   # the raw D-alpha traces
for r in flux:
    print(f'{r["tag"]:12s} -> {r["node_path"]}')
print(f'{len(flux)} raw D-alpha traces; {len(rows)} *DA tags total')
```

For a typical shot expect ~24 `photon_flux` pointnames (the answer to "which
D-alpha filterscope pointnames exist"), plus `photo_el_sig` / `midplane` / `elm` /
`obsolete` variants (~62 `*DA` tags total). Channel number is NOT the PMT number
(`\fs04` -> PMT42, `\FS00` -> PMT24) — always resolve the real path, never infer.

## Two members per channel (photon flux vs photo-electric)

Each filterscope channel exposes two related members at the same PMT:
- `:PHOTON_FLUX` — calibrated photon flux (units `ph/cm2/sr/s`), addressed by the
  `\FS##DA` tag. THIS is the D-alpha signal for ELM detection.
- `:PHOTO_EL_SIG` — the raw photo-electric current, addressed by the `\PMC##DA`
  tag (the same PMT as the matching `\FS##DA`).

So `\FS04DA` and `\PMC04DA` are the calibrated and raw views of PMT42's D-alpha.

## How to fetch a filterscope signal

Fetch by the tag (or the PMT node path) from the `spectroscopy` tree with
TokSearch. The raw trace is ~400k samples at ~50 kHz — high enough to resolve
individual ELMs (which recur at 10-200 Hz and last ~200-500 us each).

```python
from toksearch import MdsSignal, Pipeline
import numpy as np

p = Pipeline([165920])
p.fetch("fs04", MdsSignal(r"\fs04", "spectroscopy"))   # fetch() mutates in place, returns None
rec = p.compute_serial()[0]

if "fs04" in rec.errors:            # use rec.errors, NOT rec.has_error()
    print("fetch failed:", rec.errors["fs04"])
else:
    sig = rec["fs04"]               # signals return a dict, not a raw array
    data = np.asarray(sig["data"])  # extract the array
    times = np.asarray(sig["times"])
    dt = np.median(np.diff(times))  # times are in ms for this signal
    # dt is in MILLIseconds, so 1/dt is already kHz -- do NOT write 1e3/dt and
    # call it kHz, that yields Hz and reports the rate 1000x too high
    # (verified 2026-08-02: the old example printed "49952.5 kHz" for a real
    # ~50 kHz trace; a live run caught it and had to self-correct).
    print(f"samples={data.size}  rate={1/dt:.2f} kHz  span={times[-1]-times[0]:.1f} ms")
```

## Checking which shots have a filterscope signal archived

To answer "across a shot range, which shots have `\fs04` (or another filterscope
signal) archived" (FEDER competency question Q7), use this function -- it checks
presence via `getNode`+`getLength`, not a full data fetch, one shot at a time.

```python
def _check_one_shot_availability(args):
    """Module-level (NOT nested) on purpose -- multiprocessing.Pool cannot
    pickle a closure/nested function. Takes a single (shot, expr, tree) tuple
    so it works with pool.map()."""
    shot, expr, tree = args
    from MDSplus import Tree
    try:
        t = Tree(tree, shot)
        n = t.getNode(expr)
        available = n.getLength() > 0
    except Exception:
        available = False
    return {"shot": shot, "available": available}


def check_filterscope_availability(shots, expr=r"\fs04", tree="spectroscopy", workers=8):
    """For each shot, does `expr` exist and carry data in `tree`?

    Returns a list of {"shot", "available"} in the same order as `shots`.
    Runs across `workers` processes (default 8 -- measured ~5x speedup over
    serial; more workers plateau fast, see the cost note below). Pass
    workers=1 to force the old serial behavior.

    IMPORTANT: define `_check_one_shot_availability` at the TOP LEVEL of your
    script (not nested inside another function) -- multiprocessing.Pool needs
    to pickle it by name, which fails for nested/closure functions.
    """
    tasks = [(shot, expr, tree) for shot in shots]
    if workers <= 1 or len(shots) <= 1:
        return [_check_one_shot_availability(t) for t in tasks]
    from multiprocessing import Pool
    with Pool(processes=workers) as pool:
        return pool.map(_check_one_shot_availability, tasks)
```

**Composition with `d3d-relational-db`** -- the canonical Q7 pattern is: get
candidate shots from the shot-metadata database, then check archive presence for
each on Pelican:

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/d3d-relational-db"))
from d3d_relational_db import plasma_shots_in_range

shots = plasma_shots_in_range(190000, 190020)              # step 1: candidates (fast, no network)
rows = check_filterscope_availability(shots)                # step 2: Pelican presence, 8 parallel workers by default
have_it = [r["shot"] for r in rows if r["available"]]
print(f"{len(have_it)}/{len(shots)} shots have \\fs04 archived: {have_it}")
```

**Cost note (measured, not a guess):** each shot costs roughly 200-400ms
serially. The default `workers=8` gives close to a 5x speedup over serial (measured
separately on a comparable fetch) -- still fine for a couple hundred shots in
under a minute, but a genuinely large range (thousands of shots) will still take
**minutes**, not seconds -- more workers past ~8-30 plateau fast (shared
bottleneck on the Pelican origin, not local CPU), so don't expect linear gains
from cranking `workers` way up. For a wide range, either narrow it
to a small span first, or state plainly that a full scan will take a while
rather than silently running long or silently sampling without saying so.

## Verify your own summary before presenting it

Before stating a count or an "X out of Y" claim (e.g. "18 out of 18 shots have
`\fs04`"), count the rows in the table you are actually about to display and
confirm it matches. If a query returned 18 shots, the table you print must have
18 rows and the text must say 18 -- not silently drop one while still claiming
the original total. This has happened before: correct availability-check code,
correct data, but the final written table was missing a row the summary text
didn't notice. Do the arithmetic on what you are about to show, not on what you
expected to compute.

**Range compression is a second way to get this wrong even when the count is
right.** If you summarize a shot list as ranges (e.g. `190044-190117`) instead
of listing every shot, the ranges must decode back to EXACTLY the stated count
-- not just look plausible. A real shot list has gaps (missing shot numbers
that were never plasma shots at all), and collapsing "190044, 190045, ...,
190071, 190076, 190077, ..." into "190044-190117" silently erases that internal
gap, overstating how many shots actually have the signal. Before presenting
compressed ranges, sum `(hi - lo + 1)` for each range and confirm the total
equals your stated count. If it doesn't, or if you are not certain a span is
truly gap-free, list the shots individually instead of compressing them.

## Execution

Run any script that touches DIII-D data with the fdp wrapper (both the
`MDSplus.Tree` enumeration and the TokSearch fetch above):

```
fdp run python script.py
```

Do NOT hardcode an absolute path to `fdp`/`python` (e.g. `/opt/conda/bin/fdp`)
-- verified 2026-08-02: the real location varies by environment
(`/opt/conda/bin/` in the JupyterHub/Docker image, `/usr/local/bin/` on Colab
under `condacolab`), and a hardcoded script breaks on whichever one it wasn't
written for. Plain `fdp run python script.py` (normal `PATH` resolution) is
verified working end-to-end on both.

## Notes

- Data-quality: midplane channels (`*MIDDA` -> `MIDPLANEFS`) may have broken units
  metadata; obsolete channels (e.g. `FS230BUMP...`) may carry no data. Report the
  path, and flag units/length problems rather than dropping the channel silently.
- The precise viewing geometry (which divertor location / chord) is NOT stored in
  the tree; the tag name only encodes region hints (`UP`/`DW`, midplane vs
  divertor). Treat exact geometry as unknown unless given a mapping.

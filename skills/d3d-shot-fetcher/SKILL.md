---
name: d3d-shot-fetcher
description: Fetch plasma data for DIII-D shot numbers — elongation (kappa), poloidal flux (psirz), plasma current (ipmhd), stored energy (wmhd), beta, and other efit01 signals
license: Apache-2.0
compatibility: Designed for deepagents CLI with fdp-d3d
metadata:
  author: DeepTok
  version: "1.3"
---

# DIII-D Shot Data Fetcher Skill

## First: D-alpha / filterscope / ELM requests go to another skill

If the request mentions D-alpha (Dalpha, D_alpha, Dα), filterscopes, ELM (Edge
Localized Mode) light, or spectroscopy-tree pointnames, STOP and use the
`d3d-filterscopes` skill and its `list_dalpha_pointnames()` function. Do NOT
enumerate the spectroscopy tree yourself. The D-alpha filterscope pointnames are
the tags ending in `DA` that resolve to `FILTERSCOPE.PMT##:PHOTON_FLUX` — NOT the
full set of PMT channels (those span many spectral lines: C-II, C-III, He,
broadband, ...). This skill (below) is for `efit01` and other scalar/profile trees.

## Execution rule

Every Python script that fetches DIII-D data must be run with:

```
fdp run python script.py
```

**Do not hardcode an absolute path to `fdp` or `python`** (e.g.
`/opt/conda/bin/fdp`) -- verified 2026-08-02: this environment's real
`fdp`/`python` location varies (`/opt/conda/bin/` in the JupyterHub/Docker
image, `/usr/local/bin/` on Colab under `condacolab`), and a script hardcoded
to one breaks on the other with confusing errors (wrong interpreter, missing
`toksearch`) that cost several debugging turns to diagnose live. Plain
`fdp run python script.py`, relying on normal `PATH` resolution, has been
verified end-to-end (real data, correct values) on BOTH environments -- use
it exactly as written, no absolute paths.

This is the only working invocation shape. All other forms fail silently and
return 0 shots:
- `python script.py` — fails (skips fdp's environment setup entirely)
- `fdp python script.py` — fails (old fdp CLI form; `fdp` is now a subcommand CLI, `run` is required)
- setting env vars manually and calling python — fails

When writing an execute call, always use `fdp run python script.py`. Never deviate from it.

**Exception -- interactive charts (Plotly / ipywidgets):** an interactive chart
must render in the notebook, so run that script IN-KERNEL with plain
`python /path/to/script.py` (NOT the fdp wrapper -- fdp is a subprocess and cannot
render interactive output). In-kernel scripts inherit the kernel's Pelican
environment, so TokSearch fetches still work. See the `signal-zoom` skill. This
exception applies ONLY to interactive rendering; every other data script uses the
fdp command above.

## Data access constraints

Data comes from the Pelican mirror. MDSplus tree paths for ALL DIII-D trees are
configured at kernel start (or by calling `reload_pelican()`), so many trees
work -- not just efit01. Verified working:
- `efit01` -- computed equilibrium (EFIT). Signal current is in Amps (A).
- `spectroscopy` -- raw diagnostics, including the D-alpha filterscopes used for
  ELM detection. For those, use the `d3d-filterscopes` skill.

Other trees the environment sets up (the many efit variants, transp, zipfit,
onetwo, electrons, ...) are generally reachable too -- try them; a failed tree
shows up as an entry in `rec.errors`, not a crash.

Common `efit01` signals:
- `\kappa` — plasma elongation
- `\ipmhd` — plasma current (A)
- `\betap` — poloidal beta
- `\betat` — toroidal beta
- `\q95` — safety factor at 95% flux surface
- `\wmhd` — plasma stored energy
- `\psirz` — poloidal flux, 2D (r, z, times), requires dims parameter
- `\ne` — electron density profile
- `\t_e` — electron temperature profile

The `fetch_dataset` + `\psirz` anchor pattern below is specific to `efit01`. For
other trees (e.g. `spectroscopy`), a plain `MdsSignal(expr, tree)` fetch with
`compute_serial()` works fine -- see the `d3d-filterscopes` skill.

**Plot titles/labels: don't wrap a signal's backslash-prefixed name in
matplotlib mathtext.** Every signal name in this skill starts with `\` (e.g.
`\ipmhd`). Putting one inside `$...$` (mathtext, e.g. `f"...($\\{name}$)"`)
makes matplotlib try to parse it as a LaTeX command and it can crash on a
malformed one (verified 2026-08-02, cost a live debugging round-trip). Use
the signal name as plain text in titles/labels -- it doesn't need to render
as math.

## The `d3d` master tree -- read this before concluding a signal doesn't exist

Most subsystems (IONS, TRANSPORT, MHD, plus a second, DIFFERENT copy of
SPECTROSCOPY) are NOT standalone MDSplus trees. They are branches nested
under `TOP` inside a single master tree called `d3d`. Only a handful of
subsystems ALSO have their own genuine standalone top-level tree -- `efit01`
and `spectroscopy` are the two verified in this project.

**The mistake this causes (verified 2026-08-01, real case):** asked for shot
165340's Zeff, a script tried `Tree("IONS", 165340)` -- because d3drdb's own
`SIGNAL_NAMES.Tree` column literally says `'IONS'` for that signal, and
`Full_Path` is `\D3D::TOP.IONS.IMPDENS:ZEFF`. Opening a tree named `"IONS"`
fails (it isn't one), and the script concluded the signal "isn't found" --
then fell back to a different, transport-code-DERIVED Zeff instead of the
directly-measured one, and reported the wrong one as "the most complete
Zeff product available." **The measured signal was fetchable the whole
time**, just under the wrong tree name:

```python
from toksearch import MdsSignal
# WRONG -- "IONS" is a branch label from SIGNAL_NAMES.Tree, not a real tree:
MdsSignal(r"\zeff", "IONS")        # fails, but does NOT mean the signal is missing

# RIGHT -- open the master tree instead, same short tag:
MdsSignal(r"\zeff", "d3d")         # SUCCESS -- 294 samples, range 1.37-3.00
```

**Rule: if `SIGNAL_NAMES.Tree` (or any branch-looking name from a
`Full_Path` like `\D3D::TOP.<Branch>...`) fails to open as a tree, retry with
`tree="d3d"` and the SAME short tag (`\` + `SIGNAL_NAMES.Name`) before
concluding the signal doesn't exist.** Do not silently substitute a
different, lower-quality, or differently-derived signal (e.g. a transport
code's modeled value instead of a direct measurement) without both (a)
actually retrying against `d3d` first, and (b) if a substitution is still
necessary, saying clearly in the final answer that a different quantity was
used and why, not that the standard one "isn't found."

**Second, related bug (verified 2026-08-01, same Zeff case, after the fix
above): don't cite `SIGNAL_NAMES.Full_Path` verbatim as "the signal path" in
your final answer -- it can be stale.** For this exact case, `d3drdb`'s
catalog says `Full_Path` = `\D3D::TOP.IONS.IMPDENS:ZEFF` for `ZEFF`, but that
path does NOT exist (`TreeNNF`, node not found) -- the tag `\zeff` actually
resolves to a DIFFERENT real node, `\D3D::TOP.SPECTROSCOPY.VB.ZEFF:ZEFF`. The
fetched DATA was correct (the tag lookup found the right node regardless),
but a report that quotes the catalog's `Full_Path` string as the source can
print a path that doesn't even exist. **Rule: when reporting which MDSplus
node a value came from, call `.getFullPath()` on the node object you actually
fetched (or that `MdsSignal` resolved) and report THAT string -- never quote
`SIGNAL_NAMES.Full_Path` (or any other catalog field) as if it were
independently verified.** The catalog is a hint for what to try, not a
citation-quality source of truth.

**Third, related bug (verified 2026-08-01): don't state what a signal MEANS
from its name -- look it up, even when meaning wasn't the question asked.**
Asked only for `\EFIT01::CPASMA`'s full path, a script correctly resolved the
path (`\EFIT01::TOP.RESULTS.GEQDSK:CPASMA`) but then volunteered, unprompted,
that CPASMA is "the plasma cross-sectional area (in m²)" -- wrong. The real
`d3d-relational-db` catalog entry says `Description: "Plasma current"`,
`Units: A` -- CPASMA is the same physical quantity as `\ipmhd`, not an area.
The mistake wasn't caught until a LATER, unrelated question happened to query
the catalog for a different reason. **Rule: any time an answer states what a
signal physically represents -- whether that was the actual question or just
supporting color -- get that meaning from `d3d-relational-db`'s
`search_signal_catalog()` (or equivalent `SIGNAL_INFO` lookup), never infer it
from the tag name alone.** Verification discipline applies to everything
stated in the answer, not only to the part that was explicitly asked for --
a domain scientist reading the answer can't tell which parts were "the
question" and which were bonus context, and will trust both equally.

## Required code pattern

Always use this structure. Deviations (e.g., omitting psirz, using compute_serial) may reduce reliability.

```python
from toksearch import MdsSignal, Pipeline

def create_pipeline(shots):
    pipe = Pipeline(shots)
    dims = ("r", "z", "times")
    # Always include psirz as a 2D anchor signal
    psirz_signal = MdsSignal(r"\psirz", "efit01", dims=dims, data_order=["times", "z", "r"])
    # Add the signals you need
    kappa_signal = MdsSignal(r"\kappa", "efit01")
    pipe.fetch_dataset("ds", {"kappa": kappa_signal, "psirz": psirz_signal})

    @pipe.where
    def no_errors(rec):
        return not rec.errors

    return pipe

def main():
    shots = [188702, 191744]
    pipe = create_pipeline(shots)
    results = pipe.compute_multiprocessing()
    print(f"Got {len(results)} shots")
    for res in results:
        shot = res['shot']
        ds = res['ds']
        kappa = ds['kappa'].values
        times = ds.coords['times'].values
        print(f"Shot {shot}: kappa {kappa.min():.3f} - {kappa.max():.3f}, {len(times)} time points")

if __name__ == "__main__":
    main()
```

Run this script with:
```
fdp run python script.py
```

Expected output:
```
Got 2 shots
Shot 188702: kappa 1.305 - 1.908, 314 time points
Shot 191744: kappa 1.426 - 1.950, 254 time points
```

**Don't re-check for errors inside the `for res in results:` loop -- the
`@pipe.where` filter above already removed error records, `results` only
contains clean ones.** If you do add your own extra check anyway, `res` is a
`Record`-like object, not a plain dict: use `res.errors` (attribute access,
same as the filter above), never `res.get("errors")` -- `Record` has no
`.get()` method and that call fails at runtime (verified 2026-08-02, cost a
live debugging round-trip fixing exactly this).

## Accessing fetched data

```python
ds = res['ds']
data = ds['kappa'].values          # numpy array, shape (times,)
times = ds.coords['times'].values  # time base in ms
r = ds.coords['r'].values          # radial grid (for 2D signals)
z = ds.coords['z'].values          # vertical grid (for 2D signals)
psirz = ds['psirz'].values         # shape (times, z, r)
```

## Plasma current example

```python
from toksearch import MdsSignal, Pipeline

def create_pipeline(shots):
    pipe = Pipeline(shots)
    dims = ("r", "z", "times")
    psirz_signal = MdsSignal(r"\psirz", "efit01", dims=dims, data_order=["times", "z", "r"])
    ip_signal = MdsSignal(r"\ipmhd", "efit01")
    pipe.fetch_dataset("ds", {"ip": ip_signal, "psirz": psirz_signal})

    @pipe.where
    def no_errors(rec):
        return not rec.errors

    return pipe

def main():
    shots = [188702, 191744]
    results = create_pipeline(shots).compute_multiprocessing()
    for res in results:
        ds = res['ds']
        ip = ds['ip'].values
        times = ds.coords['times'].values
        ip_MA = ip / 1e6  # raw \ipmhd is in AMPERES; divide by 1e6 for MA
        print(f"Shot {res['shot']}: IP {ip_MA.min():.2f} - {ip_MA.max():.2f} MA (raw signal is A)")

if __name__ == "__main__":
    main()
```

Run with:
```
fdp run python script.py
```

## PTDATA access

PTDATA is a SEPARATE data source from the MDSplus trees above -- raw digitizer
signals (e.g. from the plasma control system / magnetics), not equilibrium
reconstructions. Different import, different fetch class, no `tree` argument.

```python
from toksearch import Pipeline
from toksearch_d3d import PtDataSignal

def create_pipeline(shots):
    pipe = Pipeline(shots)
    pipe.fetch("ip", PtDataSignal("ip"))  # no tree arg -- PTDATA is not MDSplus

    @pipe.where
    def no_errors(rec):
        return not rec.errors

    return pipe

def main():
    shots = [165920]
    results = create_pipeline(shots).compute_serial()
    for res in results:
        d = res["ip"]["data"]
        print(f"Shot {res['shot']}: ip {d.min():.3g} - {d.max():.3g} A, {len(d)} samples")

if __name__ == "__main__":
    main()
```

Expected output:
```
Shot 165920: ip -2.8e+04 - 1.15e+06 A, 30720 samples
```

**IMPORTANT -- PTDATA only works via the `fdp run` subprocess pattern above, not
in-kernel.** Unlike efit01/spectroscopy (which work both in-kernel and via
`fdp run`), a plain in-kernel `python` fetch of PtDataSignal fails with
`getservbyname failed for task 'PTSERVER'` -- PTDATA needs `fdp run`'s full
environment, not just the token/tree-path setup the kernel configures at
startup. Never attempt PTDATA in an in-kernel/interactive-chart script.

`PtDataSignal("ip")` is a raw digitizer trace and a DIFFERENT diagnostic
pipeline than `efit01`'s `\ipmhd` (computed equilibrium reconstruction) -- same
physical quantity, different source, so don't expect identical values between
the two; report which one you fetched.

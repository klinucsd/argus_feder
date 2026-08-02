---
name: signal-zoom
description: "Render an INTERACTIVE, zoomable signal chart (Plotly, HighStock-style: drag to box-zoom, double-click to reset, range-slider to pan). Use ONLY when the request explicitly asks for a ZOOMABLE / INTERACTIVE / ZOOM-IN chart, or says zoom in/out, or mentions HighCharts / HighStock. For a normal plot/chart request WITHOUT such a term, do NOT use this skill -- render a static image (matplotlib PNG) as usual. Works for any time-series signal: filterscopes, EFIT scalars, multi-shot overlays."
license: Apache-2.0
compatibility: Colab (condacolab) -- see the TWO-STEP note below, this differs from the JupyterHub/Docker version
metadata:
  author: DeepTok
  version: "1.0-colab"
---

# signal-zoom -- Interactive, Zoomable Signal Charts (Colab)

## When to use (routing) -- the trigger term matters

Use this skill ONLY when the user's request contains a zoom/interactive trigger:
`zoomable`, `interactive chart`, `zoom-in chart`, `zoomable view`,
`let me zoom in/out`, `HighCharts-style`, `HighStock-style`.

If the request just says "plot" / "chart" / "show" with NO such term, do NOT use
this skill -- produce a normal static image (matplotlib PNG) via `d3d-shot-fetcher`
as usual. The interactive chart is opt-in via the trigger term; static image is
the default.

This applies even when an interactive chart seems like it would be nice
unprompted "bonus" value -- e.g. after computing an aggregate result across
many shots and wanting to visualize the winner. Don't reach for this skill
just because a signal happens to be available or interesting to zoom into.
Verified 2026-08-02: an aggregation-query request with no trigger word still
triggered an unprompted attempt at this skill, which then failed to render
silently -- wrong default and a silent failure, stacked. If a chart adds
value but wasn't asked for as interactive, make it static instead.

## CRITICAL: this is a TWO-STEP pattern on Colab -- read before writing any script

On the JupyterHub/Docker image, fetching and plotting can happen in one
in-kernel script. **On Colab this does NOT work**: Colab's kernel process
imports its own `numpy` (2.0.2) as part of its own startup, before any user
code runs. MDSplus needs `numpy<2` and can never be imported in-kernel here as
a result -- no `sys.path` trick fixes this, since the wrong numpy is already
bound in `sys.modules` before your script gets a chance to intervene
(verified 2026-08-02, cost real live debugging to pin down).

So fetching and plotting are two separate scripts, handed off through a
small `.npz` file:

1. **Fetch (subprocess, uses toksearch/MDSplus):**
   ```
   fdp run python fetch_script.py
   ```
2. **Plot (in-kernel, renders the chart):**
   ```
   python plot_script.py
   ```

Step 2 never imports toksearch/MDSplus -- only numpy/plotly, which the
kernel's own numpy (2.0.2, otherwise fine) handles without issue. This is why
splitting the steps works even though in-kernel toksearch cannot.

**Also fixed (verified 2026-08-02): Colab's frontend needs Plotly's renderer
set explicitly, or the chart silently doesn't render at all.** A first version
of this skill ran with no errors anywhere, reported "the chart is now
displayed," and produced nothing -- confirmed by checking output size (under
1.1KB; a real rendered chart is 200KB+). `plot_signal_zoom()` now sets
`plotly.io.renderers.default = "colab"` before calling `display()`. If a
chart still doesn't appear, check the output for a printed
`plot_signal_zoom: display(fig) failed: ...` line -- the old silent
`except: pass` that hid this is now a visible print instead.

## Import the helper

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import fetch_signal_for_zoom, plot_signal_zoom_from_npz
```

## Step 1 -- fetch script (run via `fdp run`)

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import fetch_signal_for_zoom

fetch_signal_for_zoom(
    out_path="/content/zoom_data.npz",
    shots=[165920],
    expr=r"\fs04",
    tree="spectroscopy",
)
```
Run with: `fdp run python fetch_script.py`

`fetch_signal_for_zoom(out_path, shots, expr, tree, names=None)`:
- Fetches `expr` from `tree` for each shot (same `MdsSignal` pattern as
  `d3d-shot-fetcher`/`d3d-filterscopes`).
- Silently skips shots that error (matches every other skill's
  `@pipe.where no_errors` convention) -- prints how many of the requested
  shots actually got saved; check that count before assuming success.
- `names`: optional display name per shot (default: the shot number as a
  string). For a multi-shot overlay, pass one name per shot in the same
  order as `shots`.
- Writes ONE `.npz` file holding all series (times/data/name per shot) --
  step 2 reads this file, nothing else needs to be passed between the steps.

## Step 2 -- plot script (run in-kernel, plain `python`)

```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import plot_signal_zoom_from_npz

plot_signal_zoom_from_npz(
    "/content/zoom_data.npz",
    title="Shot 165920 — \\fs04 (D-alpha filterscope)",
    y_label="ph/cm2/sr/s",
)
```
Run with: `python plot_script.py` (NOT `fdp run` -- this step must render
in-kernel for the interactive chart to display).

`plot_signal_zoom_from_npz(npz_path, title="Signal", y_label="", x_label="Time (ms)", height=500, max_points=10000)`:
- Loads the `.npz` written by step 1 and renders it via the same
  min-max-decimated Plotly chart as before -- drag to box-zoom, double-click
  to reset, range-slider to pan. Full-resolution WebGL (Scattergl), so a
  ~400k-sample filterscope trace stays responsive and zooming reveals real
  detail such as individual ELM spikes.
- `max_points`: min-max decimation for display (default 10000 -- preserves
  each bin's min AND max exactly, so spike peaks are never lost to
  decimation, verified). Pass `None` to plot every raw sample (may be laggy
  for a ~400k-point trace).
- Display-only: renders and returns the figure, sets no kernel variable.

## Complete example -- single signal (the canonical ELM-visibility case)

Request: "Show a **zoomable** chart of `\fs04` for shot 165920."

Fetch script (`fdp run python fetch_fs04.py`):
```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import fetch_signal_for_zoom

fetch_signal_for_zoom("/content/fs04_165920.npz", [165920], r"\fs04", "spectroscopy")
```

Plot script (`python plot_fs04.py`):
```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import plot_signal_zoom_from_npz

plot_signal_zoom_from_npz("/content/fs04_165920.npz",
    title="Shot 165920 — \\fs04 (D-alpha filterscope)", y_label="ph/cm2/sr/s")
```

## Complete example -- multi-shot overlay

Request: "**Zoomable** comparison of plasma current for shots 165340 and 188702."

Fetch (`fdp run python fetch_ip.py`):
```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import fetch_signal_for_zoom

fetch_signal_for_zoom("/content/ip_compare.npz", [165340, 188702], r"\ipmhd", "efit01")
```

Plot (`python plot_ip.py`):
```python
import os, sys
sys.path.insert(0, os.path.expanduser("~/.deepagents/agent/skills/signal-zoom"))
from signal_zoom_colab import plot_signal_zoom_from_npz

plot_signal_zoom_from_npz("/content/ip_compare.npz",
    title="Plasma current (zoomable)", y_label="A")
```
Note: `\ipmhd` is in amperes -- `fetch_signal_for_zoom` doesn't unit-convert,
so if MA is wanted, convert before plotting (load the npz manually and divide
by 1e6, or note the unit as A in the title/label as shown here).

## Rules

- Only use when the request has a zoom/interactive trigger term (see routing).
- ALWAYS two scripts: fetch via `fdp run python fetch.py`, then plot via
  plain `python plot.py`. Never combine them into one script -- fetching
  cannot happen in-kernel here (see CRITICAL note above).
- Do NOT build your own Plotly figure -- call `plot_signal_zoom_from_npz`
  (or the lower-level `fetch_signal_for_zoom`/`plot_signal_zoom` if you need
  more control, e.g. unit conversion before plotting).
- Display-only: do NOT read any kernel variable afterward; it sets none.
